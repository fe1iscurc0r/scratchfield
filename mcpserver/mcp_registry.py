"""MCP注册表 - manifest加载、agent实例创建、服务发现与查询"""

import importlib
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcpserver.mcporter_bridge import ExternalMCPAgent, load_external_mcp_services

logger = logging.getLogger(__name__)

ALLOWED_MODULE_PREFIXES = ["mcpserver.", "vendor."]

# 全局注册表
MCP_REGISTRY: dict[str, Any] = {}  # MCP服务池 {name: agent_instance}（热表：已实例化）
MANIFEST_CACHE: dict[str, Any] = {}  # manifest信息缓存 {name: manifest_dict}（冷热都在这）
_ADAPTER_CAPABILITIES: dict[str, dict[str, Any]] = {}  # adapter 非 manifest 型能力登记 {name: capability_dict}
_REGISTERED = False  # 是否已完成注册
_ADAPTER_REGISTERED = False  # adapters 是否已跑过 register_all_adapters（独立于 _REGISTERED）

# === 卷189-A1 manifest 懒加载（冷热分层）===
# 冷表：启动时只登记 manifest 占位、**不实例化** agent 类（省掉 import 各种重依赖）。
# 首次调用该服务时才 create_agent_instance 并转入 MCP_REGISTRY（热表）。
# 缺省启用；MCP_LAZY_REGISTRY=0 回退到「启动即全量实例化」的旧行为（兼容红线）。
_COLD_TABLE: dict[str, dict[str, Any]] = {}  # {name: {"manifest_path","agent_dir","manifest"}}
_COLD_HOT_FAILED: dict[str, str] = {}  # 冷表转热失败的记录 {name: 失败原因}（供 B2 结构化报错）


def _lazy_enabled() -> bool:
    """MCP_LAZY_REGISTRY：默认 1。0/false/no/off → 关闭懒加载（回退旧行为）。"""
    return os.environ.get("MCP_LAZY_REGISTRY", "1").strip().lower() not in ("0", "false", "no", "off")


def is_hot(service_name: str) -> bool:
    """该服务是否已实例化（在热表）。"""
    return service_name in MCP_REGISTRY


def cold_service_names() -> list[str]:
    """仍在冷表、尚未实例化的服务名（sorted）。"""
    return sorted(_COLD_TABLE.keys())


def all_service_names() -> list[str]:
    """全部服务名（热表 ∪ 冷表，sorted）——懒加载下的权威服务清单。"""
    return sorted(set(MCP_REGISTRY) | set(_COLD_TABLE))


def ensure_hot(service_name: str) -> Any | None:
    """把冷表服务实例化并转入热表（幂等）；已在热表直接返回实例。

    实例化失败（依赖缺失 / 入口不可解析）返回 None，并把原因记入 _COLD_HOT_FAILED，
    供调用侧做结构化报错（不抛 500 堆栈）。
    """
    inst = MCP_REGISTRY.get(service_name)
    if inst is not None:
        return inst
    cold = _COLD_TABLE.get(service_name)
    if not cold:
        return None
    manifest = cold.get("manifest") or MANIFEST_CACHE.get(service_name) or {}
    try:
        if cold.get("kind") == "mcporter":
            # 外部 MCP 服务（懒加载冷项）：存的是 mcporter service config
            agent_instance = ExternalMCPAgent(service_name, cold.get("service_config") or {})
        else:
            agent_instance = create_agent_instance(manifest, cold.get("agent_dir", ""))
    except Exception as e:  # 依赖缺失/入口异常 → 记因不抛
        _COLD_HOT_FAILED[service_name] = f"{type(e).__name__}: {e}"
        logger.warning("[MCP Registry] 冷表转热异常 %s: %s", service_name, e)
        return None
    if agent_instance is None:
        _COLD_HOT_FAILED[service_name] = "create_agent_instance 返回 None（入口不可用）"
        return None
    MCP_REGISTRY[service_name] = agent_instance
    _COLD_TABLE.pop(service_name, None)
    logger.debug("[MCP Registry] 冷表转热: %s", service_name)
    return agent_instance


def get_cold_hot_failure(service_name: str) -> str | None:
    """冷表转热失败原因（无则 None）。"""
    return _COLD_HOT_FAILED.get(service_name)


def get_service_source(service_name: str) -> str:
    """服务来源（供熔断判定豁免）：manifest（内置）/ mcporter（外部）/ adapter。"""
    if service_name in _ADAPTER_CAPABILITIES:
        return "adapter"
    m = MANIFEST_CACHE.get(service_name)
    if isinstance(m, dict) and m.get("source") in ("mcporter",):
        return "mcporter"
    return "manifest"

# === B1 跨源冲突严格化（CONFLICT_STRICT）===
# strict=1 时冲突登记从"静默 WARNING"变"可配置阻断"：
# 拒绝登记的调用方收到 CONFLICT_REJECTED，仲裁决策（OVERRIDE/REJECT）记入 _CONFLICT_LOG
CONFLICT_REJECTED = "CONFLICT_REJECTED"
_CONFLICT_LOG: list[dict[str, Any]] = []  # strict 模式仲裁日志（仅 CONFLICT_STRICT=1 时写入）
_SOURCE_PRIORITY = {"mcporter": 1, "manifest": 2, "adapter": 3}  # adapter > manifest > mcporter


def _conflict_strict_enabled() -> bool:
    """CONFLICT_STRICT 环境变量：默认 0（保持现状仅 WARNING）。1/true/yes/on 视为开启。"""
    return os.environ.get("CONFLICT_STRICT", "0").strip().lower() in ("1", "true", "yes", "on")


def _existing_sources_for(name: str) -> list[str]:
    """收集 name 当前已登记的来源列表（MANIFEST_CACHE 区分 manifest/mcporter，_ADAPTER_CAPABILITIES 为 adapter）。"""
    existing_sources: list[str] = []
    if name in MANIFEST_CACHE:
        m = MANIFEST_CACHE[name]
        if isinstance(m, dict):
            src = m.get("source")
            existing_sources.append(src if src in ("mcporter",) else "manifest")
        else:
            existing_sources.append("manifest")
    if name in _ADAPTER_CAPABILITIES:
        existing_sources.append("adapter")
    return existing_sources


def _record_conflict(name: str, new_source: str, existing_sources: list[str], action: str) -> None:
    """strict 模式仲裁决策落 _CONFLICT_LOG 并打 WARNING。action: OVERRIDE / REJECT / REJECT_SAME_SOURCE"""
    entry = {
        "name": name,
        "new_source": new_source,
        "existing_sources": list(existing_sources),
        "action": action,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    _CONFLICT_LOG.append(entry)
    logger.warning(
        "[MCP Registry] CONFLICT_STRICT=1 仲裁 name='%s'：新来源 %s vs 已有来源 %s → %s",
        name, new_source, "+".join(existing_sources), action,
    )


def _gate_cross_source_registration(name: str, new_source: str) -> str | None:
    """登记门禁（三条写入路径共用，替代直接调 _check_cross_source_conflict 后忽略返回值）。

    返回 None=放行登记；返回 CONFLICT_REJECTED=调用方必须放弃本次登记。

    CONFLICT_STRICT=0（默认）：与现状完全一致，冲突只打 WARNING（检测逻辑见
    _check_cross_source_conflict），_CONFLICT_LOG 不写，一律放行。

    CONFLICT_STRICT=1：按 _SOURCE_PRIORITY 仲裁（adapter > manifest > mcporter）：
    - 新来源优先级高于所有已有来源 → 高优先级覆盖低优先级，放行（记 OVERRIDE）。
      注意跨表不做 eviction：manifest/mcporter 住在实例表（MANIFEST_CACHE/MCP_REGISTRY），
      adapter 住在能力卡表（_ADAPTER_CAPABILITIES），覆盖方向由 _CONFLICT_LOG +
      list_registered_capabilities 的 conflict_sources 暴露；跨表清除会连带杀掉
      可用实例（get_service_instance 取不到），风险大于收益。
    - 新来源优先级 ≤ 任一已有来源（含跨源低优先级、同类源重复）→ 拒绝（记
      REJECT / REJECT_SAME_SOURCE），调用方收到 CONFLICT_REJECTED。

    new_source 取值："manifest" (scan 本地 agent-manifest) / "mcporter" (外部服务) / "adapter" (能力卡)
    """
    existing_sources = _existing_sources_for(name)
    if not existing_sources:
        return None  # 全新名字，直接放行
    conflicted = _check_cross_source_conflict(name, new_source)  # 保持 WARNING 日志现状
    if not _conflict_strict_enabled():
        return None  # 非严格模式：冲突仅 WARNING，登记照常（现状不变）
    if not conflicted:
        # 同类源重复登记：strict=0 允许覆盖（manifest 重扫等），strict=1 必拒
        _record_conflict(name, new_source, existing_sources, "REJECT_SAME_SOURCE")
        return CONFLICT_REJECTED
    new_pri = _SOURCE_PRIORITY.get(new_source, 0)
    if all(new_pri > _SOURCE_PRIORITY.get(s, 0) for s in existing_sources):
        _record_conflict(name, new_source, existing_sources, "OVERRIDE")
        return None
    _record_conflict(name, new_source, existing_sources, "REJECT")
    return CONFLICT_REJECTED


def _check_cross_source_conflict(name: str, new_source: str) -> bool:
    """跨源查重：返回 True=冲突已打 WARNING，返回 False=可安全登记。

    三张独立注册表（MANIFEST_CACHE / MCP_REGISTRY / _ADAPTER_CAPABILITIES）由三条
    写入路径各自维护。为避免 manifest/mcporter/adapter 同名能力出现卡片可见但
    调用路径错位（get_service_instance 只取 manifest 那份，工具在 adapter 命名空间），
    登记前统一调用本函数做跨源检测。

    不做阻断（强行阻断会导致 mcporter 新配服务被老 adapter 锁死无法登记），
    只打 WARNING 并在 list_registered_capabilities 里附 conflict_sources 字段。
    （阻断语义由 _gate_cross_source_registration 在 CONFLICT_STRICT=1 时叠加，本函数保持纯检测。）

    new_source 取值："manifest" (scan 本地 agent-manifest) / "mcporter" (外部服务) / "adapter" (能力卡)
    """
    existing_sources = _existing_sources_for(name)
    # 同源不算冲突（manifest 内重新扫描同名 manifest 允许覆盖）
    other_sources = [s for s in existing_sources if s != new_source]
    if other_sources:
        logger.warning(
            "[MCP Registry] name='%s' 跨源冲突：已有来源 %s，新来源 %s → "
            "list_registered_capabilities 会同时出现两条，调用 get_service_instance 只会取 manifest 那份。"
            "建议重命名其中一方，或确认后手动移除冲突源。",
            name, "+".join(other_sources), new_source,
        )
        return True
    return False


def load_manifest_file(manifest_path: Path) -> dict[str, Any] | None:
    """加载manifest文件"""
    try:
        with open(manifest_path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("加载manifest文件失败 %s: %s", manifest_path, e)
        return None


def _resolve_entrypoint(manifest: dict[str, Any], agent_dir_name: str = "") -> tuple:
    """从 manifest 解析 (module, class)，支持多种格式。

    合并自 mod/mcpserver/mcp_registry.py，支持：
    - Format A (spec):   {"entryPoint": {"module": "...", "class": "..."}}
    - Format B (legacy): {"agent_class": "...", "module": "...", "entrypoint": "..."}
    - Format C (string): entrypoint 字符串如 "agent_nuclei.handle_handoff"
    - Format D (derive): 从目录名推导 mcpserver.<name>.<name>
    """
    name = str(manifest.get("name") or agent_dir_name or "")

    # Format A: spec entryPoint（scratchpad 原生格式）
    ep = manifest.get("entryPoint")
    if isinstance(ep, dict):
        module = ep.get("module", "")
        cls = ep.get("class", "")
        if module and cls:
            return module, cls

    # Format B: legacy 扁平字段（mod 的 agent-manifest.json 用此格式）
    cls = manifest.get("agent_class") or manifest.get("class") or ""
    module = manifest.get("module") or ""
    if module and cls:
        return module, cls

    # Format C: entrypoint 字符串 "pkg.mod.func_or_class"
    entrypoint = manifest.get("entrypoint") or ""
    if entrypoint:
        parts = entrypoint.split(".")
        if len(parts) >= 2:
            module = ".".join(parts[:-1])
            return module, parts[-1]

    # Format D: 从目录名推导（最后的兜底，保证注册率）
    if name:
        module = f"mcpserver.{name}.{name}"
        try:
            mod = importlib.import_module(module)
            if hasattr(mod, "handle_handoff"):
                return module, "handle_handoff"
        except Exception:
            pass
        return module, ""

    return "", ""


def create_agent_instance(manifest: dict[str, Any], agent_dir_name: str = "") -> Any | None:
    """根据manifest创建agent实例

    支持多格式 manifest 解析（合并自 mod 版本的 _resolve_entrypoint）：
    - Format A (spec):   entryPoint.module + entryPoint.class
    - Format B (legacy): agent_class + module
    - Format C (string): entrypoint 字符串
    - Format D (derive): 从目录名推导
    """
    try:
        module_name, class_name = _resolve_entrypoint(manifest, agent_dir_name)

        if not module_name:
            logger.warning("manifest缺少entryPoint信息: %s", manifest.get('displayName', 'unknown'))
            return None

        # Format C/D 下 class 可能为空，兜底用 handle_handoff
        if not class_name:
            class_name = "handle_handoff"

        if not any(module_name.startswith(prefix) for prefix in ALLOWED_MODULE_PREFIXES):
            logger.warning("模块名不在允许列表中: %s，允许前缀: %s", module_name, ALLOWED_MODULE_PREFIXES)
            return None

        module = importlib.import_module(module_name)
        agent_class = getattr(module, class_name)
        instance = agent_class()
        return instance

    except Exception as e:
        logger.warning("创建agent实例失败 %s: %s", manifest.get('displayName', 'unknown'), e)
        return None


def verify_entrypoint(manifest: dict[str, Any], agent_dir_name: str = "") -> tuple[bool, str]:
    """零实例化深检 entryPoint：解析 → 前缀白名单 → import → getattr → handle_handoff 契约。

    与 create_agent_instance 的区别：**不实例化**。GET /mcp/services 会对每个内置
    agent 调用本函数，实例化的副作用（开连接 / 起线程 / 读配置）不可控且浪费；
    本函数只回答「运行时能否创建实例并调到 handle_handoff」。

    契约要求与注册表运行时一致：entryPoint.class 指向的类必须具备
    handle_handoff（类方法）；Format C/D 下类名为 handle_handoff，则目标本身
    须为可调用对象。

    返回 (ok, 失败原因)；ok=True 时 reason 为空串。
    """
    module_name, class_name = _resolve_entrypoint(manifest, agent_dir_name)
    if not module_name:
        return False, "manifest 缺少 entryPoint"
    if not any(module_name.startswith(p) for p in ALLOWED_MODULE_PREFIXES):
        return False, f"模块名不在允许列表: {module_name}"
    try:
        module = importlib.import_module(module_name)
    except Exception as e:
        return False, f"模块导入失败: {type(e).__name__}: {e}"
    if not class_name:
        class_name = "handle_handoff"
    target = getattr(module, class_name, None)
    if target is None:
        return False, f"模块 {module_name} 中不存在 {class_name}"
    if class_name == "handle_handoff":
        # Format C/D：目标本身就是 handoff 函数
        if not callable(target):
            return False, f"{class_name} 不是可调用对象"
    elif not hasattr(target, "handle_handoff"):
        # Format A/B：目标为类，须具备 handle_handoff（运行时按 instance.handle_handoff 调用）
        return False, f"{class_name} 缺少 handle_handoff 契约"
    return True, ""


def _trust_gate_registration(manifest: dict[str, Any], manifest_path: Path) -> str | None:
    """②-1 认知免疫层：manifest 信任门禁。

    仅当 manifest 显式携带 source/lineage 等信任元数据时评估；无元数据视为
    存量 manifest（信任基线），直接放行——默认不改变现有注册行为。

    返回 None=放行；返回字符串=拒绝原因（低信任，进隔离区不注册）。
    """
    source = manifest.get("source") or ""
    lineage = manifest.get("lineage") or ""
    if not source and not lineage:
        return None  # 存量 manifest 无信任元数据 → 信任基线放行

    from mcpserver.trust_layer import get_trust_scorer
    name = str(manifest.get("name") or manifest.get("displayName") or manifest_path.parent.name)
    assessment = get_trust_scorer().assess(
        name,
        source=source,
        signature=bool(manifest.get("signature")),
        lineage=lineage,
        reviewed=bool(manifest.get("reviewed")),
        force=False,
    )
    if assessment.quarantined:
        return (f"低信任({assessment.score}分)进隔离区: {name} — "
                f"source={source or '(空)'}, lineage={lineage or '(空)'}")
    return None


def scan_and_register_mcp_agents(mcp_dir: str = "mcpserver", *,
                                 lazy: bool | None = None) -> list[str]:
    """扫描目录中的agent-manifest.json，注册MCP类型的agent。

    lazy=None（默认）时按 MCP_LAZY_REGISTRY 环境变量决定：
    - 懒加载（默认开）：只读 manifest 写 MANIFEST_CACHE + 冷表占位，**不实例化** agent；
      首次调用时由 ensure_hot() 转热（冷启动省掉 50 个 agent 模块的 import）。
    - 关闭（MCP_LAZY_REGISTRY=0）：旧行为，扫到即实例化写入 MCP_REGISTRY。
    信任门禁与跨源门禁在两条路径下都照跑（语义不变）。
    """
    d = Path(mcp_dir)
    registered_agents = []
    lazy_mode = _lazy_enabled() if lazy is None else lazy

    for manifest_file in d.glob("**/agent-manifest.json"):
        try:
            manifest = load_manifest_file(manifest_file)
            if not manifest:
                continue

            # ②-1 认知免疫：低信任 manifest 进隔离区，不注册
            trust_block = _trust_gate_registration(manifest, manifest_file)
            if trust_block:
                logger.warning("[MCP Registry] 信任门禁拦截 %s: %s", manifest_file, trust_block)
                continue

            agent_type = manifest.get("agentType")
            display_name = manifest.get("displayName")
            name = manifest.get("name")
            # service_name 优先级：displayName → name → manifest 所在目录名
            service_name = display_name or name or manifest_file.parent.name

            if not (display_name or name):
                # manifest 缺少 displayName/name，用目录名兜底注册但标记低质量
                logger.warning("manifest缺少displayName/name字段，使用目录名兜底: %s", manifest_file)

            if agent_type == "mcp":
                # 优先使用 name 字段（英文标识）做注册 key，fallback 到 displayName
                registry_key = manifest.get("name") or service_name
                # 跨源门禁：CONFLICT_STRICT=0 仅 WARNING（现状）；=1 低优先级/同类源拒绝登记
                if _gate_cross_source_registration(registry_key, "manifest") == CONFLICT_REJECTED:
                    logger.warning(
                        "[MCP Registry] name='%s' (manifest) 登记被 CONFLICT_STRICT=1 拒绝，跳过 (%s)",
                        registry_key, manifest_file,
                    )
                    continue
                if lazy_mode:
                    # 冷表：只登记 manifest（轻量），实例化推迟到首次调用
                    MANIFEST_CACHE[registry_key] = manifest
                    _COLD_TABLE[registry_key] = {
                        "manifest_path": str(manifest_file),
                        "agent_dir": manifest_file.parent.name,
                        "manifest": manifest,
                    }
                    registered_agents.append(registry_key)
                    logger.debug("冷表登记MCP服务: %s (来自 %s)", registry_key, manifest_file)
                else:
                    agent_instance = create_agent_instance(manifest, manifest_file.parent.name)
                    if agent_instance:
                        # 实例创建成功才写入 MANIFEST_CACHE，避免半挂载状态
                        # （LLM 看到工具但调用失败）
                        MANIFEST_CACHE[registry_key] = manifest
                        MCP_REGISTRY[registry_key] = agent_instance
                        registered_agents.append(registry_key)
                        logger.info("注册MCP服务: %s (%s) (来自 %s)", registry_key, service_name, manifest_file)

        except Exception as e:
            logger.warning("处理manifest文件失败 %s: %s", manifest_file, e)
            continue

    return registered_agents


def register_external_mcp_agents() -> list[str]:
    """注册通过 mcporter 配置的外部 MCP 服务。

    懒加载（`MCP_LAZY_REGISTRY` 默认开）下**只登记冷表占位、不实例化**
    `ExternalMCPAgent` —— 与 manifest 路径口径一致，避免启动期逐个拉起外部服务；
    关闭懒加载时保持旧行为（扫到即实例化写入热表）。

    冷表项以 ``kind="mcporter"`` 标记（与 manifest 型冷项区分），
    ``ensure_hot`` 据此走 `ExternalMCPAgent` 分支。
    """
    registered_agents = []
    lazy = _lazy_enabled()
    for service in load_external_mcp_services(enabled_only=True):
        if service.name in MANIFEST_CACHE or service.name in MCP_REGISTRY:
            logger.warning("[MCP Registry] 外部MCP名称冲突，跳过注册: %s", service.name)
            continue
        # 跨源门禁：CONFLICT_STRICT=0 仅 WARNING；=1 时 mcporter 最低优先级，
        # 与 manifest/adapter 冲突一律拒绝（上方同名检查已挡 manifest 域，此处主要挡 adapter 域）
        if _gate_cross_source_registration(service.name, "mcporter") == CONFLICT_REJECTED:
            logger.warning(
                "[MCP Registry] 外部MCP %s 登记被 CONFLICT_STRICT=1 拒绝，跳过注册", service.name)
            continue
        try:
            if lazy:
                _COLD_TABLE[service.name] = {
                    "kind": "mcporter",
                    "service_config": service.config,
                    "manifest": service.manifest,
                }
                MANIFEST_CACHE[service.name] = service.manifest
                registered_agents.append(service.name)
                logger.debug("[MCP Registry] 外部MCP 冷登记（懒加载）: %s", service.name)
            else:
                agent_instance = ExternalMCPAgent(service.name, service.config)
                # 实例创建成功才写入缓存，避免半挂载状态（与 scan 路径保持一致）
                MANIFEST_CACHE[service.name] = service.manifest
                MCP_REGISTRY[service.name] = agent_instance
                registered_agents.append(service.name)
        except Exception as e:
            logger.error("[MCP Registry] 外部MCP实例化失败 %s: %s", service.name, e)
            continue
    return registered_agents


def get_service_scope(service_name: str) -> str:
    manifest = MANIFEST_CACHE.get(service_name) or {}
    return str(manifest.get("scope") or "public").strip().lower()


def get_service_owner_agent_id(service_name: str) -> str | None:
    manifest = MANIFEST_CACHE.get(service_name) or {}
    owner_agent_id = str(manifest.get("ownerAgentId") or "").strip()
    return owner_agent_id or None


def is_service_visible_to_agent(service_name: str, agent_id: str | None = None) -> bool:
    manifest = MANIFEST_CACHE.get(service_name)
    if not manifest:
        return False

    if manifest.get("source") != "mcporter":
        return True

    scope = str(manifest.get("scope") or "public").strip().lower()
    if scope != "private":
        return True

    owner_agent_id = str(manifest.get("ownerAgentId") or "").strip()
    return bool(agent_id and owner_agent_id and owner_agent_id == agent_id)


def list_visible_service_names(agent_id: str | None = None) -> list[str]:
    return [
        service_name
        for service_name in MANIFEST_CACHE.keys()
        if is_service_visible_to_agent(service_name, agent_id=agent_id)
    ]


def get_service_info(service_name: str):
    """获取服务详细信息"""
    manifest = MANIFEST_CACHE.get(service_name)
    instance = MCP_REGISTRY.get(service_name)
    if not manifest:
        return None
    return {
        "name": service_name,
        "manifest": manifest,
        "instance_class": type(instance).__name__ if instance else None,
        "tools": get_available_tools(service_name),
    }


def get_available_tools(service_name: str):
    """获取服务的可用工具列表"""
    manifest = MANIFEST_CACHE.get(service_name)
    if not manifest:
        return []
    caps = manifest.get("capabilities", {})
    if not isinstance(caps, dict):
        return []
    return caps.get("invocationCommands", [])


def get_all_services_info():
    """获取所有服务信息（以 MANIFEST_CACHE 为权威源——懒加载下冷表项也须可见）。

    注意：卷189-A1 前以 MCP_REGISTRY 为权威源；懒加载后冷表项不在 MCP_REGISTRY，
    改以 MANIFEST_CACHE 为准（manifest 型全覆盖），实例类名对冷表项为 None（未实例化）。
    """
    result = {}
    for name in MANIFEST_CACHE:
        result[name] = get_service_info(name)
    return result


def query_services_by_capability(keyword: str) -> list[dict[str, Any]]:
    """按关键词搜索服务（manifest + adapter 统一）。"""
    if not keyword or not keyword.strip():
        return []
    matched: list[dict[str, Any]] = []
    keyword_lower = keyword.lower()
    for name, manifest in MANIFEST_CACHE.items():
        desc = manifest.get("description", "").lower()
        display = manifest.get("displayName", "").lower()
        if keyword_lower in desc or keyword_lower in display:
            matched.append({"name": name, "source": "manifest"})
    for name, cap in _ADAPTER_CAPABILITIES.items():
        desc = (cap.get("description") or "").lower()
        display = (cap.get("displayName") or "").lower()
        if keyword_lower in desc or keyword_lower in display:
            matched.append({"name": name, "source": "adapter"})
    return matched


def get_service_statistics():
    """获取服务统计信息（manifest 型冷+热 + adapter 能力型）。

    卷189-A1：total_services 改为「热表 ∪ 冷表」的合并数（懒加载下不再等于 len(MCP_REGISTRY)），
    并新增 hot_services / cold_services 明细。
    """
    total_tools = 0
    names = all_service_names()
    for name in names:
        manifest = MANIFEST_CACHE.get(name, {})
        caps = manifest.get("capabilities", {})
        if isinstance(caps, dict):
            total_tools += len(caps.get("invocationCommands", []))
    return {
        "total_services": len(names),
        "total_tools": total_tools,
        "hot_services": len(MCP_REGISTRY),
        "cold_services": len(_COLD_TABLE),
        "adapter_capabilities": len(_ADAPTER_CAPABILITIES),
        "service_names": names,
        "adapter_names": list(_ADAPTER_CAPABILITIES.keys()),
    }


def register_capability(capability: dict[str, Any]) -> bool:
    """登记一个 adapter 的能力卡片（capability 查询用）。

    与 scan_and_register_mcp_agents 不同：adapter 不要求有 manifest 文件、
    不要求 MANIFEST_CACHE 已有记录、不创建 handle_handoff 实例。
    它只在搜索/查询时让能力可见，实际工具注册通过 mcp_server.add_tool 完成。

    冲突检测：同名且 _from_adapter 不同时打 warning（不阻止覆盖，保持低级 API 灵活性；
    高级门禁在 adapters/__init__.py 的 _ADAPTER_CAPABILITY_NAMES 里做跳过）。

    capability 建议字段: name displayName description version license vendor _from_adapter
    """
    name = str(capability.get("name", "")).strip()
    if not name:
        return False
    # B4 声明式鉴权：capability 声明 requires_auth → 登记守卫（凭证未配时调用被拦）
    auth = capability.get("requires_auth")
    if isinstance(auth, dict) and auth.get("provider"):
        try:
            from mcpserver.mcp_manager import register_auth_requirement
            register_auth_requirement(
                name,
                provider=str(auth["provider"]),
                scopes=auth.get("scopes"),
                env_key=auth.get("env_key"),
            )
        except Exception as e:  # 守卫登记失败不阻断注册
            logger.warning("[MCP Registry] requires_auth 登记失败 name=%s: %s", name, e)
    # B1 跨源门禁：CONFLICT_STRICT=0 仅 WARNING；=1 时 adapter 优先级最高可覆盖
    # manifest/mcporter，但同类源（同名能力卡重复登记）必拒
    if _gate_cross_source_registration(name, "adapter") == CONFLICT_REJECTED:
        logger.warning("[MCP Registry] CAPABILITY name=%s 登记被 CONFLICT_STRICT=1 拒绝", name)
        return False
    prev_cap = _ADAPTER_CAPABILITIES.get(name)
    if prev_cap:
        prev_from = prev_cap.get("_from_adapter", "?")
        new_from = capability.get("_from_adapter", "?")
        if prev_from != new_from:
            logger.warning(
                "[MCP Registry] CAPABILITY name=%s 被覆盖：%s → %s",
                name, prev_from, new_from,
            )
    _ADAPTER_CAPABILITIES[name] = dict(capability)
    return True


def auto_register_mcp():
    """自动扫描并注册MCP服务（幂等，重复调用不会重新注册）。

    顺序：扫描 mcpserver 本地 agent → mcporter 外部配置 → adapters 第三方能力包。
    adapters 步骤总是调用 register_all_adapters()（不是 mcp_registry 自己去搞工具注册，
    因为 mcp_server 实例在启动流程里才会创建，这里只是"准备 MCP_REGISTRY"）。
    """
    global _REGISTERED
    if _REGISTERED:
        return list(MCP_REGISTRY.keys())
    registered = scan_and_register_mcp_agents("mcpserver")
    registered.extend(register_external_mcp_agents())
    _REGISTERED = True
    logger.info(
        "[MCP Registry] 自动注册完成，已登记 %d 个服务（热 %d / 冷 %d，lazy=%s）",
        len(registered), len(MCP_REGISTRY), len(_COLD_TABLE), _lazy_enabled(),
    )
    return registered


def register_adapters(mcp_server: Any = None) -> list[str]:
    """主动调 mcpserver.adapters.register_all_adapters。

    被 mcp_server 启动主流程调用（在 FastMCP 实例创建后）。
    mcp_server 为 None 时只跑 healthcheck 做 dry-run，便于 unittest。

    幂等：_ADAPTER_REGISTERED=True 后不再重复注册（与 auto_register_mcp 行为一致），
    避免 mcp_server.add_tool 被重复调用导致同名工具重复挂载。
    dry-run（mcp_server=None）不设 _ADAPTER_REGISTERED，允许后续真正注册。
    """
    global _ADAPTER_REGISTERED
    if _ADAPTER_REGISTERED:
        logger.debug("[MCP Registry] adapters 已注册过，跳过（幂等）")
        return []
    try:
        from mcpserver.adapters import register_all_adapters
    except Exception as e:
        logger.warning("[MCP Registry] 导入 adapters 入口失败: %s", e)
        return []
    names = register_all_adapters(mcp_server, mcp_registry=sys.modules[__name__])
    if mcp_server is not None:
        _ADAPTER_REGISTERED = True
    logger.info("[MCP Registry] adapters 注册完成: %s", names or "(none)")
    return names


def get_registered_services() -> list[str]:
    """全部已登记服务名（热 ∪ 冷）——懒加载下仍返回完整清单，避免调用方少看到服务。"""
    return all_service_names()


def list_registered_capabilities() -> list[dict[str, Any]]:
    """列出所有已登记能力（MANIFEST_CACHE 本地服务 + _ADAPTER_CAPABILITIES）。

    同名跨源冲突的条目会自动附带 conflict_sources: [manifest, adapter] 字段
    告知用户有重复名需要处理，避免能力卡片可见但调用路径错位。
    """
    caps: list[dict[str, Any]] = []
    for name, manifest in MANIFEST_CACHE.items():
        source = (manifest.get("source") or "manifest") if isinstance(manifest, dict) else "manifest"
        caps.append({
            "name": name,
            "displayName": manifest.get("displayName") or name,
            "description": manifest.get("description", ""),
            "version": manifest.get("version", ""),
            "license": manifest.get("license", ""),
            "vendor": manifest.get("vendor", manifest.get("author", "")),
            "source": source,
        })
    for name, cap in _ADAPTER_CAPABILITIES.items():
        caps.append({"name": name, **cap, "source": "adapter"})
    # 同名多源 → 每条追加 conflict_sources 字段告知用户有重名
    name_to_sources: dict[str, list[str]] = {}
    for c in caps:
        name_to_sources.setdefault(c["name"], []).append(c["source"])
    for c in caps:
        srcs = name_to_sources[c["name"]]
        if len(srcs) > 1:
            c["conflict_sources"] = list(srcs)
    return caps


def get_service_instance(service_name: str) -> Any | None:
    """取服务实例；冷表项首次调用会触发 ensure_hot 转热（卷189-A1）。"""
    return ensure_hot(service_name)


def clear_registry():
    """清空所有注册表和缓存，恢复到初始状态。

    联动清空 _common.py 的全局状态（_INJECTED_VENDORS / _ADAPTER_CAPABILITY_NAMES），
    确保测试隔离完整（延迟导入避免循环依赖）。
    """
    global _REGISTERED, _ADAPTER_REGISTERED
    MCP_REGISTRY.clear()
    MANIFEST_CACHE.clear()
    _ADAPTER_CAPABILITIES.clear()
    _COLD_TABLE.clear()
    _COLD_HOT_FAILED.clear()
    _CONFLICT_LOG.clear()
    _REGISTERED = False
    _ADAPTER_REGISTERED = False
    try:
        from mcpserver.adapters._common import reset_for_tests
        reset_for_tests()
    except Exception:
        pass  # _common 尚未加载（如单独 import mcp_registry 做单元测试）


def get_conflict_log() -> list[dict[str, Any]]:
    """返回 CONFLICT_STRICT=1 模式下的冲突仲裁记录（只读副本）。

    每条含 name / new_source / existing_sources / action(OVERRIDE|REJECT|REJECT_SAME_SOURCE) / ts。
    非严格模式不写入，恒为空列表。
    """
    return [dict(e) for e in _CONFLICT_LOG]


def get_registry_status() -> dict[str, Any]:
    return {
        "registered_services": len(MCP_REGISTRY),
        "cold_services": len(_COLD_TABLE),
        "lazy_enabled": _lazy_enabled(),
        "cached_manifests": len(MANIFEST_CACHE),
        "service_names": all_service_names(),
        "conflict_strict": _conflict_strict_enabled(),
        "conflict_log_entries": len(_CONFLICT_LOG),
    }


__all__ = [
    # 注册入口
    "auto_register_mcp",
    "register_adapters",
    "scan_and_register_mcp_agents",
    "register_external_mcp_agents",
    "register_capability",
    # 冲突严格化（CONFLICT_STRICT）
    "CONFLICT_REJECTED",
    "get_conflict_log",
    # 查询
    "get_service_instance",
    "get_service_info",
    "get_all_services_info",
    "get_available_tools",
    "get_registered_services",
    "get_service_statistics",
    "get_registry_status",
    # 懒加载（卷189-A1 冷热分层）
    "ensure_hot",
    "is_hot",
    "cold_service_names",
    "all_service_names",
    "get_cold_hot_failure",
    "get_service_source",
    "get_service_scope",
    "get_service_owner_agent_id",
    "is_service_visible_to_agent",
    "list_visible_service_names",
    "list_registered_capabilities",
    "query_services_by_capability",
    # 工具
    "load_manifest_file",
    "create_agent_instance",
    # 测试
    "clear_registry",
    # 域分组（工单204 任务二）
    "DOMAINS",
    "DEFAULT_DOMAIN",
    "register_service_domain",
    "get_service_domain",
    "list_services_by_domain",
    "get_domain_statistics",
    "RISK_LEVELS",
    "register_service_risk",
    "get_service_risk",
    "get_risk_statistics",
]


# === 域分组（工单204 任务二）===
#: 域的规范取值（工单指定四域 + 兜底 general）
DOMAINS: tuple[str, ...] = ("radio", "material", "agent", "memory", "general")
DEFAULT_DOMAIN = "general"

#: 服务名 → 域 的规则（顺序敏感：先匹配先生效；前缀命中或子串命中都算）
_DOMAIN_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("radio", ("rf_brain", "antenna_sim", "antenna_rotator", "ptz_service",
               "sentinel", "sdr", "hamlog")),
    ("material", ("material_science", "bio_adapter", "biopred", "eis", "retrosynthesis",
                  "scikit_fingerprints", "bofire", "porous", "glyco")),
    ("agent", ("agent_",)),
    ("memory", ("graph_memory", "memory_maas", "summer_memory", "memclaw", "hindsight")),
)

#: 显式登记覆盖（规则覆盖不到的服务名走这里；不登记则纯规则推导）
_DOMAIN_OVERRIDES: dict[str, str] = {}


def register_service_domain(service_name: str, domain: str) -> None:
    """显式登记某服务的域（覆盖规则推导）。domain 必须是 ``DOMAINS`` 之一。"""
    name = str(service_name or "").strip()
    dom = str(domain or "").strip().lower()
    if not name:
        raise ValueError("service_name 不能为空")
    if dom not in DOMAINS:
        raise ValueError(f"未知域 {domain!r}，可选：{DOMAINS}")
    _DOMAIN_OVERRIDES[name] = dom


def get_service_domain(service_name: str) -> str:
    """服务 → 域。优先级：显式登记 > 名字规则 > ``general``。"""
    name = str(service_name or "").strip()
    if name in _DOMAIN_OVERRIDES:
        return _DOMAIN_OVERRIDES[name]
    lowered = name.lower()
    for domain, prefixes in _DOMAIN_RULES:
        if any(lowered.startswith(p) or p in lowered for p in prefixes):
            return domain
    return DEFAULT_DOMAIN


def list_services_by_domain() -> dict[str, list[str]]:
    """按域分组输出全部服务（热表 ∪ 冷表，sorted）；空域不出现在结果里。"""
    out: dict[str, list[str]] = {}
    for name in all_service_names():
        out.setdefault(get_service_domain(name), []).append(name)
    return {d: sorted(v) for d, v in sorted(out.items())}


def get_domain_statistics() -> dict[str, int]:
    """各域服务数（**含 0 的域**，便于前端稳定渲染分组）。"""
    grouped = list_services_by_domain()
    return {d: len(grouped.get(d, [])) for d in DOMAINS}


# === 风险等级注解（工单205 任务一）===
#: 风险等级取值
RISK_LEVELS: tuple[str, ...] = ("low", "medium", "high")

#: **主判据复用既有分类**：manifest 的 classification.tier → 风险等级（不发明新维度）
_RISK_BY_TIER: dict[str, str] = {
    "read-only": "low",
    "local-write": "medium",
    "process-control": "high",   # 控制外部进程/设备
    "offensive": "high",         # 默认关闭，需 *_ENABLE_INVOKE=1
}

#: 名字兜底规则（无 classification 的服务，如 mcporter 外部件）
_RISK_NAME_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("high", ("agent_decompile", "webapp-testing", "browseskill", "openclaw")),
)

#: 显式覆盖（优先级最高）
_RISK_OVERRIDES: dict[str, str] = {}


def register_service_risk(service_name: str, risk: str) -> None:
    """显式登记风险等级（覆盖 tier 判据）。risk 必须是 RISK_LEVELS 之一。"""
    name = str(service_name or "").strip()
    lvl = str(risk or "").strip().lower()
    if not name:
        raise ValueError("service_name 不能为空")
    if lvl not in RISK_LEVELS:
        raise ValueError(f"未知风险等级 {risk!r}，可选：{RISK_LEVELS}")
    _RISK_OVERRIDES[name] = lvl


def get_service_risk(service_name: str) -> str:
    """服务 → 风险等级。优先级：显式登记 > manifest.classification.tier > 名字规则 > low。

    只读注解：**不改变任何装配/调用行为**（与 classification 同款口径，缺省不限制）。
    """
    name = str(service_name or "").strip()
    if name in _RISK_OVERRIDES:
        return _RISK_OVERRIDES[name]
    manifest = MANIFEST_CACHE.get(name)
    if isinstance(manifest, dict):
        tier = str((manifest.get("classification") or {}).get("tier") or "").strip().lower()
        if tier in _RISK_BY_TIER:
            return _RISK_BY_TIER[tier]
    lowered = name.lower()
    for lvl, prefixes in _RISK_NAME_RULES:
        if any(p in lowered for p in prefixes):
            return lvl
    return "low"


def get_risk_statistics() -> dict[str, int]:
    """各风险等级的服务数（含 0 档）。"""
    stats = {lvl: 0 for lvl in RISK_LEVELS}
    for n in all_service_names():
        stats[get_service_risk(n)] += 1
    return stats
