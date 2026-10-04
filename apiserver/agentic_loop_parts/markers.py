"""标记常量与结果口径（迭代控制基础设施）（卷190-A2：从 agentic_tool_loop.py 纯搬移）。"""
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


_TOOL_SECTION_BEGIN = "<|tool_calls_section_begin|>"

_TOOL_SECTION_END = "<|tool_calls_section_end|>"

_TOOL_CALL_BEGIN = "<|tool_call_begin|>functions."

_TOOL_CALL_ARG_BEGIN = "<|tool_call_argument_begin|>"

_TOOL_CALL_END = "<|tool_call_end|>"


# ---------------------------------------------------------------------------
# W121-02：迭代控制（步数上限 / 失败重试 / 收敛摘要）
# ---------------------------------------------------------------------------

#: 可重试的失败特征（瞬时/环境类）× 工具无关
_RETRYABLE_MARKERS = (
    "timeout", "超时", "timed out",
    "connection", "连接", "network", "网络",
    "temporarily", "暂时", "rate limit", "429", "502", "503", "504",
    "执行异常", "internalservererror", "server error",
)


#: 不可重试的失败特征（策略/权限/参数类）——重试只会重复被拒
_PERMANENT_MARKERS = (
    "hard_denied", "not_allowlisted", "shell_metachar_denied",
    "path_traversal_denied", "absolute_path_denied", "path_escape_denied",
    "unsupported_language", "invalid_argument", "参数",
    "等待用户确认", "用户拒绝", "被安全门拦截", "熔断", "已禁用", "权限",
)



def _loop_config() -> Any:
    """读取 `agent_loop` 配置；配置不可用时返回 None（各调用点用内置默认）。"""
    try:
        return get_config().agent_loop
    except Exception as e:  # noqa: BLE001
        logger.debug("[AgenticLoop] 读取 agent_loop 配置失败，用默认值: %s", e)
        return None



#: MCP 桥返回体里的错误标记（`{"status": "error", "message": ...}`）
_MCP_PAYLOAD_ERROR_RE = re.compile(r'["\']?status["\']?\s*:\s*["\']?error', re.IGNORECASE)



def _effective_status(result: dict[str, Any]) -> str:
    """工具结果的真实状态。

    MCP 桥把业务错误包在返回体里（`{"status": "error", ...}`），而 dispatch 层对 MCP 调用
    一律标 `status=success`——只看外层会让「本轮全失败」「重试」这类判断失真。
    这里对 MCP 返回体做一次错判修正，仅用于本卷的失败检测/重试/展示口径，
    W119 熔断与指标的 ok 语义不变。
    """
    outer = str(result.get("status") or "")
    if outer == "error":
        return "error"
    if _MCP_PAYLOAD_ERROR_RE.search(str(result.get("result") or "")[:2000]):
        return "error"
    return outer or "unknown"



def _retryable_failure(result: dict[str, Any]) -> bool:
    """判断一次失败的工具调用是否值得重试（策略类拒绝一律不重试）。"""
    if _effective_status(result) != "error":
        return False
    text = str(result.get("result") or "").lower()
    if any(marker in text for marker in _PERMANENT_MARKERS):
        return False
    return any(marker in text for marker in _RETRYABLE_MARKERS)



def _step_entry(round_num: int, call: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """记录一步（供收敛摘要使用）：谁、在哪一轮、成没成、结果摘要。"""
    service = str(result.get("service_name") or call.get("agentType") or "tool")
    tool = str(result.get("tool_name") or call.get("tool_name") or "")
    label = f"{service}:{tool}" if tool and tool not in service else service
    summary = re.sub(r"\s+", " ", str(result.get("result") or ""))[:200]
    return {
        "round": round_num,
        "label": label,
        "status": _effective_status(result),
        "attempts": int(result.get("attempts") or 1),
        "summary": summary,
    }

__all__ = ['_MCP_PAYLOAD_ERROR_RE', '_PERMANENT_MARKERS', '_RETRYABLE_MARKERS', '_TOOL_CALL_ARG_BEGIN', '_TOOL_CALL_BEGIN', '_TOOL_CALL_END', '_TOOL_SECTION_BEGIN', '_TOOL_SECTION_END', '_effective_status', '_loop_config', '_retryable_failure', '_step_entry']

# ruff: noqa: F405  # 薄壳模式：星号聚合导入的公共名（导出面由 tools/verify_export_parity.py 钉住）
