"""MCP 装配策略 + 依赖预检：按 manifest 的 classification 与 requires 判定能力状态。

**纯函数核心**——不依赖 FastAPI / 路由 / 包级导入链，便于单元测试。
配置读写走显式路径参数，不在模块级绑定全局路径。

两部分：
1. **装配策略**（classification → enabled）：决定内置 agent 默认启用与否
2. **依赖预检**（requires → ready/missing）：判定环境是否具备
   （供 `GET /mcp/services` 与 `check_agent_requirements.py` 共用——单一真源）

判定优先级（高 → 低）：
    1. ``agent_overrides[name]``    —— 用户在前端的显式开关
    2. ``disabled_agents``          —— 显式黑名单
    3. ``disable_tiers``            —— 按 tier 关（如默认关 offensive）
    4. ``enabled_families``         —— 只启用选中的族（空 = 不限）
    5. 默认启用

**缺省（策略为空 dict）= 全启用**，保证引入本模块不改变既有行为。

设计见 ``docs/总线能力标签体系-2026-09-29.md``「装配策略」一节。
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import socket
from pathlib import Path
from typing import Any

# config.json 里承载装配策略的位置
CONFIG_SECTION = "mcp_server"
CONFIG_SUBKEY = "assembly"

# 词汇表（单一真源）：check_classification.py 与 GET /mcp/assembly 都从这里取。
# 与 docs/总线能力标签体系-2026-09-29.md 的一致性由该脚本静态校验兜底。
KNOWN_FAMILIES = (
    "context", "document", "code", "verbal", "compute",
    "instrument", "offense", "ecology", "semantic",
)
KNOWN_TIERS = ("read-only", "local-write", "process-control", "offensive")
KNOWN_POLICY_KEYS = ("enabled_families", "disable_tiers", "disabled_agents", "agent_overrides")


def empty_policy() -> dict[str, Any]:
    """空策略：等价于「全启用」。"""
    return {}


def load_policy(config_path: str | Path) -> dict[str, Any]:
    """读 config 的 mcp_server.assembly；缺失/不可解析/类型不符时返回空策略。"""
    try:
        raw = json.loads(Path(config_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty_policy()
    section = raw.get(CONFIG_SECTION)
    if not isinstance(section, dict):
        return empty_policy()
    policy = section.get(CONFIG_SUBKEY)
    return policy if isinstance(policy, dict) else empty_policy()


def decide_enabled(
    name: str, classification: dict[str, Any] | None, policy: dict[str, Any] | None
) -> tuple[bool, str | None]:
    """判定某个 agent 是否启用，返回 ``(enabled, disabled_reason)``。

    ``classification`` 取 manifest 的 ``classification`` 块（families / tier）。
    ``policy`` 取 :func:`load_policy` 的结果；空字典表示全启用。
    """
    if not policy:
        return True, None
    cls = classification or {}

    overrides = policy.get("agent_overrides")
    if isinstance(overrides, dict) and name in overrides:
        return (True, None) if overrides[name] else (False, "user_disabled")

    disabled_agents = policy.get("disabled_agents") or []
    if name in disabled_agents:
        return False, "in_disabled_agents"

    tier = str(cls.get("tier") or "")
    disable_tiers = policy.get("disable_tiers") or []
    if tier and tier in disable_tiers:
        return False, f"tier:{tier}"

    families = {str(f) for f in (cls.get("families") or [])}
    enabled_families = policy.get("enabled_families") or []
    # 未分类的 agent 不参与族过滤（避免因分类缺失被静默关掉）
    if enabled_families and families and not (families & {str(f) for f in enabled_families}):
        return False, "family_not_enabled"

    return True, None


def set_agent_override(config_path: str | Path, name: str, enabled: bool) -> dict[str, Any]:
    """把显式开关写入 ``config.json`` 的 ``mcp_server.assembly.agent_overrides``。

    返回更新后的完整 config 字典。路径不可读/结构不符时抛 ``ValueError``，
    由调用方翻译成 HTTP 错误。
    """
    p = Path(config_path)
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"config.json 不可读写: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError("config.json 顶层不是对象")

    section = raw.setdefault(CONFIG_SECTION, {})
    if not isinstance(section, dict):
        raise ValueError(f"config.json 的 {CONFIG_SECTION} 不是对象")
    assembly = section.setdefault(CONFIG_SUBKEY, {})
    if not isinstance(assembly, dict):
        raise ValueError(f"config.json 的 {CONFIG_SUBKEY} 不是对象")
    overrides = assembly.setdefault("agent_overrides", {})
    if not isinstance(overrides, dict):
        raise ValueError("agent_overrides 不是对象")

    overrides[name] = bool(enabled)
    p.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    return raw


def set_policy(config_path: str | Path, updates: dict[str, Any]) -> dict[str, Any]:
    """写装配策略（``enabled_families`` / ``disable_tiers`` / ``disabled_agents``）。

    - 值为 ``None`` → 删除该键（该维度回到「不限」的缺省语义）
    - 值为 list → 全量替换（families/tiers 逐项校验词汇表，非法项抛 ``ValueError``）
    - ``agent_overrides`` 不在此写（走 :func:`set_agent_override`，语义是按 agent
      显式开关而非策略维度）；传入即抛 ``ValueError``
    - 未知键忽略——宁可少写不误写

    返回更新后的完整 config 字典。路径不可读/结构不符时抛 ``ValueError``。
    """
    p = Path(config_path)
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"config.json 不可读写: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError("config.json 顶层不是对象")

    assembly = raw.setdefault(CONFIG_SECTION, {}).setdefault(CONFIG_SUBKEY, {})
    if not isinstance(assembly, dict):
        raise ValueError(f"config.json 的 {CONFIG_SECTION}.{CONFIG_SUBKEY} 不是对象")

    for key, value in updates.items():
        if key == "agent_overrides":
            raise ValueError("agent_overrides 请走按 agent 的开关接口（PUT /mcp/services/{name}）")
        if key not in ("enabled_families", "disable_tiers", "disabled_agents"):
            continue
        if value is None:
            assembly.pop(key, None)
            continue
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise ValueError(f"{key} 必须是字符串列表或 null")
        if key == "enabled_families":
            bad = [v for v in value if v not in KNOWN_FAMILIES]
            if bad:
                raise ValueError(f"未知族: {bad}（词汇表: {list(KNOWN_FAMILIES)}）")
        if key == "disable_tiers":
            bad = [v for v in value if v not in KNOWN_TIERS]
            if bad:
                raise ValueError(f"未知 tier: {bad}（词汇表: {list(KNOWN_TIERS)}）")
        assembly[key] = value

    p.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    return raw


# ============ 依赖预检（requires → 环境是否具备） ============
# 单一真源：check_agent_requirements.py 脚本与 GET /mcp/services 都从这里取逻辑。


def check_python_package(pkg: str) -> bool:
    try:
        return importlib.util.find_spec(pkg) is not None
    except (ImportError, ValueError):
        return False


def check_service(spec: str, timeout: float = 0.5) -> bool:
    """`name@host:port` 或 `host:port` 形式的 TCP 探测。"""
    if ":" not in spec:
        return False
    host_part, port_part = spec.rsplit(":", 1)
    host = host_part.split("@", 1)[1] if "@" in host_part else host_part
    try:
        with socket.create_connection((host, int(port_part)), timeout=timeout):
            return True
    except (OSError, ValueError):
        return False


def _iter_requirement_entries(entries: Any) -> list[tuple[str, bool]]:
    """解析 requires 条目列表，兼容两种形态。

    - 字符串 ``"numpy"`` → (name, required=True)
    - 对象 ``{"name": "docling", "optional": true}`` → (name, required=False)

    其他形态（dict 缺 name / 非字符串标量）忽略——宁可少判不误判。
    """
    out: list[tuple[str, bool]] = []
    if not isinstance(entries, list):
        return out
    for item in entries:
        if isinstance(item, str) and item.strip():
            out.append((item.strip(), True))
        elif isinstance(item, dict) and isinstance(item.get("name"), str) and item["name"].strip():
            is_optional = bool(item.get("optional"))
            out.append((item["name"].strip(), not is_optional))
    return out


def check_requirements(
    req: dict[str, Any] | None,
) -> tuple[list[str], list[str], list[str]]:
    """按 requires 块判定环境是否具备。

    返回 ``(missing, optional_missing, available)``，元素形如 ``python:frida`` /
    ``cli:nuclei`` / ``svc:ollama@127.0.0.1:11434``。``req`` 非 dict（未声明）
    时返回空三元组。

    条目缺省为必须（进 missing）；声明为 optional 的软依赖缺失时进
    ``optional_missing``——语义是「缺了功能降级但 agent 可用」，不作为
    不可用依据。格式见 ``_iter_requirement_entries``。
    """
    missing: list[str] = []
    optional_missing: list[str] = []
    available: list[str] = []
    if not isinstance(req, dict):
        return missing, optional_missing, available
    for pkg, required in _iter_requirement_entries(req.get("python_packages")):
        tag = f"python:{pkg}"
        if check_python_package(pkg):
            available.append(tag)
        elif required:
            missing.append(tag)
        else:
            optional_missing.append(tag)
    for cli, required in _iter_requirement_entries(req.get("external_cli")):
        tag = f"cli:{cli}"
        if shutil.which(cli):
            available.append(tag)
        elif required:
            missing.append(tag)
        else:
            optional_missing.append(tag)
    for srv, required in _iter_requirement_entries(req.get("services")):
        tag = f"svc:{srv}"
        if check_service(srv):
            available.append(tag)
        elif required:
            missing.append(tag)
        else:
            optional_missing.append(tag)
    return missing, optional_missing, available
