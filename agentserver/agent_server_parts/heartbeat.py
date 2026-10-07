"""agent_server_parts.heartbeat —— 自 agentserver/agent_server.py 拆出（工单204 任务一，纯移动）。"""
from __future__ import annotations

from .common import *  # noqa: F401,F403
from .common import Modules, logger  # noqa: F401
from .dogtag import dogtag_conversation_event  # noqa: F401
from .lifecycle import app  # noqa: F401

@app.post("/heartbeat/conversation_event")
async def heartbeat_conversation_event(payload: dict[str, Any]):
    """接收 api_server 的对话生命周期事件（兼容旧路由，委托给军牌系统）"""
    return await dogtag_conversation_event(payload)


@app.get("/heartbeat/config")
async def get_heartbeat_config():
    """获取心跳系统配置"""
    try:
        from agentserver.dogtag import load_heartbeat_config

        cfg = load_heartbeat_config()
        return {"success": True, "config": cfg.model_dump()}
    except Exception as e:
        logger.error(f"获取 Heartbeat 配置失败: {e}")
        raise HTTPException(500, f"获取失败: {e}")


@app.post("/heartbeat/config")
async def update_heartbeat_config(payload: dict[str, Any]):
    """更新心跳系统配置（含重新注册职责）"""
    try:
        from agentserver.dogtag import (
            HeartbeatConfig,
            create_heartbeat_executor,
            get_dogtag_registry,
            load_heartbeat_config,
            save_heartbeat_config,
        )
        from agentserver.dogtag.duties.heartbeat_duty import create_heartbeat_duty

        old_config = load_heartbeat_config()
        config_dict = old_config.model_dump()
        config_dict.update(payload)
        new_config = HeartbeatConfig(**config_dict)

        if not save_heartbeat_config(new_config):
            raise HTTPException(500, "配置保存失败")

        # 重建执行器 + 重新注册职责
        create_heartbeat_executor(new_config)
        registry = get_dogtag_registry()
        hb_tag, hb_exec = create_heartbeat_duty(new_config)
        registry.register(hb_tag, hb_exec)
        logger.info("[Heartbeat] 配置已更新，heartbeat 职责已重新注册")

        return {"success": True, "message": "配置已更新", "config": new_config.model_dump()}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新 Heartbeat 配置失败: {e}")
        raise HTTPException(500, f"更新失败: {e}")


@app.post("/heartbeat/enable")
async def enable_heartbeat(payload: dict[str, Any]):
    """快捷开关：启用/禁用心跳系统"""
    try:
        enabled = payload.get("enabled", True)

        from agentserver.dogtag import get_dogtag_registry, load_heartbeat_config, save_heartbeat_config
        from agentserver.dogtag.models import DutyStatus

        cfg = load_heartbeat_config()
        cfg.enabled = enabled

        if save_heartbeat_config(cfg):
            registry = get_dogtag_registry()
            registry.update_status(
                "heartbeat",
                DutyStatus.ENABLED if enabled else DutyStatus.DISABLED,
            )

            # 同步执行器的配置
            from agentserver.dogtag import get_heartbeat_executor
            hb = get_heartbeat_executor()
            if hb:
                hb.config = cfg

            status = "已启用" if enabled else "已禁用"
            return {"success": True, "message": f"心跳系统{status}", "enabled": enabled}
        else:
            raise HTTPException(500, "配置保存失败")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"切换 Heartbeat 状态失败: {e}")
        raise HTTPException(500, f"操作失败: {e}")


@app.post("/heartbeat/trigger")
async def trigger_heartbeat():
    """手动触发一次心跳检查"""
    try:
        if not Modules.dogtag_scheduler:
            raise HTTPException(400, "军牌调度器未初始化")

        await Modules.dogtag_scheduler.trigger_once("heartbeat")
        return {
            "success": True,
            "message": "心跳已触发",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"手动触发 Heartbeat 失败: {e}")
        raise HTTPException(500, f"触发失败: {e}")


@app.get("/heartbeat/status")
async def get_heartbeat_status():
    """获取心跳系统运行状态"""
    try:
        from agentserver.dogtag import get_dogtag_registry, get_heartbeat_executor

        hb = get_heartbeat_executor()
        if not hb:
            return {
                "success": True,
                "running": False,
                "enabled": False,
                "message": "执行器未初始化",
            }

        status = hb.get_status()

        # 从军牌系统补充调度状态
        if Modules.dogtag_scheduler:
            registry = get_dogtag_registry()
            tag = registry.get("heartbeat")
            countdown_active = (
                "heartbeat" in Modules.dogtag_scheduler._event_countdowns
                and not Modules.dogtag_scheduler._event_countdowns["heartbeat"].done()
            )
            status["running"] = Modules.dogtag_scheduler._running
            status["conversation_active"] = Modules.dogtag_scheduler._conversation_active
            status["countdown_active"] = countdown_active
            status["duty_status"] = tag.status.value if tag else "unregistered"
            status["in_active_hours"] = Modules.dogtag_scheduler._is_in_active_hours(
                hb.config.active_hours_start, hb.config.active_hours_end
            )

        return {"success": True, **status}
    except Exception as e:
        logger.error(f"获取 Heartbeat 状态失败: {e}")
        raise HTTPException(500, f"获取失败: {e}")


@app.get("/heartbeat/checklist")
async def get_heartbeat_checklist(status: str | None = None):
    """获取 checklist 条目列表，可选 ?status=pending 过滤"""
    try:
        from agentserver.dogtag import load_checklist

        cl = load_checklist()
        items = cl.items
        if status:
            items = [i for i in items if i.status == status]
        return {
            "success": True,
            "items": [i.model_dump() for i in items],
            "total": len(items),
        }
    except Exception as e:
        logger.error(f"获取 Checklist 失败: {e}")
        raise HTTPException(500, f"获取失败: {e}")


@app.post("/heartbeat/checklist")
async def create_checklist_item(payload: dict[str, Any]):
    """新增 checklist 条目 {"content": "...", "priority": "normal"}"""
    try:
        from agentserver.dogtag import add_item

        content = payload.get("content", "").strip()
        if not content:
            raise HTTPException(400, "content 不能为空")

        priority = payload.get("priority", "normal")
        item = add_item(content, source="user", priority=priority)
        return {"success": True, "item": item.model_dump()}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"新增 Checklist 条目失败: {e}")
        raise HTTPException(500, f"新增失败: {e}")


@app.put("/heartbeat/checklist/{item_id}")
async def update_checklist_item(item_id: str, payload: dict[str, Any]):
    """更新 checklist 条目 {"status": "done", "notes": "..."}"""
    try:
        from agentserver.dogtag import update_item

        allowed_fields = {"status", "notes", "priority", "content"}
        updates = {k: v for k, v in payload.items() if k in allowed_fields}
        if not updates:
            raise HTTPException(400, "无有效更新字段")

        ok = update_item(item_id, **updates)
        if not ok:
            raise HTTPException(404, f"条目不存在: {item_id}")
        return {"success": True, "message": "更新成功"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新 Checklist 条目失败: {e}")
        raise HTTPException(500, f"更新失败: {e}")


@app.delete("/heartbeat/checklist/{item_id}")
async def delete_checklist_item(item_id: str):
    """删除 checklist 条目"""
    try:
        from agentserver.dogtag import remove_item

        ok = remove_item(item_id)
        if not ok:
            raise HTTPException(404, f"条目不存在: {item_id}")
        return {"success": True, "message": "删除成功"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除 Checklist 条目失败: {e}")
        raise HTTPException(500, f"删除失败: {e}")
