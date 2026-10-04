"""工具执行器（MCP / 记忆 / 子代理 / 控制 / Live2D 分发）（卷190-A2：从 agentic_tool_loop.py 纯搬移）。"""
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
from .executor_openclaw import *  # noqa: F401,F403
from .executor_search import *  # noqa: F401,F403
from .markers import *  # noqa: F401,F403

# ---------------------------------------------------------------------------
# 工具执行
# ---------------------------------------------------------------------------


async def _execute_mcp_call(call: dict[str, Any], source_agent_id: str | None = None) -> dict[str, Any]:
    """执行单个MCP调用"""
    service_name = call.get("service_name", "")
    tool_name = call.get("tool_name", "")

    if not service_name and tool_name in {
        "ask_guide",
        "ask_guide_with_screenshot",
        "calculate_damage",
        "get_team_recommendation",
    }:
        service_name = "game_guide"
        call["service_name"] = service_name

    # 游戏攻略功能仅登录用户可用
    if service_name == "game_guide":
        if not naga_auth.is_authenticated():
            return {
                "tool_call": call,
                "result": "游戏攻略功能需要登录陆墨账号后才能使用，请先登录。",
                "status": "error",
                "service_name": service_name,
                "tool_name": tool_name,
            }

    try:
        from mcpserver.mcp_manager import get_mcp_manager
        from mcpserver.mcp_registry import is_service_visible_to_agent

        if not is_service_visible_to_agent(service_name, agent_id=source_agent_id):
            return {
                "tool_call": call,
                "result": f"当前干员无权访问 MCP 服务: {service_name}",
                "status": "error",
                "service_name": service_name,
                "tool_name": tool_name,
            }

        manager = get_mcp_manager()
        t0 = _time.monotonic()
        result = await manager.unified_call(service_name, call)
        elapsed = _time.monotonic() - t0
        logger.info(f"[AgenticLoop] MCP调用完成: {service_name}/{tool_name} 耗时 {elapsed:.2f}s")
        return {
            "tool_call": call,
            "result": result,
            "status": "success",
            "service_name": service_name,
            "tool_name": tool_name,
        }
    except Exception as e:
        logger.error(f"[AgenticLoop] MCP调用失败: service={service_name}, error={e}")
        return {
            "tool_call": call,
            "result": f"调用失败: {e}",
            "status": "error",
            "service_name": service_name,
            "tool_name": tool_name,
        }



async def _execute_memory_tool(
    call: dict[str, Any],
    tool_name: str,
    tool_args: dict[str, Any],
) -> dict[str, Any]:
    """memory_search / memory_get → 本机 memory_maas（五件套：血统+卡片+混合检索）。

    OpenClaw 网关未安装 memory 插件时该工具必然不可用（实测日志），本机
    memory_maas 才是陆墨的记忆事实源，故在此接管而非转发网关。
    """
    def _run() -> str:
        from mcpserver.memory_maas.core import get_core

        core = get_core()
        if tool_name == "memory_search":
            query = str(tool_args.get("query") or tool_args.get("keyword") or "").strip()
            if not query:
                return "缺少 query 参数"
            limit = max(1, min(int(tool_args.get("limit") or 8), 20))
            result = core.search(query, limit=limit)
            matches = result.get("matches", [])
            if not matches:
                return ""
            lines = [f"检索「{query}」命中 {len(matches)} 条："]
            for item in matches[:limit]:
                content = str(item.get("content") or "").strip().replace(chr(10), " ")
                lines.append(f"- [{item.get('id')}] ({item.get('score')}) {content[:200]}")
            return chr(10).join(lines)

        key = str(
            tool_args.get("id")
            or tool_args.get("name")
            or tool_args.get("query")
            or ""
        ).strip()
        if not key:
            return "缺少 id/name 参数"
        cards = core.search_cards(key, limit=5)
        if not cards:
            return ""
        lines = []
        for card in cards[:5]:
            content = str(card.get("content") or "").strip()
            lines.append(f"- [{card.get('id')}] {content[:400]}")
        return chr(10).join(lines)

    try:
        text = await asyncio.to_thread(_run)
        if not text:
            # memory_maas 未命中 → 回退知识库 RAG（vault 向量库/全文索引），
            # 陆墨的材料知识与文献都在那边；两条都空才算未找到。
            query = str(
                tool_args.get("query")
                or tool_args.get("keyword")
                or tool_args.get("id")
                or tool_args.get("name")
                or ""
            ).strip()
            rag_text = ""
            if query:
                try:
                    from apiserver.routes.lumo_proxy import _query_rag_standalone

                    rag_text = await _query_rag_standalone(query)
                except Exception as exc:  # noqa: BLE001
                    logger.debug(f"[AgenticLoop] 记忆工具 RAG 回退失败: {exc}")
            if rag_text:
                return {
                    "tool_call": call,
                    "result": f"知识库检索「{query}」：{rag_text}",
                    "status": "success",
                    "service_name": "knowledge_rag",
                    "tool_name": tool_name,
                }
            return {
                "tool_call": call,
                "result": f"未找到与「{query or '（空）'}」相关的记忆或知识",
                "status": "error",
                "service_name": "memory_maas",
                "tool_name": tool_name,
            }
        return {
            "tool_call": call, "result": text,
            "status": "error" if text.startswith("缺少") else "success",
            "service_name": "memory_maas", "tool_name": tool_name,
        }
    except Exception as exc:
        logger.warning(f"[AgenticLoop] 本地记忆工具失败 {tool_name}: {exc}")
        return {
            "tool_call": call, "result": f"记忆检索失败: {exc}",
            "status": "error", "service_name": "memory_maas", "tool_name": tool_name,
        }



async def _execute_agent_relay(
    call: dict[str, Any],
    tool_args: dict[str, Any],
    source_agent_id: str | None,
) -> dict[str, Any]:
    target_agent_id = str(tool_args.get("target_agent_id") or "").strip() or None
    target_agent_name = str(tool_args.get("target_agent_name") or "").strip() or None
    message = str(tool_args.get("message") or "").strip()
    if not message:
        return {
            "tool_call": call,
            "result": "缺少 message 参数",
            "status": "error",
            "service_name": "agent_directory",
            "tool_name": "agent_relay",
        }

    if not target_agent_id and not target_agent_name:
        return {
            "tool_call": call,
            "result": "缺少目标干员，请先调用 agents_list 再指定 target_agent_id 或 target_agent_name",
            "status": "error",
            "service_name": "agent_directory",
            "tool_name": "agent_relay",
        }

    target = resolve_agent_descriptor(agent_id=target_agent_id, agent_name=target_agent_name, include_builtin=True)
    if target is None:
        return {
            "tool_call": call,
            "result": "目标干员不存在，请先调用 agents_list 检查通讯录",
            "status": "error",
            "service_name": "agent_directory",
            "tool_name": "agent_relay",
        }

    payload = {
        "message": message,
        "target_agent_id": target.id,
        "source_agent_id": source_agent_id,
        "purpose": tool_args.get("purpose"),
        "context": tool_args.get("context"),
        "timeout_seconds": max(5, min(int(tool_args.get("timeout_seconds", 120) or 120), 600)),
    }

    try:
        client = _get_openclaw_client()
        response = await client.post(
            f"http://localhost:{get_server_port('api_server')}/agents/relay",
            json=payload,
            timeout=payload["timeout_seconds"] + 30,
        )
        if response.status_code != 200:
            return {
                "tool_call": call,
                "result": f"转发失败: HTTP {response.status_code} {response.text[:300]}",
                "status": "error",
                "service_name": "agent_directory",
                "tool_name": "agent_relay",
            }
        data = response.json()
        if not data.get("success", False):
            return {
                "tool_call": call,
                "result": data.get("error") or "目标干员未返回成功结果",
                "status": "error",
                "service_name": "agent_directory",
                "tool_name": "agent_relay",
            }
        reply = str(data.get("reply") or "").strip() or "(目标干员未返回正文)"
        result_text = (
            f"目标干员: {data.get('target', {}).get('name', target.name)}\n"
            f"目标引擎: {data.get('target', {}).get('engine', target.engine)}\n"
            f"回复:\n{reply}"
        )
        return {
            "tool_call": call,
            "result": result_text,
            "status": "success",
            "service_name": "agent_directory",
            "tool_name": "agent_relay",
        }
    except Exception as e:
        logger.error(f"[AgenticLoop] 干员转发失败: {e}")
        return {
            "tool_call": call,
            "result": f"转发异常: {e}",
            "status": "error",
            "service_name": "agent_directory",
            "tool_name": "agent_relay",
        }



async def _execute_control_tool(call: dict[str, Any]) -> dict[str, Any]:
    """执行陆墨自身控制操作（直接调用，无需 HTTP）"""
    from ..naga_control import execute

    action = call.get("action", "")
    params = call.get("params", {})

    t0 = _time.monotonic()
    result = await execute(action, params)
    elapsed = _time.monotonic() - t0
    logger.info(f"[AgenticLoop] NagaControl 完成: {action} 耗时 {elapsed:.2f}s")

    return {
        "tool_call": call,
        "result": json.dumps(result, ensure_ascii=False),
        "status": "success" if result.get("success") else "error",
        "service_name": "naga_control",
        "tool_name": action,
    }



async def _send_live2d_actions(live2d_calls: list[dict[str, Any]], session_id: str):
    """Fire-and-forget发送Live2D动作到UI"""

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout=5.0)) as client:
            for call in live2d_calls:
                action_name = call.get("action", "")
                logger.info(f"[AgenticLoop] 发送 Live2D 动作: {action_name}, 完整调用: {call}")
                if not action_name:
                    continue
                payload = {
                    "session_id": session_id,
                    "action": "live2d_action",
                    "action_name": action_name,
                }
                try:
                    await client.post(
                        f"http://localhost:{get_server_port('api_server')}/ui_notification",
                        json=payload,
                    )
                except Exception:
                    pass
    except Exception as e:
        logger.debug(f"[AgenticLoop] Live2D动作发送失败: {e}")

__all__ = ['_execute_agent_relay', '_execute_control_tool', '_execute_mcp_call', '_execute_memory_tool', '_send_live2d_actions']

# ruff: noqa: F405  # 薄壳模式：星号聚合导入的公共名（导出面由 tools/verify_export_parity.py 钉住）
