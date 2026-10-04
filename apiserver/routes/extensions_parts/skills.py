"""技能目录、导入、克隆与删除（卷190-A1：从 extensions.py 纯搬移）。"""
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



def _write_skill_file(skill_name: str, content: str) -> Path:
    return _write_skill_file_to_dir(OPENCLAW_SKILLS_DIR, skill_name, content)



def _normalize_skill_name(skill_name: str) -> str:
    name = (skill_name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="技能名称不能为空")
    if len(name) > MAX_SKILL_NAME_LENGTH:
        raise HTTPException(status_code=400, detail=f"技能名称不能超过 {MAX_SKILL_NAME_LENGTH} 个字符")
    if name in {".", ".."}:
        raise HTTPException(status_code=400, detail="技能名称不能是路径保留名称")
    if "/" in name or "\\" in name:
        raise HTTPException(status_code=400, detail="技能名称不能包含路径分隔符")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in name):
        raise HTTPException(status_code=400, detail="技能名称不能包含控制字符")

    posix_path = PurePosixPath(name)
    windows_path = PureWindowsPath(name)
    if posix_path.is_absolute() or windows_path.is_absolute() or windows_path.drive or windows_path.root:
        raise HTTPException(status_code=400, detail="技能名称不能是绝对路径或盘符路径")
    return name



def _resolve_child_dir(base_dir: Path, child_name: str, label: str = "技能名称") -> Path:
    name = _normalize_skill_name(child_name)
    base = base_dir.resolve(strict=False)
    target = (base / name).resolve(strict=False)
    try:
        target.relative_to(base)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"{label} 指向了不允许的目录")
    if target == base:
        raise HTTPException(status_code=400, detail=f"{label} 不能指向根目录")
    return target



def _resolve_skill_dir(base_dir: Path, skill_name: str) -> Path:
    return _resolve_child_dir(base_dir, skill_name, "技能名称")



def _resolve_agent_skills_dir(agent_id: str) -> Path:
    agent_dir = _resolve_child_dir(NAGA_AGENTS_DIR, agent_id, "agent_id")
    return agent_dir / "skills"



def _write_skill_file_to_dir(base_dir: Path, skill_name: str, content: str) -> Path:
    skill_dir = _resolve_skill_dir(base_dir, skill_name)
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_path = skill_dir / "SKILL.md"
    skill_path.write_text(content, encoding="utf-8")
    return skill_path



def _load_agents_manifest() -> list[dict[str, Any]]:
    if not NAGA_AGENTS_MANIFEST_PATH.exists():
        return []
    try:
        data = json.loads(NAGA_AGENTS_MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []
    agents = data.get("agents")
    return agents if isinstance(agents, list) else []



def _get_agent_record(agent_id: str) -> dict[str, Any] | None:
    for agent in _load_agents_manifest():
        if agent.get("id") == agent_id:
            return agent
    return None



def _parse_skill_summary(
    skill_dir: Path,
    scope: str,
    source: str,
    owner: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    skill_path = skill_dir / "SKILL.md"
    if not skill_path.exists():
        return None

    name = skill_dir.name
    description = ""
    version = "1.0.0"
    tags: list[str] = []

    try:
        content = skill_path.read_text(encoding="utf-8")
        match = SKILL_FRONTMATTER_PATTERN.match(content)
        if match:
            metadata = yaml.safe_load(match.group(1)) or {}
            name = metadata.get("name") or name
            description = metadata.get("description") or ""
            version = metadata.get("version") or version
            tags = list(metadata.get("tags") or [])
        if not description:
            for line in content.splitlines():
                stripped = line.strip()
                if stripped and stripped != "---" and not stripped.startswith("#"):
                    description = stripped[:120]
                    break
    except Exception as exc:
        logger.warning(f"读取技能摘要失败 [{skill_path}]: {exc}")
        description = "技能内容解析失败"

    item = {
        "name": name,
        "description": description,
        "version": version,
        "tags": tags,
        "scope": scope,
        "source": source,
        "path": str(skill_path),
    }
    if owner:
        item.update({
            "owner_agent_id": owner.get("id"),
            "owner_agent_name": owner.get("name"),
            "owner_engine": owner.get("engine", "openclaw"),
        })
    return item



def _list_skill_dir(
    base_dir: Path,
    scope: str,
    source: str,
    owner: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if not base_dir.exists():
        return []

    items: list[dict[str, Any]] = []
    for skill_dir in sorted(base_dir.iterdir()):
        if not skill_dir.is_dir() or skill_dir.name.startswith("."):
            continue
        item = _parse_skill_summary(skill_dir, scope=scope, source=source, owner=owner)
        if item:
            items.append(item)
    return items



def _copy_template_dir(template_name: str, skill_name: str) -> None:
    template_dir = SKILLS_TEMPLATE_DIR / template_name
    if not template_dir.exists():
        raise FileNotFoundError(f"模板不存在: {template_dir}")
    skill_dir = OPENCLAW_SKILLS_DIR / skill_name
    for path in template_dir.rglob("*"):
        if path.is_dir():
            continue
        relative = path.relative_to(template_dir)
        target_path = skill_dir / relative
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target_path)



# ============ 技能导入 ============


class SkillImportRequest(BaseModel):
    name: str
    content: str
    scope: str | None = None
    agent_id: str | None = None



class SkillCloneRequest(BaseModel):
    name: str
    source_scope: str
    target_scope: str = "private"
    source_agent_id: str | None = None
    target_agent_id: str | None = None



def _render_skill_file_content(name: str, content: str) -> str:
    raw = (content or "").strip()
    if SKILL_FRONTMATTER_PATTERN.match(raw):
        return raw + ("\n" if not raw.endswith("\n") else "")
    return f"""---
name: {name}
description: 用户自定义技能
version: 1.0.0
author: User
tags:
  - custom
enabled: true
---

{raw}
"""



def _write_skill_to_scope(name: str, content: str, scope: str, agent_id: str | None = None) -> Path:
    name = _normalize_skill_name(name)
    rendered_content = _render_skill_file_content(name, content)

    if scope == "openclaw-local":
        return _write_skill_file(name, rendered_content)
    if scope == "cache":
        return _write_skill_file_to_dir(NAGA_CACHE_SKILLS_DIR, name, rendered_content)
    if scope == "public":
        path = _write_skill_file_to_dir(NAGA_PUBLIC_SKILLS_DIR, name, rendered_content)
        try:
            from system.skill_manager import get_skill_manager

            get_skill_manager().refresh()
        except Exception:
            pass
        return path
    if scope == "private":
        agent_id = (agent_id or "").strip()
        if not agent_id:
            raise HTTPException(status_code=400, detail="私有技能必须指定 agent_id")
        agent = _get_agent_record(agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="目标干员不存在")
        agent_skill_dir = _resolve_agent_skills_dir(agent_id)
        return _write_skill_file_to_dir(agent_skill_dir, name, rendered_content)

    raise HTTPException(status_code=400, detail=f"未知技能范围: {scope}")



def _delete_skill_from_scope(name: str, scope: str, agent_id: str | None = None) -> Path:
    name = _normalize_skill_name(name)
    if scope == "cache":
        candidates = [_resolve_skill_dir(NAGA_CACHE_SKILLS_DIR, name), _resolve_skill_dir(OPENCLAW_SKILLS_DIR, name)]
    elif scope == "public":
        candidates = [_resolve_skill_dir(NAGA_PUBLIC_SKILLS_DIR, name)]
    elif scope == "private":
        agent_id = (agent_id or "").strip()
        if not agent_id:
            raise HTTPException(status_code=400, detail="私有技能必须指定 agent_id")
        candidates = [_resolve_skill_dir(_resolve_agent_skills_dir(agent_id), name)]
    else:
        raise HTTPException(status_code=400, detail=f"未知技能范围: {scope}")

    for path in candidates:
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
            if scope == "public":
                try:
                    from system.skill_manager import get_skill_manager

                    get_skill_manager().refresh()
                except Exception:
                    pass
            return path
    raise HTTPException(status_code=404, detail=f"技能不存在: {name}")



def _read_skill_content_from_scope(name: str, scope: str, agent_id: str | None = None) -> str:
    name = _normalize_skill_name(name)
    candidates: list[Path]
    if scope == "cache":
        candidates = [
            _resolve_skill_dir(NAGA_CACHE_SKILLS_DIR, name) / "SKILL.md",
            _resolve_skill_dir(OPENCLAW_SKILLS_DIR, name) / "SKILL.md",
        ]
    elif scope == "public":
        candidates = [_resolve_skill_dir(NAGA_PUBLIC_SKILLS_DIR, name) / "SKILL.md"]
    elif scope == "private":
        agent_id = (agent_id or "").strip()
        if not agent_id:
            raise HTTPException(status_code=400, detail="私有技能必须指定 source_agent_id")
        candidates = [_resolve_skill_dir(_resolve_agent_skills_dir(agent_id), name) / "SKILL.md"]
    else:
        raise HTTPException(status_code=400, detail=f"未知技能范围: {scope}")

    for path in candidates:
        if path.exists():
            return path.read_text(encoding="utf-8")
    raise HTTPException(status_code=404, detail=f"技能不存在: {name}")



def _build_skill_catalog() -> dict[str, Any]:
    public_skills = _list_skill_dir(
        NAGA_PUBLIC_SKILLS_DIR,
        scope="public",
        source="naga-public",
    )
    cache_skills = _list_skill_dir(
        NAGA_CACHE_SKILLS_DIR,
        scope="cache",
        source="naga-cache",
    ) + _list_skill_dir(
        OPENCLAW_SKILLS_DIR,
        scope="cache",
        source="openclaw-local",
    )

    private_skills: list[dict[str, Any]] = []
    for agent in _load_agents_manifest():
        agent_id = agent.get("id")
        if not agent_id:
            continue
        try:
            agent_dir = _resolve_agent_skills_dir(str(agent_id))
        except HTTPException:
            continue
        private_skills.extend(
            _list_skill_dir(
                agent_dir,
                scope="private",
                source="agent-private",
                owner=agent,
            ),
        )

    return {
        "remote_hub": {
            "status": "configured",
            "base_url": _hub_base_url("tencent-skillhub"),
            "skill_endpoint_template": f"{_hub_base_url('tencent-skillhub')}/skill/{{skill_name}}",
            "mcp_endpoint_template": "https://mcp.so/server/{mcp_name}/modelcontextprotocol",
            "message": "当前 Skill 下载支持腾讯 SkillHub 与 ClawHub；MCP 下载当前使用 mcp.so 页面抓取。",
        },
        "local_cache": {
            "skills": cache_skills,
            "base_dirs": [str(NAGA_CACHE_SKILLS_DIR), str(OPENCLAW_SKILLS_DIR)],
        },
        "public_skills": {
            "skills": public_skills,
            "base_dir": str(NAGA_PUBLIC_SKILLS_DIR),
        },
        "private_skills": {
            "skills": private_skills,
            "base_dir": str(NAGA_AGENTS_DIR),
        },
    }



@router.get("/skills/catalog")
async def list_skill_catalog():
    return {
        "status": "success",
        "catalog": _build_skill_catalog(),
    }



@router.post("/skills/import")
async def import_custom_skill(request: SkillImportRequest):
    """创建自定义技能 SKILL.md"""
    scope = (request.scope or "openclaw-local").strip().lower()
    if scope == "legacy":
        scope = "openclaw-local"
    telemetry_props = {
        "name": request.name,
        "scope": scope,
        "agent_id": request.agent_id,
        "content_chars": len(request.content or ""),
        "has_frontmatter": bool(SKILL_FRONTMATTER_PATTERN.match((request.content or "").strip())),
    }
    # W124-05：静态 manifest 预检——frontmatter 缺 name/description 的技能直接拒绝导入
    # （装上就能查元数据、被技能检索命中，而不是跑起来才发现是坏的）
    from apiserver.skill_loader import parse_frontmatter, validate_frontmatter

    _meta, _body = parse_frontmatter(request.content or "")
    _ok, _reason = validate_frontmatter(_meta)
    if not _ok:
        _emit_extensions_telemetry(
            "skill_import_fail",
            {**telemetry_props, "status_code": 400, "error": _reason},
            agent_id=(request.agent_id or "").strip() or None,
        )
        raise HTTPException(status_code=400, detail=f"技能 frontmatter 不合法：{_reason}")
    try:
        skill_path = _write_skill_to_scope(request.name, request.content, scope, request.agent_id)
    except HTTPException as exc:
        _emit_extensions_telemetry(
            "skill_import_fail",
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
            "skill_import_fail",
            {
                **telemetry_props,
                "error": exc,
            },
            agent_id=(request.agent_id or "").strip() or None,
        )
        raise
    _emit_extensions_telemetry("skill_import_success", telemetry_props, agent_id=(request.agent_id or "").strip() or None)

    return {
        "status": "success",
        "message": f"技能已创建: {skill_path}",
        "scope": scope,
        "path": str(skill_path),
    }



@router.post("/skills/clone")
async def clone_skill(request: SkillCloneRequest):
    source_scope = (request.source_scope or "").strip().lower()
    target_scope = (request.target_scope or "private").strip().lower()
    source_agent_id = (request.source_agent_id or "").strip() or None
    target_agent_id = (request.target_agent_id or "").strip() or None

    if source_scope == "legacy":
        source_scope = "cache"
    if target_scope == "legacy":
        target_scope = "private"

    content = _read_skill_content_from_scope(request.name, source_scope, source_agent_id)
    skill_path = _write_skill_to_scope(request.name, content, target_scope, target_agent_id)

    return {
        "status": "success",
        "message": f"技能已复制: {request.name}",
        "source_scope": source_scope,
        "target_scope": target_scope,
        "path": str(skill_path),
    }



@router.delete("/skills/{name}")
async def delete_skill(name: str, scope: str, agent_id: str | None = None):
    scope = (scope or "").strip().lower()
    if scope == "legacy":
        scope = "cache"
    telemetry_props = {
        "name": name,
        "scope": scope,
        "agent_id": agent_id,
    }
    try:
        skill_path = _delete_skill_from_scope(name, scope, agent_id)
    except HTTPException as exc:
        _emit_extensions_telemetry(
            "skill_delete_fail",
            {
                **telemetry_props,
                "status_code": exc.status_code,
                "error": exc.detail,
            },
            agent_id=(agent_id or "").strip() or None,
        )
        raise
    except Exception as exc:
        _emit_extensions_telemetry(
            "skill_delete_fail",
            {
                **telemetry_props,
                "error": exc,
            },
            agent_id=(agent_id or "").strip() or None,
        )
        raise
    _emit_extensions_telemetry("skill_delete", telemetry_props, agent_id=(agent_id or "").strip() or None)
    return {
        "status": "success",
        "message": f"技能已删除: {skill_path}",
        "scope": scope,
        "path": str(skill_path),
    }

# ruff: noqa: F405  # 薄壳模式：星号聚合导入的公共名（导出面由 tools/verify_export_parity.py 钉住）
