"""MCP adapters 公共设施：Protocol 契约 + 统一 vendor 路径注入 + 工具合并 + 纳入前门禁。

P1 三件套改造的核心文件：
1. Protocol(MCPAdapterModule)：runtime_checkable，结构性契约（不继承，仅 hasattr 校验）
2. inject_vendor_path(name, *subpaths)：统一 sys.path 注入，去重 + 注入顺序确定性
3. merge_tools(source_module, mcp_server, prefix)：统一 FastMCP 工具合并（三层 for 不再复制粘贴）
4. register_capability_safe(mcp_registry, capability)：登记能力卡片，异常 warning（不再静默 pass）
5. validate_adapter(mod, name)：纳入前门禁，返回空列表=通过
6. _ADAPTER_CAPABILITY_NAMES：全局 name 注册表，register_all_adapters 检测同名冲突
"""
from __future__ import annotations

import inspect
import logging
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any, Dict, List, Protocol, TypedDict, runtime_checkable


class CapabilityDict(TypedDict, total=False):
    """adapter CAPABILITY 字段契约（与 _REQUIRED_CAPABILITY_KEYS 同源）。

    用 TypedDict 而非 dataclass：
    - 保持现有 dict 字面量写法（4 个 adapter 不需要改）
    - mypy 静态检查字段拼写错误
    - IDE 补全字段名
    """
    # === 必需字段（与 _REQUIRED_CAPABILITY_KEYS 严格对齐）===
    name: str
    displayName: str
    description: str
    version: str
    license: str
    vendor: str
    _from_adapter: str
    # === 可选字段 ===
    degradation_mode: str
    security_notice: str
    deployment_mode: str
    rust_core_available: bool


logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]  # scratchpad/
_VENDOR_TOP5 = _PROJECT_ROOT / "vendor" / "top5"
_INJECTED_VENDORS: dict[str, list[str]] = {}  # vendor_name -> list[paths injected]
_ADAPTER_CAPABILITY_NAMES: dict[str, str] = {}  # cap_name -> adapter 模块名（用于冲突检测）


def get_vendor_top5_root() -> Path:
    """返回 vendor/top5 根路径（替代直接 import _VENDOR_TOP5 私有变量）。"""
    return _VENDOR_TOP5


# =====================================================================
# 1. Protocol 契约（结构性，零运行时成本）
# =====================================================================
@runtime_checkable
class MCPAdapterModule(Protocol):
    """adapter 模块必须实现的契约。

    用法：`isinstance(mod, MCPAdapterModule)` 等价于 hasattr 三件套。
    不强制继承；仅在 adapters/__init__.py register_all_adapters 时做门禁校验。
    """

    CAPABILITY: CapabilityDict
    """模块级常量。至少含 name / displayName / description / version / license / vendor。"""

    def healthcheck(self) -> bool:
        """依赖/凭证/路径探测。失败则 register_all_adapters 跳过本 adapter。"""

    def register(self, mcp_server: Any, mcp_registry: Any = None) -> None:
        """把工具注册进 mcp_server，登记 capability 到 mcp_registry（通过 register_capability_safe）。"""


# =====================================================================
# 2. 统一 vendor 路径注入
# =====================================================================
def inject_vendor_path(name: str, *subpaths: str) -> None:
    """统一 vendor/top5/ 下 Python 路径注入，替代各 adapter 内部的 _ensure_path()。

    - 有记忆：重复调用安全（已注入的 name 不再改 sys.path）
    - memclaw 等需注入子目录的，用 subpaths 传：`inject_vendor_path("caura-memclaw", "core-api/src", "common")`
    - 顶层目录注入永远排在最前面（Python sys.path[0] 优先），子路径靠后
    - 边界校验：name / subpath 都必须在 vendor/top5/ 目录内（Path.resolve().relative_to()）
      防止构造 "../.." 跳出 vendor 目录做路径逃逸式 sys.path 劫持。
    """
    if name in _INJECTED_VENDORS:
        return
    # === 边界校验 1：name 本身不能跳出 vendor/top5 ===
    try:
        vendor_root_resolved = _VENDOR_TOP5.resolve()
        name_path_resolved = (_VENDOR_TOP5 / name).resolve()
        name_path_resolved.relative_to(vendor_root_resolved)
    except (OSError, ValueError):
        logger.warning(
            "[_common] inject_vendor_path name=%r 跳出 vendor/top5 边界（%s），拒绝注入",
            name, _VENDOR_TOP5,
        )
        return
    root = _VENDOR_TOP5 / name
    added: list[str] = []
    # 先加子路径，再加根目录（保证根目录包名查找优先于子目录同名顶层）
    for sub in reversed(subpaths):
        full = root / sub
        # === 边界校验 2：subpath 不能跳出 _VENDOR_TOP5 ===
        try:
            full_resolved = full.resolve()
            full_resolved.relative_to(vendor_root_resolved)
        except (OSError, ValueError):
            logger.warning(
                "[_common] inject_vendor_path %s subpath=%r 跳出 vendor/top5 边界，跳过敏感路径注入",
                name, sub,
            )
            continue
        # === 边界校验 2b：subpath 必须是已存在的目录 ===
        if not full.is_dir():
            logger.warning(
                "[_common] inject_vendor_path %s subpath=%r 不存在或非目录，跳过",
                name, sub,
            )
            continue
        p = str(full)
        if p not in sys.path:
            sys.path.insert(0, p)
            added.append(p)
    # === 边界校验 3：root 目录必须真实存在（避免 vendor 源目录缺失时注入空路径） ===
    if not root.is_dir():
        logger.warning(
            "[_common] inject_vendor_path name=%s: vendor 源目录不存在 (%s)，跳过根目录注入",
            name, root,
        )
        # 如果子路径也一个都没注入成功，则不记入 _INJECTED_VENDORS，允许下一次重试
        if not added:
            return
    else:
        p_root = str(root)
        if p_root not in sys.path:
            sys.path.insert(0, p_root)
            added.append(p_root)
    _INJECTED_VENDORS[name] = added


# =====================================================================
# 3. 统一 FastMCP 工具合并（四层探索：getter × toolbox）
# =====================================================================
def merge_tools(source_module: Any, mcp_server: Any, prefix: str) -> int:
    """从 source_module 的 FastMCP 实例合并 tools 到 mcp_server。

    统一替代各 adapter 里三层/四层 for 循环的复制粘贴。
    探索顺序匹配市面上 FastMCP/mcp 项目的常见属性名：
    - getter 属性：get_mcp_app() / server / mcp / app
    - toolbox 属性：_tool_manager / tools / tool_manager
    - 工具集合迭代：list_tools() / items() / 或直接 list_tools 属性

    Returns:
        成功合并的工具数量。0 表示完全没找到可合并工具。
    """
    if not hasattr(mcp_server, "add_tool"):
        return 0
    merged = 0
    for attr in ("get_mcp_app", "server", "mcp", "app"):
        getter = getattr(source_module, attr, None)
        if getter is None:
            continue
        sub = getter() if callable(getter) else getter
        if sub is None:
            continue
        for toolbox in ("_tool_manager", "tools", "tool_manager"):
            tools = getattr(sub, toolbox, None)
            if tools is None:
                continue
            try:
                iter_items: Iterable[Any]
                list_fn = getattr(tools, "list_tools", None)
                if callable(list_fn):
                    if inspect.iscoroutinefunction(list_fn):
                        logger.warning(
                            "[_common] %s.%s.list_tools 是 async，merge_tools 不支持 async，跳过该 toolbox",
                            attr, toolbox,
                        )
                        continue
                    iter_items = list_fn() or []
                elif hasattr(tools, "items") and callable(tools.items):
                    iter_items = tools.items() or []
                else:
                    try:
                        iter_items = iter(tools)  # 当作 dict/Sequence
                    except TypeError:
                        continue
                for entry in iter_items:
                    tool_name: str | None = None
                    fn: Any = None
                    if isinstance(entry, tuple):
                        tool_name, fn = entry[0], entry[1]
                    else:
                        tool_name = getattr(entry, "name", None)
                        fn = getattr(entry, "callable", None) or getattr(entry, "handler", None)
                    if not tool_name or not callable(fn):
                        continue
                    mcp_server.add_tool(fn, name=f"{prefix}_{tool_name}")
                    merged += 1
            except Exception as e:
                logger.debug("[_common] merge %s.%s tools 跳过: %s", attr, toolbox, e)
        if merged:
            break
    return merged


# =====================================================================
# 4. 登记 capability（fail-safe，不再 4 个 adapter 复制粘贴 try/except pass）
# =====================================================================
def register_capability_safe(mcp_registry: Any, capability: dict[str, Any]) -> bool:
    """登记 capability 到 mcp_registry。失败打 warning 不抛。

    与 4 个 adapter 中 `try: register_capability() except: pass` 的静默失败不同：
    这里会 warning 记录失败原因（registry 不存在/name 为空等），便于维护者定位。
    """
    if mcp_registry is None:
        return False
    fn = getattr(mcp_registry, "register_capability", None)
    if not callable(fn):
        logger.warning("[_common] mcp_registry 无 register_capability 方法，capability 未登记")
        return False
    name = str(capability.get("name", "")).strip()
    if not name:
        logger.warning("[_common] register_capability_safe 收到空 name capability，跳过")
        return False
    # 去重/冲突检测：已登记同名且来自不同 adapter → warning 覆盖
    prev = _ADAPTER_CAPABILITY_NAMES.get(name)
    who = capability.get("_from_adapter", "?")
    if prev and prev != who:
        logger.warning("[_common] CAPABILITY name=%s 冲突：原模块 %s，新模块 %s → 以新的为准", name, prev, who)
    try:
        fn(dict(capability))
    except Exception as e:
        logger.warning("[_common] register_capability(%s) 失败: %s", name, e)
        return False
    _ADAPTER_CAPABILITY_NAMES[name] = who
    return True


# =====================================================================
# 5. 纳入前门禁：validate_adapter(mod, name) → list[str] issues（空=通过）
# =====================================================================
_REQUIRED_CAPABILITY_KEYS = ("name", "displayName", "description", "version", "license", "vendor", "_from_adapter")


def validate_adapter(mod: Any, registered_name: str) -> list[str]:
    """纳入前校验。返回问题列表，空=通过。

    校验项：
    - 必须有 healthcheck / register / CAPABILITY 三要素
    - CAPABILITY 必须含 6 个必需键
    - CAPABILITY.name 必须等于模块注册名（防维护者把 CAPABILITY 配错名导致注册名 vs 能力名分裂）
    - healthcheck/register 必须 callable
    """
    issues: list[str] = []
    if not hasattr(mod, "healthcheck"):
        issues.append(f"{registered_name}: 缺 healthcheck()")
    elif not callable(mod.healthcheck):
        issues.append(f"{registered_name}: healthcheck 不是 callable")

    if not hasattr(mod, "register"):
        issues.append(f"{registered_name}: 缺 register()")
    elif not callable(mod.register):
        issues.append(f"{registered_name}: register 不是 callable")

    if not hasattr(mod, "CAPABILITY"):
        issues.append(f"{registered_name}: 缺 CAPABILITY 模块级常量")
        return issues  # 下面校验依赖 CAPABILITY 存在

    cap = mod.CAPABILITY
    if not isinstance(cap, dict):
        issues.append(f"{registered_name}: CAPABILITY 不是 dict（类型 {type(cap).__name__}）")
        return issues

    for key in _REQUIRED_CAPABILITY_KEYS:
        if key not in cap or not str(cap.get(key, "")).strip():
            issues.append(f"{registered_name}: CAPABILITY 缺/空必需字段 '{key}'")

    cap_name = str(cap.get("name", "")).strip()
    if cap_name and cap_name != registered_name:
        issues.append(
            f"{registered_name}: CAPABILITY.name='{cap_name}' 与注册名 '{registered_name}' 不一致 "
            f"（会导致工具名 headroom_xxx 对应能力卡片 vulnclaw，维护性灾难）"
        )
    cap_from = str(cap.get("_from_adapter", "")).strip()
    if cap_from and cap_from != registered_name:
        issues.append(
            f"{registered_name}: CAPABILITY._from_adapter='{cap_from}' 与注册名 '{registered_name}' 不一致 "
            f"（会导致 register_capability_safe 冲突检测误判为同一模块，覆盖不告警）"
        )
    return issues


# =====================================================================
# 6. 辅助：reset_for_tests() — 供 tests 清空全局状态（测试隔离）
# =====================================================================
def reset_for_tests() -> None:
    """测试用：清空注入记忆与 capability name 注册表。unittest setUp 时调用。"""
    _INJECTED_VENDORS.clear()
    _ADAPTER_CAPABILITY_NAMES.clear()


__all__ = [
    # Protocol + TypedDict
    "MCPAdapterModule",
    "CapabilityDict",
    # 公共 API
    "get_vendor_top5_root",
    "inject_vendor_path",
    "merge_tools",
    "register_capability_safe",
    "validate_adapter",
    # 测试辅助
    "reset_for_tests",
]
