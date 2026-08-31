#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DATE_RE = re.compile(r"(20\d{2})[年./-](\d{1,2})[月./-](\d{1,2})日?")
COMPACT_DATE_RE = re.compile(r"(?<!\d)(20\d{2})(\d{2})(\d{2})(?!\d)")
SPACE_RE = re.compile(r"\s+")
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
)


def clean_text(value, limit=220):
    value = SPACE_RE.sub(" ", value or "").strip()
    return "".join(char for char in value if char >= " " and char != "\x7f")[:limit]


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self.current = None
        self.recent = None

    def _finish_recent(self):
        if self.recent:
            self.links.append(self.recent)
            self.recent = None

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            self._finish_recent()
            href = dict(attrs).get("href", "")
            self.current = {"href": href, "title_parts": [], "context_parts": []}

    def handle_data(self, data):
        if self.current is not None:
            self.current["title_parts"].append(data)
        elif self.recent is not None and sum(map(len, self.recent["context_parts"])) < 240:
            self.recent["context_parts"].append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self.current is not None:
            self.recent = self.current
            self.current = None

    def close(self):
        super().close()
        self._finish_recent()


def normalize_date(value):
    match = DATE_RE.search(value)
    if match:
        year, month, day = map(int, match.groups())
    else:
        compact_match = COMPACT_DATE_RE.search(value)
        if not compact_match:
            return ""
        year, month, day = map(int, compact_match.groups())
    if not 1 <= month <= 12 or not 1 <= day <= 31:
        return ""
    return f"{year:04d}-{month:02d}-{day:02d}"


def host_allowed(url, allowed_hosts):
    host = (urlparse(url).hostname or "").lower()
    return any(host == allowed or host.endswith("." + allowed) for allowed in allowed_hosts)


def extract_candidates(html, source):
    parser = LinkParser()
    parser.feed(html)
    parser.close()
    keywords = source["keywords"]
    excluded = source.get("exclude_title_terms", [])
    candidates = []
    seen = set()
    for link in parser.links:
        title = clean_text("".join(link["title_parts"]))
        if not 8 <= len(title) <= 180:
            continue
        folded = title.casefold()
        if not any(keyword.casefold() in folded for keyword in keywords):
            continue
        if any(term in title for term in excluded):
            continue
        url = urljoin(source["url"], link["href"])
        if urlparse(url).scheme not in {"http", "https"} or not host_allowed(url, source["allowed_hosts"]):
            continue
        issue_date = normalize_date(title + " " + "".join(link["context_parts"]) + " " + url)
        if not issue_date or url in seen:
            continue
        seen.add(url)
        candidates.append({
            "title": title,
            "issuer": source["issuer"],
            "document_no": "",
            "issue_date": issue_date,
            "region": source["region"],
            "source_url": url,
            "source_label": source["name"],
        })
    return candidates


def fetch_source_http(source, timeout=25):
    request = Request(source["url"], headers={
        "User-Agent": "medical-ai-policy-monitor/0.1 (+https://github.com/yishupan/medical-ai-policy-pages-test)",
        "Accept": "text/html,application/xhtml+xml",
    })
    try:
        with urlopen(request, timeout=timeout) as response:
            content_type = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(content_type, errors="replace")
    except Exception as primary_error:
        result = subprocess.run([
            "curl", "--location", "--fail", "--silent", "--show-error",
            "--max-time", str(timeout),
            "--user-agent", "Mozilla/5.0 policy-monitor/0.1",
            source["url"],
        ], capture_output=True, check=False)
        if result.returncode:
            message = result.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"{primary_error}; curl fallback: {message}") from primary_error
        return result.stdout.decode("utf-8", errors="replace")


def wait_for_rendered_links(page, source, timeout_ms):
    minimum_links = int(source.get("browser_min_links", 5))
    allowed_hosts = [host.lower() for host in source["allowed_hosts"]]
    page.wait_for_function(
        """
        ({ allowedHosts, minimumLinks }) => {
          const matchesAllowedHost = (href) => {
            try {
              const host = new URL(href || "", location.href).hostname.toLowerCase();
              return allowedHosts.some((allowed) => host === allowed || host.endsWith("." + allowed));
            } catch (error) {
              return false;
            }
          };
          const linkCount = Array.from(document.querySelectorAll("a")).filter((anchor) => {
            const text = (anchor.textContent || "").replace(/\\s+/g, " ").trim();
            const href = anchor.href || anchor.getAttribute("href") || "";
            return text.length >= 8 && matchesAllowedHost(href);
          }).length;
          return linkCount >= minimumLinks;
        }
        """,
        arg={"allowedHosts": allowed_hosts, "minimumLinks": minimum_links},
        timeout=timeout_ms,
    )


def fetch_source_browser(source, timeout=25):
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise RuntimeError(
            "browser fetch mode requires the Python 'playwright' package and an installed Chromium runtime"
        ) from error

    navigation_timeout_ms = int(source.get("browser_navigation_timeout_ms", timeout * 1000))
    wait_timeout_ms = int(source.get("browser_wait_timeout_ms", max(15000, timeout * 1000)))
    parsed_url = urlparse(source["url"])
    referer = f"{parsed_url.scheme}://{parsed_url.netloc}/"

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            context = browser.new_context(
                user_agent=BROWSER_USER_AGENT,
                locale="zh-CN",
                extra_http_headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                    "Referer": referer,
                },
            )
            page = context.new_page()
            page.goto(source["url"], wait_until="domcontentloaded", timeout=navigation_timeout_ms)
            try:
                page.wait_for_load_state("networkidle", timeout=min(wait_timeout_ms, 15000))
            except PlaywrightTimeoutError:
                pass
            wait_for_rendered_links(page, source, wait_timeout_ms)
            return page.content()
        finally:
            browser.close()


def fetch_source(source, timeout=25):
    mode = source.get("fetch_mode", "http")
    if mode == "browser":
        return fetch_source_browser(source, timeout=timeout)
    if mode == "http":
        return fetch_source_http(source, timeout=timeout)
    raise ValueError(f"unsupported fetch_mode for {source['name']}: {mode}")


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def run(sources_path, output_path):
    sources = [source for source in load_json(sources_path)["sources"] if source.get("enabled", True)]
    all_candidates = []
    failures = []
    successful_sources = 0
    for source in sources:
        try:
            all_candidates.extend(extract_candidates(fetch_source(source), source))
            successful_sources += 1
        except Exception as error:
            failures.append(f"{source['name']}: {error}")
    if not successful_sources:
        raise RuntimeError("all monitoring sources failed:\n" + "\n".join(failures))
    for failure in failures:
        print(f"warning: {failure}", file=sys.stderr)
    unique = {item["source_url"]: item for item in all_candidates}
    payload = {"policies": sorted(unique.values(), key=lambda item: (item["issue_date"], item["title"]), reverse=True)}
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return len(payload["policies"]), successful_sources, len(failures)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sources", type=Path, default=ROOT / "data" / "sources.json")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "candidates.json")
    args = parser.parse_args()
    try:
        count, successes, failures = run(args.sources, args.output)
    except Exception as error:
        print(error, file=sys.stderr)
        return 1
    print(f"wrote {count} candidate policies from {successes} sources to {args.output}; {failures} source failures")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
