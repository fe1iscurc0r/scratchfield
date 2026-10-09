"""openclaw 通道执行器（客户端池 / 健康检查 / 会话工具）（卷190-A2：从 agentic_tool_loop.py 纯搬移）。"""
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
import threading

# ---------------------------------------------------------------------------
# OpenClaw 共享客户端与可用性预检
# ---------------------------------------------------------------------------

_shared_openclaw_client: httpx.AsyncClient | None = None
_shared_openclaw_client_lock = threading.Lock()



def _get_openclaw_client() -> httpx.AsyncClient:
    """获取或创建共享的 httpx 客户端（避免每次调用都新建连接）。

    工单222 任务三：并发首建加锁，防重复建连/连接泄漏。
    """
    global _shared_openclaw_client
    if _shared_openclaw_client is None or _shared_openclaw_client.is_closed:
        with _shared_openclaw_client_lock:
            if _shared_openclaw_client is None or _shared_openclaw_client.is_closed:
                _shared_openclaw_client = httpx.AsyncClient(
                    timeout=httpx.Timeout(timeout=150.0, connect=10.0),
                    proxy=None,  # localhost 请求不走系统代理
                )
    return _shared_openclaw_client



_openclaw_available: bool | None = None

_openclaw_check_time: float = 0.0

_OPENCLAW_CHECK_TTL = 30.0

_openclaw_start_attempted: bool = False  # 每次进程生命周期内只自动启动一次



async def _check_openclaw_available() -> bool:
    """检查 OpenClaw 服务是否可用，不可用时尝试自动启动"""
    global _openclaw_available, _openclaw_check_time, _openclaw_start_attempted
    now = _time.monotonic()
    if _openclaw_available is not None and (now - _openclaw_check_time) < _OPENCLAW_CHECK_TTL:
        return _openclaw_available

    agent_base = f"http://localhost:{get_server_port('agent_server')}"
    client = _get_openclaw_client()

    _openclaw_available = await _probe_openclaw_health(client, agent_base)

    # 不可用且还没尝试过自动启动 → 启动一次
    if not _openclaw_available and not _openclaw_start_attempted:
        _openclaw_start_attempted = True
        logger.info("[AgenticLoop] OpenClaw gateway 不可用，尝试自动启动...")
        try:
            resp = await client.post(f"{agent_base}/openclaw/gateway/start", timeout=45.0)
            if resp.status_code == 200:
                start_result = resp.json()
                # start_gateway 内部已经等待并检查了连通性
                if start_result.get("success"):
                    logger.info("[AgenticLoop] OpenClaw gateway 启动成功")
                    # 再确认一次 health
                    _openclaw_available = await _probe_openclaw_health(client, agent_base)
                    if not _openclaw_available:
                        # start 说成功但 health 还没好，短暂等待
                        await asyncio.sleep(2)
                        _openclaw_available = await _probe_openclaw_health(client, agent_base)
                else:
                    msg = start_result.get("message", "未知原因")
                    logger.warning(f"[AgenticLoop] OpenClaw gateway 启动失败: {msg}")
            else:
                logger.warning(f"[AgenticLoop] OpenClaw gateway 启动请求失败: HTTP {resp.status_code}")
        except Exception as e:
            logger.warning(f"[AgenticLoop] OpenClaw gateway 自动启动异常: {e}")

    _openclaw_check_time = _time.monotonic()
    return _openclaw_available



async def _probe_openclaw_health(client: httpx.AsyncClient, agent_base: str) -> bool:
    """探测 OpenClaw gateway 是否健康"""
    try:
        resp = await client.get(f"{agent_base}/openclaw/health", timeout=3.0)
        data = resp.json()
        return (
            resp.status_code == 200
            and data.get("success", False)
            and data.get("health", {}).get("status") == "healthy"
        )
    except Exception:
        return False



async def _execute_openclaw_call(call: dict[str, Any], session_id: str) -> dict[str, Any]:
    """执行单个OpenClaw调用（Agent 模式，通过 /hooks/agent 走二次 LLM）"""
    message = call.get("message", "")
    task_type = call.get("task_type", "message")

    if not message:
        return {
            "tool_call": call,
            "result": "缺少message字段",
            "status": "error",
            "service_name": "openclaw",
            "tool_name": task_type,
        }

    if not await _check_openclaw_available():
        return {
            "tool_call": call,
            "result": "OpenClaw 服务当前不可用，请稍后重试",
            "status": "error",
            "service_name": "openclaw",
            "tool_name": task_type,
        }

    payload = {
        "message": message,
        "session_key": call.get("session_key", f"naga_{session_id}"),
        "name": "Naga",
        "wake_mode": "now",
        "timeout_seconds": 120,
    }

    if task_type == "cron" and call.get("schedule"):
        payload["message"] = f"[定时任务 cron: {call.get('schedule')}] {message}"
    elif task_type == "reminder" and call.get("at"):
        payload["message"] = f"[提醒 在 {call.get('at')} 后] {message}"

    try:
        client = _get_openclaw_client()
        response = await client.post(
            f"http://localhost:{get_server_port('agent_server')}/openclaw/send",
            json=payload,
        )
        if response.status_code == 200:
            result_data = response.json()
            # 先检查 agent_server 返回的 success 标记
            if not result_data.get("success", True):
                error_msg = result_data.get("error") or "OpenClaw任务执行失败"
                return {
                    "tool_call": call,
                    "result": f"联网搜索失败: {error_msg}",
                    "status": "error",
                    "service_name": "openclaw",
                    "tool_name": task_type,
                }
            # agent_server 返回两个字段：replies(列表，异步轮询时填充) 和 reply(字符串，同步完成时填充)
            replies = result_data.get("replies") or []
            if replies:
                combined = "\n".join(replies)
            elif result_data.get("reply"):
                combined = result_data["reply"]
            else:
                combined = "任务已提交，暂无返回结果"
            return {
                "tool_call": call,
                "result": combined,
                "status": "success",
                "service_name": "openclaw",
                "tool_name": task_type,
            }
        else:
            return {
                "tool_call": call,
                "result": f"HTTP {response.status_code}: {response.text[:200]}",
                "status": "error",
                "service_name": "openclaw",
                "tool_name": task_type,
            }
    except Exception as e:
        logger.error(f"[AgenticLoop] OpenClaw调用失败: {e}")
        return {
            "tool_call": call,
            "result": f"调用失败: {e}",
            "status": "error",
            "service_name": "openclaw",
            "tool_name": task_type,
        }



# Gateway 可直接调用的工具（/tools/invoke），其余为 agent-session 工具需走 /hooks/agent
_GATEWAY_DIRECT_TOOLS = frozenset({
    "web_search", "web_fetch", "browser",
    "memory_search", "memory_get",
    "sessions_list", "sessions_history", "session_status",
    "agents_list", "cron", "message", "tts", "canvas", "nodes",
})



async def _execute_openclaw_tool_call(
    call: dict[str, Any],
    source_agent_id: str | None = None,
) -> dict[str, Any]:
    """调用 OpenClaw 工具。
    Gateway 级工具直接走 /tools/invoke；
    agent-session 级工具（exec/read/write 等）走 /hooks/agent 让 agent 代执行。
    """
    tool_name = call.get("tool_name", "")
    tool_args = call.get("args", {})

    if not tool_name:
        return {
            "tool_call": call, "result": "缺少 tool_name",
            "status": "error", "service_name": "openclaw_tool", "tool_name": "unknown",
        }

    # web_search: 已登录走陆墨代理，未登录有 key 走 Brave，都没有走 OpenClaw
    if tool_name == "web_search":
        if naga_auth.is_authenticated():
            return await _execute_search_tool(call)
        cfg = get_config()
        if cfg.online_search.search_api_key:
            return await _execute_brave_search(call)

    # neko_cua: 陆墨 agent 决策 → NEKO CUA/浏览器执行（M4 桥接，Bearer 鉴权 + fail-safe）
    if tool_name == "neko_cua":
        from apiserver.neko_cua import run_neko_action
        action = tool_args.get("action", "computer_use")
        payload = tool_args.get("payload", {})
        result = await run_neko_action(action, payload)
        return {
            "tool_call": call,
            "result": result,
            "status": "success" if result.get("success") else "error",
            "service_name": "neko_cua",
            "tool_name": tool_name,
        }

    # 本地可执行工具：直接在本机执行，不经过 OpenClaw agent session
    if tool_name in _LOCAL_EXEC_TOOLS:
        return await _execute_local_tool(call, tool_name, tool_args, source_agent_id=source_agent_id)

    # memory_search / memory_get：由本机 memory_maas 承接。
    # 原实现直连 OpenClaw 网关，而网关未安装 memory 插件（实测日志
    # 「[OpenClaw] 调用工具: memory_search → 工具不可用」），必然失败。
    if tool_name in ("memory_search", "memory_get"):
        return await _execute_memory_tool(call, tool_name, tool_args)

    if not await _check_openclaw_available():
        return {
            "tool_call": call, "result": "OpenClaw 服务当前不可用，请稍后重试",
            "status": "error", "service_name": "openclaw_tool", "tool_name": tool_name,
        }

    try:
        client = _get_openclaw_client()
        t0 = _time.monotonic()
        response = await client.post(
            f"http://localhost:{get_server_port('agent_server')}/openclaw/tools/invoke",
            json={"tool": tool_name, "args": tool_args},
        )
        elapsed = _time.monotonic() - t0
        if response.status_code == 200:
            result_data = response.json()
            # 先检查 agent_server 层面的 success 标记（如 tool_not_found）
            if not result_data.get("success", True):
                error_msg = result_data.get("error") or result_data.get("detail") or "工具调用失败"
                logger.error(f"[AgenticLoop] OpenClaw工具返回失败: {tool_name}, error={error_msg}")
                return {
                    "tool_call": call, "result": f"调用失败: {error_msg}",
                    "status": "error", "service_name": "openclaw_tool", "tool_name": tool_name,
                }
            # agent_server 返回 { success: true, result: { ok, result: { content: [...] } } }
            # invoke_tool 包了一层，需解开两层 result 才能到 OpenClaw 的原始工具输出
            result_content = result_data.get("result", result_data)
            if isinstance(result_content, dict) and "result" in result_content:
                result_content = result_content["result"]

            # 检查 OpenClaw 工具级别的错误（isError 标记 或 error 字段）
            if isinstance(result_content, dict) and (result_content.get("isError") or "error" in result_content):
                readable = _extract_openclaw_tool_result(result_content)
                logger.error(f"[AgenticLoop] OpenClaw工具错误: {tool_name}, result={readable[:300]}")
                return {
                    "tool_call": call, "result": f"工具执行错误: {readable}",
                    "status": "error", "service_name": "openclaw_tool", "tool_name": tool_name,
                }

            readable = _extract_openclaw_tool_result(result_content)

            # 检测嵌套在 content text 中的 JSON 错误（如 {"error": "missing_brave_api_key", ...}）
            if readable.lstrip().startswith("{"):
                try:
                    parsed = json.loads(readable)
                    if isinstance(parsed, dict) and "error" in parsed:
                        error_msg = parsed.get("message") or str(parsed["error"])
                        logger.error(f"[AgenticLoop] OpenClaw工具错误: {tool_name}, error={error_msg}")
                        return {
                            "tool_call": call, "result": f"工具执行错误: {error_msg}",
                            "status": "error", "service_name": "openclaw_tool", "tool_name": tool_name,
                        }
                except (json.JSONDecodeError, TypeError):
                    pass

            logger.info(f"[AgenticLoop] OpenClaw直接工具调用完成: {tool_name} 耗时 {elapsed:.2f}s, 结果长度={len(readable)}")
            logger.info(f"[AgenticLoop] OpenClaw工具结果预览: {readable[:300]}")
            return {
                "tool_call": call, "result": readable,
                "status": "success", "service_name": "openclaw_tool", "tool_name": tool_name,
            }
        else:
            logger.error(f"[AgenticLoop] OpenClaw直接工具调用HTTP错误: {tool_name}, status={response.status_code}, body={response.text[:200]}")
            return {
                "tool_call": call, "result": f"调用失败: HTTP {response.status_code} - {response.text[:200]}",
                "status": "error", "service_name": "openclaw_tool", "tool_name": tool_name,
            }
    except Exception as e:
        logger.error(f"[AgenticLoop] OpenClaw直接工具调用失败: {tool_name}, error={e}")
        return {
            "tool_call": call, "result": f"调用异常: {e}",
            "status": "error", "service_name": "openclaw_tool", "tool_name": tool_name,
        }



async def _execute_openclaw_session_tool(
    call: dict[str, Any], tool_name: str, tool_args: dict[str, Any]
) -> dict[str, Any]:
    """通过 agent session (/hooks/agent) 执行需要 OpenClaw agent 的工具。"""
    args_str = json.dumps(tool_args, ensure_ascii=False) if tool_args else ""
    instruction = f"请直接使用 {tool_name} 工具执行以下操作，只返回工具执行结果：\n{args_str}"

    payload = {
        "message": instruction,
        "session_key": f"naga_tool_{tool_name}",
        "name": "Naga",
        "wake_mode": "now",
        "timeout_seconds": 120,
    }

    try:
        client = _get_openclaw_client()
        response = await client.post(
            f"http://localhost:{get_server_port('agent_server')}/openclaw/send",
            json=payload,
        )
        if response.status_code == 200:
            result_data = response.json()
            if not result_data.get("success", True):
                error_msg = result_data.get("error") or "agent 会话执行失败"
                return {
                    "tool_call": call, "result": f"调用失败: {error_msg}",
                    "status": "error", "service_name": "openclaw_tool", "tool_name": tool_name,
                }
            replies = result_data.get("replies") or []
            reply = "\n".join(replies) if replies else (result_data.get("reply") or "任务已提交，暂无返回结果")
            return {
                "tool_call": call, "result": reply,
                "status": "success", "service_name": "openclaw_tool", "tool_name": tool_name,
            }
        else:
            return {
                "tool_call": call, "result": f"HTTP {response.status_code}: {response.text[:200]}",
                "status": "error", "service_name": "openclaw_tool", "tool_name": tool_name,
            }
    except Exception as e:
        logger.error(f"[AgenticLoop] OpenClaw session工具调用失败: {tool_name}, error={e}")
        return {
            "tool_call": call, "result": f"调用异常: {e}",
            "status": "error", "service_name": "openclaw_tool", "tool_name": tool_name,
        }



def _extract_openclaw_tool_result(result: Any) -> str:
    """从 OpenClaw /tools/invoke 返回值中提取可读文本"""
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        # 标准格式: { content: [{ type: "text", text: "..." }] }
        content = result.get("content", [])
        if isinstance(content, list) and content:
            texts = []
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        texts.append(item.get("text", ""))
                    elif "text" in item:
                        texts.append(str(item["text"]))
                elif isinstance(item, str):
                    texts.append(item)
            if texts:
                return "\n".join(texts)
        # 备选: 直接有 text 字段
        if "text" in result:
            return str(result["text"])
        # 备选: 有 error/message 字段（OpenClaw 错误响应）
        if "error" in result:
            return f"错误: {result['error']}"
        if "message" in result:
            return str(result["message"])
        # 兜底: JSON dump
        return json.dumps(result, ensure_ascii=False)
    if isinstance(result, list):
        # 直接是 content 数组
        texts = []
        for item in result:
            if isinstance(item, dict) and item.get("type") == "text":
                texts.append(item.get("text", ""))
            elif isinstance(item, str):
                texts.append(item)
        return "\n".join(texts) if texts else json.dumps(result, ensure_ascii=False)
    return str(result)

__all__ = ['_GATEWAY_DIRECT_TOOLS', '_OPENCLAW_CHECK_TTL', '_check_openclaw_available', '_execute_openclaw_call', '_execute_openclaw_session_tool', '_execute_openclaw_tool_call', '_extract_openclaw_tool_result', '_get_openclaw_client', '_openclaw_available', '_openclaw_check_time', '_openclaw_start_attempted', '_probe_openclaw_health', '_shared_openclaw_client']

# ruff: noqa: F405  # 薄壳模式：星号聚合导入的公共名（导出面由 tools/verify_export_parity.py 钉住）
