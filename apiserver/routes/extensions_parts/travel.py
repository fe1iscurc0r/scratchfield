"""旅行会话（/travel 全家桶）（卷190-A1：从 extensions.py 纯搬移）。"""
"""OpenClaw 技能市场、MCP 服务、技能导入、文件上传、旅行、记忆、搜索代理路由"""

import html
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from datetime import datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import URLError
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

import yaml
from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from agentserver.openclaw.state_paths import get_openclaw_config_path, get_openclaw_state_dir
from apiserver import naga_auth
from apiserver.api_server import FileUploadResponse, _call_agentserver
from apiserver.mcp_assembly import (
    KNOWN_FAMILIES,
    KNOWN_TIERS,
)
from apiserver.mcp_assembly import (
    check_requirements as _assembly_check_requirements,
)
from apiserver.mcp_assembly import (
    decide_enabled as _assembly_decide_enabled,
)
from apiserver.mcp_assembly import (
    load_policy as _assembly_load_policy,
)
from apiserver.mcp_assembly import (
    set_agent_override as _assembly_set_override,
)
from apiserver.mcp_assembly import (
    set_policy as _assembly_set_policy,
)
from apiserver.telemetry import emit_telemetry
from system.config import get_config, get_data_dir

from .common import *  # noqa: F401,F403

router = APIRouter()



# ============ 旅行端点 ============


async def _create_travel_session_and_dispatch(payload: dict[str, Any]) -> dict[str, Any]:
    from apiserver.travel_service import (
        TravelStatus,
        create_session,
        get_open_session_for_agent,
        load_session,
        save_session,
    )

    agent_id = payload.get("agent_id")
    if agent_id:
        agent = _get_agent_record(str(agent_id))
        if not agent:
            raise HTTPException(404, "指定的探索干员不存在")
        if agent.get("engine", "openclaw") != "openclaw":
            raise HTTPException(400, "网络探索目前仅支持 OpenClaw 干员执行")

    active_for_agent = get_open_session_for_agent(str(agent_id) if agent_id is not None else None)
    if active_for_agent:
        raise HTTPException(409, f"该干员已有进行中的探索: {active_for_agent.session_id}")

    session = create_session(
        agent_id=str(agent_id) if agent_id is not None else None,
        agent_name=str(agent.get("name") or "").strip() if agent_id is not None and agent else None,
        time_limit_minutes=payload.get("time_limit_minutes", 300),
        credit_limit=payload.get("credit_limit", 1000),
        want_friends=payload.get("want_friends", True),
        friend_description=payload.get("friend_description"),
        goal_prompt=payload.get("goal_prompt"),
        post_to_forum=payload.get("post_to_forum", True),
        deliver_full_report=payload.get("deliver_full_report", True),
        deliver_channel=payload.get("deliver_channel"),
        deliver_to=payload.get("deliver_to"),
        browser_visible=payload.get("browser_visible", False),
        browser_keep_open=payload.get("browser_keep_open", False),
        browser_idle_timeout_seconds=payload.get("browser_idle_timeout_seconds", 300),
    )
    emit_telemetry(
        "explore_start",
        {
            "time_limit_minutes": session.time_limit_minutes,
            "credit_limit": session.credit_limit,
            "want_friends": session.want_friends,
            "deliver_channel": session.deliver_channel,
            "deliver_full_report": session.deliver_full_report,
            "post_to_forum": session.post_to_forum,
            "goal_prompt_chars": len(session.goal_prompt or ""),
        },
        source="apiserver",
        session_id=session.session_id,
        agent_id=session.agent_id,
        trace_id=f"travel:{session.session_id}",
    )

    try:
        await _call_agentserver(
            "POST", "/travel/execute",
            json_body={"session_id": session.session_id},
            timeout_seconds=10.0,
        )
    except Exception as e:
        logger.warning(f"代理旅行到 agent server 失败（将本地标记失败）: {e}")
        s = load_session(session.session_id)
        s.status = TravelStatus.FAILED
        s.error = f"agent server 不可达: {e}"
        save_session(s)
        emit_telemetry(
            "explore_fail",
            {
                "stage": "dispatch",
                "error": e,
            },
            source="apiserver",
            session_id=session.session_id,
            agent_id=session.agent_id,
            trace_id=f"travel:{session.session_id}",
        )
        raise HTTPException(503, f"agent server 不可达: {e}")

    return {"status": "success", "session_id": session.session_id, "session": session.model_dump()}



def _cancel_travel_session(session_id: str) -> dict[str, Any]:
    from apiserver.travel_service import TravelStatus, load_session, remove_session_browser_policy, save_session

    try:
        session = load_session(session_id)
    except FileNotFoundError:
        raise HTTPException(404, f"旅行 session 不存在: {session_id}")

    if session.status in {TravelStatus.COMPLETED, TravelStatus.FAILED, TravelStatus.CANCELLED}:
        return {"status": "success", "session_id": session.session_id, "session": session.model_dump()}

    session.status = TravelStatus.CANCELLED
    session.completed_at = datetime.now().isoformat()
    save_session(session)
    remove_session_browser_policy(session.openclaw_session_key)
    emit_telemetry(
        "explore_cancel",
        {
            "elapsed_minutes": session.elapsed_minutes,
            "discoveries": len(session.discoveries),
        },
        source="apiserver",
        session_id=session.session_id,
        agent_id=session.agent_id,
        trace_id=f"travel:{session.session_id}",
    )
    return {"status": "success", "session_id": session.session_id, "session": session.model_dump()}



@router.post("/travel/sessions")
async def create_travel_session(payload: dict[str, Any]):
    return await _create_travel_session_and_dispatch(payload)



@router.get("/travel/sessions")
async def list_travel_sessions():
    from apiserver.travel_service import list_sessions

    sessions = list_sessions()
    return {"status": "success", "sessions": [s.model_dump() for s in sessions]}



@router.get("/travel/sessions/{session_id}")
async def get_travel_session(session_id: str):
    from apiserver.travel_service import load_session

    try:
        session = load_session(session_id)
    except FileNotFoundError:
        raise HTTPException(404, f"旅行 session 不存在: {session_id}")
    return {"status": "success", "session": session.model_dump()}



@router.get("/travel/sessions/{session_id}/report")
async def get_travel_session_report(session_id: str):
    from apiserver.travel_service import load_session

    try:
        session = load_session(session_id)
    except FileNotFoundError:
        raise HTTPException(404, f"旅行 session 不存在: {session_id}")

    report_path = (session.summary_report_path or "").strip()
    if not report_path:
        return {
            "status": "success",
            "exists": False,
            "path": None,
            "title": session.summary_report_title,
            "content": None,
            "missing_reason": "not_generated",
        }

    path = Path(report_path)
    if not path.exists():
        return {
            "status": "success",
            "exists": False,
            "path": report_path,
            "title": session.summary_report_title,
            "content": None,
            "missing_reason": "missing",
        }

    try:
        content = path.read_text(encoding="utf-8")
    except Exception as e:
        raise HTTPException(500, f"读取探索成果文件失败: {e}")

    return {
        "status": "success",
        "exists": True,
        "path": report_path,
        "title": session.summary_report_title,
        "content": content,
    }



@router.get("/travel/sessions/{session_id}/history")
async def get_travel_session_history(session_id: str, limit: int = 0, include_tools: bool = True):
    from apiserver.travel_service import load_session

    try:
        session = load_session(session_id)
    except FileNotFoundError:
        raise HTTPException(404, f"旅行 session 不存在: {session_id}")

    session_key = (session.openclaw_session_key or "").strip()
    if not session_key:
        return {
            "status": "success",
            "session_id": session_id,
            "session_key": None,
            "messages": [],
        }

    history = await _call_agentserver(
        "GET",
        "/openclaw/history",
        params={
            "session_key": session_key,
            "limit": limit,
            "include_tools": str(include_tools).lower(),
        },
        timeout_seconds=20.0,
    )

    messages = []
    if isinstance(history, dict):
        raw_history = history.get("history")
        if isinstance(raw_history, dict):
            messages = raw_history.get("messages", []) or []

    return {
        "status": "success",
        "session_id": session_id,
        "session_key": session_key,
        "messages": messages,
    }



@router.post("/travel/sessions/{session_id}/stop")
async def stop_travel_session(session_id: str):
    return _cancel_travel_session(session_id)



@router.post("/travel/sessions/{session_id}/browser")
async def update_travel_browser_settings(session_id: str, payload: dict[str, Any]):
    from apiserver.travel_service import append_progress_event, load_session, save_session, sync_session_browser_policy

    try:
        session = load_session(session_id)
    except FileNotFoundError:
        raise HTTPException(404, f"旅行 session 不存在: {session_id}")

    visibility_changed = False
    if "browser_visible" in payload:
        next_visible = bool(payload.get("browser_visible"))
        visibility_changed = session.browser_visible != next_visible
        session.browser_visible = next_visible
    if "browser_keep_open" in payload:
        session.browser_keep_open = bool(payload.get("browser_keep_open"))
    if "browser_idle_timeout_seconds" in payload:
        session.browser_idle_timeout_seconds = max(30, int(payload.get("browser_idle_timeout_seconds") or 300))

    append_progress_event(
        session,
        "browser_settings_updated",
        "已更新探索浏览器策略。",
        meta={
            "browser_visible": session.browser_visible,
            "browser_keep_open": session.browser_keep_open,
            "browser_idle_timeout_seconds": session.browser_idle_timeout_seconds,
        },
    )
    save_session(session)
    sync_session_browser_policy(session)

    if visibility_changed and session.agent_id and session.status in {"pending", "running", "interrupted"}:
        try:
            await _call_agentserver(
                "POST",
                "/travel/browser-settings",
                json_body={
                    "session_id": session.session_id,
                    "browser_visible": session.browser_visible,
                },
                timeout_seconds=10.0,
            )
        except Exception as e:
            logger.warning(f"同步探索浏览器可见性到 agent_server 失败: {e}")

    return {"status": "success", "session": session.model_dump()}



@router.post("/travel/sessions/{session_id}/instruction")
async def send_travel_instruction(session_id: str, payload: dict[str, Any]):
    from apiserver.travel_service import OPEN_TRAVEL_STATUSES, append_progress_event, load_session, save_session

    message = str(payload.get("message") or "").strip()
    if not message:
        raise HTTPException(400, "message 不能为空")

    try:
        session = load_session(session_id)
    except FileNotFoundError:
        raise HTTPException(404, f"旅行 session 不存在: {session_id}")

    if session.status not in OPEN_TRAVEL_STATUSES:
        raise HTTPException(409, "当前探索已结束，不能再追加指令")

    await _call_agentserver(
        "POST",
        "/travel/instruction",
        json_body={"session_id": session_id, "message": message},
        timeout_seconds=10.0,
    )
    append_progress_event(
        session,
        "instruction_requested",
        f"用户追加了探索指令：{message[:80]}",
        meta={"message": message[:400]},
    )
    save_session(session)
    return {"status": "success", "session": session.model_dump()}



@router.post("/travel/start")
async def travel_start(payload: dict[str, Any]):
    """兼容旧接口。"""
    result = await _create_travel_session_and_dispatch(payload)
    return {"status": result["status"], "session_id": result["session_id"]}



@router.get("/travel/status")
async def travel_status():
    """兼容旧接口：返回任一活跃 session 或最近一条记录。"""
    from apiserver.travel_service import get_latest_session, list_active_sessions

    active = list_active_sessions()
    if active:
        return {"status": "success", "session": active[0].model_dump(), "active": True}

    latest = get_latest_session()
    if latest:
        return {"status": "success", "session": latest.model_dump(), "active": False}

    return {"status": "success", "session": None, "active": False}



@router.post("/travel/stop")
async def travel_stop(payload: dict[str, Any] = None):
    """兼容旧接口：可选指定 session_id，否则停止最近活跃 session。"""
    from apiserver.travel_service import list_active_sessions

    session_id = (payload or {}).get("session_id")
    if not session_id:
        active = list_active_sessions()
        if not active:
            raise HTTPException(404, "没有进行中的旅行")
        session_id = active[0].session_id
    result = _cancel_travel_session(str(session_id))
    return {"status": result["status"], "session_id": result["session_id"]}



@router.get("/travel/history")
async def travel_history():
    """兼容旧接口。"""
    from apiserver.travel_service import list_sessions

    sessions = list_sessions()
    return {"status": "success", "sessions": [s.model_dump() for s in sessions]}



@router.get("/travel/history/{session_id}")
async def travel_history_detail(session_id: str):
    """兼容旧接口。"""
    return await get_travel_session(session_id)

# ruff: noqa: F405  # 薄壳模式：星号聚合导入的公共名（导出面由 tools/verify_export_parity.py 钉住）
