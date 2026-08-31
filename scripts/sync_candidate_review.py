#!/usr/bin/env python3
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
PENDING_DIR = ROOT / "pending_markdown"
CANDIDATES_PATH = DATA_DIR / "candidates.json"
POLICIES_PATH = DATA_DIR / "policies.json"
STATUS_PATH = DATA_DIR / "candidate_status.json"
REVIEW_PATH = DATA_DIR / "candidate_review.json"
STATUS_OPTIONS = {"pending", "confirmed", "rejected"}
STATUS_LABELS = {
    "pending": "待确认",
    "confirmed": "已确认待入库",
    "rejected": "不入库",
}
CATEGORY_LABELS = {
    "A_十五五与产业支持": "十五五与产业支持",
    "B_医疗AI应用与卫健治理": "医疗AI应用与卫健治理",
    "C_医疗器械注册监管": "医疗器械注册监管",
    "D_医保支付与服务价格": "医保支付与服务价格",
    "E_医疗数据利用与流通": "医疗数据利用与流通",
    "F_数据安全与跨境": "数据安全与跨境",
    "G_地方试点": "地方政策",
}


def load_json(path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, payload):
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_repo_url(raw_url):
    if not raw_url:
        return ""
    raw_url = raw_url.strip()
    if raw_url.startswith("git@github.com:"):
        raw_url = "https://github.com/" + raw_url[len("git@github.com:") :]
    elif raw_url.startswith("https://github.com/"):
        pass
    else:
        return ""
    if raw_url.endswith(".git"):
        raw_url = raw_url[:-4]
    return raw_url.rstrip("/")


def detect_repo_url(root):
    github_repository = os.environ.get("GITHUB_REPOSITORY", "")
    github_server = os.environ.get("GITHUB_SERVER_URL", "")
    if github_repository and github_server:
        return f"{github_server.rstrip('/')}/{github_repository}"
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "remote", "get-url", "origin"],
            capture_output=True,
            check=True,
            encoding="utf-8",
        )
        return normalize_repo_url(result.stdout)
    except Exception:
        return ""


def collapse_spaces(value):
    return re.sub(r"\s+", " ", (value or "")).strip()


def clean_filename_piece(value, limit):
    value = collapse_spaces(value)
    value = re.sub(r'[\\/:*?"<>|]+', " ", value)
    value = re.sub(r"[^\w\u4e00-\u9fff（）()《》、·—\- ]+", "", value, flags=re.UNICODE)
    value = collapse_spaces(value).replace(" ", "")
    return value[:limit] or "候选政策"


def draft_path_for(candidate, existing_path=""):
    if existing_path:
        return existing_path
    issue_date = candidate.get("issue_date") or "0000-00-00"
    issuer = clean_filename_piece(candidate.get("issuer"), 18)
    title = clean_filename_piece(candidate.get("title"), 42)
    suffix = hashlib.sha1(candidate["source_url"].encode("utf-8")).hexdigest()[:8]
    filename = f"{issue_date}_{issuer}_{title}_{suffix}.md"
    return f"pending_markdown/{filename}"


def candidate_key_for(source_url):
    return f"CAND-{hashlib.sha1(source_url.encode('utf-8')).hexdigest()[:8].upper()}"


def suggest_category(candidate):
    title = candidate.get("title", "")
    issuer = candidate.get("issuer", "")
    source_label = candidate.get("source_label", "")
    region = candidate.get("region", "")
    text = " ".join([title, issuer, source_label])
    if region not in {"全国", "国际", ""}:
        return "G_地方试点"
    if any(token in text for token in ("药监", "器审", "医疗器械", "指导原则", "注册", "审评", "审查")):
        return "C_医疗器械注册监管"
    if any(token in text for token in ("医保", "医疗服务价格", "支付", "价格项目")):
        return "D_医保支付与服务价格"
    if any(token in text for token in ("网信", "网络安全", "个人信息", "跨境", "安全事件")):
        return "F_数据安全与跨境"
    if any(token in text for token in ("数据", "数据集", "数据局", "数据资源", "可信数据空间")):
        return "E_医疗数据利用与流通"
    if any(token in text for token in ("卫健", "卫生健康", "医院", "医学影像", "诊疗", "中医药", "临床")):
        return "B_医疗AI应用与卫健治理"
    return "A_十五五与产业支持"


def build_candidate_status(active_candidates, existing_payload):
    existing_entries = {
        item["source_url"]: item for item in existing_payload.get("candidates", []) if item.get("source_url")
    }
    entries = []
    for candidate in active_candidates:
        previous = existing_entries.get(candidate["source_url"], {})
        status = previous.get("status", "pending")
        if status not in STATUS_OPTIONS:
            status = "pending"
        suggested_category = previous.get("suggested_category") or suggest_category(candidate)
        if suggested_category not in CATEGORY_LABELS:
            suggested_category = suggest_category(candidate)
        draft_path = draft_path_for(candidate, previous.get("draft_path", ""))
        candidate_key = previous.get("candidate_key") or candidate_key_for(candidate["source_url"])
        entries.append(
            {
                "candidate_key": candidate_key,
                "source_url": candidate["source_url"],
                "title": candidate.get("title", ""),
                "issuer": candidate.get("issuer", ""),
                "issue_date": candidate.get("issue_date", ""),
                "region": candidate.get("region", ""),
                "source_label": candidate.get("source_label", ""),
                "status": status,
                "review_note": previous.get("review_note", ""),
                "suggested_category": suggested_category,
                "suggested_policy_id": previous.get("suggested_policy_id", ""),
                "draft_path": draft_path,
            }
        )
    entries.sort(
        key=lambda item: (
            {"pending": 0, "confirmed": 1, "rejected": 2}[item["status"]],
            -(int(item.get("issue_date", "0000-00-00").replace("-", "")) if item.get("issue_date") else 0),
            item.get("title", ""),
        )
    )
    return {
        "schema_version": 1,
        "status_file_path": "data/candidate_status.json",
        "draft_root": "pending_markdown",
        "status_guide": {
            "pending": "已发现，待人工判断是否进入专题库。",
            "confirmed": "确认纳入专题库，待补齐重要原文、官方解读和正式编号。",
            "rejected": "确认不纳入专题库，保留记录供后续复核。",
        },
        "candidates": entries,
    }


def build_review_payload(status_payload, repo_url):
    counts = {key: 0 for key in STATUS_OPTIONS}
    candidates = []
    for item in status_payload["candidates"]:
        counts[item["status"]] += 1
        draft_path = item["draft_path"]
        draft_url = f"{repo_url}/blob/main/{quote(draft_path)}" if repo_url else ""
        draft_edit_url = f"{repo_url}/edit/main/{quote(draft_path)}" if repo_url else ""
        candidates.append(
            {
                **item,
                "status_label": STATUS_LABELS[item["status"]],
                "suggested_category_label": CATEGORY_LABELS[item["suggested_category"]],
                "draft_url": draft_url,
                "draft_edit_url": draft_edit_url,
            }
        )
    return {
        "schema_version": 1,
        "candidate_count": len(candidates),
        "status_counts": {
            "pending": counts["pending"],
            "confirmed": counts["confirmed"],
            "rejected": counts["rejected"],
        },
        "repo_url": repo_url,
        "status_edit_url": f"{repo_url}/edit/main/data/candidate_status.json" if repo_url else "",
        "draft_tree_url": f"{repo_url}/tree/main/pending_markdown" if repo_url else "",
        "candidates": candidates,
    }


def build_draft_text(candidate_entry):
    source_url = candidate_entry["source_url"]
    candidate_key = candidate_entry["candidate_key"]
    title = candidate_entry["title"]
    issuer = candidate_entry["issuer"]
    issue_date = candidate_entry["issue_date"]
    region = candidate_entry["region"]
    source_label = candidate_entry["source_label"]
    suggested_category = candidate_entry["suggested_category"]
    suggested_policy_id = candidate_entry["suggested_policy_id"]
    status = candidate_entry["status"]
    review_note = candidate_entry["review_note"]
    draft_path = candidate_entry["draft_path"]
    lines = [
        "---",
        'policy_id: ""',
        f'title: "{title}"',
        'document_type: "政策观察项"',
        f'issuer: "{issuer}"',
        'document_no: ""',
        f'policy_category: "{suggested_category}"',
        f'published_date: "{issue_date}"',
        'effective_date: ""',
        'effective_date_note: ""',
        'status: "待确认"',
        f'region: "{region}"',
        'citation_priority: "候选政策草稿"',
        f'source_url: "{source_url}"',
        'local_source: ""',
        f'local_markdown: "{draft_path}"',
        'parse_method: "自动巡检候选草稿"',
        'full_text_status: "待提取原文"',
        'full_text_note: "请补录官方原文或附件，再决定是否正式入库。"',
        "---",
        "",
        f"# {title}",
        "",
        "## 候选信息",
        "",
        f"- 候选键：{candidate_key}",
        f"- 当前状态：{STATUS_LABELS[status]}",
        f"- 建议分区：{CATEGORY_LABELS[suggested_category]}",
        f"- 建议编号：{suggested_policy_id or '待确认'}",
        f"- 来源栏目：{source_label}",
        f"- 原文链接：{source_url}",
    ]
    if review_note:
        lines.append(f"- 备注：{review_note}")
    else:
        lines.append("- 备注：")
    lines.extend(
        [
            "",
            "## 待补字段",
            "",
            "- 内部编号：",
            "- 文号：",
            "- 生效时间：",
            "- 文件状态：",
            "",
            "## 正文",
            "",
            "- 待从官方网页、附件或 Markdown 原文补录。",
            "",
            "## 重要原文",
            "",
            "- 待补录",
            "",
            "## 官方解读（若有）",
            "",
            "- 待补录",
            "",
            "## 处理记录",
            "",
            "- 本文件由巡检脚本自动创建；后续可直接在 GitHub 网页或本地仓库继续编辑。",
        ]
    )
    return "\n".join(lines) + "\n"


def ensure_draft_files(status_payload):
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    created = 0
    for item in status_payload["candidates"]:
        path = ROOT / item["draft_path"]
        if path.exists():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(build_draft_text(item), encoding="utf-8")
        created += 1
    return created


def sync_candidate_review(root=ROOT):
    candidates_payload = load_json(CANDIDATES_PATH, {"policies": []})
    policies_payload = load_json(POLICIES_PATH, {"policies": []})
    existing_status = load_json(STATUS_PATH, {"candidates": []})
    formal_urls = {item.get("source_url") for item in policies_payload.get("policies", []) if item.get("source_url")}
    active_candidates = [
        item
        for item in candidates_payload.get("policies", [])
        if item.get("source_url") and item.get("source_url") not in formal_urls
    ]
    repo_url = detect_repo_url(root)
    status_payload = build_candidate_status(active_candidates, existing_status)
    review_payload = build_review_payload(status_payload, repo_url)
    created = ensure_draft_files(status_payload)
    write_json(STATUS_PATH, status_payload)
    write_json(REVIEW_PATH, review_payload)
    return review_payload["candidate_count"], created


def main():
    try:
        candidate_count, created = sync_candidate_review()
    except Exception as error:
        print(error, file=sys.stderr)
        return 1
    print(f"synced {candidate_count} active candidates; created {created} new draft files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
