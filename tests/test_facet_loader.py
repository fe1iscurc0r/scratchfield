"""卷178-B 验收测试：Facet manifest 校验 + 宿主加载器激活语义。

覆盖：合法/非法 manifest、precheck 过/不过、重复 facet id 冲突、
装配同源判定（enabled/available）、演示 facet 端到端。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from apiserver.facet_loader import (  # noqa: E402
    FacetActivationError,
    FacetRegistration,
    FacetRegistry,
    PanelSpec,
    PrecheckSpec,
    load_registry,
)
from mcpserver.tool_registry.check_classification import check_facets_rules  # noqa: E402

pytestmark = [pytest.mark.core]


def _manifest(**overrides):
    base = {
        "name": "demo_agent",
        "tools": [{"name": "demo_status"}, {"name": "demo_estop"}],
        "capabilities": {"invocationCommands": [{"command": "demo_status"}]},
    }
    base.update(overrides)
    return base


class TestFacetSchemaRules:
    """A：校验规则（设计稿 §二 四条强制约束）。"""

    def test_no_facets_block_is_ok(self):
        assert check_facets_rules(_manifest(), "x.json") == []

    def test_valid_status_card_passes(self):
        m = _manifest(facets={"panel": {
            "kind": "status-card", "component": "DemoStatusCard",
            "poll": {"tool": "demo_status", "interval_ms": 1000}}})
        assert check_facets_rules(m, "x.json") == []

    def test_poll_tool_must_be_declared(self):
        m = _manifest(facets={"panel": {
            "kind": "status-card", "component": "C",
            "poll": {"tool": "not_declared", "interval_ms": 1000}}})
        errs = check_facets_rules(m, "x.json")
        assert any("不在已声明工具面" in e for e in errs)

    def test_poll_interval_minimum(self):
        m = _manifest(facets={"panel": {
            "kind": "status-card", "component": "C",
            "poll": {"tool": "demo_status", "interval_ms": 100}}})
        assert any("interval_ms 必须 >= 250" in e for e in check_facets_rules(m, "x.json"))

    def test_control_panel_requires_actions(self):
        m = _manifest(facets={"panel": {"kind": "control-panel", "component": "C"}})
        assert any("control-panel 必须声明 actions" in e for e in check_facets_rules(m, "x.json"))

    def test_always_available_requires_reduces_risk(self):
        m = _manifest(facets={"panel": {
            "kind": "control-panel", "component": "C",
            "actions": [{"tool": "demo_estop", "always_available": True}]}})
        assert any("always_available" in e for e in check_facets_rules(m, "x.json"))
        # 声明 reduces_risk 后合法
        m2 = _manifest(facets={"panel": {
            "kind": "control-panel", "component": "C",
            "actions": [{"tool": "demo_estop", "always_available": True, "reduces_risk": True}]}})
        assert check_facets_rules(m2, "x.json") == []

    def test_bad_kind_and_missing_component(self):
        errs = check_facets_rules(_manifest(facets={"panel": {"kind": "chart"}}), "x.json")
        assert any("kind 非法" in e for e in errs)
        assert any("component 必填" in e for e in errs)


class TestLoaderRegistration:
    def test_repeated_id_conflicts(self):
        reg = FacetRegistry()
        reg.register(FacetRegistration("a", PanelSpec(kind="status-card", component="C"), "m1"))
        with pytest.raises(ValueError, match="重复 facet 注册"):
            reg.register(FacetRegistration("a", PanelSpec(kind="status-card", component="C"), "m2"))

    def test_scan_real_repo_no_crash(self):
        """扫真实仓库（当前无 manifest 声明 facets —— 零迁移成本的现状）。"""
        r = load_registry(PROJECT_ROOT)
        assert isinstance(r.registrations, list)


class TestActivation:
    def _reg_with_precheck(self, **pc):
        reg = FacetRegistry(command_probe=lambda c: c == "uptime")
        reg.register(FacetRegistration(
            "uptime_panel",
            PanelSpec(kind="status-card", component="UptimeCard",
                      poll={"tool": "uptime_status", "interval_ms": 1000},
                      precheck=PrecheckSpec(**pc)),
            "demo"))
        return reg

    def test_activate_requires_enabled_and_available(self):
        """装配同源判定：任一不满足 → 结构化错误。"""
        reg = self._reg_with_precheck()
        with pytest.raises(FacetActivationError) as e1:
            reg.activate("uptime_panel", enabled=False, available=True)
        assert e1.value.failed_check == "assembly" and "未启用" in e1.value.reason
        with pytest.raises(FacetActivationError) as e2:
            reg.activate("uptime_panel", enabled=True, available=False)
        assert e2.value.failed_check == "assembly"

    def test_precheck_command_pass_and_fail(self):
        reg = self._reg_with_precheck(command="uptime")
        panel = reg.activate("uptime_panel", enabled=True, available=True)
        assert panel.component == "UptimeCard"
        reg2 = self._reg_with_precheck(command="definitely-not-a-command")
        with pytest.raises(FacetActivationError) as e:
            reg2.activate("uptime_panel", enabled=True, available=True)
        assert e.value.failed_check == "precheck:command"
        assert e.value.to_dict()["agent"] == "uptime_panel"

    def test_precheck_tool_probe(self):
        reg = self._reg_with_precheck(tool="uptime_probe")
        with pytest.raises(FacetActivationError) as e:
            reg.activate("uptime_panel", enabled=True, available=True, tool_probe=lambda t: False)
        assert e.value.failed_check == "precheck:tool"
        panel = reg.activate("uptime_panel", enabled=True, available=True, tool_probe=lambda t: True)
        assert panel.kind == "status-card"

    def test_unregistered_agent(self):
        with pytest.raises(FacetActivationError) as e:
            FacetRegistry().activate("nobody", enabled=True, available=True)
        assert e.value.failed_check == "registration"

    def test_error_is_structured_not_silent(self):
        """不静默：错误对象可序列化且含失败项与原因。"""
        reg = self._reg_with_precheck(command="nope")
        try:
            reg.activate("uptime_panel", enabled=True, available=True)
        except FacetActivationError as e:
            d = e.to_dict()
            assert set(d) == {"agent", "facet", "failed_check", "reason"}
            assert d["reason"]
        else:
            pytest.fail("应抛 FacetActivationError")


class TestEndToEndDemo:
    """C：演示 facet 从注册 → 激活 → 查询的端到端（uptime 状态卡片）。"""

    def test_uptime_card_end_to_end(self, tmp_path, monkeypatch):
        # 1) 造演示 manifest（tmp，不污染真实能力清单）
        mdir = tmp_path / "mcpserver" / "uptime_panel"
        mdir.mkdir(parents=True)
        manifest = {
            "name": "uptime_panel",
            "tools": [{"name": "uptime_status"}],
            "capabilities": {"invocationCommands": [{"command": "uptime_status"}]},
            "classification": {"families": ["instrument"], "domains": [], "tier": "read-only",
                               "origin": {"kind": "native"}},
            "facets": {"panel": {
                "kind": "status-card", "component": "UptimeCard", "title": "系统运行时长",
                "poll": {"tool": "uptime_status", "interval_ms": 1000},
                "precheck": {"command": "python", "label": "python 可用"}}},
        }
        (mdir / "agent-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False),
                                                  encoding="utf-8")
        # 2) 扫描注册（清单校验也要过）
        reg = load_registry(tmp_path)
        regs = reg.registrations
        assert [r.agent_name for r in regs] == ["uptime_panel"]
        assert check_facets_rules(manifest, "demo") == []
        # 3) 激活（python 命令必然存在）
        panel = reg.activate("uptime_panel", enabled=True, available=True)
        assert panel.title == "系统运行时长"
        assert panel.poll["tool"] == "uptime_status"
        # 4) 查询（模拟宿主按 poll.tool 调工具面）
        called = {}

        def fake_tool(tool, params):
            called["tool"] = tool
            return {"ok": True, "uptime_s": 42.0}

        out = fake_tool(panel.poll["tool"], {})
        assert out["ok"] is True and called["tool"] == "uptime_status"
