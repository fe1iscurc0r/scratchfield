"""W124-01：Scope 原语 —— per-角色 / per-会话 的工具可见性。

现状问题：mcpserver 注册表全局可见，任何角色都能看到并调用全部工具。本模块给出
「角色 → 可见工具集」的白名单/黑名单，并**在两个层面同时生效**：

1. **展示层**：`tool_schemas.get_all_tool_schemas(agent_id)` 只返回该角色可见的工具
2. **执行层**：`agentic_tool_loop` 派发前二次校验——直接构造调用也绕不过去

设计借鉴 DeepSeek Harness 的 Scope 机制（只抄机制，不引代码）：工具名沿用
`{agentType}__{service}__{tool}` 命名，匹配规则 = 精确 + 前缀 + `*` 通配，
`denied_tools` 优先于 `allowed_tools`。

默认**全可见**（未配置角色行为不变，向后兼容）；`scope.enabled=false` 整层旁路。
"""
from __future__ import annotations

import fnmatch
import json
import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 配置与注册表
# ---------------------------------------------------------------------------


def _cfg() -> Any:
    try:
        from system.config import get_config

        return getattr(get_config(), "scope", None)
    except Exception as e:  # noqa: BLE001 - 配置不可用按「不隔离」处理（向后兼容）
        logger.debug("[scope] 读取配置失败，按全可见处理: %s", e)
        return None


def enabled() -> bool:
    cfg = _cfg()
    return bool(getattr(cfg, "enabled", True)) if cfg is not None else False


def default_visible_all() -> bool:
    cfg = _cfg()
    return bool(getattr(cfg, "default_visible_all", True)) if cfg is not None else True


def _role_configs() -> Dict[str, Dict[str, List[str]]]:
    """合并两个来源的角色配置：config.json 的 `scope.roles` + 角色注册表的 `tool_scope`。"""
    merged: Dict[str, Dict[str, List[str]]] = {}

    def _put(name: str, raw: Any) -> None:
        if not isinstance(raw, dict):
            return
        entry = {
            "allowed_tools": [str(x) for x in (raw.get("allowed_tools") or [])],
            "denied_tools": [str(x) for x in (raw.get("denied_tools") or [])],
            "skills": [str(x) for x in (raw.get("skills") or [])],
        }
        current = merged.setdefault(str(name), {"allowed_tools": [], "denied_tools": [], "skills": []})
        for key in ("allowed_tools", "denied_tools", "skills"):
            if entry[key]:
                current[key] = entry[key]

    cfg = _cfg()
    roles = getattr(cfg, "roles", None) or {}
    for name, value in dict(roles).items():
        raw = value.model_dump() if hasattr(value, "model_dump") else value
        _put(name, raw)

    for role_id, role in registry_roles().items():
        scope = role.get("tool_scope")
        if isinstance(scope, dict):
            _put(role_id, scope)
        display = str(role.get("display_name") or "").strip()
        if display and isinstance(scope, dict):
            _put(display, scope)  # 允许用中文角色名配置/引用
    return merged


def registry_path() -> Path:
    cfg = _cfg()
    configured = str(getattr(cfg, "registry_path", "") or "").strip()
    path = Path(configured or "characters/registry.json")
    if not path.is_absolute():
        path = Path(__file__).resolve().parent.parent / path
    return path


def registry_roles(*, path: Path | None = None) -> Dict[str, Dict[str, Any]]:
    """读角色注册表（characters/registry.json）的 roles 段；读不到返回空 dict。"""
    target = Path(path) if path else registry_path()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except Exception as e:  # noqa: BLE001 - 注册表损坏不影响对话
        logger.warning("[scope] 角色注册表读取失败（忽略）: %s", e)
        return {}
    roles = data.get("roles")
    return {str(k): dict(v) for k, v in roles.items() if isinstance(v, dict)} if isinstance(roles, dict) else {}


def resolve_role(*, agent_id: str | None = None, session_id: str | None = None,
                 role: str | None = None) -> str:
    """解析本次调用所属角色：显式 role > 会话绑定 > agent_id > 注册表 active_role > 空串。

    agent_id 用注册表归一化：中文显示名/别名会映射回 role_id（配置里两种写法都能用）。
    """
    if role:
        return str(role).strip()
    cfg = _cfg()
    session_roles = getattr(cfg, "session_roles", None) or {}
    if session_id and str(session_id) in dict(session_roles):
        return str(dict(session_roles)[str(session_id)]).strip()
    if agent_id:
        candidate = str(agent_id).strip()
        for role_id, entry in registry_roles().items():
            names = {role_id, str(entry.get("display_name") or ""), str(entry.get("display_name_alt") or "")}
            if candidate in {n for n in names if n}:
                return role_id
        if candidate in _role_configs():
            return candidate
        return candidate
    try:
        data = json.loads(registry_path().read_text(encoding="utf-8"))
        active = str(data.get("active_role") or "").strip()
        if active:
            return active
    except Exception:  # noqa: BLE001
        pass
    return ""


# ---------------------------------------------------------------------------
# 匹配与判定
# ---------------------------------------------------------------------------


def matches(pattern: str, tool_name: str) -> bool:
    """工具名匹配：精确 | `*` 通配 | `__` 前缀。

    - `mcp__code_workspace__code_exec` == 精确
    - `mcp__code_workspace__*` 或 `mcp__code_workspace*` == 通配
    - `mcp__code_workspace` == 前缀（匹配其下全部工具）
    """
    pat = str(pattern or "").strip()
    name = str(tool_name or "").strip()
    if not pat or not name:
        return False
    if pat == name:
        return True
    if any(ch in pat for ch in "*?["):
        return fnmatch.fnmatchcase(name, pat)
    return name.startswith(pat + "__")


def tool_visible(
    tool_name: str, *, role: str | None = None, agent_id: str | None = None,
    session_id: str | None = None,
) -> Tuple[bool, str]:
    """该工具对本次调用是否可见。返回 (visible, reason)。"""
    if not enabled():
        return True, "scope_disabled"
    resolved = resolve_role(agent_id=agent_id, session_id=session_id, role=role)
    known = _role_configs()
    if not resolved or resolved not in known:
        return (True, "unconfigured_role") if default_visible_all() else (False, "unconfigured_role_denied")
    entry = known[resolved]
    denied = entry.get("denied_tools") or []
    if any(matches(p, tool_name) for p in denied):
        return False, f"denied_by_role({resolved})"
    allowed = entry.get("allowed_tools") or []
    if not allowed:
        return True, f"role_no_whitelist({resolved})"
    if any(matches(p, tool_name) for p in allowed):
        return True, f"allowed_by_role({resolved})"
    return False, f"not_in_whitelist({resolved})"


def visible_tools(
    tool_names: Iterable[str], *, role: str | None = None, agent_id: str | None = None,
    session_id: str | None = None,
) -> List[str]:
    """过滤出可见工具名（保持入参顺序）。"""
    return [
        name for name in tool_names
        if tool_visible(name, role=role, agent_id=agent_id, session_id=session_id)[0]
    ]


def candidate_names(call_name: str, *, service_name: str = "", agent_type: str = "") -> List[str]:
    """一次调用的多个别名：限定名 / 原名 / 短名。

    native function calling 用 `mcp__svc__tool`，文本兼容期只有 `service_name` + 短工具名，
    配置里两种写法都可能出现——判定时逐个试，避免因命名形态不同误拦。
    """
    names: List[str] = []
    for value in (call_name,):
        text = str(value or "").strip()
        if text:
            names.append(text)
    short = str(call_name or "").strip()
    if short and "__" in short:
        names.append(short.rsplit("__", 1)[-1])
    if short and "__" not in short and service_name and agent_type:
        names.append(f"{agent_type}__{service_name}__{short}")
    return list(dict.fromkeys(names))


def tool_visible_any(
    names: Iterable[str], *, role: str | None = None, agent_id: str | None = None,
    session_id: str | None = None,
) -> Tuple[bool, str]:
    """多别名判定：任一命中黑名单即拒；白名单非空时需至少一个别名命中。"""
    if not enabled():
        return True, "scope_disabled"
    candidates = [n for n in names if n]
    if not candidates:
        return True, "no_name"
    resolved = resolve_role(agent_id=agent_id, session_id=session_id, role=role)
    known = _role_configs()
    if not resolved or resolved not in known:
        return (True, "unconfigured_role") if default_visible_all() else (False, "unconfigured_role_denied")
    entry = known[resolved]
    for pattern in entry.get("denied_tools") or []:
        if any(matches(pattern, name) for name in candidates):
            return False, f"denied_by_role({resolved})"
    allowed = entry.get("allowed_tools") or []
    if not allowed:
        return True, f"role_no_whitelist({resolved})"
    for pattern in allowed:
        if any(matches(pattern, name) for name in candidates):
            return True, f"allowed_by_role({resolved})"
    return False, f"not_in_whitelist({resolved})"


def filter_schemas(
    schemas: List[Dict[str, Any]], *, role: str | None = None, agent_id: str | None = None,
    session_id: str | None = None,
) -> List[Dict[str, Any]]:
    """按可见性过滤 OpenAI function calling schemas。"""
    if not enabled():
        return list(schemas)
    out: List[Dict[str, Any]] = []
    for schema in schemas:
        name = str((schema.get("function") or {}).get("name") or "")
        if not name or tool_visible(name, role=role, agent_id=agent_id, session_id=session_id)[0]:
            out.append(schema)
    return out


def is_skill_visible(skill_name: str, *, role: str | None = None, agent_id: str | None = None,
                     session_id: str | None = None) -> bool:
    """卷124-05：技能白名单判定（角色配了 skills 才过滤）。"""
    if not enabled():
        return True
    resolved = resolve_role(agent_id=agent_id, session_id=session_id, role=role)
    entry = _role_configs().get(resolved) or {}
    allowed = entry.get("skills") or []
    if not allowed:
        return True
    return any(matches(p, skill_name) for p in allowed)


def scope_summary(role: str | None = None) -> Dict[str, Any]:
    """调试/README 用：当前 Scope 状态（配置的角色数与规则）。"""
    known = _role_configs()
    return {
        "enabled": enabled(),
        "default_visible_all": default_visible_all(),
        "roles": {name: entry for name, entry in known.items()},
        "resolved_role": resolve_role(role=role) if role else "",
        "registry": str(registry_path()),
    }
