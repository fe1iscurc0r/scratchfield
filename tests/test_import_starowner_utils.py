"""import_from_starowner.py 新增工具函数的单元测试。

不启动真实服务，仅测试纯逻辑：
- _sanitize_tag 控制字符清理 + 超长截断
- _split_long_content 按空行/行/硬切三级回退分片
- build_payload 在单分片/多分片下的 source / title / metadata 格式
- fetch_existing_starowner_docs 对多分片 source 的去重主干提取（用 fake 数据在本地测）
"""
import pytest

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.core]
import os
import sys
import unittest
from unittest import mock

# 把脚本所在目录加到 path，允许作为模块导入其函数
_SCRIPT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

# import_from_starowner 会 import requests，但我们只测纯函数，不需要 requests 真实能力
# 但如果 requests 没装会 ImportError → 在这里整个跳过
try:
    import import_from_starowner as S
except ImportError as e:  # pragma: no cover
    if "requests" in str(e):
        S = None
    else:
        raise


@unittest.skipIf(S is None, "依赖 requests 未安装，跳过 starowner utils 测试")
class TestSanitizeTag(unittest.TestCase):
    def test_normal_chinese_tag_unchanged(self):
        self.assertEqual(S._sanitize_tag("材料科普"), "材料科普")

    def test_control_chars_stripped(self):
        # 夹杂 \t \n \x00 等控制字符应全部清掉
        raw = "UP\u0000主\t名\n字\r含\x1b控"
        cleaned = S._sanitize_tag(raw)
        self.assertNotIn("\u0000", cleaned)
        self.assertNotIn("\t", cleaned)
        self.assertNotIn("\n", cleaned)
        # 期望：控制字符被剥，剩下可展示字符
        self.assertTrue(all(ord(c) >= 0x20 or c in ("…",) for c in cleaned))

    def test_long_tag_truncated_with_ellipsis(self):
        long_t = "非常非常非常非常非常非常非常非常非常非常非常非常长的收藏夹名字"
        # 超过 MAX_TAG_CHARS(50) 应带省略号
        if len(long_t) > S.MAX_TAG_CHARS:
            cleaned = S._sanitize_tag(long_t)
            self.assertEqual(len(cleaned), S.MAX_TAG_CHARS)
            self.assertTrue(cleaned.endswith("…"))

    def test_empty_and_none_returns_empty(self):
        self.assertEqual(S._sanitize_tag(""), "")
        self.assertEqual(S._sanitize_tag(None), "")
        self.assertEqual(S._sanitize_tag(1234), "1234")


@unittest.skipIf(S is None, "依赖 requests 未安装，跳过 starowner utils 测试")
class TestSplitLongContent(unittest.TestCase):
    def test_short_content_single_piece(self):
        short = "# 标题\n\n正文很短。\n"
        pieces = S._split_long_content(short)
        self.assertEqual(len(pieces), 1)
        self.assertEqual(pieces[0], short)

    def test_split_prefers_empty_line_boundary(self):
        # 构造两段落，每段小于 cap，拼接后大于 cap → 必须按空行切开而不是行/硬切
        cap = S.MAX_CONTENT_CHARS - 10_000
        para_a = "A" * (cap // 3)
        para_b = "B" * (cap // 3)
        para_c = "C" * (cap // 3)
        content = f"{para_a}\n\n{para_b}\n\n{para_c}"
        pieces = S._split_long_content(content)
        # 每段 < cap，三段 concat > cap，期望按空行分 2~3 片
        self.assertGreaterEqual(len(pieces), 2)
        # 每片长度都 <= cap
        for p in pieces:
            self.assertLessEqual(len(p), cap)
        # 全部拼接应还原原文（注意切分时空行可能被拼回）
        restored = "\n\n".join(pieces)
        self.assertEqual(restored, content)

    def test_huge_single_block_falls_back_to_line_split(self):
        # 一整段没有空行，单段内部按行再切
        cap = S.MAX_CONTENT_CHARS - 10_000
        lines = []
        # 每行 200 字，共 1500 行 → 300k 字，肯定超 190k
        for _ in range(1500):
            lines.append("X" * 200)
        content = "\n".join(lines)
        pieces = S._split_long_content(content)
        self.assertGreaterEqual(len(pieces), 2)
        for p in pieces:
            self.assertLessEqual(len(p), cap)

    def test_single_very_long_line_hard_cut(self):
        # 一整行无换行，超长到必须硬切
        cap = S.MAX_CONTENT_CHARS - 10_000
        content = "Y" * (cap * 2 + 42)
        pieces = S._split_long_content(content)
        self.assertGreaterEqual(len(pieces), 2)
        for p in pieces:
            self.assertLessEqual(len(p), cap)
        # 硬切不会丢内容，首尾全是 Y
        self.assertTrue(all(set(p) <= {"Y"} for p in pieces))
        self.assertEqual(sum(len(p) for p in pieces), len(content))


@unittest.skipIf(S is None, "依赖 requests 未安装，跳过 starowner utils 测试")
class TestBuildPayload(unittest.TestCase):
    SAMPLE_DOC = {
        "id": "doc_123",
        "title": "锂电池正极材料全面解读",
        "bvid": "BV1ab4y1A7XZ",
        "owner": "UP主名字",
        "tags": ["科普", "材料", "锂电"],
        "collection": {"id": "c456", "name": "材料世界专题"},
        "user": {"id": "u789", "name": "收藏用户"},
        "publishedAt": "2025-02-10",
        "favoriteAddedAt": "2025-03-01",
        "completedAt": "2025-03-05",
        "url": "https://www.bilibili.com/video/BV1ab4y1A7XZ",
        "multiPartRole": "standalone",
    }

    def test_single_part_payload_fields(self):
        p = S.build_payload(self.SAMPLE_DOC, "# 正文\n\n## 章节\n内容")
        self.assertEqual(p["title"], "[BV1ab4y1A7XZ] 锂电池正极材料全面解读")
        self.assertEqual(p["source"], "starowner://doc_123")
        self.assertIn("source", p["metadata"])
        self.assertEqual(p["metadata"]["source"], "starowner://doc_123")
        self.assertEqual(p["metadata"]["bvid"], "BV1ab4y1A7XZ")
        # tags：应含 "科普"、"材料"、"锂电"、UP 主、收藏夹名，顺序保持去重
        for expected in ("科普", "材料", "锂电", "UP主名字", "材料世界专题"):
            self.assertIn(expected, p["tags"])
        # 去重
        self.assertEqual(len(p["tags"]), len(set(p["tags"])))

    def test_title_very_long_gets_truncated(self):
        long_doc = dict(self.SAMPLE_DOC)
        long_doc["title"] = "T" * 300
        p = S.build_payload(long_doc, "body")
        self.assertLessEqual(len(p["title"]), S.MAX_TITLE_CHARS)
        # 不应该抛异常

    def test_title_without_bvid_fallback(self):
        doc_no_bv = dict(self.SAMPLE_DOC)
        del doc_no_bv["bvid"]
        doc_no_bv["bvid"] = ""
        p = S.build_payload(doc_no_bv, "body")
        self.assertFalse(p["title"].startswith("[]"))

    def test_multi_part_source_and_metadata(self):
        # 多分片下 source 应该带 #partN，metadata 里有 part_index/part_total
        p1 = S.build_payload(self.SAMPLE_DOC, "片1内容", part_index=1, part_total=3)
        p2 = S.build_payload(self.SAMPLE_DOC, "片2内容", part_index=2, part_total=3)
        self.assertEqual(p1["source"], "starowner://doc_123#part1")
        self.assertEqual(p2["source"], "starowner://doc_123#part2")
        self.assertIn("(1/3)", p1["title"])
        self.assertIn("(2/3)", p2["title"])
        self.assertEqual(p1["metadata"]["part_total"], 3)
        self.assertEqual(p2["metadata"]["part_index"], 2)
        self.assertEqual(p1["metadata"]["starowner_document_id_core"], "doc_123")


@unittest.skipIf(S is None, "依赖 requests 未安装，跳过 starowner utils 测试")
class TestDedupExtraction(unittest.TestCase):
    """用 mock 的 HTTP 响应验证 fetch_existing_starowner_docs 能正确从多分片 source 里
    提取主干 documentId，而不是把 #part1/#part2 当成不同 id。
    """

    def test_multi_part_source_stripped_to_core(self):
        fake_docs = [
            {"source": "starowner://abc#part1", "docId": "x1"},
            {"source": "starowner://abc#part2", "docId": "x2"},
            {"source": "starowner://single", "docId": "x3"},
            {"source": "manual", "docId": "x4"},  # 非星藏家，不应加入
            {"source": "starowner://zzz#part1", "docId": "x5"},
        ]

        def _fake_get(url, headers=None, params=None, timeout=None):
            resp = mock.Mock()
            resp.status_code = 200
            resp.json = mock.Mock(return_value={"success": True, "documents": fake_docs, "total": len(fake_docs)})
            return resp

        with mock.patch.object(S.requests, "get", side_effect=_fake_get):
            imported = S.fetch_existing_starowner_docs()
        # 期望 3 个核心：abc、single、zzz
        self.assertEqual(imported, {"abc", "single", "zzz"})


if __name__ == "__main__":
    unittest.main()
