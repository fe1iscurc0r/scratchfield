"""Hub / mcporter.so / clawhub 安装与市场项（卷190-A1：从 extensions.py 纯搬移）。"""
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



def _build_market_item(item: dict[str, Any]) -> dict[str, Any]:
    skill_name = str(item.get("skill_name") or item.get("id") or "unknown")
    skill_path = OPENCLAW_SKILLS_DIR / skill_name / "SKILL.md"
    return {
        "id": item.get("id"),
        "title": item.get("title"),
        "description": item.get("description"),
        "skill_name": skill_name,
        "enabled": item.get("enabled", True),
        "installed": skill_path.exists(),
        "skill_path": str(skill_path),
        "install_type": item.get("install", {}).get("type"),
    }



def _get_market_items_status() -> dict[str, Any]:
    from .openclaw import MARKET_ITEMS  # 延迟导入：openclaw 顶部引用本模块，运行时才解析
    return {
        "openclaw": {
            "skills_dir": str(OPENCLAW_SKILLS_DIR),
            "config_path": str(OPENCLAW_CONFIG_PATH),
        },
        "items": [_build_market_item(item) for item in MARKET_ITEMS],
    }



class HubInstallRequest(BaseModel):
    name: str
    scope: str = "public"
    agent_id: str | None = None
    source: str = "tencent-skillhub"


def _hub_base_url(source: str = "tencent-skillhub") -> str:
    normalized = (source or "tencent-skillhub").strip().lower()
    if normalized == "tencent-skillhub":
        return "https://skillhub-1388575217.cos.ap-guangzhou.myqcloud.com"
    if normalized == "clawhub":
        return "https://clawhub.ai"
    if normalized == "mcp.so":
        return "https://mcp.so"
    raise HTTPException(status_code=400, detail=f"未知下载源: {source}")



def _build_hub_url(kind: str, name: str, source: str = "tencent-skillhub") -> str:
    base_url = _hub_base_url(source)
    if (source or "").strip().lower() == "tencent-skillhub":
        return f"{base_url}/{kind}/{name}"
    return f"{base_url}/api/hub/{kind}/{name}"



def _resolve_skillhub_cli() -> str | None:
    try:
        from agentserver.openclaw.embedded_runtime import get_embedded_runtime

        runtime = get_embedded_runtime()
        project_runtime_root = runtime._get_project_runtime_root()
        candidates = [
            Path(runtime.runtime_root) / "skillhub" / "skills_store_cli.py" if runtime.runtime_root else None,
            project_runtime_root / "skillhub" / "skills_store_cli.py",
        ]
        for candidate in candidates:
            if candidate and candidate.exists():
                return str(candidate)
    except Exception:
        pass
    return None



def _resolve_skillhub_python() -> str | None:
    try:
        from agentserver.openclaw.embedded_runtime import get_embedded_runtime

        runtime = get_embedded_runtime()
        return runtime.python_path
    except Exception:
        return None



def _resolve_clawhub_runtime() -> tuple[str | None, str | None]:
    try:
        from agentserver.openclaw.embedded_runtime import get_embedded_runtime

        runtime = get_embedded_runtime()
        return runtime.node_path, runtime.npx_path
    except Exception:
        return None, None



def _normalize_mcpso_name(name: str) -> str:
    return re.sub(r"\s+", "", (name or "").strip().lower())



def _resolve_mcpso_url(name_or_url: str) -> tuple[str, bool]:
    raw = (name_or_url or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="请输入 MCP 名称或完整链接")
    if raw.startswith("http://") or raw.startswith("https://"):
        return raw, True
    normalized_name = _normalize_mcpso_name(raw)
    return f"https://mcp.so/server/{normalized_name}/modelcontextprotocol", False



def _extract_json_code_blocks_from_html(page_html: str) -> list[str]:
    blocks = re.findall(r"```json\s*(.*?)\s*```", page_html, flags=re.S | re.I)
    normalized_blocks: list[str] = []
    for block in blocks:
        text = html.unescape(block)
        try:
            text = text.encode("utf-8").decode("unicode_escape")
        except Exception:
            pass
        stripped = text.strip()
        if stripped:
            normalized_blocks.append(stripped)
    return normalized_blocks



def _strip_json_line_comments(raw_text: str) -> str:
    result: list[str] = []
    in_string = False
    escaped = False
    i = 0
    length = len(raw_text)
    while i < length:
        ch = raw_text[i]
        nxt = raw_text[i + 1] if i + 1 < length else ""
        if in_string:
            result.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            result.append(ch)
            i += 1
            continue
        if ch == "/" and nxt == "/":
            i += 2
            while i < length and raw_text[i] not in "\r\n":
                i += 1
            continue
        result.append(ch)
        i += 1
    return "".join(result)



def _parse_mcp_install_payload(block_text: str, fallback_name: str) -> tuple[str, str | None, str | None, dict[str, Any]]:
    try:
        payload = json.loads(_strip_json_line_comments(block_text))
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=502, detail=f"获取到的 MCP 配置不是合法 JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=502, detail="获取到的 MCP 配置不是 JSON 对象")

    if isinstance(payload.get("mcpServers"), dict) and payload["mcpServers"]:
        mcp_name, config = next(iter(payload["mcpServers"].items()))
        if not isinstance(config, dict):
            raise HTTPException(status_code=502, detail="mcpServers 下的配置格式无效")
        return str(mcp_name), None, None, config

    mcp_section = payload.get("mcp")
    if isinstance(mcp_section, dict) and isinstance(mcp_section.get("servers"), dict) and mcp_section["servers"]:
        mcp_name, config = next(iter(mcp_section["servers"].items()))
        if not isinstance(config, dict):
            raise HTTPException(status_code=502, detail="mcp.servers 下的配置格式无效")
        return str(mcp_name), None, None, config

    if "command" in payload or "type" in payload or "url" in payload:
        return fallback_name, None, None, payload

    raise HTTPException(status_code=502, detail="未在 mcp.so 页面中找到可安装的 MCP 配置")



def _install_mcp_via_mcpso(name_or_url: str) -> tuple[str, str | None, str | None, dict[str, Any]]:
    target_url, provided_full_url = _resolve_mcpso_url(name_or_url)
    req = UrlRequest(target_url, headers={"User-Agent": "陆墨/mcpso-installer"})
    try:
        with urlopen(req, timeout=20) as resp:
            page_html = resp.read().decode("utf-8", errors="ignore")
    except HTTPException:
        raise
    except Exception as exc:
        if provided_full_url:
            raise HTTPException(status_code=502, detail="获取mcp内容失败") from exc
        raise HTTPException(status_code=404, detail="获取mcp失败，请传输完整链接") from exc

    blocks = _extract_json_code_blocks_from_html(page_html)
    if not blocks:
        if provided_full_url:
            raise HTTPException(status_code=502, detail="获取mcp内容失败")
        raise HTTPException(status_code=404, detail="获取mcp失败，请传输完整链接")

    fallback_name = _normalize_mcpso_name(name_or_url)
    if provided_full_url:
        matched = re.search(r"/server/([^/]+)/", target_url)
        if matched:
            fallback_name = _normalize_mcpso_name(matched.group(1)) or fallback_name
    for block in reversed(blocks):
        try:
            return _parse_mcp_install_payload(block, fallback_name)
        except HTTPException:
            continue

    if provided_full_url:
        raise HTTPException(status_code=502, detail="获取mcp内容失败")
    raise HTTPException(status_code=404, detail="获取mcp失败，请传输完整链接")



def _install_skill_via_tencent_skillhub(name: str) -> tuple[str, str]:
    cli = _resolve_skillhub_cli()
    python_bin = _resolve_skillhub_python()
    if not cli or not python_bin:
        raise HTTPException(
            status_code=503,
            detail="未找到内置腾讯 SkillHub CLI 或 Python 运行时，无法执行下载。",
        )
    with tempfile.TemporaryDirectory(prefix="naga-skillhub-") as tmp:
        install_dir = Path(tmp)
        try:
            subprocess.run(
                [python_bin, cli, "--dir", str(install_dir), "install", name, "--force"],
                check=True,
                cwd=str(install_dir),
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or exc.stdout or "").strip()
            raise HTTPException(status_code=502, detail=f"腾讯 SkillHub 安装失败: {stderr or exc}") from exc

        direct_path = install_dir / name / "SKILL.md"
        if direct_path.exists():
            return name, direct_path.read_text(encoding="utf-8")

        fallback_path = next(install_dir.rglob("SKILL.md"), None)
        if fallback_path is None:
            raise HTTPException(status_code=502, detail="腾讯 SkillHub 安装完成，但未找到 SKILL.md")

        resolved_name = fallback_path.parent.name or name
        return resolved_name, fallback_path.read_text(encoding="utf-8")



def _install_skill_via_clawhub(name: str) -> tuple[str, str]:
    node_bin, npx_bin = _resolve_clawhub_runtime()
    if not node_bin or not npx_bin:
        raise HTTPException(
            status_code=503,
            detail="未找到内置 Node runtime 或 npx，无法执行 ClawHub 下载。",
        )

    with tempfile.TemporaryDirectory(prefix="naga-clawhub-") as tmp:
        workdir = Path(tmp)
        try:
            subprocess.run(
                [
                    node_bin,
                    npx_bin,
                    "--yes",
                    "clawhub@latest",
                    "--no-input",
                    "--workdir",
                    str(workdir),
                    "--dir",
                    "skills",
                    "install",
                    name,
                    "--force",
                ],
                check=True,
                cwd=str(workdir),
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or exc.stdout or "").strip()
            raise HTTPException(status_code=502, detail=f"ClawHub 安装失败: {stderr or exc}") from exc

        direct_path = workdir / "skills" / name / "SKILL.md"
        if direct_path.exists():
            return name, direct_path.read_text(encoding="utf-8")

        fallback_path = next(workdir.rglob("SKILL.md"), None)
        if fallback_path is None:
            raise HTTPException(status_code=502, detail="ClawHub 安装完成，但未找到 SKILL.md")

        resolved_name = fallback_path.parent.name or name
        return resolved_name, fallback_path.read_text(encoding="utf-8")



def _fetch_hub_payload(kind: str, name: str, source: str = "tencent-skillhub") -> tuple[str, Any]:
    url = _build_hub_url(kind, name, source)
    headers = {"User-Agent": "陆墨/hub-installer"}
    if naga_auth.is_authenticated():
        token = naga_auth.get_access_token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
    try:
        request = UrlRequest(url, headers=headers)
        with urlopen(request, timeout=20) as response:
            content_type = response.headers.get("Content-Type", "")
            body = response.read()
        text = body.decode("utf-8")
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"陆墨Hub 不可达: {exc}")

    if "json" in content_type.lower():
        try:
            return content_type, json.loads(text)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=502, detail=f"陆墨Hub 返回了无效 JSON: {exc}")
    return content_type, text



def _parse_hub_skill_payload(name: str, payload: Any) -> tuple[str, str]:
    if isinstance(payload, dict):
        content = payload.get("content") or payload.get("skill") or payload.get("template") or payload.get("markdown")
        resolved_name = str(payload.get("name") or name).strip() or name
        if not isinstance(content, str) or not content.strip():
            raise HTTPException(status_code=502, detail="陆墨Hub skill 模板缺少 content")
        return resolved_name, content
    if isinstance(payload, str) and payload.strip():
        return name, payload
    raise HTTPException(status_code=502, detail="陆墨Hub skill 模板为空")



def _parse_hub_mcp_payload(name: str, payload: Any) -> tuple[str, str | None, str | None, dict[str, Any]]:
    if isinstance(payload, dict):
        resolved_name = str(payload.get("name") or name).strip() or name
        display_name = payload.get("display_name") or payload.get("displayName")
        description = payload.get("description")
        config = payload.get("config") if isinstance(payload.get("config"), dict) else payload
        clean_config = {k: v for k, v in config.items() if not str(k).startswith("_")} if isinstance(config, dict) else None
        if not clean_config:
            raise HTTPException(status_code=502, detail="陆墨Hub MCP 模板缺少 config")
        return resolved_name, display_name, description, clean_config
    if isinstance(payload, str) and payload.strip():
        try:
            config = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=502, detail=f"陆墨Hub MCP 模板不是合法 JSON: {exc}")
        if not isinstance(config, dict):
            raise HTTPException(status_code=502, detail="陆墨Hub MCP 模板必须返回 JSON 对象")
        return name, None, None, config
    raise HTTPException(status_code=502, detail="陆墨Hub MCP 模板为空")



@router.post("/hub/skills/install")
async def install_skill_from_hub(request: HubInstallRequest):
    telemetry_props = {
        "requested_name": request.name,
        "scope": request.scope,
        "agent_id": request.agent_id,
        "source": "hub",
        "hub_source": request.source,
    }
    try:
        normalized_source = (request.source or "").strip().lower()
        if normalized_source == "tencent-skillhub":
            skill_name, content = _install_skill_via_tencent_skillhub(request.name)
        elif normalized_source == "clawhub":
            skill_name, content = _install_skill_via_clawhub(request.name)
        else:
            _, payload = _fetch_hub_payload("skill", request.name, request.source)
            skill_name, content = _parse_hub_skill_payload(request.name, payload)
        telemetry_props["resolved_name"] = skill_name
        skill_path = _write_skill_to_scope(skill_name, content, request.scope, request.agent_id)
    except HTTPException as exc:
        _emit_extensions_telemetry(
            "hub_skill_install_fail",
            {
                **telemetry_props,
                "status_code": exc.status_code,
                "error": exc.detail,
            },
            agent_id=(request.agent_id or "").strip() or None,
        )
        raise
    except Exception as exc:
        _emit_extensions_telemetry(
            "hub_skill_install_fail",
            {
                **telemetry_props,
                "error": exc,
            },
            agent_id=(request.agent_id or "").strip() or None,
        )
        raise
    _emit_extensions_telemetry("hub_skill_install_success", telemetry_props, agent_id=(request.agent_id or "").strip() or None)
    return {
        "status": "success",
        "message": f"已从 Hub 安装技能: {skill_name}",
        "scope": request.scope,
        "path": str(skill_path),
        "name": skill_name,
        "source": "hub",
    }



@router.post("/hub/mcp/install")
async def install_mcp_from_hub(request: HubInstallRequest):
    telemetry_props = {
        "requested_name": request.name,
        "scope": request.scope,
        "agent_id": request.agent_id,
        "source": "hub",
        "hub_source": request.source,
    }
    try:
        normalized_source = (request.source or "").strip().lower()
        if normalized_source == "mcp.so":
            mcp_name, display_name, description, config = _install_mcp_via_mcpso(request.name)
        elif normalized_source == "tencent-skillhub":
            raise HTTPException(status_code=400, detail="腾讯 SkillHub 当前只支持 Skill CLI 安装，暂不支持 MCP 模板下载")
        elif normalized_source == "clawhub":
            raise HTTPException(status_code=400, detail="ClawHub 当前只支持 Skill 下载，暂不支持 MCP 模板下载")
        else:
            _, payload = _fetch_hub_payload("mcp", request.name, request.source)
            mcp_name, display_name, description, config = _parse_hub_mcp_payload(request.name, payload)

        scope = _normalize_mcp_scope(request.scope, strict=True)
        agent_id = (request.agent_id or "").strip() or None
        if scope == "private":
            if not agent_id:
                raise HTTPException(status_code=400, detail="私有 MCP 必须指定 agent_id")
            if not _get_agent_record(agent_id):
                raise HTTPException(status_code=404, detail="目标干员不存在")

        telemetry_props.update(
            {
                "resolved_name": mcp_name,
                "scope": scope,
                "agent_id": agent_id,
                "config_keys": _telemetry_config_keys(config),
                "has_display_name": bool((display_name or "").strip()) if isinstance(display_name, str) else bool(display_name),
                "has_description": bool((description or "").strip()) if isinstance(description, str) else bool(description),
            }
        )

        MCPORTER_DIR.mkdir(parents=True, exist_ok=True)
        mcporter_config = _load_mcporter_config()
        servers = mcporter_config.setdefault("mcpServers", {})
        servers[mcp_name] = _attach_mcp_meta(
            config,
            display_name=display_name,
            description=description,
            scope=scope,
            agent_id=agent_id,
        )
        mcporter_config["mcpServers"] = servers
        MCPORTER_CONFIG_PATH.write_text(
            json.dumps(mcporter_config, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        _refresh_mcp_runtime_state(preheat_service_names=_list_public_enabled_external_mcp_names())
    except HTTPException as exc:
        _emit_extensions_telemetry(
            "hub_mcp_install_fail",
            {
                **telemetry_props,
                "status_code": exc.status_code,
                "error": exc.detail,
            },
            agent_id=(request.agent_id or "").strip() or None,
        )
        raise
    except Exception as exc:
        _emit_extensions_telemetry(
            "hub_mcp_install_fail",
            {
                **telemetry_props,
                "error": exc,
            },
            agent_id=(request.agent_id or "").strip() or None,
        )
        raise
    _emit_extensions_telemetry("hub_mcp_install_success", telemetry_props, agent_id=agent_id)
    return {
        "status": "success",
        "message": f"已从 Hub 安装 MCP: {mcp_name}",
        "scope": scope,
        "name": mcp_name,
        "source": "hub",
    }

# ruff: noqa: F405  # 薄壳模式：星号聚合导入的公共名（导出面由 tools/verify_export_parity.py 钉住）
