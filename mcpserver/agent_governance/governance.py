"""MCP agent 适配层 —— 把身份/授权/审计三件套暴露成可路由工具（工单 241）。

形态对齐 ``mcpserver/agent_signing/agent_signing.py``：模块级 ``handle_handoff(task)``
+ 类方法委托，``task = {"tool": ..., "params": {...}}``，返回值是 JSON **字符串**。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from mcpserver.agent_governance import audit
from mcpserver.agent_governance.authorization import AuthorizationAuthority
from mcpserver.agent_governance.errors import E_MISSING_KEY, GovernanceError
from mcpserver.agent_governance.identity import ENV_ID_KEY, IdentitySigner

KEY_PARAM = "key"


def _ok(message: str, data: Any) -> dict[str, Any]:
    return {"status": "ok", "message": message, "data": data}


def _error(err: GovernanceError) -> dict[str, Any]:
    return {"status": "error", "message": err.message, **err.to_dict()}


class AgentGovernance:
    """治理 agent：签名 / 验签 / 发令牌 / 验令牌 / 审计读写。"""

    def __init__(
        self,
        key: str | bytes | None = None,
        *,
        ttl_s: int = 0,
        audit_path: Path | str | None = None,
    ) -> None:
        self._explicit_key = key
        self._ttl_s = ttl_s or None
        self._audit_path = audit_path

    # ------------------------------------------------------------------ 密钥
    def _key(self, params: dict[str, Any]) -> bytes:
        """密钥优先级：params["key"]（显式，便于测试/调试）→ 环境变量。都没有则抛错。"""
        raw = params.get(KEY_PARAM) or self._explicit_key or os.environ.get(ENV_ID_KEY, "")
        if not raw:
            raise GovernanceError(E_MISSING_KEY, f"未提供密钥：params['{KEY_PARAM}'] 与 {ENV_ID_KEY} 均为空")
        return raw if isinstance(raw, bytes) else raw.encode("utf-8")

    def _signer(self, params: dict[str, Any]) -> IdentitySigner:
        return IdentitySigner(self._key(params))

    def _authority(self, params: dict[str, Any]) -> AuthorizationAuthority:
        kwargs: dict[str, Any] = {}
        if self._ttl_s:
            kwargs["ttl_s"] = self._ttl_s
        return AuthorizationAuthority(self._key(params), **kwargs)

    # ------------------------------------------------------------------ 工具
    def sign_output(self, params: dict[str, Any]) -> dict[str, Any]:
        envelope = self._signer(params).sign(
            str(params.get("agent_id", "")),
            str(params.get("provider", "")),
            model=str(params.get("model", "")),
            content=params.get("content", ""),
        )
        return _ok("已签名", envelope.to_dict())

    def verify_output(self, params: dict[str, Any]) -> dict[str, Any]:
        try:
            envelope = self._signer(params).verify(params.get("envelope"), params.get("content", ""))
        except GovernanceError as err:
            audit.record(
                audit.EVENT_IDENTITY_REJECTED,
                agent_id=str(params.get("agent_id", "")),
                ok=False,
                code=err.code,
                detail={"reason": "verify_output"},
                path=self._audit_path,
            )
            return _error(err)
        return _ok("验签通过", envelope.to_dict())

    def issue_token(self, params: dict[str, Any]) -> dict[str, Any]:
        ttl = params.get("ttl_s")
        token = self._authority(params).issue(
            str(params.get("agent_id", "")),
            str(params.get("provider", "")),
            ttl_s=None if ttl is None else int(ttl),
        )
        return _ok("已签发令牌", {"token": token})

    def verify_token(self, params: dict[str, Any]) -> dict[str, Any]:
        agent_id = params.get("agent_id") or None
        provider = params.get("provider") or None
        try:
            claims = self._authority(params).verify(
                str(params.get("token", "")),
                agent_id=agent_id,
                provider=provider,
            )
        except GovernanceError as err:
            audit.record_unauthorized(
                err.code,
                agent_id=params.get("agent_id"),
                provider=params.get("provider"),
                detail={"reason": "verify_token"},
                path=self._audit_path,
            )
            return _error(err)
        return _ok("令牌有效", claims.to_dict())

    def audit_record(self, params: dict[str, Any]) -> dict[str, Any]:
        rec = audit.record(
            str(params.get("event", audit.EVENT_AGENT_CALL)),
            agent_id=params.get("agent_id"),
            provider=params.get("provider"),
            model=params.get("model"),
            ok=bool(params.get("ok", True)),
            code=params.get("code"),
            detail=params.get("detail"),
            path=self._audit_path,
        )
        return _ok("已记录", rec)

    def audit_tail(self, params: dict[str, Any]) -> dict[str, Any]:
        limit = int(params.get("limit", 10))
        events = audit.tail(self._audit_path, n=limit)
        return _ok(f"最近 {len(events)} 条", {"events": events, "path": str(audit.resolve_audit_path())})

    def audit_count(self, params: dict[str, Any]) -> dict[str, Any]:
        event = params.get("event") or None
        return _ok("统计完成", {"count": audit.count_events(self._audit_path, event=event), "event": event})

    # ------------------------------------------------------------------ 入口
    async def handle_handoff(self, task: dict) -> str:
        """类方法入口（对齐主仓 agent 约定）；委托模块级 ``handle_handoff``。"""
        return await handle_handoff(task)


DISPATCH: dict[str, str] = {
    "sign_output": "sign_output",
    "verify_output": "verify_output",
    "issue_token": "issue_token",
    "verify_token": "verify_token",
    "audit_record": "audit_record",
    "audit_tail": "audit_tail",
    "audit_count": "audit_count",
}


async def handle_handoff(task: dict) -> str:
    """入口：``{"tool": "...", "params": {...}}`` → JSON 字符串。

    任何异常都被收敛成结构化错误 JSON —— MCP 路由层不该看到裸异常。
    """
    tool = str((task or {}).get("tool", ""))
    params = (task or {}).get("params") or {}
    agent = AgentGovernance()
    method_name = DISPATCH.get(tool)
    if method_name is None:
        return json.dumps(
            {"status": "error", "error_type": "unknown_tool", "message": f"未知工具: {tool}", "available": sorted(DISPATCH)},
            ensure_ascii=False,
        )
    try:
        result = getattr(agent, method_name)(params)
    except GovernanceError as err:
        result = _error(err)
    except Exception as exc:  # 兜底：绝不把异常抛回 MCP 路由层
        result = {"status": "error", "error_type": "internal_error", "message": f"治理 agent 内部异常: {exc}"}
    return json.dumps(result, ensure_ascii=False)
