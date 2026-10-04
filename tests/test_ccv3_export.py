"""授粉-A1 验收：陆墨人格 CCv3 导出。

镜像 airi packages/ccc/src/codec/characterCardV3.ts 的 valibot schema
必需字段检查（MIT），确保卡片可被 airi codec 反序列化、字段不缺失。
"""

from __future__ import annotations

import pytest

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.core]

import json
import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, REPO_ROOT)

CARD_PATH = os.path.join(REPO_ROOT, "characters", "陆墨", "陆墨.chara_card_v3.json")

# ── 与 characterCardV3.ts schema 对齐的必需字段清单 ──────────────────────
_TOP_REQUIRED = {"spec": "chara_card_v3", "spec_version": r"^\d+(?:\.\d+)*$"}

_DATA_REQUIRED_STR = (
    "name", "description", "personality", "scenario",
    "first_mes", "mes_example", "character_version",
    "creator", "creator_notes", "post_history_instructions", "system_prompt",
)
_DATA_REQUIRED_ARR = ("alternate_greetings", "tags", "group_only_greetings")


class TestA1CharacterCardV3(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(CARD_PATH, encoding="utf-8") as f:
            cls.card = json.load(f)

    def test_envelope(self):
        """spec/spec_version 与 airi literal+regex 校验一致。"""
        self.assertEqual(self.card["spec"], _TOP_REQUIRED["spec"])
        self.assertRegex(self.card["spec_version"], _TOP_REQUIRED["spec_version"])
        self.assertIsInstance(self.card.get("data"), dict)

    def test_data_required_fields(self):
        """characterCardDataSchema 的全部必需字段齐全且非空。"""
        data = self.card["data"]
        for field in _DATA_REQUIRED_STR:
            self.assertIn(field, data, f"缺失字段: {field}")
            self.assertIsInstance(data[field], str, f"{field} 必须是 string")
            self.assertTrue(data[field].strip(), f"{field} 不能为空")
        for field in _DATA_REQUIRED_ARR:
            self.assertIn(field, data, f"缺失字段: {field}")
            self.assertIsInstance(data[field], list, f"{field} 必须是 array")

    def test_extensions_shape(self):
        """extensions 的 depth_prompt/talkativeness/world 结构。"""
        ext = self.card["data"]["extensions"]
        self.assertIsInstance(ext, dict)
        dp = ext["depth_prompt"]
        self.assertIsInstance(dp["depth"], int)
        self.assertIsInstance(dp["prompt"], str)
        self.assertIsInstance(dp["role"], str)
        self.assertIsInstance(ext["talkativeness"], (int, float))
        self.assertIsInstance(ext["world"], str)

    def test_character_book_structure(self):
        """character_book 空结构也须满足 entries 为 array。"""
        book = self.card["data"].get("character_book")
        self.assertIsNotNone(book, "A1 要求 character_book 先落空结构")
        self.assertIsInstance(book["entries"], list)
        self.assertIsInstance(book["extensions"], dict)

    def test_persona_fidelity(self):
        """人格内容忠实于源 prompt.txt（关键锚点抽查）。"""
        data = self.card["data"]
        with open(
            os.path.join(REPO_ROOT, "characters", "陆墨", "prompt.txt"),
            encoding="utf-8",
        ) as f:
            source = f.read()
        for anchor in ("陆墨", "木质素", "遥", "严谨"):
            self.assertIn(anchor, data["personality"] + data["description"])
        # system_prompt 应完整包含源提示词的身份锁定段落
        self.assertIn("绝对身份锁定", data["system_prompt"])
        self.assertIn("你不是任何其他角色", source)
        self.assertIn("你不是任何其他角色", data["system_prompt"])

    def test_spec_version_compatibility(self):
        """spec_version 解析为 current（=3），与 airi resolveCompatibility 一致。"""
        self.assertEqual(float(self.card["spec_version"]), 3.0)


if __name__ == "__main__":
    unittest.main()
