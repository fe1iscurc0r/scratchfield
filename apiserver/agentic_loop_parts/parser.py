"""文本 → 工具调用解析（含 native 格式转换）（卷190-A2：从 agentic_tool_loop.py 纯搬移）。"""
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

# ---------------------------------------------------------------------------
# 解析工具
# ---------------------------------------------------------------------------


def _normalize_fullwidth_json_chars(text: str) -> str:
    """将常见全角JSON相关字符归一化为ASCII"""
    if not text:
        return text
    translation_table = str.maketrans(
        {
            "｛": "{",
            "｝": "}",
            "：": ":",
            "，": ",",
            "\u201c": '"',
            "\u201d": '"',
            "\u2018": "'",
            "\u2019": "'",
        }
    )
    return text.translate(translation_table)



def _extract_json_objects(text: str) -> list[dict[str, Any]]:
    """从文本中提取所有顶层JSON对象（花括号深度匹配 + json5/json 解析 + agentType过滤）"""

    def _loads(s: str) -> Any:
        try:
            import json5 as _json5

            return _json5.loads(s)
        except Exception:
            return json.loads(s)

    objects: list[dict[str, Any]] = []
    start: int | None = None
    depth = 0

    for i, ch in enumerate(text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    candidate = text[start : i + 1].strip()
                    start = None
                    if candidate in ("{}", "{ }"):
                        continue
                    try:
                        parsed = _loads(candidate)
                    except Exception:
                        continue
                    if isinstance(parsed, dict):
                        objects.append(parsed)
                    elif isinstance(parsed, list):
                        for item in parsed:
                            if isinstance(item, dict):
                                objects.append(item)

    # 只保留含 agentType 字段的对象
    return [obj for obj in objects if isinstance(obj.get("agentType"), str) and obj["agentType"]]



def _extract_tool_blocks(text: str) -> tuple[str, list[dict[str, Any]]]:
    """从 ```tool``` 代码块中提取工具调用JSON。

    Returns:
        (clean_text, tool_calls) — clean_text 是移除代码块后的纯文本
    """

    tool_calls: list[dict[str, Any]] = []
    # 匹配 ```tool ... ``` 代码块（允许未闭合的尾部块用 \Z 兜底）
    # 注意: 用 [ \t]* 而非 \s* 避免吃掉换行符; 用 \Z 而非 $ 避免 MULTILINE 下提前匹配行尾
    pattern = re.compile(r"```tool[ \t]*\n([\s\S]*?)(?:```|\Z)")

    for match in pattern.finditer(text):
        block_content = match.group(1).strip()
        if not block_content:
            continue
        normalized = _normalize_fullwidth_json_chars(block_content)
        extracted = _extract_json_objects(normalized)
        tool_calls.extend(extracted)

    # 从文本中移除 ```tool...``` 代码块
    clean_text = pattern.sub("", text).strip()
    # 清理多余空行
    clean_text = re.sub(r"\n{3,}", "\n\n", clean_text)
    return clean_text, tool_calls



def _convert_special_tool_call_to_dispatch(tool_name: str, arguments: Any) -> list[dict[str, Any]]:
    args = arguments if isinstance(arguments, dict) else {"value": arguments}

    if tool_name == "web_search":
        queries = args.get("queries")
        if isinstance(queries, list):
            shared_args = {k: v for k, v in args.items() if k != "queries"}
            dispatches: list[dict[str, Any]] = []
            for query in queries:
                if not isinstance(query, str) or not query.strip():
                    continue
                dispatch_args = dict(shared_args)
                dispatch_args["query"] = query.strip()
                dispatches.append({
                    "agentType": "tool",
                    "tool_name": "web_search",
                    "args": dispatch_args,
                })
            if dispatches:
                return dispatches

    return [{
        "agentType": "tool",
        "tool_name": tool_name,
        "args": args,
    }]



def _extract_special_tool_calls(text: str) -> tuple[str, list[dict[str, Any]]]:
    """提取 Kimi/OpenAI 兼容层泄露出的特殊工具调用语法。"""
    if _TOOL_CALL_BEGIN not in text:
        return text, []

    decoder = json.JSONDecoder()
    tool_calls: list[dict[str, Any]] = []
    clean_parts: list[str] = []
    cursor = 0

    while True:
        start = text.find(_TOOL_CALL_BEGIN, cursor)
        if start < 0:
            clean_parts.append(text[cursor:])
            break

        section_start = text.rfind(_TOOL_SECTION_BEGIN, cursor, start)
        clean_parts.append(text[cursor:section_start if section_start >= 0 else start])

        name_start = start + len(_TOOL_CALL_BEGIN)
        colon = text.find(":", name_start)
        arg_start = text.find(_TOOL_CALL_ARG_BEGIN, colon if colon >= 0 else name_start)
        if colon < 0 or arg_start < 0:
            clean_parts.append(text[start:])
            break

        tool_name = text[name_start:colon].strip()
        json_start = arg_start + len(_TOOL_CALL_ARG_BEGIN)

        try:
            arguments, consumed = decoder.raw_decode(text[json_start:])
        except JSONDecodeError:
            logger.warning("[AgenticLoop] 无法解析特殊工具调用 JSON，保留原始文本")
            clean_parts.append(text[start:])
            break

        tool_calls.extend(_convert_special_tool_call_to_dispatch(tool_name, arguments))

        end = text.find(_TOOL_CALL_END, json_start + consumed)
        if end < 0:
            cursor = json_start + consumed
        else:
            cursor = end + len(_TOOL_CALL_END)
            if text.startswith(_TOOL_SECTION_END, cursor):
                cursor += len(_TOOL_SECTION_END)

    clean_text = "".join(clean_parts).strip()
    clean_text = re.sub(r"\n{3,}", "\n\n", clean_text)
    return clean_text, tool_calls



def parse_tool_calls_from_text(text: str) -> tuple[str, list[dict[str, Any]]]:
    """从LLM完整输出中提取所有工具调用JSON。

    优先从 ```tool``` 代码块提取，回退到裸JSON行提取（向后兼容）。

    Returns:
        (clean_text, tool_calls) — clean_text 是去掉工具调用后的纯文本
    """
    # 优先使用 ```tool``` 代码块
    clean_text, tool_calls = _extract_tool_blocks(text)
    if tool_calls:
        return clean_text, tool_calls

    clean_text, tool_calls = _extract_special_tool_calls(text)
    if tool_calls:
        return clean_text, tool_calls

    # 回退：从裸文本中提取含 agentType 的JSON对象（向后兼容）
    normalized = _normalize_fullwidth_json_chars(text)
    tool_calls = _extract_json_objects(normalized)

    if not tool_calls:
        return text, []

    # 从原始文本中移除工具调用JSON所在的行
    clean_lines = []
    for line in text.split("\n"):
        norm_line = _normalize_fullwidth_json_chars(line.strip())
        if norm_line:
            extracted = _extract_json_objects(norm_line)
            if extracted:
                continue  # 跳过包含工具调用的行
        clean_lines.append(line)

    clean_text = "\n".join(clean_lines).strip()
    return clean_text, tool_calls



# ---------------------------------------------------------------------------
# Native Function Calling → Dispatch 格式转换
# ---------------------------------------------------------------------------


def _convert_native_to_dispatch(native_calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """将 OpenAI function call 格式转换为现有 dispatch 格式

    命名约定: {agentType}__{service_name}__{tool_name}
    - tool__web_search → agentType="tool", tool_name="web_search"
    - mcp__weather_time__today_weather → agentType="mcp", service_name="weather_time", tool_name="today_weather"
    - openclaw__agent → agentType="openclaw", task_type="message"
    - live2d__action → agentType="live2d"
    - naga_control__command → agentType="naga_control"

    MCP 工具名在生成时可能被 sanitize（service_name/command 含中文等非法字符），
    故优先用 resolve_mcp_func_name() 反查还原原始名，查不到再 fallback 到 split。
    """
    result = []
    for call in native_calls:
        name = call.get("name", "")
        raw_args = call.get("arguments", "{}")
        try:
            args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
        except (json.JSONDecodeError, TypeError):
            args = {}

        parts = name.split("__", 2)
        agent_type = parts[0]

        dispatch: dict[str, Any] = {"agentType": agent_type}

        if agent_type == "openclaw_tool" and len(parts) >= 2:
            # 兼容旧格式
            dispatch["agentType"] = "tool"
            dispatch["tool_name"] = parts[1]
            dispatch["args"] = args
        elif agent_type == "tool" and len(parts) >= 2:
            dispatch["tool_name"] = parts[1]
            dispatch["args"] = args
        elif agent_type == "mcp" and len(parts) >= 3:
            # 优先用反查映射还原原始 service_name/command（function name 可能被 sanitize 过）
            resolved = resolve_mcp_func_name(name)
            if resolved is not None:
                dispatch["service_name"], dispatch["tool_name"] = resolved
            else:
                dispatch["service_name"] = parts[1]
                dispatch["tool_name"] = parts[2]
            # MCP 工具参数直接展开到 dispatch 顶层（与现有格式一致）
            dispatch.update(args)
        elif agent_type == "openclaw":
            dispatch["task_type"] = "message"
            dispatch.update(args)
        elif agent_type == "live2d" or agent_type == "naga_control":
            dispatch.update(args)
        else:
            dispatch.update(args)

        # 保存原始信息用于 tool message 回注
        dispatch["_tool_call_id"] = call.get("id", "")
        dispatch["_original_name"] = name
        dispatch["_original_args"] = raw_args if isinstance(raw_args, str) else json.dumps(args, ensure_ascii=False)

        result.append(dispatch)
    return result



def _build_native_assistant_message(
    clean_text: str,
    calls: list[dict[str, Any]],
    reasoning_content: str = "",
) -> dict[str, Any]:
    """构造 OpenAI 兼容的 assistant tool_calls 历史消息。"""
    assistant_msg: dict[str, Any] = {
        "role": "assistant",
        "content": clean_text or None,
        "tool_calls": [
            {
                "id": c.get("_tool_call_id", f"call_{i}"),
                "type": "function",
                "function": {
                    "name": c.get("_original_name", ""),
                    "arguments": c.get("_original_args", "{}"),
                },
            }
            for i, c in enumerate(calls)
        ],
    }
    if reasoning_content.strip():
        assistant_msg["reasoning_content"] = reasoning_content
    return assistant_msg

__all__ = ['_build_native_assistant_message', '_convert_native_to_dispatch', '_convert_special_tool_call_to_dispatch', '_extract_json_objects', '_extract_special_tool_calls', '_extract_tool_blocks', '_normalize_fullwidth_json_chars', 'parse_tool_calls_from_text']

# ruff: noqa: F405  # 薄壳模式：星号聚合导入的公共名（导出面由 tools/verify_export_parity.py 钉住）
