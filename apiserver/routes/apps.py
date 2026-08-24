"""本地应用启动路由（NEKO / HamLog）

复用 mcpserver.agent_open_launcher.local_apps（与 Agent 侧启动器同一实现）：
- 幂等：已在运行直接返回，不重复拉起
- fail-fast：依赖缺失（解释器/token/入口脚本）明确报错
探测依赖进程/端口查询（阻塞），路由用同步 def 走线程池，不阻塞事件循环。
"""

import logging

from fastapi import APIRouter, HTTPException

from mcpserver.agent_open_launcher.local_apps import (
    get_launch_status,
    launch_hamlog,
    launch_neko,
)

logger = logging.getLogger(__name__)

router = APIRouter()

_LAUNCHERS = {"neko": launch_neko, "hamlog": launch_hamlog}


@router.get("/apps/launch-status")
def apps_launch_status():
    """查询 NEKO / HamLog 运行状态（秒级进程/端口探测）"""
    return get_launch_status()


@router.post("/apps/launch/{app}")
def apps_launch(app: str):
    """启动指定本地应用（幂等：已在运行直接返回）"""
    launcher = _LAUNCHERS.get(app.lower())
    if launcher is None:
        raise HTTPException(status_code=404, detail=f"不支持的应用: {app}")
    result = launcher()
    logger.info("launch app=%s status=%s", app, result.get("status"))
    return result
