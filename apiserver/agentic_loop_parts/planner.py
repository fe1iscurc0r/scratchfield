"""计划段、收敛提示、任务与子代理编排（卷190-A2：从 agentic_tool_loop.py 纯搬移）。"""
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


def extract_plan_section(text: str) -> str | None:
    """W121-03：抽取模型输出里的 `[PLAN]…[/PLAN]` 执行计划段（未闭合时取到文本末尾）。

    计划文本本身保留在正文里（前端把它渲染成卡片），这里只额外给前端一个事件，
    便于做进度提示 / 确认按钮挂点。
    """
    if not text or "[PLAN]" not in text:
        return None
    match = re.search(r"\[PLAN\]([\s\S]*?)(?:\[/PLAN\]|$)", text)
    if not match:
        return None
    plan = match.group(1).strip()
    return plan or None



def build_convergence_prompt(
    ledger: List[dict[str, Any]],
    reason: str,
    max_steps: int,
) -> str:
    """W121-02：收敛轮提示词 —— 已做工作摘要 + 未完成/失败事项。

    Args:
        ledger: `_step_entry` 累积的步骤清单
        reason: `max_steps`（步数用尽）/ `consecutive_failures`（连续失败）/ `empty`（无步骤）
        max_steps: 配置的步数上限（写进提示，便于模型自述）
    """
    reason_text = {
        "max_steps": f"工具迭代已达上限（{max_steps} 步）",
        "consecutive_failures": "连续多轮工具调用全部失败",
        "no_tools": "本轮未产生工具调用",
    }.get(reason, "本轮工具迭代结束")

    done = [s for s in ledger if s.get("status") == "success"]
    failed = [s for s in ledger if s.get("status") != "success"]

    lines = [f"[系统提示] {reason_text}，现在必须直接回答用户，不要再发起任何工具调用。"]
    if done:
        lines.append("已完成：")
        for s in done:
            retry_note = f"（重试 {s['attempts'] - 1} 次后成功）" if s.get("attempts", 1) > 1 else ""
            lines.append(f"- 第{s['round']}轮 {s['label']}：成功{retry_note}，结果：{s['summary']}")
    else:
        lines.append("已完成：（无）")
    if failed:
        lines.append("未完成 / 失败：")
        for s in failed:
            retry_note = f"，重试 {s['attempts'] - 1} 次仍失败" if s.get("attempts", 1) > 1 else ""
            lines.append(f"- 第{s['round']}轮 {s['label']}：失败{retry_note}，原因：{s['summary']}")
    else:
        lines.append("未完成 / 失败：（无）")
    lines.append("请基于以上结果给出最终答复；未完成的部分请明确说明原因与下一步建议。")
    return "\n".join(lines)



def _collect_task_ops(text: str) -> List[dict[str, Any]]:
    """卷123 W123-02：抽取模型输出里的 [TASK] 段任务操作（失败静默，不影响对话）。"""
    try:
        from apiserver.task_flow import extract_task_ops

        return extract_task_ops(text)
    except Exception as e:  # noqa: BLE001
        logger.debug("[AgenticLoop] [TASK] 段解析跳过: %s", e)
        return []



def _apply_task_ops(session_id: str, ops: List[dict[str, Any]]) -> List[dict[str, Any]]:
    """把 [TASK] 段操作落到 task_store（fail-closed 判定在 task_flow 内）。"""
    try:
        from apiserver.task_flow import apply_task_ops

        return apply_task_ops(session_id, ops)
    except Exception as e:  # noqa: BLE001
        logger.warning("[AgenticLoop] 任务操作落库失败: %s", e)
        return []



def _collect_subagent_specs(text: str) -> List[dict[str, Any]]:
    """W124-02：抽取模型输出的 [SUBAGENT] 段。"""
    try:
        from apiserver.subagent import extract_subagent_specs

        return extract_subagent_specs(text)
    except Exception as e:  # noqa: BLE001
        logger.debug("[AgenticLoop] [SUBAGENT] 段解析跳过: %s", e)
        return []



async def _run_subagents(session_id: str, specs: List[dict[str, Any]]) -> List[dict[str, Any]]:
    """W124-02：派生子代理并等结果（并行，上限见 subagent.max_parallel）。"""
    try:
        from apiserver.subagent import spawn_many

        goals = [
            {"goal": str(s.get("goal") or ""), "tools": s.get("tools"), "context": str(s.get("context") or "")}
            for s in specs
            if str(s.get("goal") or "").strip()
        ]
        if not goals:
            return []
        return await spawn_many(goals, session_id=session_id)
    except Exception as e:  # noqa: BLE001 - 子代理失败不拖垮父对话
        logger.warning("[AgenticLoop] 子代理派生失败: %s", e)
        return [{"ok": False, "error": str(e)}]



def _subagent_results_prompt(session_id: str) -> str:
    """W124-02：子代理结果聚合摘要（注入父对话上下文）。"""
    try:
        from apiserver.subagent import results_prompt

        return results_prompt(session_id)
    except Exception as e:  # noqa: BLE001
        logger.debug("[AgenticLoop] 子代理结果聚合跳过: %s", e)
        return ""



def _build_review_prompt(applied: List[dict[str, Any]]) -> str:
    """卷123 W123-04：任务转入 review 时生成审查汇总（失败返回空串，不影响对话）。"""
    task_ids = [str(item.get("task_id") or "") for item in applied
                if str(item.get("task_status") or "") == "review" and item.get("task_id")]
    if not task_ids:
        return ""
    try:
        from apiserver.task_review import review_prompt

        return review_prompt(task_ids[0])
    except Exception as e:  # noqa: BLE001
        logger.warning("[AgenticLoop] 审查汇总生成失败: %s", e)
        return ""



def _maybe_create_task_from_plan(
    session_id: str, plan_text: str, messages: list[dict[str, Any]]
) -> List[dict[str, Any]]:
    """卷123 W123-02：模型出 [PLAN] 时按计划建任务（已确认过的不重复建）。"""
    try:
        from apiserver.task_flow import goal_from_messages, maybe_create_task_from_plan

        task = maybe_create_task_from_plan(session_id, plan_text, goal_from_messages(messages))
    except Exception as e:  # noqa: BLE001
        logger.warning("[AgenticLoop] 按 [PLAN] 建任务失败: %s", e)
        return []
    if not task:
        return []
    logger.info("[AgenticLoop] 已按 [PLAN] 建任务 %s（%d 步，待确认）", task["task_id"], len(task["steps"]))
    return [{"op": "plan_task", "ok": True, "task_id": task["task_id"], "steps": len(task["steps"]),
             "status": task["status"]}]

__all__ = ['_apply_task_ops', '_build_review_prompt', '_collect_subagent_specs', '_collect_task_ops', '_maybe_create_task_from_plan', '_run_subagents', '_subagent_results_prompt', 'build_convergence_prompt', 'extract_plan_section']

# ruff: noqa: F405  # 薄壳模式：星号聚合导入的公共名（导出面由 tools/verify_export_parity.py 钉住）
