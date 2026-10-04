"""MCP 服务清单、装配策略与 mcporter 存储（卷190-A1：从 extensions.py 纯搬移）。"""
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



def _update_mcporter_firecrawl_config(api_key: str | None) -> Path:
    MCPORTER_DIR.mkdir(parents=True, exist_ok=True)
    mcporter_config: dict[str, Any] = {}
    if MCPORTER_CONFIG_PATH.exists():
        try:
            mcporter_config = json.loads(MCPORTER_CONFIG_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            mcporter_config = {}
    servers = mcporter_config.get("mcpServers")
    if not isinstance(servers, dict):
        servers = {}
    server_entry = servers.get("firecrawl-mcp")
    if not isinstance(server_entry, dict):
        server_entry = {}
    env = server_entry.get("env")
    if not isinstance(env, dict):
        env = {}
    if api_key:
        env["FIRECRAWL_API_KEY"] = api_key
    elif "FIRECRAWL_API_KEY" not in env:
        env["FIRECRAWL_API_KEY"] = "YOUR_FIRECRAWL_API_KEY"
    server_entry.update({"command": "npx", "args": ["-y", "firecrawl-mcp"], "env": env})
    servers["firecrawl-mcp"] = server_entry
    mcporter_config["mcpServers"] = servers
    MCPORTER_CONFIG_PATH.write_text(json.dumps(mcporter_config, ensure_ascii=True, indent=2), encoding="utf-8")
    return MCPORTER_CONFIG_PATH



def _ensure_mcporter_storage() -> None:
    if MCPORTER_CONFIG_PATH.exists():
        MCPORTER_DIR.mkdir(parents=True, exist_ok=True)
        return

    if LEGACY_MCPORTER_DIR.exists() and not MCPORTER_DIR.exists():
        MCPORTER_DIR.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.move(str(LEGACY_MCPORTER_DIR), str(MCPORTER_DIR))
            return
        except Exception:
            pass

    MCPORTER_DIR.mkdir(parents=True, exist_ok=True)
    if LEGACY_MCPORTER_CONFIG_PATH.exists() and not MCPORTER_CONFIG_PATH.exists():
        try:
            MCPORTER_CONFIG_PATH.write_text(
                LEGACY_MCPORTER_CONFIG_PATH.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
        except Exception:
            pass



# ============ MCP 服务列表 & 导入 ============


def _load_mcporter_config() -> dict[str, Any]:
    """读取 ~/.naga/mcporter/config.json，不存在或格式错误时返回空 dict。"""
    _ensure_mcporter_storage()
    if not MCPORTER_CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(MCPORTER_CONFIG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}



def _normalize_mcp_scope(scope: str | None, *, strict: bool = False) -> str:
    value = (scope or "public").strip().lower()
    if value not in {"public", "private"}:
        if strict:
            raise HTTPException(status_code=400, detail=f"未知 MCP 范围: {scope}")
        return "public"
    return value



def _resolve_agent_name(agent_id: str | None) -> str | None:
    if not agent_id:
        return None
    agent = _get_agent_record(agent_id)
    return str(agent.get("name") or agent_id) if agent else None



def _attach_mcp_meta(
    config: dict[str, Any],
    *,
    display_name: str | None = None,
    description: str | None = None,
    scope: str = "public",
    agent_id: str | None = None,
) -> dict[str, Any]:
    data = {k: v for k, v in config.items() if not str(k).startswith("_")}
    data["_scope"] = scope
    if display_name:
        data["_displayName"] = display_name
    if description:
        data["_description"] = description
    if scope == "private" and agent_id:
        data["_ownerAgentId"] = agent_id
    else:
        data.pop("_ownerAgentId", None)
    return data



def _list_public_enabled_external_mcp_names() -> list[str]:
    names: list[str] = []
    for name, cfg in _load_mcporter_config().get("mcpServers", {}).items():
        if not isinstance(cfg, dict):
            continue
        if cfg.get("_disabled", False):
            continue
        if _normalize_mcp_scope(cfg.get("_scope")) == "public":
            names.append(name)
    return names



def _refresh_mcp_runtime_state(preheat_service_names: list[str] | None = None) -> None:
    try:
        from mcpserver.mcp_registry import auto_register_mcp, clear_registry
        from mcpserver.mcporter_bridge import invalidate_mcporter_cache, preheat_external_mcp_services

        invalidate_mcporter_cache()
        clear_registry()
        auto_register_mcp()
        if preheat_service_names:
            preheat_external_mcp_services(preheat_service_names)
    except Exception as exc:
        logger.warning("MCP runtime refresh failed: %s", exc)

    try:
        from apiserver.tool_schemas import invalidate_schema_cache

        invalidate_schema_cache()
    except Exception as exc:
        logger.warning("MCP schema cache refresh failed: %s", exc)

    try:
        from apiserver.intent_router import invalidate_tool_list_cache

        invalidate_tool_list_cache()
    except Exception as exc:
        logger.warning("MCP intent cache refresh failed: %s", exc)



def _check_agent_available(manifest: dict[str, Any]) -> tuple[bool, str | None]:
    """深检内置 agent entryPoint 可用性（零实例化）。

    复用 mcp_registry.verify_entrypoint：解析 entryPoint → 前缀白名单 → 导入
    模块 → 类存在 → handle_handoff 契约。旧实现只 __import__ 模块，class 名
    写错也会显示 available=True，与注册表运行时（create_agent_instance）语义
    不一致——本函数对齐两层语义。返回 (ok, 失败原因)。
    """
    try:
        from mcpserver.mcp_registry import verify_entrypoint

        ok, reason = verify_entrypoint(manifest)
        return ok, (reason or None)
    except Exception as e:
        # 检查器自身不可用：退回 import-only 旧语义，并显式标注降级原因
        module_path = (manifest.get("entryPoint") or {}).get("module", "")
        if not module_path:
            return False, "manifest 缺少 entryPoint"
        try:
            __import__(module_path)
            return True, None
        except Exception as imp_exc:
            logger.warning(f"MCP 模块导入失败 {module_path}: {imp_exc}")
            return False, f"模块导入失败: {imp_exc}"



# ============ MCP 装配策略（按 classification 决定内置 agent 默认启用状态） ============
#
# 设计见 docs/总线能力标签体系-2026-09-29.md「装配策略」一节。
# 优先级：agent_overrides（用户显式开关） > disabled_agents > disable_tiers
#         > enabled_families > 默认启用。
# **缺省（config.json 无 mcp_server.assembly）= 全启用**，保证既有行为不变。


def _config_json_path() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "config.json"



def _iter_builtin_manifests() -> list[tuple[Path, dict[str, Any]]]:
    """扫描 mcpserver 下所有 agent-manifest.json（get_mcp_services 与 update 共用）。"""
    mcpserver_dir = Path(__file__).resolve().parent.parent.parent / "mcpserver"
    if not mcpserver_dir.exists():
        logger.warning(f"MCP 目录不存在: {mcpserver_dir}")
        return []
    out: list[tuple[Path, dict[str, Any]]] = []
    for manifest_path in sorted(mcpserver_dir.glob("**/agent-manifest.json")):
        try:
            out.append((manifest_path, json.loads(manifest_path.read_text(encoding="utf-8"))))
        except (json.JSONDecodeError, OSError):
            continue
    return out



def _is_builtin_agent_name(name: str) -> bool:
    """判断 name 是否为内置 agent（按 manifest 的 name 字段）。"""
    for manifest_path, manifest in _iter_builtin_manifests():
        if manifest.get("name", manifest_path.parent.name) == name:
            return True
    return False




# ============ 装配策略端点（前端策略面板的数据源） ============
# 策略的判定逻辑与词汇表常量在 mcp_assembly（单一真源）；本节只做
# HTTP 编排 + 展示层文案（label/desc）。

_ASSEMBLY_VOCABULARY = {
    "families": [
        {"key": "context", "label": "上下文", "desc": "记忆、会话、知识检索类能力"},
        {"key": "document", "label": "文档", "desc": "文档解析、转换、批注类能力"},
        {"key": "code", "label": "代码", "desc": "代码生成、审查、重构、工作区类能力"},
        {"key": "verbal", "label": "言语", "desc": "对话、语音、翻译等言语交互能力"},
        {"key": "compute", "label": "计算", "desc": "数值计算、优化、数据科学类能力"},
        {"key": "instrument", "label": "仪器", "desc": "硬件、仪器、总线、电台控制类能力"},
        {"key": "offense", "label": "攻防", "desc": "渗透、扫描、逆向等攻防研究能力"},
        {"key": "ecology", "label": "生态", "desc": "与 NEKO / 外部服务的生态桥接能力"},
        {"key": "semantic", "label": "语义", "desc": "知识图谱、本体推理等语义网能力"},
    ],
    "tiers": [
        {"key": "read-only", "label": "只读", "desc": "只读不写，无副作用"},
        {"key": "local-write", "label": "本地写", "desc": "写本地文件或本地状态"},
        {"key": "process-control", "label": "进程控制", "desc": "起停进程、驱动硬件、执行命令"},
        {"key": "offensive", "label": "攻防", "desc": "双重闸门：此处关闭即不可见；能力入口另有环境变量闸门"},
    ],
}



@router.get("/mcp/assembly")
def get_mcp_assembly():
    """装配策略读取：当前策略 + 词汇表 + 逐 agent 生效判定摘要。"""
    policy = _assembly_load_policy(_config_json_path())
    agents: list[dict[str, Any]] = []
    for manifest_path, manifest in _iter_builtin_manifests():
        if manifest.get("agentType") != "mcp":
            continue
        name = manifest.get("name", manifest_path.parent.name)
        enabled, reason = _assembly_decide_enabled(
            name, manifest.get("classification") or {}, policy
        )
        entry: dict[str, Any] = {"name": name, "enabled": enabled}
        if reason:
            entry["disabled_reason"] = reason
        agents.append(entry)
    return {"policy": policy, "vocabulary": _ASSEMBLY_VOCABULARY, "agents": agents}



@router.put("/mcp/assembly")
async def update_mcp_assembly(body: dict[str, Any]):
    """装配策略写入：enabled_families / disable_tiers / disabled_agents。

    值 null = 清除该维度（回到「不限」）；list = 全量替换；缺省键不动。
    按 agent 的显式开关走 PUT /mcp/services/{name}，不接受 agent_overrides。
    """
    allowed = ("enabled_families", "disable_tiers", "disabled_agents")
    updates = {k: body[k] for k in allowed if k in body}
    if not updates:
        raise HTTPException(status_code=400, detail=f"body 需包含 {allowed} 之一")
    try:
        _assembly_set_policy(_config_json_path(), updates)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _emit_extensions_telemetry("mcp_assembly_update", {"keys": sorted(updates)})
    return {"status": "success", "message": "已更新装配策略", "updated": sorted(updates)}



@router.get("/mcp/status")
async def get_mcp_status_offline():
    """MCP Server 未启动时返回离线状态，避免前端 503"""
    return {
        "server": "offline",
        "timestamp": datetime.now().isoformat(),
        "tasks": {"total": 0, "active": 0, "completed": 0, "failed": 0},
    }



@router.get("/mcp/tasks")
async def get_mcp_tasks_offline(status: str | None = None):
    """MCP Server 未启动时返回空任务列表，避免前端 503"""
    return {"tasks": [], "total": 0}



@router.get("/mcp/services")
def get_mcp_services(agent_id: str | None = None):
    """列出所有 MCP 服务并检查可用性（同步端点，由 FastAPI 在线程池中执行）"""
    services: list[dict[str, Any]] = []

    # 1. 内置 agent（扫描 mcpserver 下所有 agent-manifest.json，与 mcp_registry 一致）
    #    启用状态由装配策略决定：缺省（config.json 无 mcp_server.assembly）= 全启用。
    #    策略依据 manifest 的 classification（families / tier），见
    #    docs/总线能力标签体系-2026-09-29.md。
    assembly_policy = _assembly_load_policy(_config_json_path())
    for manifest_path, manifest in _iter_builtin_manifests():
        if manifest.get("agentType") != "mcp":
            continue
        agent_name = manifest.get("name", manifest_path.parent.name)
        available, unavailable_reason = _check_agent_available(manifest)
        enabled, disabled_reason = _assembly_decide_enabled(
            agent_name, manifest.get("classification") or {}, assembly_policy
        )
        req = manifest.get("requires")
        req_missing, req_optional_missing, _req_all = _assembly_check_requirements(req)
        entry: dict[str, Any] = {
            "name": agent_name,
            "display_name": manifest.get("displayName", agent_name),
            "description": manifest.get("description", ""),
            "source": "builtin",
            "scope": "public",
            "owner_agent_id": None,
            "owner_agent_name": None,
            "available": available,
            "enabled": enabled,
            # 依赖预检（requires）：declared=False 表示尚未声明（见 check_agent_requirements.py）
            # missing=必须依赖缺失；optional_missing=软依赖缺失（功能降级但 agent 可用）
            "requirements": {
                "declared": isinstance(req, dict),
                "missing": req_missing,
                "optional_missing": req_optional_missing,
            },
        }
        if disabled_reason:
            entry["disabled_reason"] = disabled_reason
        if unavailable_reason:
            entry["unavailable_reason"] = unavailable_reason
        services.append(entry)

    # 2. mcporter 外部配置（~/.mcporter/config.json 中的 mcpServers）
    mcporter_config = _load_mcporter_config()
    # 打包模式下用内置运行时解析 npx/uvx 等命令
    try:
        from agentserver.openclaw.embedded_runtime import get_embedded_runtime
        _runtime = get_embedded_runtime()
    except Exception:
        _runtime = None
    for name, cfg in mcporter_config.get("mcpServers", {}).items():
        if agent_id and _normalize_mcp_scope(cfg.get("_scope")) == "private" and cfg.get("_ownerAgentId") != agent_id:
            continue
        cmd = cfg.get("command", "")
        if cmd and _runtime:
            available = _runtime.resolve_command(cmd) is not None
        else:
            available = shutil.which(cmd) is not None if cmd else False
        # 提取 meta 字段（以 _ 开头的不属于 MCP 协议本身）
        display_name = cfg.get("_displayName", name)
        description = cfg.get("_description", "")
        disabled = cfg.get("_disabled", False)
        scope = _normalize_mcp_scope(cfg.get("_scope"))
        owner_agent_id = str(cfg.get("_ownerAgentId") or "").strip() or None
        if not description and cmd:
            description = f"{cmd} {' '.join(cfg.get('args', []))}"
        # 构建干净的 config（去掉 _ 开头的 meta 字段）
        clean_config = {k: v for k, v in cfg.items() if not k.startswith("_")}
        services.append({
            "name": name,
            "display_name": display_name,
            "description": description,
            "source": "mcporter",
            "scope": scope,
            "owner_agent_id": owner_agent_id,
            "owner_agent_name": _resolve_agent_name(owner_agent_id),
            "available": available,
            "enabled": not disabled,
            "config": clean_config,
        })

    return JSONResponse(
        content={"status": "success", "services": services},
        headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
    )



class McpImportRequest(BaseModel):
    name: str
    config: dict[str, Any]
    display_name: str | None = None
    description: str | None = None
    scope: str = "public"
    agent_id: str | None = None



@router.post("/mcp/import")
async def import_mcp_config(request: McpImportRequest):
    """将 MCP JSON 配置写入 ~/.naga/mcporter/config.json"""
    telemetry_props = {
        "name": request.name,
        "scope": request.scope,
        "agent_id": request.agent_id,
        "config_keys": _telemetry_config_keys(request.config),
        "has_display_name": bool((request.display_name or "").strip()),
        "has_description": bool((request.description or "").strip()),
    }
    MCPORTER_DIR.mkdir(parents=True, exist_ok=True)
    try:
        mcporter_config = _load_mcporter_config()
        servers = mcporter_config.setdefault("mcpServers", {})
        scope = _normalize_mcp_scope(request.scope, strict=True)
        agent_id = (request.agent_id or "").strip() or None
        if scope == "private":
            if not agent_id:
                raise HTTPException(status_code=400, detail="私有 MCP 必须指定 agent_id")
            if not _get_agent_record(agent_id):
                raise HTTPException(status_code=404, detail="目标干员不存在")
        telemetry_props["scope"] = scope
        telemetry_props["agent_id"] = agent_id
        servers[request.name] = _attach_mcp_meta(
            request.config,
            display_name=request.display_name,
            description=request.description,
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
            "mcp_import_fail",
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
            "mcp_import_fail",
            {
                **telemetry_props,
                "error": exc,
            },
            agent_id=(request.agent_id or "").strip() or None,
        )
        raise
    _emit_extensions_telemetry("mcp_import_success", telemetry_props, agent_id=agent_id)
    return {"status": "success", "message": f"已添加 MCP 服务: {request.name}"}



@router.put("/mcp/services/{name}")
async def update_mcp_service(name: str, body: dict[str, Any]):
    """更新 MCP 服务配置（支持 config / displayName / description / enabled）"""
    telemetry_props = {
        "name": name,
        "changed_fields": sorted(
            field for field in ("config", "displayName", "description", "enabled") if field in body
        ),
        "config_keys": _telemetry_config_keys(body.get("config")),
    }
    try:
        # 内置 agent 不在 mcporter 配置里：其开关写入 config.json 的装配策略覆盖，
        # 而不是走下面的 mcporter 分支（此前会直接 404 —— 前端开关对内置 agent 失效）。
        if _is_builtin_agent_name(name):
            if "enabled" not in body:
                raise HTTPException(
                    status_code=400, detail=f"内置 agent {name} 仅支持切换 enabled"
                )
            try:
                _assembly_set_override(_config_json_path(), name, bool(body["enabled"]))
            except ValueError as exc:
                raise HTTPException(status_code=500, detail=str(exc)) from exc
            _emit_extensions_telemetry("mcp_service_update", telemetry_props)
            return {"status": "success", "message": f"已更新内置 agent 开关: {name}"}
        mcporter_config = _load_mcporter_config()
        servers = mcporter_config.get("mcpServers", {})
        if name not in servers:
            raise HTTPException(status_code=404, detail=f"MCP 服务 {name} 不存在")
        existing = servers[name]
        telemetry_props["scope"] = _normalize_mcp_scope(existing.get("_scope"))
        telemetry_props["agent_id"] = str(existing.get("_ownerAgentId") or "").strip() or None
        if "config" in body:
            # 替换整个配置（但保留 meta 字段）
            meta_keys = {"_displayName", "_description", "_disabled", "_scope", "_ownerAgentId"}
            old_meta = {k: v for k, v in existing.items() if k in meta_keys}
            servers[name] = {**body["config"], **old_meta}
            existing = servers[name]
        if "displayName" in body:
            existing["_displayName"] = body["displayName"]
        if "description" in body:
            existing["_description"] = body["description"]
        if "enabled" in body:
            if body["enabled"]:
                existing.pop("_disabled", None)
            else:
                existing["_disabled"] = True
        mcporter_config["mcpServers"] = servers
        MCPORTER_CONFIG_PATH.write_text(
            json.dumps(mcporter_config, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        _refresh_mcp_runtime_state(preheat_service_names=_list_public_enabled_external_mcp_names())
    except HTTPException as exc:
        _emit_extensions_telemetry(
            "mcp_service_update_fail",
            {
                **telemetry_props,
                "status_code": exc.status_code,
                "error": exc.detail,
            },
            agent_id=telemetry_props.get("agent_id"),
        )
        raise
    except Exception as exc:
        _emit_extensions_telemetry(
            "mcp_service_update_fail",
            {
                **telemetry_props,
                "error": exc,
            },
            agent_id=telemetry_props.get("agent_id"),
        )
        raise
    _emit_extensions_telemetry("mcp_service_update", telemetry_props, agent_id=telemetry_props.get("agent_id"))
    return {"status": "success", "message": f"已更新 MCP 服务: {name}"}



@router.delete("/mcp/services/{name}")
async def delete_mcp_service(name: str):
    """删除外部 MCP 服务配置"""
    telemetry_props = {"name": name}
    try:
        mcporter_config = _load_mcporter_config()
        servers = mcporter_config.get("mcpServers", {})
        if name not in servers:
            raise HTTPException(status_code=404, detail=f"MCP 服务 {name} 不存在")
        existing = servers[name]
        telemetry_props["scope"] = _normalize_mcp_scope(existing.get("_scope"))
        telemetry_props["agent_id"] = str(existing.get("_ownerAgentId") or "").strip() or None
        telemetry_props["enabled"] = not bool(existing.get("_disabled", False))
        del servers[name]
        mcporter_config["mcpServers"] = servers
        MCPORTER_CONFIG_PATH.write_text(
            json.dumps(mcporter_config, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        _refresh_mcp_runtime_state(preheat_service_names=_list_public_enabled_external_mcp_names())
    except HTTPException as exc:
        _emit_extensions_telemetry(
            "mcp_service_delete_fail",
            {
                **telemetry_props,
                "status_code": exc.status_code,
                "error": exc.detail,
            },
            agent_id=telemetry_props.get("agent_id"),
        )
        raise
    except Exception as exc:
        _emit_extensions_telemetry(
            "mcp_service_delete_fail",
            {
                **telemetry_props,
                "error": exc,
            },
            agent_id=telemetry_props.get("agent_id"),
        )
        raise
    _emit_extensions_telemetry("mcp_service_delete", telemetry_props, agent_id=telemetry_props.get("agent_id"))
    return {"status": "success", "message": f"已删除 MCP 服务: {name}"}

# ruff: noqa: F405  # 薄壳模式：星号聚合导入的公共名（导出面由 tools/verify_export_parity.py 钉住）
