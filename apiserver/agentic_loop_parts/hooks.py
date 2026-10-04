"""调用门禁与生命周期钩子（卷190-A2：从 agentic_tool_loop.py 纯搬移）。"""
#!/usr/bin/env python3
"""
Agentic Tool Loop 核心引擎
实现单LLM agentic loop：模型在对话中发起工具调用，接收结果，再继续推理，直到不再需要工具。
"""

import asyncio
import base64
import ipaddress
import json
import logging
import mimetypes
import re
import socket
import time as _time
from collections.abc import AsyncGenerator
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx

from apiserver import naga_auth
from apiserver.agent_directory import format_agent_directory_text, resolve_agent_descriptor
from apiserver.tool_schemas import resolve_mcp_func_name
from system.config import get_config, get_data_dir, get_server_port

logger = logging.getLogger("apiserver.agentic_tool_loop")  # 保持原日志通道名
from .markers import *  # noqa: F401,F403


def _run_guard(call: dict[str, Any], session_id: str) -> dict[str, Any] | None:
    """W124-03 阶段①：guard 参数合法性校验（`file_write` 路径 / `code_exec` 语言 / manifest 声明）。

    被拒直接返回结构化错误（不写盘、不进 pre-execute）；guard 自身异常 fail-open。
    """
    try:
        from apiserver.event_bus.tool_pipeline import guard_tool

        tool_name = str(call.get("tool_name") or call.get("name") or "")
        if not tool_name:
            return None
        verdict = guard_tool(tool_name, dict(call))
        if not verdict:
            return None
    except Exception as e:  # noqa: BLE001
        logger.warning("[AgenticLoop] guard 校验异常，放行该次调用: %s", e)
        return None
    logger.warning("[AgenticLoop] 工具 %s 未通过 guard：%s", tool_name, verdict.get("reason"))
    return {
        "tool_call": call,
        "result": f"参数不合法（{verdict.get('error')}）：{verdict.get('reason')}",
        "status": "error",
        "service_name": str(call.get("service_name") or "guard"),
        "tool_name": tool_name,
        "attempts": 1,
    }



def _emit_post_execute(
    call: dict[str, Any], result: dict[str, Any], session_id: str, *, duration_s: float, ok: bool
) -> None:
    """W124-03 阶段④：post-execute 事实广播（审计 + 失败统计 + 正交字段）。"""
    try:
        from apiserver.event_bus.tool_pipeline import emit_post_execute

        tool_name = str(call.get("tool_name") or call.get("name") or "")
        emit_post_execute(
            tool=tool_name,
            args=dict(call),
            result=result,
            duration_s=duration_s,
            session_id=session_id,
            ok=ok,
        )
    except Exception as e:  # noqa: BLE001 - 广播失败不影响工具结果
        logger.debug("[AgenticLoop] post-execute 广播跳过: %s", e)



def _run_scope_gate(
    call: dict[str, Any], session_id: str, source_agent_id: str | None
) -> dict[str, Any] | None:
    """W124-01：执行层工具可见性校验（展示层过滤之外的第二道）。

    直接构造的调用（绕过 schema 展示）也必须被拦下，返回可直接回给模型的结果字典；
    放行返回 None。Scope 模块不可用时放行（fail-open，不破坏既有链路）。
    """
    try:
        from mcpserver import scope as scope_mod

        if not scope_mod.enabled():
            return None
        tool_name = str(call.get("_original_name") or call.get("tool_name") or call.get("name") or "")
        if not tool_name:
            return None
        names = scope_mod.candidate_names(
            tool_name,
            service_name=str(call.get("service_name") or ""),
            agent_type=str(call.get("agentType") or ""),
        )
        # 文本兼容期的调用只有短名，把「短名」也当别名一起判（见 candidate_names）
        short = str(call.get("tool_name") or "")
        if short and short != tool_name:
            names = list(dict.fromkeys([*names, *scope_mod.candidate_names(
                short,
                service_name=str(call.get("service_name") or ""),
                agent_type=str(call.get("agentType") or ""),
            )]))
        visible, reason = scope_mod.tool_visible_any(
            names, agent_id=source_agent_id, session_id=session_id
        )
        if visible:
            return None
    except Exception as e:  # noqa: BLE001 - Scope 异常不拦工具，但告警
        logger.warning("[AgenticLoop] Scope 校验异常，放行该次调用: %s", e)
        return None

    logger.warning("[AgenticLoop] 工具 %s 对角色不可见（%s），已拦截", tool_name, reason)
    return {
        "tool_call": call,
        "result": f"当前角色无权使用工具 {tool_name}（{reason}），请换一个做法或说明需求。",
        "status": "error",
        "service_name": str(call.get("service_name") or "scope"),
        "tool_name": tool_name,
        "attempts": 1,
    }



async def _run_tool_gate(
    call: dict[str, Any], session_id: str, source_agent_id: str | None
) -> dict[str, Any] | None:
    """W119-03：工具执行前过 TOOL_PRE_EXECUTE waterfall 安全门。

    Returns:
        被 veto 时返回可直接回给模型的结果字典；放行返回 None。
    """
    try:
        from apiserver.event_bus import Topics, get_bus
        from apiserver.event_bus.tool_gate import get_tool_gate_runtime

        runtime = get_tool_gate_runtime()
        if not runtime.enabled:
            return None
        tool_name = str(call.get("tool_name") or call.get("name") or "")
        gate_event = {
            "tool": tool_name,
            "agent_type": call.get("agentType", ""),
            "session_id": session_id,
            "agent_id": source_agent_id,
            "args": {k: v for k, v in call.items() if not k.startswith("_")},
        }
        verdict = get_bus().waterfall(Topics.TOOL_PRE_EXECUTE, gate_event, final=lambda: None)
    except Exception as e:  # noqa: BLE001 - 安全门自身异常不拦工具（fail-open）并告警
        logger.warning("[AgenticLoop] 工具安全门异常，放行该次调用: %s", e)
        return None

    if isinstance(verdict, dict) and verdict.get("veto"):
        tool_name = str(call.get("tool_name") or call.get("name") or "")
        logger.warning("[AgenticLoop] 工具被安全门拦截: %s（%s）", tool_name, verdict.get("reason"))
        blocked: dict[str, Any] = {
            "tool_call": call,
            "result": str(verdict.get("reason") or "工具被策略拦截"),
            "status": "error",
            "service_name": str(call.get("agentType") or "tool_gate"),
            "tool_name": tool_name,
        }
        # W121-03：确认门附带待确认信息 → 透传给前端做确认卡片
        if isinstance(verdict.get("pending_confirm"), dict):
            blocked["pending_confirm"] = verdict["pending_confirm"]
        return blocked
    return None

__all__ = ['_emit_post_execute', '_run_guard', '_run_scope_gate', '_run_tool_gate']

# ruff: noqa: F405  # 薄壳模式：星号聚合导入的公共名（导出面由 tools/verify_export_parity.py 钉住）
