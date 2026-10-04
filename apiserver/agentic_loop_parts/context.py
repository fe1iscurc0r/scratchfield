"""上下文注入与步骤边界压缩（卷190-A2：从 agentic_tool_loop.py 纯搬移）。"""
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


def _current_step_type(session_id: str) -> str:
    """卷125 W125-01：取当前任务步骤类型（卷123 Goal Mode），供路由的 step_budget 用。"""
    try:
        from apiserver.task_flow import active_task, next_step

        task = active_task(session_id)
        if not task:
            return ""
        step = next_step(task)
        return str((step or {}).get("type") or "")
    except Exception:  # noqa: BLE001
        return ""



def _inject_skill_context(messages: list[dict[str, Any]], session_id: str) -> List[dict[str, Any]]:
    """卷124 W124-05：按本轮用户意图加载技能（SKILL.md）并注入 system 层。

    未命中 → **零注入**（不动 messages）。返回命中记录（供 SSE/回写）。
    """
    from system.config import merge_context_supplement

    try:
        from apiserver.skill_loader import build_skill_context, record_usage

        last_user = next((m for m in reversed(messages) if str(m.get("role")) == "user"), None)
        text = str((last_user or {}).get("content") or "")
        if not text.strip():
            return []
        context, records = build_skill_context(text, session_id=session_id)
        if not context:
            return []
        messages[:] = merge_context_supplement(messages, context)
        record_usage(records)
        logger.info("[AgenticLoop] 命中技能 %s（会话 %s）", [r["skill"] for r in records], session_id)
        return records
    except Exception as e:  # noqa: BLE001 - 技能加载失败不影响对话
        logger.debug("[AgenticLoop] 技能加载跳过: %s", e)
        return []



def _inject_task_context(messages: list[dict[str, Any]], session_id: str) -> str:
    """卷123 W123-02：把活动任务的目标/进度注入 system 层（并入 messages[0]，见合并说明）。

    无活动任务时，若用户这轮带 `goal:` / `目标：` 前缀，则注入目标模式提示（引导模型先出 [PLAN]）。

    Returns:
        注入的上下文文本（空串表示没有可注入内容）。
    """
    from system.config import merge_context_supplement

    context = ""
    try:
        from apiserver.task_flow import goal_from_messages, goal_mode_prompt, task_context_prompt

        context = task_context_prompt(session_id)
        if not context:
            goal = goal_from_messages(messages)
            if goal:
                from apiserver.task_flow import goal_from_text

                last_user = next((m for m in reversed(messages) if str(m.get("role")) == "user"), None)
                if goal_from_text(str((last_user or {}).get("content") or "")):
                    context = goal_mode_prompt(goal)
    except Exception as e:  # noqa: BLE001 - 任务上下文缺失不影响对话
        logger.debug("[AgenticLoop] 任务上下文注入跳过: %s", e)
        return ""
    if not context:
        return ""
    messages[:] = merge_context_supplement(messages, f"━━━━━━━━━━ 当前任务 ━━━━━━━━━━\n{context}")
    return context



def _compact_at_step_boundary(messages: list[dict[str, Any]], session_id: str) -> int:
    """卷123 W123-05：步骤边界压缩（保留 goal/当前步/关键结果，收敛历史工具结果）。

    Returns:
        收敛掉的消息条数（0 表示未动）。
    """
    try:
        from apiserver.task_flow import step_boundary_compact

        return step_boundary_compact(messages, session_id)
    except Exception as e:  # noqa: BLE001 - 压缩失败不影响对话
        logger.debug("[AgenticLoop] 步骤边界压缩跳过: %s", e)
        return 0



def _inject_session_id(call: dict[str, Any], session_id: str) -> None:
    """W121-04：给 manifest 里声明了 `session_id` 入参的 MCP 工具补上当前会话号。

    只在工具自己声明了这个参数时才注入——否则会把无关字段塞进其它 MCP 桥的入参
    （Code Workspace 的按会话子目录隔离就靠它）。
    """
    if not session_id or call.get("session_id"):
        return
    try:
        from mcpserver.mcp_registry import MANIFEST_CACHE

        manifest = MANIFEST_CACHE.get(str(call.get("service_name") or "")) or {}
        commands = (manifest.get("capabilities") or {}).get("invocationCommands") or []
        target = str(call.get("tool_name") or "")
        for cmd in commands:
            if str(cmd.get("command") or "") != target:
                continue
            props = (cmd.get("parameters") or {}).get("properties") or {}
            if "session_id" in props:
                call["session_id"] = session_id
            return
    except Exception as e:  # noqa: BLE001 - 注入失败不影响调用本身
        logger.debug("[AgenticLoop] session_id 注入跳过: %s", e)

__all__ = ['_compact_at_step_boundary', '_current_step_type', '_inject_session_id', '_inject_skill_context', '_inject_task_context']

# ruff: noqa: F405  # 薄壳模式：星号聚合导入的公共名（导出面由 tools/verify_export_parity.py 钉住）
