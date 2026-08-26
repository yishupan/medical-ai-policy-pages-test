import importlib.util
import unittest
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "monitor_sources.py"
SPEC = importlib.util.spec_from_file_location("monitor_sources", MODULE_PATH)
MONITOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MONITOR)


class MonitorSourcesTest(unittest.TestCase):
    def setUp(self):
        self.source = {
            "name": "测试官方源",
            "url": "https://example.gov.cn/policies/list.html",
            "issuer": "测试机关",
            "region": "全国",
            "allowed_hosts": ["example.gov.cn"],
            "keywords": ["人工智能", "医学影像"],
            "exclude_title_terms": ["解读"],
        }

    def test_extracts_only_dated_matching_official_links(self):
        html = """
        <ul>
          <li><a href="/policy/1.html">关于人工智能医疗应用的通知</a><span>2026-08-26</span></li>
          <li><a href="https://outside.example/policy/2">医学影像政策</a><span>2026-08-25</span></li>
          <li><a href="/policy/3.html">人工智能政策解读</a><span>2026-08-24</span></li>
          <li><a href="/policy/4.html">普通医疗通知</a><span>2026-08-23</span></li>
        </ul>
        """
        result = MONITOR.extract_candidates(html, self.source)
        self.assertEqual(1, len(result))
        self.assertEqual("关于人工智能医疗应用的通知", result[0]["title"])
        self.assertEqual("2026-08-26", result[0]["issue_date"])
        self.assertEqual("https://example.gov.cn/policy/1.html", result[0]["source_url"])

    def test_normalizes_chinese_date(self):
        self.assertEqual("2026-03-07", MONITOR.normalize_date("2026年3月7日"))


if __name__ == "__main__":
    unittest.main()
