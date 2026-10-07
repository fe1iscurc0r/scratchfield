"""agent_server_parts.vision —— 自 agentserver/agent_server.py 拆出（工单204 任务一，纯移动）。"""
from __future__ import annotations

from .common import *  # noqa: F401,F403
from .common import Modules, logger  # noqa: F401
from .lifecycle import app  # noqa: F401

@app.get("/proactive_vision/config")
async def get_proactive_vision_config():
    """获取主动视觉系统配置"""
    try:
        from agentserver.dogtag import load_proactive_config

        config = load_proactive_config()
        return {"success": True, "config": config.model_dump()}
    except Exception as e:
        logger.error(f"获取 ProactiveVision 配置失败: {e}")
        raise HTTPException(500, f"获取失败: {e}")


@app.post("/proactive_vision/config")
async def update_proactive_vision_config(payload: dict[str, Any]):
    """更新主动视觉系统配置"""
    try:
        from agentserver.dogtag import (
            ProactiveVisionConfig,
            create_proactive_analyzer,
            get_dogtag_registry,
            load_proactive_config,
            save_proactive_config,
        )
        from agentserver.dogtag.duties.screen_vision_duty import create_screen_vision_duty

        # 加载当前配置并备份到内存（用于回滚）
        old_config_backup = load_proactive_config()

        # 更新字段
        config_dict = old_config_backup.model_dump()
        config_dict.update(payload)

        # 创建新配置对象并验证
        new_config = ProactiveVisionConfig(**config_dict)

        # 先保存配置，确保配置有效
        if not save_proactive_config(new_config):
            raise HTTPException(500, "配置保存失败")

        # 重新注册 screen_vision 职责
        try:
            create_proactive_analyzer(new_config)
            registry = get_dogtag_registry()
            sv_tag, sv_exec = create_screen_vision_duty(new_config)
            registry.register(sv_tag, sv_exec)
            logger.info("[ProactiveVision] 配置已更新，screen_vision 职责已重新注册")
        except Exception as e:
            logger.error(f"[ProactiveVision] 应用新配置失败: {e}")
            # 回滚
            try:
                save_proactive_config(old_config_backup)
                create_proactive_analyzer(old_config_backup)
                sv_tag_old, sv_exec_old = create_screen_vision_duty(old_config_backup)
                registry.register(sv_tag_old, sv_exec_old)
                logger.info("[ProactiveVision] 已成功回滚到旧配置")
            except Exception as rollback_error:
                logger.error(f"[ProactiveVision] 回滚失败: {rollback_error}")
            raise HTTPException(500, f"应用新配置失败，已尝试回滚: {e}")

        return {"success": True, "message": "配置已更新", "config": new_config.model_dump()}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"更新 ProactiveVision 配置失败: {e}")
        raise HTTPException(500, f"更新失败: {e}")


@app.post("/proactive_vision/enable")
async def enable_proactive_vision(payload: dict[str, Any]):
    """启用/禁用主动视觉系统"""
    try:
        enabled = payload.get("enabled", True)

        from agentserver.dogtag import get_dogtag_registry, load_proactive_config, save_proactive_config
        from agentserver.dogtag.models import DutyStatus

        config = load_proactive_config()
        config.enabled = enabled

        if save_proactive_config(config):
            registry = get_dogtag_registry()
            registry.update_status(
                "screen_vision",
                DutyStatus.ENABLED if enabled else DutyStatus.DISABLED,
            )

            status = "已启用" if enabled else "已禁用"
            return {"success": True, "message": f"主动视觉系统{status}", "enabled": enabled}
        else:
            raise HTTPException(500, "配置保存失败")
    except Exception as e:
        logger.error(f"切换 ProactiveVision 状态失败: {e}")
        raise HTTPException(500, f"操作失败: {e}")


@app.get("/proactive_vision/status")
async def get_proactive_vision_status():
    """获取主动视觉系统运行状态"""
    try:
        if not Modules.dogtag_scheduler:
            return {
                "success": True,
                "running": False,
                "enabled": False,
                "message": "调度器未初始化",
            }

        from agentserver.dogtag import get_dogtag_registry, get_proactive_analyzer, load_proactive_config

        config = load_proactive_config()
        registry = get_dogtag_registry()
        sv_tag = registry.get("screen_vision")

        # 获取性能统计
        performance_stats = {}
        analyzer = get_proactive_analyzer()
        if analyzer:
            performance_stats = analyzer.get_performance_stats()

        return {
            "success": True,
            "running": Modules.dogtag_scheduler._running,
            "enabled": config.enabled,
            "duty_status": sv_tag.status.value if sv_tag else "unregistered",
            "last_check": Modules.dogtag_scheduler._last_check_times.get("screen_vision", 0),
            "last_activity": Modules.dogtag_scheduler._last_user_activity,
            "check_interval": config.check_interval_seconds,
            "performance": performance_stats,
        }
    except Exception as e:
        logger.error(f"获取 ProactiveVision 状态失败: {e}")
        raise HTTPException(500, f"获取失败: {e}")


@app.post("/proactive_vision/trigger/test")
async def test_proactive_vision_trigger(payload: dict[str, Any]):
    """测试触发规则（忽略冷却时间）"""
    try:
        rule_id = payload.get("rule_id")
        if not rule_id:
            raise HTTPException(400, "rule_id 不能为空")

        from agentserver.dogtag import get_proactive_trigger, load_proactive_config

        config = load_proactive_config()
        rule = None
        for r in config.trigger_rules:
            if r.rule_id == rule_id:
                rule = r
                break

        if not rule:
            raise HTTPException(404, f"规则不存在: {rule_id}")

        trigger = get_proactive_trigger()
        if not trigger:
            raise HTTPException(503, "触发器未初始化")

        # 重置冷却时间以允许立即触发
        trigger.reset_cooldown(rule_id)

        # 发送测试消息
        test_context = "这是一条测试消息"
        await trigger.send_proactive_message(rule, test_context)

        return {"success": True, "message": f"测试触发规则: {rule.name}"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"测试 ProactiveVision 触发失败: {e}")
        raise HTTPException(500, f"测试失败: {e}")


@app.post("/proactive_vision/activity")
async def update_user_activity():
    """更新用户活动时间（由前端定期调用）"""
    try:
        if Modules.dogtag_scheduler:
            Modules.dogtag_scheduler.update_user_activity()
        return {"success": True}
    except Exception as e:
        logger.error(f"更新用户活动时间失败: {e}")
        return {"success": False, "error": str(e)}


@app.post("/proactive_vision/window_mode")
async def set_proactive_vision_window_mode(payload: dict[str, Any]):
    """设置窗口模式（由前端在模式切换时调用）

    ProactiveVision只在悬浮球模式（ball/compact/full）下运行，classic模式时暂停

    Args:
        payload: {"mode": "classic" | "ball" | "compact" | "full"}
    """
    try:
        mode = payload.get("mode", "classic")

        if mode not in ("classic", "ball", "compact", "full"):
            return {"success": False, "error": f"无效的窗口模式: {mode}"}

        if Modules.dogtag_scheduler:
            Modules.dogtag_scheduler.set_window_mode(mode)

        return {
            "success": True,
            "mode": mode,
            "active": mode in ("ball", "compact", "full"),
        }
    except Exception as e:
        logger.error(f"设置窗口模式失败: {e}")
        return {"success": False, "error": str(e)}


@app.post("/proactive_vision/reset_timer")
async def reset_proactive_vision_timer(payload: dict[str, Any]):
    """重置ProactiveVision检查计时器（由MCP Server调用）

    当AI主动调用screen_vision MCP时，MCP Server会调用此API重置计时器，
    避免ProactiveVision短时间内重复分析同一屏幕。

    Args:
        payload: {"reason": "mcp_call_screen_vision"}
    """
    try:
        reason = payload.get("reason", "external_trigger")

        if Modules.dogtag_scheduler:
            Modules.dogtag_scheduler.reset_check_timer("screen_vision", reason)
            return {
                "success": True,
                "message": "计时器已重置",
                "reason": reason,
            }
        else:
            return {
                "success": False,
                "error": "军牌调度器未初始化",
            }
    except Exception as e:
        logger.error(f"重置ProactiveVision计时器失败: {e}")
        return {"success": False, "error": str(e)}


@app.get("/proactive_vision/metrics")
async def get_proactive_vision_metrics():
    """获取ProactiveVision性能指标"""
    try:
        from agentserver.dogtag.screen_vision.metrics import get_metrics

        metrics = get_metrics()
        all_metrics = metrics.get_all_metrics()

        return {
            "success": True,
            "metrics": all_metrics,
        }
    except Exception as e:
        logger.error(f"获取 ProactiveVision metrics 失败: {e}")
        raise HTTPException(500, f"获取失败: {e}")


@app.get("/proactive_vision/metrics/prometheus")
async def get_proactive_vision_metrics_prometheus():
    """获取Prometheus格式的性能指标"""
    try:
        from fastapi.responses import PlainTextResponse

        from agentserver.dogtag.screen_vision.metrics import get_metrics

        metrics = get_metrics()
        prometheus_text = metrics.get_prometheus_format()

        return PlainTextResponse(content=prometheus_text, media_type="text/plain; version=0.0.4")
    except Exception as e:
        logger.error(f"获取 Prometheus metrics 失败: {e}")
        raise HTTPException(500, f"获取失败: {e}")
