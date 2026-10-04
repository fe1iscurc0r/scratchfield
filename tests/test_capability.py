"""授粉-A3 验收：CharacterCapability 工作端/宠物端解耦。

- 两端 profile 可分别指定不同后端（work: DeepSeek V4 Pro + Edge TTS；pet: 轻量模型）
- 切换不互相污染（每次解析返回独立实例，改动不回写、不串端）
- provider overlay：LUMO_CAP_<PROFILE>_<TYPE>_* 环境变量覆写（同 lumo_proxy LUMO_VISION_* 模式）
- 铁律7：json 只存环境变量名，不落真实密钥
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

from system.capability import (
    CapabilityBinding,
    load_capabilities,
    resolve_capability,
)

CHARACTER_ID = "陆墨"
CAPS_JSON = os.path.join(REPO_ROOT, "characters", CHARACTER_ID, "capabilities.json")


class TestA3DualProfileBindings(unittest.TestCase):
    """验收：两端 profile 可分别指定不同后端。"""

    @classmethod
    def setUpClass(cls):
        cls.caps = load_capabilities(CHARACTER_ID)

    def test_both_profiles_exist(self):
        self.assertEqual(set(self.caps.profiles), {"work", "pet"})
        self.assertEqual(self.caps.default_profile, "work")

    def test_work_binds_deepseek_pro_and_edge_tts(self):
        work = self.caps.profiles["work"]
        self.assertEqual(work.llm.provider, "deepseek")
        self.assertEqual(work.llm.model, "deepseek-v4-pro")
        self.assertTrue(work.llm.base_url)
        self.assertEqual(work.tts.provider, "edge-tts")
        self.assertTrue(work.tts.voice_id)

    def test_pet_binds_lightweight_backend(self):
        pet = self.caps.profiles["pet"]
        work = self.caps.profiles["work"]
        self.assertTrue(pet.llm.provider)
        self.assertNotEqual(pet.llm.model, work.llm.model, "宠物端必须与工作端不同模型")
        self.assertNotEqual(pet.tts.voice_id, work.tts.voice_id)

    def test_no_secret_on_disk(self):
        """铁律7：json 只存 api_key_env（环境变量名），绝不落真实密钥。"""
        with open(CAPS_JSON, encoding="utf-8") as f:
            raw = f.read()
        payload = json.loads(raw)
        self.assertNotIn("api_key\"", raw.replace("api_key_env", ""))
        for profile in payload["profiles"].values():
            for binding in profile.values():
                if isinstance(binding, dict):
                    key_env = binding.get("api_key_env", "")
                    if key_env:
                        self.assertTrue(
                            key_env.endswith("_API_KEY"),
                            f"api_key_env 应为环境变量名: {key_env}",
                        )


class TestA3SwitchIsolation(unittest.TestCase):
    """验收：切换不互相污染。"""

    def test_resolved_binding_is_independent_copy(self):
        """改动解析结果不回写磁盘、不影响后续解析。"""
        binding = resolve_capability(CHARACTER_ID, "llm", profile="work")
        binding.model = "被污染的模型"
        fresh = resolve_capability(CHARACTER_ID, "llm", profile="work")
        self.assertEqual(fresh.model, "deepseek-v4-pro")

    def test_work_pet_switch_no_cross_pollution(self):
        """反复交错切换 work/pet，各自绑定保持不变。"""
        for _ in range(3):
            work = resolve_capability(CHARACTER_ID, "llm", profile="work")
            pet = resolve_capability(CHARACTER_ID, "llm", profile="pet")
            work.temperature = 9.9
            self.assertEqual(pet.model, "deepseek-v4-lite")
            self.assertNotEqual(pet.temperature, 9.9)
        self.assertEqual(
            resolve_capability(CHARACTER_ID, "llm", profile="work").model,
            "deepseek-v4-pro",
        )

    def test_default_profile_used_when_omitted(self):
        caps = load_capabilities(CHARACTER_ID)
        self.assertEqual(caps.default_profile, "work")
        self.assertEqual(
            resolve_capability(CHARACTER_ID, "llm").model,
            resolve_capability(CHARACTER_ID, "llm", profile="work").model,
        )


class TestA3EnvOverlay(unittest.TestCase):
    """provider overlay：LUMO_CAP_<PROFILE>_<TYPE>_* 覆写，优先级高于 json。"""

    def tearDown(self):
        for key in list(os.environ):
            if key.startswith("LUMO_CAP_"):
                del os.environ[key]

    def test_model_overlay_wins_over_json(self):
        os.environ["LUMO_CAP_PET_LLM_MODEL"] = "overlay-model"
        binding = resolve_capability(CHARACTER_ID, "llm", profile="pet")
        self.assertEqual(binding.model, "overlay-model")
        # json 原值不受影响
        self.assertEqual(
            load_capabilities(CHARACTER_ID).profiles["pet"].llm.model,
            "deepseek-v4-lite",
        )

    def test_overlay_scoped_to_its_own_profile_and_type(self):
        os.environ["LUMO_CAP_PET_LLM_MODEL"] = "overlay-model"
        work_llm = resolve_capability(CHARACTER_ID, "llm", profile="work")
        pet_tts = resolve_capability(CHARACTER_ID, "tts", profile="pet")
        self.assertEqual(work_llm.model, "deepseek-v4-pro")
        self.assertNotEqual(pet_tts.model, "overlay-model")

    def test_overlay_without_env_keeps_json(self):
        binding = resolve_capability(CHARACTER_ID, "llm", profile="work")
        self.assertEqual(binding.model, "deepseek-v4-pro")


class TestA3FailFastAndKeyResolution(unittest.TestCase):
    def test_unknown_profile_raises(self):
        with self.assertRaises(KeyError):
            resolve_capability(CHARACTER_ID, "llm", profile="不存在")

    def test_unknown_capability_type_raises(self):
        with self.assertRaises(ValueError):
            resolve_capability(CHARACTER_ID, "量子纠缠", profile="work")

    def test_missing_character_yields_empty_table(self):
        caps = load_capabilities("查无此角色")
        self.assertEqual(caps.profiles, {})
        with self.assertRaises(KeyError):
            resolve_capability("查无此角色", "llm")

    def test_resolve_api_key_from_env(self):
        binding = CapabilityBinding(api_key_env="A3_TEST_KEY")
        os.environ["A3_TEST_KEY"] = "test-secret"
        try:
            self.assertEqual(binding.resolve_api_key(), "test-secret")
        finally:
            del os.environ["A3_TEST_KEY"]
        self.assertEqual(binding.resolve_api_key(), "")

    def test_no_key_env_means_no_key(self):
        self.assertEqual(CapabilityBinding(provider="edge-tts").resolve_api_key(), "")


if __name__ == "__main__":
    unittest.main()
