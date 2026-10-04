"""第三方能力包 MCP 适配层总入口。

用法:
    from mcpserver.adapters import register_all_adapters
    registered = register_all_adapters(mcp_server, mcp_registry)
    # registered 是成功注册的 adapter 名称列表

纳入前门禁（P1 三件套改造后生效）：
- validate_adapter(mod, name)：三要素校验（CAPABILITY/healthcheck/register + 6 个必需字段 + name 与注册名对齐）
- CAPABILITY name 冲突检测：_common._ADAPTER_CAPABILITY_NAMES 全局注册表防止同名覆盖
"""
from __future__ import annotations

import logging
from typing import Any

from mcpserver.adapters._common import (
    _ADAPTER_CAPABILITY_NAMES,
    MCPAdapterModule,
    reset_for_tests,
    validate_adapter,
)

logger = logging.getLogger(__name__)

# adapter 名 → (模块路径, enable_key 环境变量开关)
_ADAPTERS = {
    "agent_reach": ("mcpserver.adapters.agent_reach", "ENABLE_ADAPTER_AGENT_REACH"),
    "vulnclaw": ("mcpserver.adapters.vulnclaw", "ENABLE_ADAPTER_VULNCLAW"),
    "memclaw": ("mcpserver.adapters.memclaw", "ENABLE_ADAPTER_MEMCLAW"),
    "headroom": ("mcpserver.adapters.headroom", "ENABLE_ADAPTER_HEADROOM"),
    "markitdown": ("mcpserver.adapters.markitdown", "ENABLE_ADAPTER_MARKITDOWN"),
    "llm4decompile": ("mcpserver.adapters.llm4decompile", "ENABLE_ADAPTER_LLM4DECOMPILE"),
    "paper_miner": ("mcpserver.adapters.paper_miner", "ENABLE_ADAPTER_PAPER_MINER"),
    "context7": ("mcpserver.adapters.context7", "ENABLE_ADAPTER_CONTEXT7"),
    "chemmcp": ("mcpserver.adapters.chemmcp", "ENABLE_ADAPTER_CHEMMCP"),
}


def register_all_adapters(mcp_server: Any, mcp_registry: Any = None) -> list[str]:
    """按顺序注册所有已通过 enable + healthcheck 的 adapter，返回成功注册的名称列表。

    门禁流程：
    1. ENABLE_ADAPTER_* 开关（默认开，=0/false 禁用）
    2. import 模块 → 异常则跳过
    3. validate_adapter() 契约校验（缺 CAPABILITY/healthcheck/register → 跳过并警告）
    4. CAPABILITY.name 冲突检测（同名已注册其他 adapter → 跳过并警告）
    5. healthcheck() → False 则跳过（缺依赖/凭证）
    6. register() → 异常则跳过（不回滚已注册的工具）
    """
    import importlib
    import os

    registered: list[str] = []
    for name, (module_path, env_key) in _ADAPTERS.items():
        enable_switch = os.environ.get(env_key, "1").strip().lower()
        if enable_switch in ("0", "false", "no", "off"):
            logger.info("[adapters] %s 已通过 %s=0 禁用，跳过", name, env_key)
            continue
        # 步骤 2: import
        try:
            mod = importlib.import_module(module_path)
        except Exception as e:
            logger.warning("[adapters] %s 导入失败: %s，跳过", name, e)
            continue
        # 步骤 3: Protocol 契约门禁（validate_adapter 深度校验，不被 isinstance 短路）
        # isinstance(mod, MCPAdapterModule) 只做 hasattr 三要素检查，无法发现 CAPABILITY 字段缺/空、
        # name/_from_adapter 与注册名错位等问题；所以无论 isinstance 结果如何都跑 validate_adapter。
        issues: list[str] = validate_adapter(mod, name)
        if not isinstance(mod, MCPAdapterModule) and not issues:
            # isinstance 失败但 validate_adapter 没报问题（极少见），至少列一条三要素缺失
            issues.append(f"{name}: 不满足 MCPAdapterModule Protocol（缺 CAPABILITY/healthcheck/register）")
        if issues:
            logger.warning(
                "[adapters] %s 契约校验失败，跳过: %s",
                name,
                "；".join(issues),
            )
            continue
        # 步骤 4: CAPABILITY name 全局冲突检测 + 立即写入（不依赖 register() 内部自觉调 safe）
        cap_name = getattr(getattr(mod, "CAPABILITY", {}), "get", lambda *_: "")("name")
        cap_from = getattr(getattr(mod, "CAPABILITY", {}), "get", lambda *_: "")("_from_adapter") or name
        if cap_name:
            prev = _ADAPTER_CAPABILITY_NAMES.get(cap_name)
            if prev and prev != cap_from:
                logger.warning(
                    "[adapters] %s 的 CAPABILITY.name='%s' 已被模块 %s 占用，跳过（避免能力卡片错位）",
                    name, cap_name, prev,
                )
                continue
            # 门禁通过即写入：即使 register() 忘了调 register_capability_safe，下一个同名 adapter
            # 走到步骤 4 时也能检测到冲突，不再漏报
            _ADAPTER_CAPABILITY_NAMES[cap_name] = cap_from
        # 步骤 5: healthcheck
        try:
            ok = mod.healthcheck()
        except Exception as e:
            logger.warning("[adapters] %s healthcheck 异常: %s，跳过", name, e)
            continue
        if not ok:
            logger.info("[adapters] %s healthcheck 未通过（依赖/凭证缺失或未启用），跳过", name)
            continue
        # 步骤 6: register（带回滚）
        existing_tools: set[str] = set()
        if hasattr(mcp_server, "_tool_manager"):
            try:
                existing_tools = set(getattr(mcp_server._tool_manager, "_tools", {}).keys())
            except Exception:
                pass
        try:
            mod.register(mcp_server, mcp_registry=mcp_registry)
        except Exception as e:
            # 回滚本次 register 新增的工具
            if hasattr(mcp_server, "_tool_manager"):
                try:
                    current_tools = set(getattr(mcp_server._tool_manager, "_tools", {}).keys())
                    new_tools = current_tools - existing_tools
                    for t in new_tools:
                        mcp_server._tool_manager._tools.pop(t, None)
                    if new_tools:
                        logger.warning(
                            "[adapters] %s register 失败，已回滚 %d 个半挂载工具: %s",
                            name, len(new_tools), new_tools,
                        )
                except Exception as rollback_err:
                    logger.warning("[adapters] %s 回滚失败（mcp_server 内部结构可能已变）: %s", name, rollback_err)
            logger.warning("[adapters] %s 注册失败: %s，跳过", name, e)
            continue
        registered.append(name)
        logger.info("[adapters] %s 注册成功", name)
    return registered


__all__ = ["register_all_adapters", "reset_for_tests", "validate_adapter", "MCPAdapterModule"]
