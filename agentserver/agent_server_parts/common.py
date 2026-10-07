"""agent_server_parts.common —— 自 agentserver/agent_server.py 拆出（工单204 任务一，纯移动）。"""
from __future__ import annotations


"""
陆墨独立服务 - 通过OpenClaw执行任务
提供意图识别和OpenClaw任务调度功能
"""


import asyncio


import logging


import os


import sys


from contextlib import asynccontextmanager


from datetime import datetime


from typing import Any, Dict, Optional


import httpx


from fastapi import FastAPI, HTTPException


from agentserver.openclaw import get_openclaw_client, set_openclaw_config


from agentserver.openclaw.embedded_runtime import EmbeddedRuntime, get_embedded_runtime


from agentserver.telemetry_client import emit_local_telemetry


from system.config import add_config_listener, config


from system.cors_config import apply_local_cors


logger = logging.getLogger(__name__)


_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


class Modules:
    """全局模块管理器"""

    openclaw_client = None
    dogtag_scheduler = None  # 军牌系统统一调度器
    instance_manager = None  # 干员多实例管理器
    travel_tasks: dict[str, asyncio.Task] = {}


def _now_iso() -> str:
    """获取当前时间ISO格式"""
    return datetime.now().isoformat()
