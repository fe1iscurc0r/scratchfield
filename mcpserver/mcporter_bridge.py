from __future__ import annotations

import asyncio
import copy
import json
import logging
import os
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MCPORTER_DIR = Path.home() / ".mcporter"
MCPORTER_CONFIG_PATH = MCPORTER_DIR / "config.json"
_MCPORTER_LIST_TIMEOUT = 25
_MCPORTER_CALL_TIMEOUT = 60
_MCPORTER_SCHEMA_CACHE: dict[tuple[str, float], list[dict[str, Any]]] = {}


@dataclass
class ExternalMCPService:
    name: str
    config: dict[str, Any]
    manifest: dict[str, Any]


def _is_packaged() -> bool:
    return bool(getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"))


def _resolve_runtime_root() -> Path | None:
    if _is_packaged():
        meipass = Path(sys._MEIPASS)  # type: ignore[attr-defined]
        resources_dir = meipass.parent.parent
        for candidate in (resources_dir / "runtime", resources_dir / "openclaw-runtime"):
            if candidate.exists():
                return candidate
        return None

    candidate = PROJECT_ROOT / "frontend" / "backend-dist" / "runtime"
    if candidate.exists():
        return candidate
    return None


def _platform_bin(runtime_root: Path, subdir: str, name: str) -> str | None:
    base_dir = runtime_root / subdir
    if not base_dir.exists():
        return None

    if os.name == "nt":
        for ext in (".cmd", ".exe", ""):
            candidate = base_dir / f"{name}{ext}"
            if candidate.exists():
                return str(candidate)
    else:
        for prefix in ("bin/", ""):
            candidate = base_dir / f"{prefix}{name}"
            if candidate.exists():
                return str(candidate)
    return None


def _runtime_path_dirs(runtime_root: Path) -> list[str]:
    extra_dirs: list[str] = []
    for subdir in ("node", "python", "uv"):
        base_dir = runtime_root / subdir
        if not base_dir.exists():
            continue
        bin_dir = base_dir / "bin"
        if os.name == "nt":
            extra_dirs.append(str(base_dir))
        else:
            if bin_dir.exists():
                extra_dirs.append(str(bin_dir))
            extra_dirs.append(str(base_dir))
    return extra_dirs


def _sanitize_packaged_subprocess_env(env: dict[str, str]) -> dict[str, str]:
    if not _is_packaged():
        return env

    cleaned = env.copy()
    meipass = str(Path(sys._MEIPASS))  # type: ignore[attr-defined]
    for key in ("LD_LIBRARY_PATH", "DYLD_LIBRARY_PATH"):
        orig_key = f"{key}_ORIG"
        if orig_key in cleaned:
            orig_val = cleaned.get(orig_key, "")
            if orig_val:
                cleaned[key] = orig_val
            else:
                cleaned.pop(key, None)
            continue
        current_val = cleaned.get(key, "")
        if current_val and meipass in current_val:
            cleaned.pop(key, None)
    return cleaned


def _resolve_runtime_command(cmd: str, env: dict[str, str]) -> str | None:
    runtime_root = _resolve_runtime_root()
    internal_commands = {"node", "npm", "npx", "python", "python3", "pip", "pip3", "uv", "uvx"}
    if runtime_root is not None:
        mapping = {
            "node": ("node", "node"),
            "npm": ("node", "npm"),
            "npx": ("node", "npx"),
            "python": ("python", "python"),
            "python3": ("python", "python"),
            "pip": ("python", "pip"),
            "pip3": ("python", "pip"),
            "uv": ("uv", "uv"),
            "uvx": ("uv", "uvx"),
        }
        if cmd in mapping:
            subdir, name = mapping[cmd]
            resolved = _platform_bin(runtime_root, subdir, name)
            if resolved:
                return resolved
            return None

    if _is_packaged() and cmd in internal_commands:
        return None
    return shutil.which(cmd, path=env.get("PATH"))


def _build_runtime_env() -> dict[str, str]:
    env = _sanitize_packaged_subprocess_env(os.environ.copy())
    extra_dirs: list[str] = []

    runtime_root = _resolve_runtime_root()
    if runtime_root is not None:
        extra_dirs.extend(_runtime_path_dirs(runtime_root))

    vendor_bin = PROJECT_ROOT / "vendor" / "openclaw" / "node_modules" / ".bin"
    if vendor_bin.exists():
        extra_dirs.append(str(vendor_bin))

    if extra_dirs:
        current_path = env.get("PATH", "")
        env["PATH"] = os.pathsep.join([*extra_dirs, current_path]) if current_path else os.pathsep.join(extra_dirs)

    env["NO_COLOR"] = "1"
    return env


def invalidate_mcporter_cache() -> None:
    _MCPORTER_SCHEMA_CACHE.clear()


def load_mcporter_config() -> dict[str, Any]:
    if not MCPORTER_CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(MCPORTER_CONFIG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("[MCPorter] load config failed: %s", exc)
        return {}


def load_external_mcp_services(enabled_only: bool = True) -> list[ExternalMCPService]:
    services: list[ExternalMCPService] = []
    servers = load_mcporter_config().get("mcpServers", {})
    if not isinstance(servers, dict):
        return services

    for name, config in sorted(servers.items()):
        if not isinstance(config, dict):
            continue
        if enabled_only and config.get("_disabled", False):
            continue
        manifest = _build_external_manifest(name, config)
        services.append(ExternalMCPService(name=name, config=config, manifest=manifest))
    return services


def _build_external_manifest(name: str, config: dict[str, Any]) -> dict[str, Any]:
    tools = _list_mcporter_tools(name)
    if not tools:
        tools = [_build_fallback_tool_entry(name)]

    scope = str(config.get("_scope") or "public").strip().lower()
    owner_agent_id = str(config.get("_ownerAgentId") or "").strip() or None
    description = str(config.get("_description") or "").strip()
    if not description:
        command = str(config.get("command") or "").strip()
        args = config.get("args") or []
        rendered_args = " ".join(str(arg) for arg in args if arg is not None).strip()
        description = f"External MCP via {command} {rendered_args}".strip()

    return {
        "name": name,
        "displayName": str(config.get("_displayName") or name),
        "version": "external",
        "description": description,
        "author": "mcporter",
        "agentType": "mcp",
        "source": "mcporter",
        "scope": scope,
        "ownerAgentId": owner_agent_id,
        "capabilities": {
            "invocationCommands": tools,
        },
    }


def _build_fallback_tool_entry(service_name: str) -> dict[str, Any]:
    parameters = {
        "type": "object",
        "properties": {
            "external_tool_name": {
                "type": "string",
                "description": f"Target tool name inside external MCP service {service_name}",
            },
            "arguments_json": {
                "type": "string",
                "description": "JSON object string containing the external tool arguments",
            },
        },
        "required": ["external_tool_name"],
    }
    return {
        "command": "call",
        "description": f"Generic external MCP dispatch for service {service_name}",
        "parameters": parameters,
        "example": json.dumps(
            {
                "tool_name": "call",
                "external_tool_name": "search",
                "arguments_json": "{\"query\":\"...\"}",
            },
            ensure_ascii=False,
        ),
    }


def _mcporter_config_signature() -> float:
    try:
        return MCPORTER_CONFIG_PATH.stat().st_mtime
    except OSError:
        return 0.0


def _list_mcporter_tools(service_name: str) -> list[dict[str, Any]]:
    cache_key = (service_name, _mcporter_config_signature())
    cached = _MCPORTER_SCHEMA_CACHE.get(cache_key)
    if cached is not None:
        return copy.deepcopy(cached)

    tool_entries: list[dict[str, Any]] = []
    for include_schema in (True, False):
        stdout = _run_mcporter_command_sync(
            [
                "list",
                "--config",
                str(MCPORTER_CONFIG_PATH),
                "--json",
                *(["--schema"] if include_schema else []),
                service_name,
            ],
            timeout=_MCPORTER_LIST_TIMEOUT,
        )
        if not stdout:
            continue
        tool_entries = _extract_tool_entries(stdout)
        if tool_entries:
            break

    _MCPORTER_SCHEMA_CACHE[cache_key] = copy.deepcopy(tool_entries)
    # 审计 LOW L8: 缓存以 (name, mtime) 为 key，配置被 touch 会持续新增；加容量上限防长期膨胀
    if len(_MCPORTER_SCHEMA_CACHE) > 128:
        _MCPORTER_SCHEMA_CACHE.clear()
    return tool_entries


def _extract_tool_entries(raw_output: str) -> list[dict[str, Any]]:
    text = raw_output.strip()
    if not text:
        return []

    payload: Any
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return []

    tools = _find_tool_candidates(payload)
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    for tool in tools:
        command = str(tool.get("name") or "").strip()
        if not command or command in seen:
            continue
        seen.add(command)
        schema = _normalize_input_schema(
            tool.get("inputSchema") or tool.get("parameters") or tool.get("schema") or {}
        )
        entry = {
            "command": command,
            "description": str(tool.get("description") or "").strip(),
            "parameters": schema,
            "example": json.dumps(_build_example_from_schema(schema), ensure_ascii=False),
        }
        entries.append(entry)
    return entries


def _find_tool_candidates(node: Any) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            has_tool_name = isinstance(value.get("name"), str) and value.get("name")
            has_tool_shape = any(key in value for key in ("inputSchema", "parameters", "schema"))
            if has_tool_name and has_tool_shape:
                candidates.append(value)
            else:
                simple_tool_shape = has_tool_name and any(key in value for key in ("description", "title")) and not any(
                    key in value for key in ("tools", "capabilities", "mcpServers")
                )
                if simple_tool_shape:
                    candidates.append(value)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(node)
    return candidates


def _normalize_input_schema(schema: Any) -> dict[str, Any]:
    if not isinstance(schema, dict):
        return {"type": "object", "properties": {}}

    normalized = copy.deepcopy(schema)
    normalized.setdefault("type", "object")
    if normalized.get("type") != "object":
        normalized = {
            "type": "object",
            "properties": {
                "value": normalized,
            },
        }

    properties = normalized.get("properties")
    if not isinstance(properties, dict):
        normalized["properties"] = {}

    required = normalized.get("required")
    if not isinstance(required, list):
        normalized.pop("required", None)

    return normalized


def _build_example_from_schema(schema: dict[str, Any]) -> dict[str, Any]:
    properties = schema.get("properties")
    if not isinstance(properties, dict):
        return {}

    example: dict[str, Any] = {}
    for key, value in properties.items():
        example[key] = _placeholder_for_schema(value)
    return example


def _placeholder_for_schema(schema: Any) -> Any:
    if not isinstance(schema, dict):
        return "..."

    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        schema_type = next((item for item in schema_type if item != "null"), schema_type[0] if schema_type else None)

    if "default" in schema:
        return schema["default"]
    if "enum" in schema and isinstance(schema["enum"], list) and schema["enum"]:
        return schema["enum"][0]
    if schema_type == "boolean":
        return False
    if schema_type == "integer":
        return 0
    if schema_type == "number":
        return 0
    if schema_type == "array":
        return []
    if schema_type == "object":
        nested = schema.get("properties")
        if isinstance(nested, dict):
            return {key: _placeholder_for_schema(value) for key, value in nested.items()}
        return {}
    return "..."


def _resolve_mcporter_launcher() -> tuple[list[str], dict[str, str]] | None:
    env = _build_runtime_env()
    direct = _resolve_runtime_command("mcporter", env)
    if direct:
        return [direct], env

    npx = _resolve_runtime_command("npx", env)
    if npx:
        return [npx, "-y", "mcporter@latest"], env
    return None


def _run_mcporter_command_sync(args: list[str], timeout: int) -> str | None:
    launcher = _resolve_mcporter_launcher()
    if launcher is None:
        logger.warning("[MCPorter] mcporter launcher unavailable")
        return None

    base_cmd, env = launcher
    cmd = [*base_cmd, *args]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            cwd=str(MCPORTER_DIR) if MCPORTER_DIR.exists() else None,
        )
    except Exception as exc:
        logger.warning("[MCPorter] command failed: %s", exc)
        return None

    if result.returncode != 0:
        stderr = result.stderr.strip() or result.stdout.strip()
        logger.warning("[MCPorter] command failed (%s): %s", result.returncode, stderr)
        return None
    return result.stdout


class ExternalMCPAgent:
    name = "External MCP Agent"

    def __init__(self, service_name: str, config: dict[str, Any]) -> None:
        self.service_name = service_name
        self.config = config

    async def handle_handoff(self, task: dict[str, Any]) -> str:
        tool_name = str(task.get("tool_name") or "").strip()
        if tool_name == "call":
            tool_name = str(task.get("external_tool_name") or "").strip()
        if not tool_name:
            return json.dumps({"status": "error", "message": "Missing tool_name", "data": {}}, ensure_ascii=False)

        arguments = _extract_tool_arguments(task)
        try:
            stdout = await asyncio.to_thread(
                _run_external_tool_sync,
                self.service_name,
                tool_name,
                arguments,
            )
            payload = _normalize_call_output(stdout)
            return json.dumps(payload, ensure_ascii=False)
        except Exception as exc:
            logger.warning("[MCPorter] external call failed: service=%s tool=%s error=%s", self.service_name, tool_name, exc)
            return json.dumps({"status": "error", "message": str(exc), "data": {}}, ensure_ascii=False)


def _extract_tool_arguments(task: dict[str, Any]) -> dict[str, Any]:
    reserved = {
        "agentType",
        "service_name",
        "tool_name",
        "external_tool_name",
        "arguments_json",
        "_tool_call_id",
        "_original_name",
        "_original_args",
    }
    arguments = {key: value for key, value in task.items() if key not in reserved}

    raw_arguments = task.get("arguments_json")
    if isinstance(raw_arguments, str) and raw_arguments.strip():
        try:
            parsed = json.loads(raw_arguments)
            if isinstance(parsed, dict):
                arguments.update(parsed)
        except json.JSONDecodeError:
            arguments["arguments_json"] = raw_arguments
    return arguments


def _run_external_tool_sync(service_name: str, tool_name: str, arguments: dict[str, Any]) -> str:
    if not MCPORTER_CONFIG_PATH.exists():
        raise RuntimeError(f"MCP config missing: {MCPORTER_CONFIG_PATH}")

    arg_tokens = [
        _encode_mcporter_argument(key, value)
        for key, value in arguments.items()
        if value is not None
    ]
    stdout = _run_mcporter_command_sync(
        [
            "call",
            "--config",
            str(MCPORTER_CONFIG_PATH),
            f"{service_name}.{tool_name}",
            *arg_tokens,
        ],
        timeout=_MCPORTER_CALL_TIMEOUT,
    )
    if stdout is None:
        raise RuntimeError("mcporter call failed")
    return stdout


def _encode_mcporter_argument(key: str, value: Any) -> str:
    if isinstance(value, str):
        rendered = value
    else:
        rendered = json.dumps(value, ensure_ascii=False)
    return f"{key}={rendered}"


def _normalize_call_output(stdout: str) -> dict[str, Any]:
    text = stdout.strip()
    if not text:
        return {"status": "success", "message": "External MCP call completed", "data": {}}

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return {"status": "success", "message": text, "data": {"raw": text}}

    if isinstance(payload, dict):
        if isinstance(payload.get("status"), str):
            payload.setdefault("data", {})
            return payload
        if payload.get("ok") is False:
            return {
                "status": "error",
                "message": str(payload.get("error") or payload.get("message") or "External MCP call failed"),
                "data": payload,
            }
        return {
            "status": "success",
            "message": str(payload.get("message") or "External MCP call completed"),
            "data": payload,
        }

    if isinstance(payload, list):
        return {"status": "success", "message": "External MCP call completed", "data": {"items": payload}}

    return {"status": "success", "message": str(payload), "data": {"value": payload}}


def preheat_external_mcp_services(service_names: list[str] | None = None) -> None:
    """后台预热外部 MCP 的 schema 缓存，避免首次进入工具页完全冷启动。"""

    def _worker(targets: list[str]) -> None:
        for service_name in targets:
            try:
                _list_mcporter_tools(service_name)
            except Exception as exc:
                logger.debug("[MCPorter] preheat failed for %s: %s", service_name, exc)

    if service_names is None:
        service_names = [service.name for service in load_external_mcp_services(enabled_only=True)]

    targets = [name for name in service_names if name]
    if not targets:
        return

    threading.Thread(target=_worker, args=(targets,), daemon=True).start()
