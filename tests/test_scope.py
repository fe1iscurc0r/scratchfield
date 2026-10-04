"""W124-01 验收：Scope 原语（per-角色/会话 工具可见性）。

覆盖：白名单过滤（展示层）/ 黑名单优先 / 执行层拦截（直接构造调用）/ 未配置角色兼容 /
前缀与通配匹配 / 会话级角色绑定 / 注册表 tool_scope 合并 / 技能白名单。
"""
from __future__ import annotations

import pytest  # noqa: E402  (卷173 分层标注；与文件既有 import pytest 重复无害)

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.core]

import asyncio
import json

import pytest

from apiserver.agentic_loop_parts import loop as atl  # 卷190-A2：patch 目标须指向实际调用方命名空间
from mcpserver import scope


class _ScopeCfg:
    def __init__(self, **kw):
        self.enabled = kw.get("enabled", True)
        self.default_visible_all = kw.get("default_visible_all", True)
        self.roles = kw.get("roles", {})
        self.session_roles = kw.get("session_roles", {})
        self.registry_path = kw.get("registry_path", "characters/registry.json")


def _set_cfg(monkeypatch, **kw):
    cfg = _ScopeCfg(**kw)
    monkeypatch.setattr(scope, "_cfg", lambda: cfg)
    return cfg


@pytest.fixture()
def empty_registry(tmp_path, monkeypatch):
    """默认指向一个不存在的注册表，避免测试受真实 characters/registry.json 影响。"""
    missing = tmp_path / "no-registry.json"
    monkeypatch.setattr(scope, "registry_path", lambda: missing)
    return missing


TOOLS = [
    "mcp__code_workspace__code_exec",
    "mcp__code_workspace__file_write",
    "mcp__material_science__query_material",
    "openclaw__agent",
    "live2d__action",
]


# ---------------------------------------------------------------------------
# 匹配规则
# ---------------------------------------------------------------------------


def test_matches_exact_prefix_and_wildcard():
    assert scope.matches("mcp__code_workspace__code_exec", "mcp__code_workspace__code_exec")
    assert scope.matches("mcp__code_workspace", "mcp__code_workspace__code_exec"), "前缀匹配"
    assert scope.matches("mcp__code_workspace__*", "mcp__code_workspace__file_write")
    assert scope.matches("*", "anything__at__all")
    assert not scope.matches("mcp__weather_time", "mcp__code_workspace__code_exec")
    assert not scope.matches("", "x") and not scope.matches("x", "")


# ---------------------------------------------------------------------------
# 白名单 / 黑名单
# ---------------------------------------------------------------------------


def test_whitelist_filters_visible_tools(monkeypatch, empty_registry):
    _set_cfg(monkeypatch, roles={"科研": {"allowed_tools": ["mcp__code_workspace__*",
                                                           "mcp__material_science__query_material"]}})
    visible = scope.visible_tools(TOOLS, role="科研")
    assert visible == ["mcp__code_workspace__code_exec", "mcp__code_workspace__file_write",
                       "mcp__material_science__query_material"]
    assert "openclaw__agent" not in visible

    ok, reason = scope.tool_visible("openclaw__agent", role="科研")
    assert not ok and "not_in_whitelist" in reason
    ok, reason = scope.tool_visible("mcp__code_workspace__code_exec", role="科研")
    assert ok and "allowed_by_role" in reason


def test_denied_beats_allowed(monkeypatch, empty_registry):
    _set_cfg(monkeypatch, roles={"桌宠": {
        "allowed_tools": ["live2d__*", "tts__*"],
        "denied_tools": ["live2d__action"],
    }})
    ok, reason = scope.tool_visible("live2d__action", role="桌宠")
    assert not ok and "denied_by_role" in reason, "denied 必须优先于 allowed"

    ok, _ = scope.tool_visible("tts__speak", role="桌宠")
    assert ok


def test_unconfigured_role_keeps_full_visibility(monkeypatch, empty_registry):
    """兼容：未配置角色默认全可见；显式 default_visible_all=false 才收紧。"""
    _set_cfg(monkeypatch, roles={"科研": {"allowed_tools": ["mcp__code_workspace__*"]}})
    assert scope.visible_tools(TOOLS, role="陆墨") == TOOLS
    assert scope.visible_tools(TOOLS, role="") == TOOLS
    assert scope.tool_visible("openclaw__agent", role="陆墨")[0] is True

    _set_cfg(monkeypatch, default_visible_all=False,
             roles={"科研": {"allowed_tools": ["mcp__code_workspace__*"]}})
    assert scope.visible_tools(TOOLS, role="陆墨") == []
    ok, reason = scope.tool_visible("openclaw__agent", role="陆墨")
    assert not ok and reason == "unconfigured_role_denied"


def test_scope_disabled_bypasses_everything(monkeypatch, empty_registry):
    _set_cfg(monkeypatch, enabled=False, roles={"科研": {"allowed_tools": ["nothing"]}})
    assert scope.visible_tools(TOOLS, role="科研") == TOOLS
    assert scope.filter_schemas([{"function": {"name": "x"}}], role="科研")


# ---------------------------------------------------------------------------
# 会话绑定与注册表
# ---------------------------------------------------------------------------


def test_session_role_binding_wins(monkeypatch, empty_registry):
    _set_cfg(monkeypatch, roles={"科研": {"allowed_tools": ["mcp__code_workspace__*"]}},
             session_roles={"sess-42": "科研"})
    assert scope.resolve_role(session_id="sess-42") == "科研"
    visible = scope.visible_tools(TOOLS, session_id="sess-42")
    assert visible == ["mcp__code_workspace__code_exec", "mcp__code_workspace__file_write"]
    # 显式 role 优先级最高
    assert scope.resolve_role(session_id="sess-42", role="陆墨") == "陆墨"


def test_registry_tool_scope_is_merged(tmp_path, monkeypatch):
    """角色注册表里的 tool_scope 会被并入 Scope 配置（中英文名都能引用）。"""
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({
        "active_role": "lumo-lumu",
        "roles": {
            "lumo-lumu": {"role_id": "lumo-lumu", "display_name": "陆墨"},
            "naga-nadezhda": {
                "role_id": "naga-nadezhda", "display_name": "娜杰日达",
                "tool_scope": {"allowed_tools": ["mcp__material_science__*"], "skills": ["paper-*"]},
            },
        },
    }, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(scope, "registry_path", lambda: registry)
    _set_cfg(monkeypatch, registry_path=str(registry))

    assert scope.resolve_role(agent_id="naga-nadezhda") == "naga-nadezhda"
    assert scope.resolve_role(agent_id="娜杰日达") == "naga-nadezhda", "中文名映射回 role_id"
    visible = scope.visible_tools(TOOLS, agent_id="naga-nadezhda")
    assert visible == ["mcp__material_science__query_material"]
    assert scope.resolve_role(agent_id="unknown-id") == "unknown-id"
    assert scope.resolve_role() == "lumo-lumu", "无 agent_id 时用注册表 active_role"

    # 技能白名单（W124-05 用同一份配置）
    assert scope.is_skill_visible("paper-miner", role="娜杰日达")
    assert not scope.is_skill_visible("tts-demo", role="娜杰日达")
    assert scope.is_skill_visible("tts-demo", role="陆墨"), "未配技能的角色不限制"


# ---------------------------------------------------------------------------
# 执行层拦截
# ---------------------------------------------------------------------------


def test_execution_layer_blocks_invisible_tool(monkeypatch, empty_registry):
    """展示层过滤之外，直接构造的调用也必须被拦（执行层校验）。"""
    _set_cfg(monkeypatch, roles={"科研": {"allowed_tools": ["mcp__code_workspace__*"]}},
             session_roles={"s1": "科研"})

    blocked = atl._run_scope_gate(
        {"agentType": "mcp", "service_name": "openclaw", "tool_name": "agent",
         "_original_name": "openclaw__agent"},
        "s1", None,
    )
    assert blocked is not None
    assert blocked["status"] == "error" and "无权使用" in blocked["result"]
    assert blocked["tool_name"] == "openclaw__agent"

    # 文本兼容期只给短名，也能正确判定（用 service_name/agentType 拼限定名）
    blocked_short = atl._run_scope_gate(
        {"agentType": "mcp", "service_name": "openclaw", "tool_name": "agent"}, "s1", None
    )
    assert blocked_short is not None

    allowed = atl._run_scope_gate(
        {"agentType": "mcp", "service_name": "code_workspace", "tool_name": "code_exec"},
        "s1", None,
    )
    assert allowed is None, "白名单内工具应放行"


def test_execution_layer_respects_session_role(monkeypatch, empty_registry):
    _set_cfg(monkeypatch, roles={"科研": {"allowed_tools": ["mcp__code_workspace__*"]},
                                 "桌宠": {"allowed_tools": ["live2d__*"]}},
             session_roles={"sess-sci": "科研", "sess-pet": "桌宠"})
    call = {"agentType": "mcp", "service_name": "code_workspace", "tool_name": "code_exec"}
    assert atl._run_scope_gate(call, "sess-sci", None) is None, "科研会话可见"
    assert atl._run_scope_gate(call, "sess-pet", None) is not None, "桌宠会话不可见"


def test_scope_gate_fail_open_on_error(monkeypatch):
    """Scope 模块自身异常时放行（fail-open），不因为可见性检查把工具全掐死。"""
    def _boom(*a, **k):
        raise RuntimeError("scope down")

    monkeypatch.setattr(scope, "enabled", _boom)
    assert atl._run_scope_gate({"tool_name": "x"}, "s1", None) is None


def test_loop_blocks_invisible_tool_end_to_end(monkeypatch, empty_registry):
    """整链路：模型调不可见工具 → 循环里被拦，工具不执行。"""
    from tests.test_agentic_loop_flow import _collect, _events, _FakeLLM, _ScriptedCalls

    _set_cfg(monkeypatch, roles={"科研": {"allowed_tools": ["mcp__code_workspace__*"]}},
             session_roles={"s-scope": "科研"})
    monkeypatch.setattr(atl, "_run_tool_gate", _no_gate())
    executed = {"n": 0}

    async def _fake_dispatch(call, session_id, source_agent_id):
        executed["n"] += 1
        return {"result": "should not run", "status": "success",
                "service_name": "openclaw", "tool_name": "agent"}

    monkeypatch.setattr(atl, "_dispatch_one_call", _fake_dispatch)
    llm = _FakeLLM(["我调个工具", "好吧"])
    monkeypatch.setattr("apiserver.llm_service.get_llm_service", lambda: llm)
    monkeypatch.setattr(atl, "parse_tool_calls_from_text", _ScriptedCalls(
        [[{"agentType": "mcp", "service_name": "openclaw", "tool_name": "agent"}], []]
    ))

    chunks = asyncio.run(_collect(atl.run_agentic_loop(
        [{"role": "user", "content": "帮我搜索"}], "s-scope", max_rounds=2
    )))
    results = [e for e in _events(chunks) if e.get("type") == "tool_results"]
    assert results and results[0]["results"][0]["status"] == "error"
    assert "无权使用" in str(results[0]["results"][0]["result"])
    assert executed["n"] == 0, "不可见工具不得进入执行器"


def _no_gate():
    async def _inner(call, session_id, source_agent_id):
        return None

    return _inner
