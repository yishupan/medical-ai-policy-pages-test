import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "sync_candidate_review.py"
SPEC = importlib.util.spec_from_file_location("sync_candidate_review", MODULE_PATH)
SYNC = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SYNC)


class SyncCandidateReviewTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.data_dir = self.root / "data"
        self.pending_dir = self.root / "pending_markdown"
        self.data_dir.mkdir(parents=True)
        self.originals = {
            "ROOT": SYNC.ROOT,
            "DATA_DIR": SYNC.DATA_DIR,
            "PENDING_DIR": SYNC.PENDING_DIR,
            "CANDIDATES_PATH": SYNC.CANDIDATES_PATH,
            "POLICIES_PATH": SYNC.POLICIES_PATH,
            "STATUS_PATH": SYNC.STATUS_PATH,
            "REVIEW_PATH": SYNC.REVIEW_PATH,
        }
        SYNC.ROOT = self.root
        SYNC.DATA_DIR = self.data_dir
        SYNC.PENDING_DIR = self.pending_dir
        SYNC.CANDIDATES_PATH = self.data_dir / "candidates.json"
        SYNC.POLICIES_PATH = self.data_dir / "policies.json"
        SYNC.STATUS_PATH = self.data_dir / "candidate_status.json"
        SYNC.REVIEW_PATH = self.data_dir / "candidate_review.json"

    def tearDown(self):
        for key, value in self.originals.items():
            setattr(SYNC, key, value)
        self.tempdir.cleanup()

    def write_json(self, path, payload):
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def test_sync_generates_review_status_and_draft(self):
        source_url = "https://example.gov.cn/policy/a"
        self.write_json(
            SYNC.CANDIDATES_PATH,
            {
                "policies": [
                    {
                        "title": "关于人工智能医学影像应用的通知",
                        "issuer": "国家卫生健康委员会",
                        "document_no": "",
                        "issue_date": "2026-08-30",
                        "region": "全国",
                        "source_url": source_url,
                        "source_label": "国家卫生健康委规范性文件",
                    }
                ]
            },
        )
        self.write_json(SYNC.POLICIES_PATH, {"policies": []})
        self.write_json(SYNC.STATUS_PATH, {"candidates": []})

        with patch.dict(
            "os.environ",
            {"GITHUB_REPOSITORY": "yishupan/medical-ai-policy-pages-test", "GITHUB_SERVER_URL": "https://github.com"},
            clear=False,
        ):
            candidate_count, created = SYNC.sync_candidate_review(root=self.root)

        self.assertEqual(1, candidate_count)
        self.assertEqual(1, created)

        status_payload = json.loads(SYNC.STATUS_PATH.read_text(encoding="utf-8"))
        self.assertEqual(1, len(status_payload["candidates"]))
        candidate = status_payload["candidates"][0]
        self.assertEqual("pending", candidate["status"])
        self.assertEqual("B_医疗AI应用与卫健治理", candidate["suggested_category"])
        self.assertRegex(candidate["candidate_key"], r"^CAND-[0-9A-F]{8}$")

        review_payload = json.loads(SYNC.REVIEW_PATH.read_text(encoding="utf-8"))
        self.assertEqual(1, review_payload["candidate_count"])
        self.assertEqual(
            "https://github.com/yishupan/medical-ai-policy-pages-test/edit/main/data/candidate_status.json",
            review_payload["status_edit_url"],
        )
        review_candidate = review_payload["candidates"][0]
        self.assertTrue(review_candidate["draft_url"].endswith(".md"))
        self.assertIn("/edit/main/pending_markdown/", review_candidate["draft_edit_url"])

        draft_path = self.root / candidate["draft_path"]
        self.assertTrue(draft_path.exists())
        draft_text = draft_path.read_text(encoding="utf-8")
        self.assertIn("候选键：", draft_text)
        self.assertIn("关于人工智能医学影像应用的通知", draft_text)

    def test_sync_preserves_manual_review_fields(self):
        source_url = "https://example.gov.cn/policy/b"
        self.write_json(
            SYNC.CANDIDATES_PATH,
            {
                "policies": [
                    {
                        "title": "人工智能辅助诊断医疗器械指导原则",
                        "issuer": "国家药品监督管理局",
                        "document_no": "",
                        "issue_date": "2026-08-20",
                        "region": "全国",
                        "source_url": source_url,
                        "source_label": "医疗器械审评检查",
                    }
                ]
            },
        )
        self.write_json(SYNC.POLICIES_PATH, {"policies": []})
        self.write_json(
            SYNC.STATUS_PATH,
            {
                "candidates": [
                    {
                        "candidate_key": "CAND-KEEP123",
                        "source_url": source_url,
                        "title": "人工智能辅助诊断医疗器械指导原则",
                        "issuer": "国家药品监督管理局",
                        "issue_date": "2026-08-20",
                        "region": "全国",
                        "source_label": "医疗器械审评检查",
                        "status": "confirmed",
                        "review_note": "优先入库",
                        "suggested_category": "C_医疗器械注册监管",
                        "suggested_policy_id": "C-016",
                        "draft_path": "pending_markdown/custom.md",
                    }
                ]
            },
        )

        candidate_count, created = SYNC.sync_candidate_review(root=self.root)
        self.assertEqual(1, candidate_count)
        self.assertEqual(1, created)

        status_payload = json.loads(SYNC.STATUS_PATH.read_text(encoding="utf-8"))
        candidate = status_payload["candidates"][0]
        self.assertEqual("confirmed", candidate["status"])
        self.assertEqual("优先入库", candidate["review_note"])
        self.assertEqual("C-016", candidate["suggested_policy_id"])
        self.assertEqual("pending_markdown/custom.md", candidate["draft_path"])
        self.assertEqual("CAND-KEEP123", candidate["candidate_key"])


if __name__ == "__main__":
    unittest.main()
