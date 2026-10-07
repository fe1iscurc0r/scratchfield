"""agent_server_parts.dogtag —— 自 agentserver/agent_server.py 拆出（工单204 任务一，纯移动）。"""
from __future__ import annotations

from .common import *  # noqa: F401,F403
from .common import Modules, logger  # noqa: F401
from .lifecycle import app  # noqa: F401

@app.get("/dogtag/status")
async def get_dogtag_status():
    """获取军牌调度器状态 + 全部任务状态"""
    try:
        if not Modules.dogtag_scheduler:
            return {"success": True, "running": False, "message": "调度器未初始化"}
        return {"success": True, **Modules.dogtag_scheduler.get_status()}
    except Exception as e:
        logger.error(f"获取 DogTag 状态失败: {e}")
        raise HTTPException(500, f"获取失败: {e}")


@app.get("/dogtag/duties")
async def get_dogtag_duties():
    """获取所有注册的职责列表"""
    try:
        from agentserver.dogtag import get_dogtag_registry

        registry = get_dogtag_registry()
        duties = {
            duty_id: tag.model_dump()
            for duty_id, tag in registry.get_all().items()
        }
        return {"success": True, "duties": duties, "count": len(duties)}
    except Exception as e:
        logger.error(f"获取 DogTag 职责列表失败: {e}")
        raise HTTPException(500, f"获取失败: {e}")


@app.post("/dogtag/duties/{duty_id}/enable")
async def enable_dogtag_duty(duty_id: str):
    """启用指定职责"""
    try:
        from agentserver.dogtag import get_dogtag_registry
        from agentserver.dogtag.models import DutyStatus

        registry = get_dogtag_registry()
        if not registry.get(duty_id):
            raise HTTPException(404, f"职责不存在: {duty_id}")
        registry.update_status(duty_id, DutyStatus.ENABLED)
        return {"success": True, "message": f"职责 '{duty_id}' 已启用"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"启用 DogTag 职责失败: {e}")
        raise HTTPException(500, f"操作失败: {e}")


@app.post("/dogtag/duties/{duty_id}/disable")
async def disable_dogtag_duty(duty_id: str):
    """禁用指定职责"""
    try:
        from agentserver.dogtag import get_dogtag_registry
        from agentserver.dogtag.models import DutyStatus

        registry = get_dogtag_registry()
        if not registry.get(duty_id):
            raise HTTPException(404, f"职责不存在: {duty_id}")
        registry.update_status(duty_id, DutyStatus.DISABLED)
        return {"success": True, "message": f"职责 '{duty_id}' 已禁用"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"禁用 DogTag 职责失败: {e}")
        raise HTTPException(500, f"操作失败: {e}")


@app.post("/dogtag/duties/{duty_id}/trigger")
async def trigger_dogtag_duty(duty_id: str):
    """手动触发指定职责"""
    try:
        if not Modules.dogtag_scheduler:
            raise HTTPException(503, "军牌调度器未初始化")

        from agentserver.dogtag import get_dogtag_registry

        registry = get_dogtag_registry()
        if not registry.get(duty_id):
            raise HTTPException(404, f"职责不存在: {duty_id}")

        await Modules.dogtag_scheduler.trigger_once(duty_id)
        return {"success": True, "message": f"职责 '{duty_id}' 已触发"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"触发 DogTag 职责失败: {e}")
        raise HTTPException(500, f"触发失败: {e}")


@app.post("/dogtag/conversation_event")
async def dogtag_conversation_event(payload: dict[str, Any]):
    """接收对话生命周期事件"""
    event = payload.get("event", "")
    try:
        if not Modules.dogtag_scheduler:
            return {"status": "no_scheduler"}

        if event == "started":
            Modules.dogtag_scheduler.on_conversation_started()
        elif event == "ended":
            Modules.dogtag_scheduler.on_conversation_ended()
        else:
            return {"status": "unknown_event", "event": event}

        logger.info(f"[DogTag] 收到对话事件: {event}")
        return {"status": "ok", "event": event}
    except Exception as e:
        logger.error(f"[DogTag] 处理对话事件失败: {e}")
        return {"status": "error", "error": str(e)}
