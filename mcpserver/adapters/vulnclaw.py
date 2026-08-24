"""VulnClaw MCP 适配层。

上游 vendor: vendor/top5/VulnClaw (MIT)
MCP 入口: vulnclaw/mcp/lifecycle.py — MCPLifecycleManager 管理 MCP 服务注册/生命周期
MCP Registry: vulnclaw/mcp/registry.py — 管理工具 schema 和实例状态（schema-only，无 FastMCP 可调用）

适配策略：
- 凭证 fail-fast: 健康检查阶段校验 VULNCLAW_OPENAI_API_KEY 或 OPENAI_API_KEY
- ⚠️ 安全红线：使用前必须获得合法授权。当前仅暴露 vulnclaw_status（列出工具 schema）+ vulnclaw_invoke（诚实说明需完整运行时）
"""
from __future__ import annotations

import logging
import os
from typing import Any

from mcpserver.adapters._common import (
    get_vendor_top5_root,
    inject_vendor_path,
    register_capability_safe,
)

logger = logging.getLogger(__name__)
_VULNCLAW_SRC = get_vendor_top5_root() / "VulnClaw"

CAPABILITY: dict = {
    "name": "vulnclaw",
    "displayName": "渗透测试编排",
    "description": "AI 渗透测试 MCP 服务（信息收集→扫描→利用→报告）。⚠️ 使用前必须合法授权。",
    "version": "0.3.7",
    "license": "MIT",
    "vendor": "VulnClaw",
    "security_notice": "使用前必须获得合法授权",
    "_from_adapter": "vulnclaw",
}


def healthcheck() -> bool:
    """VulnClaw 健康检查。

    必须条件：
    - 目录存在
    - LLM API key 可用（VULNCLAW_OPENAI_API_KEY 优先，回退 OPENAI_API_KEY，禁止任何默认值）
    """
    if not _VULNCLAW_SRC.is_dir():
        logger.warning("[adapter:vulnclaw] %s 不存在", _VULNCLAW_SRC)
        return False
    inject_vendor_path("VulnClaw")
    # 凭证 fail-fast：允许 VULNCLAW_OPENAI_API_KEY 与全局 OPENAI_API_KEY 隔离
    api_key = (
        os.environ.get("VULNCLAW_OPENAI_API_KEY", "").strip()
        or os.environ.get("OPENAI_API_KEY", "").strip()
    )
    if not api_key:
        logger.warning(
            "[adapter:vulnclaw] 未配置 VULNCLAW_OPENAI_API_KEY / OPENAI_API_KEY，跳过。"
            "⚠️ 渗透功能使用前必须获得合法授权。"
        )
        return False
    try:
        import vulnclaw  # noqa: F401
        from vulnclaw.mcp import registry as _vc_reg  # noqa: F401
    except Exception as e:
        logger.warning("[adapter:vulnclaw] 导入 vulnclaw MCP 模块失败: %s", e)
        return False
    return True


def register(mcp_server: Any, mcp_registry: Any = None) -> None:
    """把 VulnClaw MCP 工具合并到主 mcp_server。

    VulnClaw 使用 MCPRegistry 管理工具 schema（无 FastMCP 实例），这里暴露两个外壳工具：
    - vulnclaw_status: 列出可用工具 schema
    - vulnclaw_invoke: 诚实说明需完整 MCP server 运行时
    """
    inject_vendor_path("VulnClaw")
    from vulnclaw.mcp import registry as vc_registry  # type: ignore

    logger.info("[adapter:vulnclaw] 暴露 vulnclaw_status + vulnclaw_invoke 外壳")

    async def vulnclaw_status() -> dict:
        """VulnClaw MCP 服务状态（列出可用工具 schema）。"""
        try:
            reg = vc_registry.MCPRegistry()
            schemas = reg.get_all_tool_schemas() if hasattr(reg, "get_all_tool_schemas") else []
            return {
                "ok": True,
                "available_tools": [s.get("name", "?") for s in schemas],
                "tool_count": len(schemas),
                "note": "VulnClaw 工具需通过其自身 MCP server 运行时调用",
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def vulnclaw_invoke(command: str, target: str) -> dict:
        """VulnClaw 渗透编排外壳。使用前必须获得合法授权。

        Args:
            command: 命令（recon / scan / exploit / report / kb）
            target: 目标（URL 或 IP 或 CIDR）
        """
        return {
            "ok": False,
            "error": "vulnclaw_invoke 需 VulnClaw MCP server 完整运行时（AgentCore + runner），当前 adapter 仅暴露 schema 状态。请直接启动 VulnClaw MCP server 使用完整渗透能力。",
            "command": command,
            "target": target,
        }

    if hasattr(mcp_server, "add_tool"):
        mcp_server.add_tool(vulnclaw_status, name="vulnclaw_status")
        mcp_server.add_tool(vulnclaw_invoke, name="vulnclaw_invoke")

    register_capability_safe(mcp_registry, CAPABILITY)
