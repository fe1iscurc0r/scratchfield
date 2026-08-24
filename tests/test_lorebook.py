"""授粉-A2 验收：Lorebook 知识注入管线。

- keys 触发路径可 grep 验证（lorebook.json 内木质素/水凝胶触发词齐全）
- mock 对话断言两态：命中注入 / 闲聊零注入
"""

from __future__ import annotations

import json
import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, REPO_ROOT)

from research.lorebook import Lorebook, LorebookEntry, lorebook_section_for

LOREBOOK_JSON = os.path.join(REPO_ROOT, "characters", "陆墨", "lorebook.json")


class TestA2LorebookKeysPath(unittest.TestCase):
    """验收：grep 可验证 keys 触发路径。"""

    @classmethod
    def setUpClass(cls):
        with open(LOREBOOK_JSON, encoding="utf-8") as f:
            cls.book = Lorebook.from_any(json.load(f))

    def test_lignin_keys_present(self):
        entry = next(e for e in self.book.entries if e.name == "木质素")
        for key in ("木质素", "木素", "lignin"):
            self.assertIn(key, entry.keys)

    def test_hydrogel_keys_present(self):
        entry = next(e for e in self.book.entries if e.name == "导电水凝胶")
        for key in ("水凝胶", "导电水凝胶", "hydrogel"):
            self.assertIn(key, entry.keys)

    def test_content_from_vault(self):
        """content 必须来自 vault 知识条目，非空且带关键参数。"""
        for e in self.book.entries:
            self.assertTrue(e.content.strip(), f"{e.name} content 为空")
        lignin = next(e for e in self.book.entries if e.name == "木质素")
        self.assertIn("碳化", lignin.content)


class TestA2LorebookInjectionStates(unittest.TestCase):
    """验收：mock 对话断言注入与零注入两态。"""

    def test_hit_dialogue_injects(self):
        """科研对话命中「木质素」→ 注入段非空且含知识。"""
        section = lorebook_section_for("木质素 800 度碳化的产率大概多少？")
        self.assertTrue(section)
        self.assertIn("Lorebook", section)
        self.assertIn("木质素", section)
        self.assertIn("碳化", section)

    def test_hit_english_alias_case_insensitive(self):
        """英文别名大小写不敏感命中。"""
        self.assertTrue(lorebook_section_for("What's the carbon yield of LIGNIN?"))

    def test_hit_hydrogel(self):
        section = lorebook_section_for("导电水凝胶的应变传感系数一般多少？")
        self.assertTrue(section)
        self.assertIn("水凝胶", section)

    def test_chitchat_zero_injection(self):
        """闲聊零负载：未命中任何 keys 时返回空串。"""
        for msg in ("今天天气不错呀", "陆墨你困不困？", "早上好，喝奶茶吗", "hello there"):
            self.assertEqual(lorebook_section_for(msg), "", f"闲聊误注入: {msg}")

    def test_missing_file_zero_injection(self):
        """lorebook 文件缺失时零注入（不抛错）。"""
        self.assertEqual(lorebook_section_for("木质素", path="/nonexistent/lb.json"), "")


class TestA2LorebookSemantics(unittest.TestCase):
    """airi character_book 语义：selective / regex / constant / priority。"""

    def _book(self, *entries) -> Lorebook:
        return Lorebook(entries=list(entries))

    def test_selective_requires_both_key_groups(self):
        entry = LorebookEntry(
            keys=["碳化"], secondary_keys=["木质素"], selective=True, content="C"
        )
        self.assertTrue(entry.matches("木质素的碳化温度"))
        self.assertFalse(entry.matches("碳化硅怎么制备"))  # 只命中 keys

    def test_regex_entry(self):
        entry = LorebookEntry(keys=[r"\bXRD\b"], use_regex=True, content="X")
        self.assertTrue(entry.matches("做了个 XRD 表征"))
        self.assertFalse(entry.matches("XRD123 不算词边界"))

    def test_constant_entry_always_hits(self):
        entry = LorebookEntry(keys=[], constant=True, content="常驻")
        self.assertTrue(entry.matches("随便什么闲聊"))

    def test_disabled_entry_never_hits(self):
        entry = LorebookEntry(keys=["木质素"], enabled=False, content="C")
        self.assertFalse(entry.matches("木质素"))

    def test_priority_ordering(self):
        low = LorebookEntry(keys=["碳"], priority=1, content="低", name="低")
        high = LorebookEntry(keys=["碳"], priority=9, content="高", name="高")
        hits = self._book(low, high).scan("生物质碳")
        self.assertEqual([h.name for h in hits], ["高", "低"])


if __name__ == "__main__":
    unittest.main()
