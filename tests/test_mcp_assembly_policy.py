"""apiserver/mcp_assembly.py 的单元测试。

纯函数测试：**不依赖 FastAPI、不触发 apiserver/__init__.py 的包级导入链**
（该链需要 matplotlib 等重依赖），故用 importlib 直接加载模块文件。

覆盖：
- decide_enabled 的六种判定路径（含「空策略 = 全启用」这条兼容性红线）
- load_policy 的四种容错（缺失/坏 JSON/结构不符/正常）
- set_agent_override 的写入与幂等
"""
from __future__ import annotations

import pytest

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.smoke, pytest.mark.core]

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_module():
    """直接按文件路径加载，绕过 apiserver 包的 __init__ 重依赖。"""
    spec = importlib.util.spec_from_file_location(
        "mcp_assembly_under_test", PROJECT_ROOT / "apiserver" / "mcp_assembly.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


asm = _load_module()

OFFENSIVE = {"families": ["offense"], "tier": "offensive"}
TRIVY = {"families": ["offense"], "tier": "read-only"}
HEADROOM = {"families": ["context"], "tier": "read-only"}


class TestDecideEnabled(unittest.TestCase):
    def test_empty_policy_keeps_everything_enabled(self):
        """兼容性红线：无策略 = 全启用（引入本模块不得改变既有行为）。"""
        for cls in (OFFENSIVE, TRIVY, HEADROOM, {}, None):
            self.assertEqual(asm.decide_enabled("any", cls, {}), (True, None))

    def test_disable_tier_offensive(self):
        pol = {"disable_tiers": ["offensive"]}
        self.assertEqual(asm.decide_enabled("agent_frida", OFFENSIVE, pol),
                         (False, "tier:offensive"))
        # 非 offensive 不受影响
        self.assertEqual(asm.decide_enabled("agent_trivy", TRIVY, pol), (True, None))

    def test_user_override_beats_tier_policy(self):
        """用户显式开关优先级最高——能覆盖 tier 策略把 offensive 打开。"""
        pol = {"disable_tiers": ["offensive"], "agent_overrides": {"agent_frida": True}}
        self.assertEqual(asm.decide_enabled("agent_frida", OFFENSIVE, pol), (True, None))
        pol2 = {"agent_overrides": {"headroom": False}}
        self.assertEqual(asm.decide_enabled("headroom", HEADROOM, pol2),
                         (False, "user_disabled"))

    def test_family_whitelist(self):
        pol = {"enabled_families": ["context"]}
        self.assertEqual(asm.decide_enabled("headroom", HEADROOM, pol), (True, None))
        self.assertEqual(asm.decide_enabled("agent_trivy", TRIVY, pol),
                         (False, "family_not_enabled"))

    def test_unclassified_agent_not_filtered_by_family(self):
        """分类缺失的 agent 不参与族过滤（避免被静默关掉）。"""
        pol = {"enabled_families": ["context"]}
        self.assertEqual(asm.decide_enabled("legacy_agent", {}, pol), (True, None))
        self.assertEqual(asm.decide_enabled("legacy_agent", None, pol), (True, None))

    def test_disabled_agents_blacklist(self):
        pol = {"disabled_agents": ["headroom"]}
        self.assertEqual(asm.decide_enabled("headroom", HEADROOM, pol),
                         (False, "in_disabled_agents"))


class TestLoadPolicy(unittest.TestCase):
    def _write(self, content: str) -> Path:
        f = Path(tempfile.mkdtemp()) / "config.json"
        f.write_text(content, encoding="utf-8")
        return f

    def test_missing_file_returns_empty(self):
        self.assertEqual(asm.load_policy(Path(tempfile.mkdtemp()) / "nope.json"), {})

    def test_bad_json_returns_empty(self):
        self.assertEqual(asm.load_policy(self._write("{not json")), {})

    def test_wrong_shape_returns_empty(self):
        self.assertEqual(asm.load_policy(self._write('{"mcp_server": {"assembly": 42}}')), {})
        self.assertEqual(asm.load_policy(self._write('{"mcp_server": "x"}')), {})

    def test_normal(self):
        p = self._write(json.dumps({"mcp_server": {"assembly": {"disable_tiers": ["offensive"]}}}))
        self.assertEqual(asm.load_policy(p), {"disable_tiers": ["offensive"]})


class TestSetOverride(unittest.TestCase):
    def test_writes_override_and_preserves_other_keys(self):
        f = Path(tempfile.mkdtemp()) / "config.json"
        f.write_text(json.dumps({"system": {"a": 1}, "mcp_server": {"port": 8003}}),
                     encoding="utf-8")
        asm.set_agent_override(f, "agent_frida", True)
        raw = json.loads(f.read_text(encoding="utf-8"))
        self.assertEqual(raw["system"], {"a": 1})                      # 既有键保留
        self.assertEqual(raw["mcp_server"]["port"], 8003)
        self.assertEqual(raw["mcp_server"]["assembly"]["agent_overrides"]["agent_frida"], True)

        asm.set_agent_override(f, "agent_frida", False)                # 幂等可覆写
        raw2 = json.loads(f.read_text(encoding="utf-8"))
        self.assertEqual(raw2["mcp_server"]["assembly"]["agent_overrides"]["agent_frida"], False)

    def test_unreadable_raises_valueerror(self):
        with self.assertRaises(ValueError):
            asm.set_agent_override(Path(tempfile.mkdtemp()) / "missing.json", "x", True)


class TestCheckRequirements(unittest.TestCase):
    """requires 预检：字符串=必须，{"name", "optional": true}=软依赖（降级不缺）。"""

    def test_undeclared_returns_empty_triple(self):
        self.assertEqual(asm.check_requirements(None), ([], [], []))
        self.assertEqual(asm.check_requirements("nope"), ([], [], []))

    def test_missing_required_python_package(self):
        missing, opt_missing, _avail = asm.check_requirements(
            {"python_packages": ["no_such_pkg_for_test"]}
        )
        self.assertEqual(missing, ["python:no_such_pkg_for_test"])
        self.assertEqual(opt_missing, [])

    def test_missing_optional_python_package(self):
        missing, opt_missing, avail = asm.check_requirements(
            {"python_packages": [{"name": "no_such_pkg_for_test", "optional": True}]}
        )
        self.assertEqual(missing, [])
        self.assertEqual(opt_missing, ["python:no_such_pkg_for_test"])
        self.assertNotIn("python:no_such_pkg_for_test", avail)

    def test_present_package_goes_to_available(self):
        import importlib.util as _iu

        present = "json" if _iu.find_spec("json") else "os"
        missing, opt_missing, avail = asm.check_requirements({"python_packages": [present]})
        self.assertEqual((missing, opt_missing), ([], []))
        self.assertIn(f"python:{present}", avail)

    def test_mixed_required_and_optional(self):
        missing, opt_missing, _avail = asm.check_requirements({
            "python_packages": [
                "json",
                {"name": "no_such_pkg_for_test", "optional": True},
                "no_such_pkg_for_test_either",
            ]
        })
        self.assertEqual(missing, ["python:no_such_pkg_for_test_either"])
        self.assertEqual(opt_missing, ["python:no_such_pkg_for_test"])

    def test_optional_missing_cli(self):
        """external_cli 的 optional 语义同构（用确定不存在的 CLI 名，deterministic）。"""
        missing, opt_missing, _avail = asm.check_requirements({
            "external_cli": [{"name": "no_such_cli_for_test_xyz", "optional": True}]
        })
        self.assertEqual(missing, [])
        self.assertEqual(opt_missing, ["cli:no_such_cli_for_test_xyz"])

    def test_malformed_entries_ignored(self):
        """坏形态（dict 缺 name / 非字符串标量）忽略——宁可少判不误判。"""
        missing, opt_missing, avail = asm.check_requirements({
            "python_packages": [{"optional": True}, 42, None, {"name": "  "}, "json"]
        })
        self.assertEqual((missing, opt_missing), ([], []))
        self.assertEqual(avail, ["python:json"])


class TestSetPolicy(unittest.TestCase):
    """set_policy：策略维度写入（families/tiers 校验词汇表，None 清除）。"""

    def _cfg(self) -> Path:
        f = Path(tempfile.mkdtemp()) / "config.json"
        f.write_text("{}", encoding="utf-8")
        return f

    def test_write_and_replace(self):
        f = self._cfg()
        asm.set_policy(f, {"enabled_families": ["context", "code"]})
        raw = json.loads(f.read_text(encoding="utf-8"))
        self.assertEqual(raw["mcp_server"]["assembly"]["enabled_families"], ["context", "code"])
        asm.set_policy(f, {"enabled_families": ["semantic"]})          # 全量替换语义
        raw2 = json.loads(f.read_text(encoding="utf-8"))
        self.assertEqual(raw2["mcp_server"]["assembly"]["enabled_families"], ["semantic"])

    def test_none_clears_key(self):
        f = self._cfg()
        asm.set_policy(f, {"disable_tiers": ["offensive"]})
        asm.set_policy(f, {"disable_tiers": None})
        raw = json.loads(f.read_text(encoding="utf-8"))
        self.assertNotIn("disable_tiers", raw["mcp_server"]["assembly"])

    def test_unknown_family_raises(self):
        with self.assertRaises(ValueError):
            asm.set_policy(self._cfg(), {"enabled_families": ["nonexistent_family"]})

    def test_unknown_tier_raises(self):
        with self.assertRaises(ValueError):
            asm.set_policy(self._cfg(), {"disable_tiers": ["tool"]})   # 旧两套语义之一，应拒

    def test_agent_overrides_rejected(self):
        with self.assertRaises(ValueError):
            asm.set_policy(self._cfg(), {"agent_overrides": {"x": True}})

    def test_unknown_key_ignored(self):
        f = self._cfg()
        asm.set_policy(f, {"whatever": 1})
        raw = json.loads(f.read_text(encoding="utf-8"))
        self.assertNotIn("whatever", raw["mcp_server"]["assembly"])

    def test_bad_value_type_raises(self):
        with self.assertRaises(ValueError):
            asm.set_policy(self._cfg(), {"disable_tiers": "offensive"})

    def test_unreadable_raises(self):
        with self.assertRaises(ValueError):
            asm.set_policy(Path(tempfile.mkdtemp()) / "nope.json", {"disable_tiers": None})


if __name__ == "__main__":
    unittest.main()
