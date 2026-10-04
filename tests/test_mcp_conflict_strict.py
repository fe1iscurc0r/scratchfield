"""B1 跨源冲突严格化（CONFLICT_STRICT）单元测试。

验收对应：
- CONFLICT_STRICT=0：行为与现状完全一致（冲突仅 WARNING，登记照常，_CONFLICT_LOG 恒空）
- CONFLICT_STRICT=1：同名冲突登记被拒（CONFLICT_REJECTED + _CONFLICT_LOG 落记录）
- 优先级规则：adapter 覆盖 manifest / manifest 覆盖 mcporter / 同类源必拒
"""
from __future__ import annotations

import pytest

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.core]

import logging
import os
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]  # scratchpad/
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(level=logging.ERROR)

from mcpserver import mcp_registry  # noqa: E402


class ConflictStrictTestBase(unittest.TestCase):
    """公共隔离：每用例清空三表 + _CONFLICT_LOG，保存/恢复 CONFLICT_STRICT 环境变量。"""

    def setUp(self):
        self._saved = os.environ.pop("CONFLICT_STRICT", None)
        mcp_registry.clear_registry()

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("CONFLICT_STRICT", None)
        else:
            os.environ["CONFLICT_STRICT"] = self._saved
        mcp_registry.clear_registry()

    # 便捷写入助手（绕过门禁直接铺底，模拟"历史已登记"状态）
    def _seed_manifest(self, name: str, source: str = "manifest") -> None:
        mcp_registry.MANIFEST_CACHE[name] = {
            "name": name, "displayName": name, "description": f"seed-{source}",
            "source": source,
        }

    def _seed_adapter(self, name: str) -> None:
        mcp_registry._ADAPTER_CAPABILITIES[name] = {
            "name": name, "displayName": name, "description": "seed-adapter",
            "_from_adapter": name,
        }


class TestStrictDisabledBehaviorUnchanged(ConflictStrictTestBase):
    """CONFLICT_STRICT=0（默认）：一切照旧。"""

    def test_default_env_allows_conflicting_registration_with_warning_only(self):
        """未设置 CONFLICT_STRICT：跨源冲突只打 WARNING，登记放行，_CONFLICT_LOG 为空。"""
        self._seed_manifest("headroom")  # manifest 域先占名
        with self.assertLogs("mcpserver.mcp_registry", level="WARNING") as ctx:
            verdict = mcp_registry._gate_cross_source_registration("headroom", "adapter")
        self.assertIsNone(verdict, "非严格模式必须放行（返回 None）")
        self.assertTrue(any("跨源冲突" in line for line in ctx.output),
                        f"应保留现状 WARNING 日志，实际: {ctx.output}")
        self.assertEqual(mcp_registry.get_conflict_log(), [],
                         "非严格模式不得写 _CONFLICT_LOG")

    def test_strict_zero_same_source_overwrite_still_allowed(self):
        """CONFLICT_STRICT=0：同类源重复登记允许覆盖（现状），register_capability 两次都成功。"""
        os.environ["CONFLICT_STRICT"] = "0"
        cap = {"name": "dup", "displayName": "dup", "description": "x",
               "version": "1", "license": "MIT", "vendor": "t", "_from_adapter": "dup"}
        self.assertTrue(mcp_registry.register_capability(dict(cap)))
        self.assertTrue(mcp_registry.register_capability(dict(cap)),
                        "strict=0 下同类源覆盖是现状行为，必须保持")
        self.assertEqual(mcp_registry.get_conflict_log(), [])

    def test_strict_disabled_cross_source_registration_succeeds_via_real_api(self):
        """CONFLICT_STRICT=0：manifest 域占名后 register_capability（跨源）仍成功。"""
        self._seed_manifest("crossx")
        ok = mcp_registry.register_capability({
            "name": "crossx", "displayName": "crossx", "description": "adapter 侧",
            "version": "1", "license": "MIT", "vendor": "t", "_from_adapter": "crossx",
        })
        self.assertTrue(ok, "strict=0 跨源登记不阻断（现状）")
        caps = [c for c in mcp_registry.list_registered_capabilities() if c["name"] == "crossx"]
        self.assertEqual(sorted(c["source"] for c in caps), ["adapter", "manifest"])


class TestStrictEnabledRejects(ConflictStrictTestBase):
    """CONFLICT_STRICT=1：冲突登记拒绝 + _CONFLICT_LOG 落记录。"""

    def test_same_name_registration_rejected_and_logged(self):
        """=1 时构造同名登记：同类源（adapter 能力卡重复）→ register_capability 返回
        False + _CONFLICT_LOG 记 REJECT_SAME_SOURCE。"""
        os.environ["CONFLICT_STRICT"] = "1"
        cap = {"name": "dup", "displayName": "dup", "description": "x",
               "version": "1", "license": "MIT", "vendor": "t", "_from_adapter": "dup"}
        self.assertTrue(mcp_registry.register_capability(dict(cap)),
                        "首次登记无冲突必须成功")
        self.assertFalse(mcp_registry.register_capability(dict(cap)),
                         "严格模式同类源重复登记必须拒绝")
        log = mcp_registry.get_conflict_log()
        self.assertEqual(len(log), 1, f"_CONFLICT_LOG 应恰有 1 条，实际 {log}")
        self.assertEqual(log[0]["name"], "dup")
        self.assertEqual(log[0]["action"], "REJECT_SAME_SOURCE")
        self.assertEqual(log[0]["new_source"], "adapter")

    def test_lower_priority_manifest_rejected_over_adapter(self):
        """=1 时低优先级覆盖高优先级：adapter 已占名，manifest 再登记 → CONFLICT_REJECTED。"""
        os.environ["CONFLICT_STRICT"] = "1"
        self._seed_adapter("taken")
        verdict = mcp_registry._gate_cross_source_registration("taken", "manifest")
        self.assertEqual(verdict, mcp_registry.CONFLICT_REJECTED)
        self.assertEqual(mcp_registry.get_conflict_log()[-1]["action"], "REJECT")

    def test_strict_enabled_end_to_end_scan_like_flow_rejects_write(self):
        """=1 时端到端：adapter 能力卡占名后，scan 路径写 MANIFEST_CACHE 前的门禁拦截
        （直接验证 gate 语义 = scan_and_register_mcp_agents 内联调用点）。"""
        os.environ["CONFLICT_STRICT"] = "1"
        self._seed_adapter("blocked")
        verdict = mcp_registry._gate_cross_source_registration("blocked", "manifest")
        self.assertEqual(verdict, mcp_registry.CONFLICT_REJECTED,
                         "manifest(2) 不得覆盖 adapter(3)")


class TestPriorityRules(ConflictStrictTestBase):
    """优先级规则单测 3 条：adapter 覆盖 manifest / manifest 覆盖 mcporter / 同类源必拒。"""

    def test_rule_1_adapter_overrides_manifest(self):
        """规则一：adapter(3) 覆盖 manifest(2) → 放行并记 OVERRIDE。"""
        os.environ["CONFLICT_STRICT"] = "1"
        self._seed_manifest("svc", source="manifest")
        verdict = mcp_registry._gate_cross_source_registration("svc", "adapter")
        self.assertIsNone(verdict, "adapter 优先级最高，应放行覆盖 manifest")
        log = mcp_registry.get_conflict_log()
        self.assertEqual(log[-1]["action"], "OVERRIDE")
        self.assertEqual(log[-1]["new_source"], "adapter")
        self.assertEqual(log[-1]["existing_sources"], ["manifest"])

    def test_rule_2_manifest_overrides_mcporter(self):
        """规则二：manifest(2) 覆盖 mcporter(1) → 放行并记 OVERRIDE。"""
        os.environ["CONFLICT_STRICT"] = "1"
        self._seed_manifest("svc", source="mcporter")
        verdict = mcp_registry._gate_cross_source_registration("svc", "manifest")
        self.assertIsNone(verdict, "manifest 优先级高于 mcporter，应放行覆盖")
        log = mcp_registry.get_conflict_log()
        self.assertEqual(log[-1]["action"], "OVERRIDE")
        self.assertEqual(log[-1]["existing_sources"], ["mcporter"])

    def test_rule_3_same_source_always_rejected(self):
        """规则三：同类源必拒（manifest vs manifest / adapter vs adapter 两个方向都验）。"""
        os.environ["CONFLICT_STRICT"] = "1"
        self._seed_manifest("svc", source="manifest")
        self.assertEqual(
            mcp_registry._gate_cross_source_registration("svc", "manifest"),
            mcp_registry.CONFLICT_REJECTED,
            "manifest 同类源重复登记必须拒绝")
        self._seed_adapter("cap")
        self.assertEqual(
            mcp_registry._gate_cross_source_registration("cap", "adapter"),
            mcp_registry.CONFLICT_REJECTED,
            "adapter 同类源重复登记必须拒绝")
        actions = [e["action"] for e in mcp_registry.get_conflict_log()]
        self.assertEqual(actions, ["REJECT_SAME_SOURCE", "REJECT_SAME_SOURCE"])


class TestConflictLogLifecycle(ConflictStrictTestBase):
    """_CONFLICT_LOG 生命周期与 get_registry_status 暴露。"""

    def test_get_conflict_log_returns_copy(self):
        """get_conflict_log 返回副本，外部 append 不污染内部状态。"""
        os.environ["CONFLICT_STRICT"] = "1"
        self._seed_adapter("svc")
        mcp_registry._gate_cross_source_registration("svc", "manifest")  # REJECT
        snapshot = mcp_registry.get_conflict_log()
        snapshot.append({"fake": True})
        self.assertEqual(len(mcp_registry.get_conflict_log()), 1)

    def test_registry_status_reports_strict_flag(self):
        """get_registry_status 暴露 conflict_strict 开关与日志条数。"""
        os.environ["CONFLICT_STRICT"] = "1"
        status = mcp_registry.get_registry_status()
        self.assertTrue(status["conflict_strict"])
        self.assertEqual(status["conflict_log_entries"], 0)
        os.environ["CONFLICT_STRICT"] = "0"
        self.assertFalse(mcp_registry.get_registry_status()["conflict_strict"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
