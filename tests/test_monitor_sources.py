import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_extracts_rendered_nhc_list_item(self):
        source = {
            "name": "国家卫生健康委规范性文件",
            "url": "https://www.nhc.gov.cn/wjw/gfxwjj/list.shtml",
            "issuer": "国家卫生健康委员会",
            "region": "全国",
            "allowed_hosts": ["nhc.gov.cn", "www.nhc.gov.cn"],
            "keywords": ["人工智能", "医学影像"],
            "exclude_title_terms": ["解读"],
        }
        html = """
        <div class="list">
          <ul>
            <li>
              <a href="/ylyjs/zcwj/202605/abc123.shtml">
                国家卫生健康委办公厅关于印发紧密型县域医共体医学影像中心建设与服务指南（试行）等4项指南的通知
              </a>
              <span>2026-05-27</span>
            </li>
            <li>
              <a href="/fzs/c100048/202605/def456.shtml">关于发布某标准的通告</a>
              <span>2026-05-20</span>
            </li>
          </ul>
        </div>
        """
        result = MONITOR.extract_candidates(html, source)
        self.assertEqual(1, len(result))
        self.assertEqual(
            "国家卫生健康委办公厅关于印发紧密型县域医共体医学影像中心建设与服务指南（试行）等4项指南的通知",
            result[0]["title"],
        )
        self.assertEqual("2026-05-27", result[0]["issue_date"])
        self.assertEqual(
            "https://www.nhc.gov.cn/ylyjs/zcwj/202605/abc123.shtml",
            result[0]["source_url"],
        )

    def test_extracts_ydcmdei_opinion_list_item(self):
        source = {
            "name": "器械长三角分中心指导原则征求意见稿",
            "url": "https://www.ydcmdei.org.cn/article/category/opinions",
            "issuer": "国家药品监督管理局医疗器械技术审评检查长三角分中心",
            "region": "全国",
            "allowed_hosts": ["ydcmdei.org.cn", "www.ydcmdei.org.cn"],
            "keywords": ["人工智能", "辅助诊断", "临床评价", "指导原则"],
            "exclude_title_terms": ["解读", "培训", "招聘"],
        }
        html = """
        <div class="news_list">
          <div class="news_item" title="关于公开征求《人工智能辅助诊断医疗器械临床评价注册审查指导原则（征求意见稿）》等3项指导原则意见的通知">
            <a href="/article/881" class="title">
              关于公开征求《人工智能辅助诊断医疗器械临床评价注册审查指导原则（征求意见稿）》等3项指导原则意见的通知
            </a>
            <span class="date">2026-06-17</span>
          </div>
          <div class="news_item" title="关于举办培训班的通知">
            <a href="/article/960" class="title">关于举办培训班的通知</a>
            <span class="date">2026-08-20</span>
          </div>
        </div>
        """
        result = MONITOR.extract_candidates(html, source)
        self.assertEqual(1, len(result))
        self.assertEqual(
            "关于公开征求《人工智能辅助诊断医疗器械临床评价注册审查指导原则（征求意见稿）》等3项指导原则意见的通知",
            result[0]["title"],
        )
        self.assertEqual("2026-06-17", result[0]["issue_date"])
        self.assertEqual("https://www.ydcmdei.org.cn/article/881", result[0]["source_url"])

    def test_fetch_source_uses_browser_mode_when_configured(self):
        source = dict(self.source, fetch_mode="browser")
        with patch.object(MONITOR, "fetch_source_browser", return_value="<html>ok</html>") as browser_fetch:
            html = MONITOR.fetch_source(source, timeout=12)
        self.assertEqual("<html>ok</html>", html)
        browser_fetch.assert_called_once_with(source, timeout=12)

    def test_normalizes_chinese_date(self):
        self.assertEqual("2026-03-07", MONITOR.normalize_date("2026年3月7日"))

    def test_normalizes_compact_date(self):
        self.assertEqual("2026-08-25", MONITOR.normalize_date("https://example.gov.cn/policy/20260825/item.html"))

    def test_extracts_when_date_only_exists_in_url_and_link_is_http(self):
        source = dict(self.source, url="http://example.gov.cn/policies/list.html")
        html = """
        <ul>
          <li><a href="http://example.gov.cn/policy/20260826/item.html">人工智能辅助诊断医疗器械检查指南</a></li>
        </ul>
        """
        result = MONITOR.extract_candidates(html, source)
        self.assertEqual(1, len(result))
        self.assertEqual("2026-08-26", result[0]["issue_date"])
        self.assertEqual("http://example.gov.cn/policy/20260826/item.html", result[0]["source_url"])


if __name__ == "__main__":
    unittest.main()
