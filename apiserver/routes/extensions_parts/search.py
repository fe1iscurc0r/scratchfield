"""搜索代理（卷190-A1：从 extensions.py 纯搬移）。"""
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



# ============ 搜索代理 ============


@router.api_route("/tools/search", methods=["GET", "POST"])
async def proxy_search(request: Request):
    """统一搜索代理: 优先陆墨Model，回退 Brave，供陆墨与 OpenClaw 共用。"""

    if request.method == "GET":
        params = dict(request.query_params)
    else:
        params = await request.json()

    import httpx

    async def _call_upstream(client: httpx.AsyncClient, url: str, headers: dict):
        if request.method == "GET":
            return await client.get(url, params=params, headers=headers, timeout=30)
        return await client.post(url, json=params, headers=headers, timeout=30)

    try:
        async with httpx.AsyncClient() as client:
            resp = None
            token = naga_auth.get_access_token()
            if not token and naga_auth.has_refresh_token():
                try:
                    await naga_auth.ensure_access_token()
                    token = naga_auth.get_access_token()
                except Exception as refresh_err:
                    logger.warning(f"搜索代理预刷新 access token 失败: {refresh_err}")

            if not token:
                auth = request.headers.get("authorization", "")
                if auth.startswith("Bearer "):
                    token = auth[7:]

            # 优先 Naga 登录态；401 时自动 refresh 一次
            if token and naga_auth.NAGA_MODEL_URL:
                upstream_url = naga_auth.NAGA_MODEL_URL + "/tools/search"
                resp = await _call_upstream(
                    client,
                    upstream_url,
                    {"Authorization": f"Bearer {token}"},
                )
                if resp.status_code == 401 and naga_auth.has_refresh_token():
                    logger.warning("搜索代理检测到 Naga token 过期，尝试刷新后重试")
                    try:
                        refresh_result = await naga_auth.refresh()
                        token = refresh_result.get("access_token") or naga_auth.get_access_token()
                        resp = await _call_upstream(
                            client,
                            upstream_url,
                            {"Authorization": f"Bearer {token}"},
                        )
                    except Exception as refresh_err:
                        logger.warning(f"搜索代理刷新 Naga token 失败: {refresh_err}")

            # Naga 不可用或仍然 401/403 时，回退 Brave
            if resp is None or resp.status_code in (401, 403):
                cfg = get_config()
                search_key = getattr(cfg.online_search, "search_api_key", "")
                search_base = getattr(cfg.online_search, "search_api_base", "")
                if search_key and search_base:
                    resp = await _call_upstream(
                        client,
                        search_base,
                        {
                            "Accept": "application/json",
                            "X-Subscription-Token": search_key,
                        },
                    )

            # W112-02：Naga 与 Brave 都不可用/未配置时，回退本地搜索
            # （DuckDuckGo HTML，零 key 零登录，固定 https 域名）。
            # 实测根因：原先此处直接 401「未登录且未配置搜索服务」，
            # 三级回退链从未生效，web_search 对本地用户形同虚设。
            if resp is None or resp.status_code in (401, 403):
                from apiserver.local_search import search_local

                try:
                    query = str(params.get("query") or params.get("q") or "").strip()
                    if query:
                        local_result = await search_local(query)
                        return JSONResponse(
                            content={"details": local_result},
                            status_code=200,
                        )
                except Exception as local_err:
                    logger.warning(f"本地搜索回退失败: {local_err}")

            if resp is None:
                raise HTTPException(status_code=401, detail="未登录且未配置搜索服务")
            if resp.status_code in (401, 403):
                detail = resp.text
                raise HTTPException(status_code=401, detail=detail or "Naga 搜索认证失败，且未配置 Brave 搜索")

        return JSONResponse(content=resp.json(), status_code=resp.status_code)
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"搜索代理失败: {e}")
        return JSONResponse(
            content={"error": {"message": f"搜索服务不可用: {e}", "type": "upstream_error"}},
            status_code=502,
        )

# ruff: noqa: F405  # 薄壳模式：星号聚合导入的公共名（导出面由 tools/verify_export_parity.py 钉住）
