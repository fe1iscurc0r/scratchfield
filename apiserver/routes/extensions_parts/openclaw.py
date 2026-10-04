"""OpenClaw 网关、任务与 agent_browser 运行时（卷190-A1：从 extensions.py 纯搬移）。"""
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


MARKET_ITEMS: list[dict[str, Any]] = [
    {
        "id": "agent-browser",
        "title": "Agent Browser",
        "description": "Browser automation skill (offline template install, prebundled runtime preferred).",
        "skill_name": "agent-browser",
        "enabled": True,
        "install": {
            "type": "template_dir",
            "template": "agent-browser",
        },
    },
    {
        "id": "office-docs",
        "title": "Office Docs (docx + xlsx)",
        "description": "Extract docx/xlsx content with local scripts (no extra deps).",
        "skill_name": "office-docs",
        "enabled": True,
        "install": {
            "type": "template_dir",
            "template": "office-docs",
        },
    },
    {
        "id": "brainstorming",
        "title": "Brainstorming",
        "description": "Guided ideation and design exploration skill.",
        "skill_name": "brainstorming",
        "enabled": True,
        "install": {
            "type": "remote_skill",
            "url": "https://raw.githubusercontent.com/obra/superpowers/refs/heads/main/skills/brainstorming/SKILL.md",
        },
    },
    {
        "id": "context7",
        "title": "Context7 Docs",
        "description": "Query library/API docs via mcporter + context7 MCP (stdio).",
        "skill_name": "context7",
        "enabled": True,
        "install": {
            "type": "template_dir",
            "template": "context7",
        },
    },
    {
        "id": "search",
        "title": "Search (Firecrawl MCP)",
        "description": "Search MCP integration via mcporter + firecrawl-mcp.",
        "skill_name": "search",
        "enabled": True,
        "install": {
            "type": "template_dir",
            "template": "search",
        },
    },
]



def _agent_browser_bin_name() -> str:
    return "agent-browser.cmd" if sys.platform == "win32" else "agent-browser"



def _resolve_packaged_openclaw_runtime_dir() -> Path | None:
    candidates: list[Path] = []
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        meipass = Path(sys._MEIPASS)  # type: ignore[attr-defined]
        candidates.append(meipass / "vendor" / "openclaw")
        candidates.append(meipass.parent.parent / "runtime" / "openclaw")
        candidates.append(meipass.parent.parent / "openclaw-runtime" / "openclaw")
    # 开发环境下也允许直接复用本地构建产物中的预装运行时
    candidates.append(Path(__file__).resolve().parent.parent.parent / "frontend" / "backend-dist" / "runtime" / "openclaw")
    # 开发模式：项目根 runtime/
    candidates.append(Path(__file__).resolve().parent.parent.parent / "runtime" / "openclaw")
    # 开发/打包通用：直接使用项目 vendor/openclaw
    candidates.append(Path(__file__).resolve().parent.parent.parent / "vendor" / "openclaw")
    for candidate in candidates:
        if (candidate / "node_modules").exists():
            return candidate
    return None



def _resolve_prebundled_agent_browser_cmd() -> str | None:
    runtime_dir = _resolve_packaged_openclaw_runtime_dir()
    if not runtime_dir:
        return None
    cmd = runtime_dir / "node_modules" / ".bin" / _agent_browser_bin_name()
    return str(cmd) if cmd.exists() else None



def _agent_browser_browser_cache_dirs(runtime_dir: Path) -> list[Path]:
    return [
        runtime_dir / "node_modules" / "playwright-core" / ".local-browsers",
        runtime_dir / "node_modules" / "agent-browser" / "node_modules" / "playwright-core" / ".local-browsers",
    ]



def _has_agent_browser_native_bundle(runtime_dir: Path | None) -> bool:
    if runtime_dir is None:
        return False
    bin_dir = runtime_dir / "node_modules" / "agent-browser" / "bin"
    if not bin_dir.exists():
        return False
    for candidate in bin_dir.iterdir():
        if candidate.is_file() and candidate.name.startswith("agent-browser-") and candidate.name != "agent-browser.js":
            return True
    return False



def _has_agent_browser_browser_cache(runtime_dir: Path | None) -> bool:
    if runtime_dir is None:
        return False
    if _has_agent_browser_native_bundle(runtime_dir):
        return True
    for candidate in _agent_browser_browser_cache_dirs(runtime_dir):
        if candidate.exists():
            try:
                if any(candidate.iterdir()):
                    return True
            except Exception:
                return True
    return False



def _remove_agent_browser_browser_cache(runtime_dir: Path | None) -> int:
    if runtime_dir is None:
        return 0
    removed = 0
    for candidate in _agent_browser_browser_cache_dirs(runtime_dir):
        if candidate.exists():
            shutil.rmtree(candidate, ignore_errors=True)
            removed += 1
    return removed



def _install_agent_browser() -> None:
    from agentserver.openclaw.embedded_runtime import get_embedded_runtime

    runtime = get_embedded_runtime()
    runtime_dir = _resolve_packaged_openclaw_runtime_dir()
    prebundled_cmd = _resolve_prebundled_agent_browser_cmd()
    if prebundled_cmd and _has_agent_browser_browser_cache(runtime_dir):
        if _has_agent_browser_native_bundle(runtime_dir):
            removed = _remove_agent_browser_browser_cache(runtime_dir)
            if removed > 0:
                logger.info(f"已清理 agent-browser 浏览器缓存目录: {removed} 个")
        logger.info(f"检测到预装 agent-browser 与浏览器缓存，跳过在线安装: {prebundled_cmd}")
        return

    if getattr(sys, "frozen", False) and runtime_dir is None:
        raise RuntimeError("打包环境缺少内置 openclaw runtime，无法安装 agent-browser")

    install_root = runtime_dir or runtime.vendor_root
    npm_cmd = runtime.npm_path
    if npm_cmd is None:
        raise RuntimeError("未检测到内置/项目 npm，无法安装 agent-browser")

    env = runtime.env
    env["PLAYWRIGHT_BROWSERS_PATH"] = "0"
    env["CI"] = "1"

    logger.info(f"安装 agent-browser 到本地运行时目录: {install_root}")
    code, stdout, stderr = _run_command(
        [
            npm_cmd,
            "install",
            "agent-browser",
            "--global=false",
            "--location=project",
            "--prefix",
            str(install_root),
        ],
        timeout=3000,
        cwd=str(install_root),
        env=env,
    )
    if code != 0:
        raise RuntimeError(stderr or stdout or "npm install agent-browser 失败")

    if _has_agent_browser_native_bundle(install_root):
        removed = _remove_agent_browser_browser_cache(install_root)
        if removed > 0:
            logger.info(f"已清理 agent-browser 浏览器缓存目录: {removed} 个")
        logger.info("agent-browser 当前版本自带原生浏览器二进制，跳过 playwright 安装")
        return

    logger.info("正在 playwright install chromium（下载浏览器，可能需要数分钟）...")
    code, stdout, stderr = _run_command(
        [npm_cmd, "exec", "--prefix", str(install_root), "playwright", "install", "chromium"],
        timeout=3000,
        cwd=str(install_root),
        env=env,
    )
    if code != 0:
        raise RuntimeError(stderr or stdout or "playwright install chromium 失败")
    prebundled_cmd = _resolve_prebundled_agent_browser_cmd()
    if prebundled_cmd is None and not (install_root / "node_modules" / ".bin" / _agent_browser_bin_name()).exists():
        raise RuntimeError("agent-browser 安装完成后仍未找到命令入口")
    logger.info("agent-browser 安装完成")



@router.get("/openclaw/market/items")
def list_openclaw_market_items():
    """获取OpenClaw技能市场条目（同步端点，由 FastAPI 在线程池中执行）"""
    try:
        status = _get_market_items_status()
        return {"status": "success", **status}
    except Exception as e:
        logger.error(f"获取技能市场失败: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="获取技能市场失败")



# ============ 项目网关（OpenClaw Gateway）启停透传 → agent_server ============


@router.get("/openclaw/gateway/status")
async def openclaw_gateway_status_proxy():
    """查询项目网关运行状态（透传 agent_server）"""
    return await _call_agentserver("GET", "/openclaw/gateway/status")



@router.post("/openclaw/gateway/start")
async def openclaw_gateway_start_proxy():
    """启动项目网关（透传 agent_server，启动含 vendor 检查可能较慢）"""
    return await _call_agentserver("POST", "/openclaw/gateway/start", timeout_seconds=120.0)



@router.post("/openclaw/gateway/stop")
async def openclaw_gateway_stop_proxy():
    """停止项目网关（透传 agent_server）"""
    return await _call_agentserver("POST", "/openclaw/gateway/stop", timeout_seconds=60.0)



@router.post("/openclaw/market/items/{item_id}/install")
def install_openclaw_market_item(item_id: str, payload: dict[str, Any] | None = None):
    """安装指定OpenClaw技能市场条目（同步端点，由 FastAPI 在线程池中执行）"""
    item = next((entry for entry in MARKET_ITEMS if entry.get("id") == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="条目不存在")
    if not item.get("enabled", True):
        raise HTTPException(status_code=400, detail="条目暂不可安装")

    install_spec = item.get("install", {})
    install_type = install_spec.get("type")
    skill_name_value = item.get("skill_name") or item.get("id")
    if not skill_name_value:
        raise HTTPException(status_code=500, detail="技能名称缺失")
    skill_name = str(skill_name_value)
    telemetry_props = {
        "item_id": item_id,
        "skill_name": skill_name,
        "install_type": install_type,
        "has_payload": bool(payload),
    }

    try:
        if install_type == "remote_skill":
            url = install_spec.get("url")
            if not url:
                raise HTTPException(status_code=500, detail="缺少安装URL")
            content = _download_text(url)
            _write_skill_file(skill_name, content)
        elif install_type == "template_dir":
            template_name = install_spec.get("template")
            if not template_name:
                raise HTTPException(status_code=500, detail="缺少模板名称")
            _copy_template_dir(template_name, skill_name)
        elif install_type == "none":
            raise HTTPException(status_code=400, detail="该条目不支持安装")
        else:
            raise HTTPException(status_code=400, detail="未知安装方式")

        if item_id == "agent-browser":
            _install_agent_browser()
        if item_id == "search":
            api_key = None
            if payload and isinstance(payload, dict):
                api_key = payload.get("api_key") or payload.get("FIRECRAWL_API_KEY")
            _update_mcporter_firecrawl_config(api_key)
    except HTTPException as exc:
        _emit_extensions_telemetry(
            "market_item_install_fail",
            {
                **telemetry_props,
                "status_code": exc.status_code,
                "error": exc.detail,
            },
        )
        raise
    except Exception as e:
        _emit_extensions_telemetry(
            "market_item_install_fail",
            {
                **telemetry_props,
                "error": e,
            },
        )
        logger.error(f"安装技能失败({item_id}): {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="安装失败")

    status = _get_market_items_status()
    installed_item = next((entry for entry in status.get("items", []) if entry.get("id") == item_id), None)
    _emit_extensions_telemetry(
        "market_item_install_success",
        {
            **telemetry_props,
            "installed": bool(installed_item and installed_item.get("installed")),
        },
    )
    return {
        "status": "success",
        "message": "安装完成",
        "item": installed_item,
        "openclaw": status.get("openclaw"),
    }



# ============ OpenClaw 任务状态查询 ============


@router.get("/openclaw/tasks")
async def api_openclaw_list_tasks():
    """列出本地缓存的 OpenClaw 任务（来自 agentserver）。

    agentserver 尚未启动或仍在预热时返回空列表，避免前端启动期持续 503。
    """
    try:
        return await _call_agentserver("GET", "/openclaw/tasks")
    except HTTPException as e:
        if e.status_code == 503:
            return {"status": "warming_up", "tasks": []}
        raise



@router.get("/openclaw/tasks/{task_id}")
async def api_openclaw_get_task(
    task_id: str,
    include_history: bool = False,
    history_limit: int = 50,
    include_tools: bool = False,
):
    """获取 OpenClaw 任务状态（支持查看中间过程）"""
    return await _call_agentserver(
        "GET",
        f"/openclaw/tasks/{task_id}/detail",
        params={
            "include_history": str(include_history).lower(),
            "history_limit": history_limit,
            "include_tools": str(include_tools).lower(),
        },
    )

# ruff: noqa: F405  # 薄壳模式：星号聚合导入的公共名（导出面由 tools/verify_export_parity.py 钉住）
