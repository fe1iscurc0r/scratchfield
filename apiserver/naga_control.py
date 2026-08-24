#!/usr/bin/env python3
"""
Naga Self-Orchestration — 让 LLM 直接调度 Naga 自身能力

通过 agentType: "naga_control" 在 agentic tool loop 中调用，
无需 HTTP 请求，直接 import 调用内部模块。

toggle_voice / toggle_live2d 控制的是**运行时状态**（暂停/恢复），
不会写入 config.json。只有 update_config 才会持久化。
"""

import json
import logging
from collections.abc import Callable, Coroutine
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Action 注册表
# ---------------------------------------------------------------------------

ACTIONS: dict[str, Callable[..., Coroutine[Any, Any, dict[str, Any]]]] = {}


def register(name: str):
    """装饰器：注册一个 naga_control action"""
    def decorator(fn):
        ACTIONS[name] = fn
        return fn
    return decorator


async def execute(action: str, params: dict) -> dict:
    """执行 naga_control action，返回 {success, result/error}"""
    handler = ACTIONS.get(action)
    if not handler:
        available = ", ".join(sorted(ACTIONS.keys()))
        return {"success": False, "error": f"未知操作: {action}。可用操作: {available}"}
    try:
        return await handler(params)
    except Exception as e:
        logger.error(f"[NagaControl] action={action} 执行异常: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


# ---------------------------------------------------------------------------
# 运行时开关状态（不写入 config.json）
# ---------------------------------------------------------------------------

_runtime_overrides: dict[str, Any] = {}
# key: "voice_paused" | "live2d_paused"


def is_voice_paused() -> bool:
    """TTS 是否被运行时暂停（供 api_server 检查）"""
    return _runtime_overrides.get("voice_paused", False)


def is_live2d_paused() -> bool:
    """Live2D 是否被运行时暂停"""
    return _runtime_overrides.get("live2d_paused", False)


# ---------------------------------------------------------------------------
# Action 实现
# ---------------------------------------------------------------------------


@register("get_config")
async def _get_config(params: dict) -> dict:
    """读取当前配置（全部或指定 section）"""
    from system.config import get_config

    cfg = get_config()
    section = params.get("section")

    if section:
        section_obj = getattr(cfg, section, None)
        if section_obj is None:
            valid = [f for f in cfg.model_fields if f != "window"]
            return {"success": False, "error": f"未知配置节: {section}。可选: {', '.join(valid)}"}
        data = section_obj.model_dump() if hasattr(section_obj, "model_dump") else str(section_obj)
        return {"success": True, "result": {section: data}}

    # 全量（排除 window 等不可序列化字段）
    data = cfg.model_dump(exclude={"window"})
    # 只返回常用 section 的摘要，避免过长
    summary = {}
    for key in ("system", "api", "tts", "live2d", "openclaw", "handoff"):
        if key in data:
            summary[key] = data[key]
    return {"success": True, "result": summary}


@register("update_config")
async def _update_config(params: dict) -> dict:
    """修改配置并持久化到 config.json + 热更新"""
    config_updates = params.get("config")
    if not config_updates or not isinstance(config_updates, dict):
        return {"success": False, "error": "需要 config 参数（dict），如 {\"api\": {\"temperature\": 0.5}}"}

    from system.config_manager import update_config

    success = update_config(config_updates)
    if success:
        return {"success": True, "result": "配置已更新并热重载"}
    return {"success": False, "error": "配置更新失败，请检查参数"}


@register("get_status")
async def _get_status(params: dict) -> dict:
    """获取系统运行状态"""
    from system.config import get_all_server_ports, get_config

    cfg = get_config()
    status = {
        "ai_name": cfg.system.ai_name,
        "active_character": cfg.system.active_character,
        "model": cfg.api.model,
        "base_url": cfg.api.base_url,
        "voice_enabled": cfg.system.voice_enabled,
        "voice_paused": is_voice_paused(),
        "live2d_enabled": cfg.live2d.enabled,
        "live2d_paused": is_live2d_paused(),
        "openclaw_enabled": cfg.openclaw.enabled,
        "server_ports": get_all_server_ports(),
    }

    # 会话数
    try:
        from apiserver.message_manager import message_manager
        status["active_sessions"] = len(message_manager.sessions)
    except Exception:
        pass

    return {"success": True, "result": status}


@register("toggle_voice")
async def _toggle_voice(params: dict) -> dict:
    """运行时暂停/恢复 TTS（不修改 config.json）"""
    enabled = params.get("enabled")
    if enabled is None:
        return {"success": False, "error": "需要 enabled 参数 (bool)"}

    _runtime_overrides["voice_paused"] = not enabled
    state = "已恢复" if enabled else "已暂停"
    logger.info(f"[NagaControl] 语音 TTS {state}（运行时）")
    return {"success": True, "result": f"语音 {state}（运行时状态，不影响设置）"}


@register("toggle_live2d")
async def _toggle_live2d(params: dict) -> dict:
    """运行时暂停/恢复 Live2D（不修改 config.json）"""
    enabled = params.get("enabled")
    if enabled is None:
        return {"success": False, "error": "需要 enabled 参数 (bool)"}

    _runtime_overrides["live2d_paused"] = not enabled

    # 通知 UI 隐藏/显示 Live2D
    try:
        import httpx

        from system.config import get_server_port
        async with httpx.AsyncClient(timeout=3.0, trust_env=False) as client:
            await client.post(
                f"http://localhost:{get_server_port('api_server')}/ui_notification",
                json={"action": "live2d_toggle", "enabled": enabled},
            )
    except Exception:
        pass

    state = "已恢复" if enabled else "已暂停"
    logger.info(f"[NagaControl] Live2D {state}（运行时）")
    return {"success": True, "result": f"Live2D {state}（运行时状态，不影响设置）"}


@register("set_model")
async def _set_model(params: dict) -> dict:
    """切换 LLM 模型（持久化到 config.json）。
    仅允许修改 model 名称，禁止 LLM 改写 base_url 或 api_key 防止提示注入→密钥外泄。
    """
    model = params.get("model")
    if not model:
        return {"success": False, "error": "需要 model 参数"}

    from system.config_manager import update_config
    success = update_config({"api": {"model": model}})
    if success:
        return {"success": True, "result": f"模型已切换为 {model}"}
    return {"success": False, "error": "模型切换失败"}


@register("list_characters")
async def _list_characters(params: dict) -> dict:
    """列出可用角色"""
    from system.config import CHARACTERS_DIR, get_config

    characters = []
    if CHARACTERS_DIR.exists():
        for d in sorted(CHARACTERS_DIR.iterdir()):
            if d.is_dir() and (d / f"{d.name}.json").exists():
                try:
                    from system.config import load_character
                    char_data = load_character(d.name)
                    characters.append({
                        "name": d.name,
                        "voice": char_data.get("voice", ""),
                        "description": char_data.get("description", ""),
                    })
                except Exception:
                    characters.append({"name": d.name})

    active = get_config().system.active_character
    return {"success": True, "result": {"active": active, "characters": characters}}


@register("switch_character")
async def _switch_character(params: dict) -> dict:
    """切换到已有角色"""
    character = params.get("character")
    if not character:
        return {"success": False, "error": "需要 character 参数"}

    from system.config import CHARACTERS_DIR, set_active_character
    char_dir = CHARACTERS_DIR / character
    if not char_dir.exists():
        return {"success": False, "error": f"角色 '{character}' 不存在"}

    set_active_character(character)

    # 同步更新 config.json 中的 active_character
    from system.config_manager import update_config
    update_config({"system": {"active_character": character}})

    return {"success": True, "result": f"已切换到角色: {character}"}


@register("list_sessions")
async def _list_sessions(params: dict) -> dict:
    """列出会话"""
    from apiserver.message_manager import message_manager

    limit = params.get("limit", 20)
    sessions = []
    for sid, sdata in list(message_manager.sessions.items())[:limit]:
        sessions.append({
            "session_id": sid,
            "created_at": sdata.get("created_at", ""),
            "last_activity": sdata.get("last_activity", ""),
            "message_count": len(sdata.get("messages", [])),
            "agent_type": sdata.get("agent_type", "default"),
        })
    return {"success": True, "result": {"count": len(message_manager.sessions), "sessions": sessions}}


@register("clear_session")
async def _clear_session(params: dict) -> dict:
    """清空指定会话"""
    session_id = params.get("session_id")
    if not session_id:
        return {"success": False, "error": "需要 session_id 参数"}

    from apiserver.message_manager import message_manager
    success = message_manager.delete_session(session_id)
    if success:
        return {"success": True, "result": f"会话 {session_id} 已清空"}
    return {"success": False, "error": f"会话 {session_id} 不存在"}


@register("list_skills")
async def _list_skills(params: dict) -> dict:
    """列出可用技能"""
    from system.skill_manager import get_skill_manager

    mgr = get_skill_manager()
    skills = mgr.list_skills()
    return {"success": True, "result": skills}


@register("toggle_skill")
async def _toggle_skill(params: dict) -> dict:
    """启用/禁用技能"""
    name = params.get("name")
    enabled = params.get("enabled")
    if not name or enabled is None:
        return {"success": False, "error": "需要 name 和 enabled 参数"}

    from system.skill_manager import get_skill_manager

    mgr = get_skill_manager()
    success = mgr.enable_skill(name, enabled)
    if success:
        state = "已启用" if enabled else "已禁用"
        return {"success": True, "result": f"技能 '{name}' {state}"}
    return {"success": False, "error": f"技能 '{name}' 不存在"}


@register("list_mcp_services")
async def _list_mcp_services(params: dict) -> dict:
    """列出 MCP 服务"""
    try:
        from mcpserver.mcp_manager import get_mcp_manager
        mgr = get_mcp_manager()
        services = mgr.get_available_services_filtered()
        return {"success": True, "result": services}
    except Exception as e:
        return {"success": False, "error": f"获取 MCP 服务列表失败: {e}"}


@register("start_travel")
async def _start_travel(params: dict) -> dict:
    """启动旅行（创建会话 + 代理到 agent_server 执行）"""
    from apiserver.travel_service import create_session, get_open_session_for_agent

    agent_id = params.get("agent_id")
    active = get_open_session_for_agent(agent_id)
    if active:
        return {"success": False, "error": f"该干员已有进行中的旅行 (session_id={active.session_id})，请先停止"}

    session = create_session(
        agent_id=agent_id,
        time_limit_minutes=params.get("time_limit", 300),
        credit_limit=params.get("credit_limit", 1000),
        goal_prompt=params.get("goal_prompt"),
        post_to_forum=params.get("post_to_forum", True),
        deliver_full_report=params.get("deliver_full_report", True),
        deliver_channel=params.get("deliver_channel"),
        deliver_to=params.get("deliver_to"),
    )

    # 代理到 agent_server 实际执行探索
    try:
        import httpx

        from system.config import get_server_port
        port = get_server_port("agent_server")
        async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
            resp = await client.post(
                f"http://127.0.0.1:{port}/travel/execute",
                json={"session_id": session.session_id},
            )
            if resp.status_code >= 400:
                logger.warning(f"[NagaControl] 旅行执行请求失败: {resp.status_code} {resp.text}")
    except Exception as e:
        logger.warning(f"[NagaControl] 代理旅行到 agent_server 失败: {e}")

    return {"success": True, "result": {
        "session_id": session.session_id,
        "status": session.status.value,
        "time_limit_minutes": session.time_limit_minutes,
    }}


@register("stop_travel")
async def _stop_travel(params: dict) -> dict:
    """停止旅行"""
    from apiserver.travel_service import (
        TravelStatus,
        get_active_session,
        load_session,
        remove_session_browser_policy,
        save_session,
    )

    session_id = params.get("session_id")
    active = load_session(session_id) if session_id else get_active_session()
    if not active:
        return {"success": False, "error": "当前没有进行中的旅行"}

    active.status = TravelStatus.CANCELLED
    active.completed_at = datetime.now().isoformat()
    save_session(active)
    remove_session_browser_policy(active.openclaw_session_key)
    return {"success": True, "result": f"旅行 {active.session_id} 已停止"}


@register("get_memory_stats")
async def _get_memory_stats(params: dict) -> dict:
    """获取记忆统计"""
    stats: dict[str, Any] = {}

    # 会话记忆
    try:
        from apiserver.message_manager import message_manager
        total_msgs = sum(len(s.get("messages", [])) for s in message_manager.sessions.values())
        stats["sessions"] = {"count": len(message_manager.sessions), "total_messages": total_msgs}
    except Exception:
        pass

    # 日志文件
    try:
        from system.config import get_data_dir
        log_dir = get_data_dir() / "logs"
        if log_dir.exists():
            log_files = list(log_dir.glob("*.log"))
            stats["logs"] = {"file_count": len(log_files)}
    except Exception:
        pass

    return {"success": True, "result": stats}


@register("play_music")
async def _play_music(params: dict) -> dict:
    """控制前端音乐播放器"""
    action = params.get("action", "play")  # play / pause / next / prev / toggle
    track = params.get("track")  # 可选：指定曲目文件名

    command = {"music_action": action}
    if track:
        command["track"] = track

    try:
        import httpx

        from system.config import get_server_port
        async with httpx.AsyncClient(timeout=3.0, trust_env=False) as client:
            await client.post(
                f"http://localhost:{get_server_port('api_server')}/ui_notification",
                json={"action": "music_control", **command},
            )
        if track:
            return {"success": True, "result": f"音乐指令已发送: {action} - {track}"}
        return {"success": True, "result": f"音乐指令已发送: {action}"}
    except Exception as e:
        return {"success": False, "error": f"音乐控制失败: {e}"}


@register("send_notification")
async def _send_notification(params: dict) -> dict:
    """发送 UI 通知"""
    message = params.get("message")
    if not message:
        return {"success": False, "error": "需要 message 参数"}

    try:
        import httpx

        from system.config import get_server_port
        async with httpx.AsyncClient(timeout=3.0, trust_env=False) as client:
            await client.post(
                f"http://localhost:{get_server_port('api_server')}/ui_notification",
                json={
                    "action": "show_notification",
                    "message": message,
                    "type": params.get("type", "info"),
                },
            )
        return {"success": True, "result": "通知已发送"}
    except Exception as e:
        return {"success": False, "error": f"通知发送失败: {e}"}
