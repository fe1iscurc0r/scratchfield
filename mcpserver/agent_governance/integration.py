"""零侵入接线层 —— 把身份/授权/审计三件套挂到**现有调用点**，不改任何既有 dispatch 逻辑。

工单 241 §2 任务一第 2/3 条要求「在现有 agent 调用点 hook 签名+授权检查，
仅新增文件 + 现有调用点的入口加 2 行 hook，不动现有 dispatch 逻辑」。

⚠️ 工单原文指的调用点是 ``mcpserver/llm_gateway/dispatcher.py`` —— 该文件在本仓
**不存在**（``mcpserver/llm_gateway/`` 只有 ``__init__.py`` + ``anthropic_compat.py``）。
本仓真正的统一派发点是 ``mcpserver/mcp_manager.py::MCPManager.unified_call``
（``mcpserver/AGENTS.md`` 明写「``MCPManager.unified_call()`` 路由工具调用到正确的
agent 实例」），hook 落在这里。

## 开关语义（默认零影响）

===================================  ==========================================
``AGENT_GOVERNANCE`` 取值            行为
===================================  ==========================================
未设置 / ``0`` / ``off`` / ``false``   **旁路**：连模块都不 import，零开销、零依赖变化
``1`` / ``on`` / ``true`` / ``yes``    强制校验：无令牌或令牌无效 → 结构化错误 JSON
===================================  ==========================================

旁路时 ``guard_dispatch`` 直接返回 ``None``，``unified_call`` 其余流程**一字未改** ——
所以既有测试与既有行为完全不受影响（工单 §3 验收 3「不破坏现有用例」）。

## 与 ``mcpserver/scope.py`` 的取舍差异

``scope.py`` 对内部异常是 **fail-open**（放宽可见性，不停业务）。本层**刻意相反**：
一旦启用（``AGENT_GOVERNANCE=1``），治理层自身异常一律 **fail-closed** 并返回结构化错误 ——
授权判定出错时放行等于把「防冒充」变成空话。爆炸半径由「必须显式开开关」控制。
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from typing import Any

from mcpserver.agent_governance import audit
from mcpserver.agent_governance.authorization import AuthorizationAuthority
from mcpserver.agent_governance.errors import (
    E_INTERNAL,
    E_MISSING_KEY,
    E_TOKEN_MISSING,
    GovernanceError,
)

ENV_ENABLE = "AGENT_GOVERNANCE"
ENV_TOKEN = "AGENT_GOVERNANCE_TOKEN"
ENV_AGENT_ID = "AGENT_GOVERNANCE_AGENT_ID"
ENV_PROVIDER = "AGENT_GOVERNANCE_PROVIDER"

ENABLED_VALUES: frozenset[str] = frozenset({"1", "on", "true", "yes"})
DISABLED_VALUES: frozenset[str] = frozenset({"", "0", "off", "false", "no"})

#: 调用点标记（自指式契约：``tests/test_agent_governance_hook.py`` 断言这三行
#: 一字不差地出现在 ``mcpserver/mcp_manager.py`` 里 —— 接线被删会被测试抓住）。
HOOK_COMMENT = "# agent_governance hook（工单241）：默认旁路，仅 AGENT_GOVERNANCE 开启时生效"
HOOK_LINES: tuple[str, ...] = (
    "gov_blocked = _agent_governance_block(service_name, tool_call)",
    "if gov_blocked:",
    "return gov_blocked",
)
HOOK_CALL_SITE = "mcpserver/mcp_manager.py"

#: 令牌与身份元数据在 tool_call 上的键（顶层优先，其次 params 内）
META_TOKEN = "_gov_token"
META_AGENT_ID = "_gov_agent_id"
META_PROVIDER = "_gov_provider"


def governance_enabled(environ: dict[str, str] | None = None) -> bool:
    """总开关。未设置或落在 ``DISABLED_VALUES`` 一律视为关闭（默认关闭）。"""
    env = os.environ if environ is None else environ
    return env.get(ENV_ENABLE, "").strip().lower() in ENABLED_VALUES


def _meta(tool_call: Any, key: str, env_key: str, environ: dict[str, str]) -> str:
    """从 tool_call 顶层 → tool_call["params"] → 环境变量 依次取元数据。"""
    if isinstance(tool_call, dict):
        for container in (tool_call, tool_call.get("params")):
            if isinstance(container, dict) and container.get(key):
                return str(container[key])
    return environ.get(env_key, "")


def _error_json(error_type: str, code: str, message: str, service_name: str, **extra: Any) -> str:
    payload: dict[str, Any] = {
        "status": "error",
        "error_type": error_type,
        "code": code,
        "tool": service_name,
        "message": message,
    }
    payload.update(extra)
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _safe_record(event: str, **kwargs: Any) -> dict[str, Any] | None:
    """审计是**旁路证据层**，不是授权判定层：写不进去不该阻断已授权的调用。"""
    try:
        return audit.record(event, **kwargs)
    except Exception:  # pragma: no cover - 受磁盘权限/只读 FS 影响
        return None


def guard_dispatch(
    service_name: str,
    tool_call: Any,
    *,
    environ: dict[str, str] | None = None,
    authority: AuthorizationAuthority | None = None,
    now: Any = None,
    audit_path: Any = None,
) -> str | None:
    """调用点守卫。返回 ``None`` = 放行；返回字符串 = 标准错误 JSON（调用方直接 return）。

    Args:
        service_name: 被调用的 MCP 服务名（同 ``unified_call`` 的入参）。
        tool_call: 调用载荷；可携带 ``_gov_token`` / ``_gov_agent_id`` / ``_gov_provider``。
        environ: 注入环境变量（测试用）；缺省读 ``os.environ``。
        authority: 注入校验器（测试用）；缺省按环境变量密钥构造。
        now: 注入当前时间（测试过期/时钟偏移用）。
        audit_path: 注入审计文件路径（测试用）。
    """
    env = os.environ if environ is None else environ
    if not governance_enabled(env):
        return None  # 旁路：零开销，不 import 校验器，不碰审计

    token = _meta(tool_call, META_TOKEN, ENV_TOKEN, env)
    want_agent = _meta(tool_call, META_AGENT_ID, ENV_AGENT_ID, env)
    want_provider = _meta(tool_call, META_PROVIDER, ENV_PROVIDER, env)

    if not token:
        err = GovernanceError(E_TOKEN_MISSING, f"服务 {service_name} 需要治理令牌，但未提供")
        _safe_record(
            audit.EVENT_UNAUTHORIZED,
            agent_id=want_agent,
            provider=want_provider,
            ok=False,
            code=err.code,
            detail={"service_name": service_name, "reason": "missing_token"},
            path=audit_path,
        )
        return _error_json("governance_required", err.code, err.message, service_name, service=service_name)

    try:
        verifier = authority or AuthorizationAuthority.from_env(environ=env)
        claims = verifier.verify(
            token,
            agent_id=want_agent or None,
            provider=want_provider or None,
            now=now,
        )
    except GovernanceError as err:
        _safe_record(
            audit.EVENT_UNAUTHORIZED,
            agent_id=want_agent,
            provider=want_provider,
            ok=False,
            code=err.code,
            detail={"service_name": service_name, "reason": "token_rejected", **err.detail},
            path=audit_path,
        )
        return _error_json("governance_denied", err.code, err.message, service_name, service=service_name)
    except Exception as exc:  # fail-closed：启用后治理层炸了也不许静默放行
        _safe_record(
            audit.EVENT_UNAUTHORIZED,
            agent_id=want_agent,
            ok=False,
            code=E_INTERNAL,
            detail={"service_name": service_name, "reason": "internal_error", "error": repr(exc)},
            path=audit_path,
        )
        return _error_json(
            "governance_internal_error",
            E_INTERNAL,
            f"治理层内部异常（fail-closed）: {exc}",
            service_name,
            service=service_name,
        )

    _safe_record(
        audit.EVENT_AGENT_CALL,
        agent_id=claims.agent_id,
        provider=claims.provider,
        ok=True,
        detail={"service_name": service_name, "exp": claims.exp},
        path=audit_path,
    )
    return None


def wrap_handler(
    service_name: str,
    handler: Callable[[dict[str, Any]], Any],
    *,
    environ: dict[str, str] | None = None,
    authority: AuthorizationAuthority | None = None,
    audit_path: Any = None,
) -> Callable[[dict[str, Any]], Any]:
    """给 agent 的 ``handle_handoff`` 包一层守卫（agent 侧 2 行接线的等价物）。

    被拒时**不调用** handler，直接返回结构化错误 JSON —— 与 ``unified_call`` 里
    hook 的语义一致，便于在 MCP 之外的入口复用同一套判定。
    """

    def _wrapped(tool_call: dict[str, Any]) -> Any:
        blocked = guard_dispatch(
            service_name,
            tool_call,
            environ=environ,
            authority=authority,
            audit_path=audit_path,
        )
        if blocked:
            return blocked
        return handler(tool_call)

    return _wrapped


def missing_key_error(var: str = "HERMES_AGENT_ID_KEY") -> str:
    """密钥缺失时的标准错误 JSON（供 CLI/agent 复用，避免各处手拼文案）。"""
    err = GovernanceError(E_MISSING_KEY, f"环境变量 {var} 未设置", env_var=var)
    return _error_json("governance_required", err.code, err.message, service_name="-")
