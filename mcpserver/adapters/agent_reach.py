"""Agent-Reach MCP 适配层。

上游 vendor: vendor/top5/Agent-Reach (MIT)
入口: agent_reach/integrations/mcp_server.py — 非 FastMCP，是 mcp.server.Server（装饰器模式）
适配策略：
- healthcheck: 纯 Python 通道（web/rss/reddit/github/v2ex/xueqiu）无外部依赖，
  需要 CLI 的通道（twitter/yt-dlp）在实际调用时才会报错
- register: Agent-Reach 是安装器+诊断工具（doctor），不是搜索引擎。
  暴露 agent_reach_status 外壳（doctor_report），不伪造 search() 假接口
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from mcpserver.adapters._common import (
    inject_vendor_path,
    register_capability_safe,
)

logger = logging.getLogger(__name__)

# 模块级 CAPABILITY（提自 register() 内部局部 dict。name=agent_reach 与注册名严格对齐）
CAPABILITY: dict = {
    "name": "agent_reach",
    "displayName": "多平台渠道状态",
    "description": "Agent-Reach 渠道安装/诊断工具（doctor）。实际搜索需调用上游 channel 工具。",
    "version": "1.5.0",
    "license": "MIT",
    "vendor": "Agent-Reach",
    "_from_adapter": "agent_reach",
}


def healthcheck() -> bool:
    """Agent-Reach 对依赖很宽容：纯 Python 通道不依赖外部可执行文件。

    只检查 vendor 目录存在 + 模块可导入（integrations.mcp_server）。
    """
    inject_vendor_path("Agent-Reach")
    try:
        from agent_reach.integrations import mcp_server as _ar_mcp  # type: ignore  # noqa: F401
    except Exception as e:
        logger.warning("[adapter:agent_reach] 导入 agent_reach MCP 失败: %s", e)
        return False
    return True


def register(mcp_server: Any, mcp_registry: Any = None) -> None:
    """将 Agent-Reach 的状态检查工具注册进 scratchpad mcp_server。

    Agent-Reach 用 mcp.server.Server（非 FastMCP），无法直接 merge_tools()。
    暴露 doctor_report 外壳。
    """
    inject_vendor_path("Agent-Reach")
    from agent_reach.config import Config  # type: ignore
    from agent_reach.core import AgentReach  # type: ignore

    logger.info("[adapter:agent_reach] 暴露 agent_reach_status 外壳（doctor_report）")

    _config = Config(read_only=True)
    _eyes = AgentReach(_config)

    async def agent_reach_status() -> dict:
        """Agent-Reach 渠道状态：哪些 channel 已安装、可用。

        Agent-Reach 是安装器+诊断工具，不是搜索引擎。
        实际搜索/阅读需调用上游工具（twitter-cli / yt-dlp / mcporter 等）。
        """
        try:
            report = await asyncio.to_thread(_eyes.doctor_report)
            return {"ok": True, "report": report}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    if hasattr(mcp_server, "add_tool"):
        mcp_server.add_tool(agent_reach_status, name="agent_reach_status")

    register_capability_safe(mcp_registry, CAPABILITY)
