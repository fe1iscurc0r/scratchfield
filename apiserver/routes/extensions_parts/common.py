"""公共件（路径常量 / 子进程 / 遥测）（卷190-A1：从 extensions.py 纯搬移）。"""
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

logger = logging.getLogger(__name__)



# ============ OpenClaw Skill Market ============

OPENCLAW_STATE_DIR = get_openclaw_state_dir()

OPENCLAW_SKILLS_DIR = OPENCLAW_STATE_DIR / "skills"

OPENCLAW_CONFIG_PATH = get_openclaw_config_path()

NAGA_DATA_DIR = get_data_dir()

NAGA_SKILLS_DIR = NAGA_DATA_DIR / "skills"

NAGA_PUBLIC_SKILLS_DIR = NAGA_SKILLS_DIR / "public"

NAGA_CACHE_SKILLS_DIR = NAGA_SKILLS_DIR / "cache"

NAGA_AGENTS_DIR = NAGA_DATA_DIR / "agents"

NAGA_AGENTS_MANIFEST_PATH = NAGA_AGENTS_DIR / "agents.json"

SKILLS_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "skills_templates"

MCPORTER_DIR = NAGA_DATA_DIR / "mcporter"

MCPORTER_CONFIG_PATH = MCPORTER_DIR / "config.json"

LEGACY_MCPORTER_DIR = Path.home() / ".mcporter"

LEGACY_MCPORTER_CONFIG_PATH = LEGACY_MCPORTER_DIR / "config.json"

SKILL_FRONTMATTER_PATTERN = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

MAX_SKILL_NAME_LENGTH = 120


for _path in (OPENCLAW_SKILLS_DIR, NAGA_PUBLIC_SKILLS_DIR, NAGA_CACHE_SKILLS_DIR, NAGA_AGENTS_DIR):
    _path.mkdir(parents=True, exist_ok=True)



# ============ OpenClaw 辅助函数 ============


def _run_command(
    command: list[str],
    timeout: int = 30,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
) -> tuple[int, str, str]:
    import locale
    enc = locale.getpreferredencoding() or "utf-8"
    # 统一 shell=False，消除 shell 拼接带来的注入面（审计 LOW L2）
    # Windows 下 .cmd/.bat 无法被 CreateProcess 直接执行，需经 cmd.exe /c
    if sys.platform == "win32" and command and command[0].lower().endswith((".cmd", ".bat")):
        exec_cmd: list[str] = [
            os.environ.get("COMSPEC", "cmd.exe"),
            "/d",
            "/s",
            "/c",
            subprocess.list2cmdline(command),  # 保留 Windows 引号语义，避免二次 shell 整形
        ]
    else:
        exec_cmd = command
    result = subprocess.run(
        exec_cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        shell=False,
        encoding=enc,
        errors="replace",
        cwd=cwd,
        env=env,
    )
    return result.returncode, (result.stdout or "").strip(), (result.stderr or "").strip()



def _download_text(url: str, timeout: int = 20) -> str:
    try:
        request = UrlRequest(url, headers={"User-Agent": "陆墨/market-installer"})
        with urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8")
    except URLError as exc:
        raise RuntimeError(f"下载失败: {exc}")



# ============ OpenClaw 技能市场端点 ============


def _telemetry_config_keys(config: dict[str, Any] | None) -> list[str]:
    if not isinstance(config, dict):
        return []
    keys = [str(key)[:80] for key in config.keys() if not str(key).startswith("_")]
    return sorted(keys)[:32]



def _emit_extensions_telemetry(
    event: str,
    props: dict[str, Any],
    *,
    agent_id: str | None = None,
) -> None:
    emit_telemetry(
        event,
        props,
        source="apiserver",
        agent_id=agent_id,
    )

# ruff: noqa: F405  # 薄壳模式：星号聚合导入的公共名（导出面由 tools/verify_export_parity.py 钉住）
