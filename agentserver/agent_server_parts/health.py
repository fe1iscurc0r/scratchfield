"""agent_server_parts.health —— 自 agentserver/agent_server.py 拆出（工单204 任务一，纯移动）。"""
from __future__ import annotations

from .common import *  # noqa: F401,F403
from .common import Modules, _now_iso, logger  # noqa: F401
from .lifecycle import app  # noqa: F401

@app.get("/health")
async def health_check():
    """健康检查"""
    return {
        "status": "healthy",
        "timestamp": _now_iso(),
        "modules": {
            "openclaw": Modules.openclaw_client is not None,
            "dogtag": Modules.dogtag_scheduler is not None,
        },
    }


@app.get("/health/full")
async def full_health_check():
    """完整健康检查（包括所有服务）"""
    from system.health_check import get_health_checker

    checker = get_health_checker()
    results = await checker.check_all()
    summary = checker.get_summary(results)

    # 转换为可序列化格式
    results_dict = {}
    for service_name, result in results.items():
        results_dict[service_name] = {
            "status": result.status.value,
            "message": result.message,
            "checks": result.checks,
            "details": result.details,
            "latency_ms": result.latency_ms,
        }

    return {
        "summary": summary,
        "services": results_dict,
        "timestamp": _now_iso(),
    }


@app.get("/openclaw/health")
async def openclaw_health_check():
    """检查 OpenClaw Gateway 健康状态"""
    if not Modules.openclaw_client:
        return {"success": False, "status": "not_configured", "message": "OpenClaw 客户端未配置"}

    try:
        health = await Modules.openclaw_client.health_check()
        return {"success": True, "health": health}
    except Exception as e:
        logger.error(f"OpenClaw 健康检查失败: {e}")
        return {"success": False, "status": "error", "error": str(e)}
