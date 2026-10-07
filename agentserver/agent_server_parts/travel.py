"""agent_server_parts.travel —— 自 agentserver/agent_server.py 拆出（工单204 任务一，纯移动）。"""
from __future__ import annotations

from .common import *  # noqa: F401,F403
from .common import Modules  # noqa: F401
from .lifecycle import app  # noqa: F401
from .session import _interrupt_travel_sessions, _spawn_travel_session  # noqa: F401

@app.post("/travel/execute")
async def travel_execute(payload: dict[str, Any]):
    """接收旅行 session_id，异步启动旅行协程"""
    session_id = payload.get("session_id")
    if not session_id:
        raise HTTPException(400, "session_id 不能为空")

    from apiserver.travel_service import TravelStatus, load_session

    try:
        session = load_session(session_id)
    except FileNotFoundError:
        raise HTTPException(404, "旅行 session 不存在")

    if session.agent_id:
        if not Modules.instance_manager:
            raise HTTPException(503, "实例管理器未就绪")
    elif not Modules.openclaw_client:
        raise HTTPException(503, "OpenClaw 客户端未就绪")

    _spawn_travel_session(session_id, resumed=session.status == TravelStatus.INTERRUPTED)
    return {"status": "accepted", "session_id": session_id}


@app.post("/travel/interrupt")
async def travel_interrupt(payload: dict[str, Any]):
    """将一个或多个探索任务切到 interrupted，并中断对应协程。"""
    raw_session_ids = payload.get("session_ids")
    session_id = payload.get("session_id")
    session_ids: list[str] | None
    if isinstance(raw_session_ids, list):
        session_ids = [str(item) for item in raw_session_ids if item]
    elif session_id:
        session_ids = [str(session_id)]
    else:
        session_ids = None

    interrupted_ids = await _interrupt_travel_sessions(
        session_ids=session_ids,
        reason=str(payload.get("reason") or "interrupted"),
    )
    return {"status": "success", "session_ids": interrupted_ids}


@app.post("/travel/browser-settings")
async def travel_browser_settings(payload: dict[str, Any]):
    from apiserver.travel_service import load_session

    session_id = payload.get("session_id")
    if not session_id:
        raise HTTPException(400, "session_id 不能为空")

    try:
        session = load_session(str(session_id))
    except FileNotFoundError:
        raise HTTPException(404, "旅行 session 不存在")

    if not session.agent_id or not Modules.instance_manager:
        return {"status": "success", "applied": False, "reason": "no_agent_instance"}

    visible = payload.get("browser_visible")
    result = await Modules.instance_manager.update_browser_preferences(
        session.agent_id,
        visible=None if visible is None else bool(visible),
    )
    return {"status": "success", "applied": True, "result": result}


@app.post("/travel/instruction")
async def travel_instruction(payload: dict[str, Any]):
    from apiserver.travel_service import (
        OPEN_TRAVEL_STATUSES,
        append_progress_event,
        build_travel_instruction_prompt,
        load_session,
        save_session,
    )

    session_id = str(payload.get("session_id") or "").strip()
    message = str(payload.get("message") or "").strip()
    if not session_id:
        raise HTTPException(400, "session_id 不能为空")
    if not message:
        raise HTTPException(400, "message 不能为空")

    try:
        session = load_session(session_id)
    except FileNotFoundError:
        raise HTTPException(404, "旅行 session 不存在")

    if session.status not in OPEN_TRAVEL_STATUSES:
        raise HTTPException(409, "当前探索已结束，不能再追加指令")

    session_key = (session.openclaw_session_key or "").strip()
    if not session_key:
        raise HTTPException(409, "当前探索还没进入可交互阶段")

    prompt = build_travel_instruction_prompt(message)
    if session.agent_id:
        if not Modules.instance_manager:
            raise HTTPException(503, "实例管理器未就绪")
        await Modules.instance_manager.ensure_running(session.agent_id)

        async def _worker(inst):
            if not inst.client:
                raise RuntimeError(f"干员 [{inst.name}] 客户端未就绪")
            return await inst.client.send_message(
                message=prompt,
                session_key=session_key,
                name="NagaTravel",
                timeout_seconds=0,
            )

        await Modules.instance_manager.run_serialized(session.agent_id, _worker)
    else:
        if not Modules.openclaw_client:
            raise HTTPException(503, "OpenClaw 客户端未就绪")
        await Modules.openclaw_client.send_message(
            message=prompt,
            session_key=session_key,
            name="NagaTravel",
            timeout_seconds=0,
        )

    append_progress_event(
        session,
        "user_instruction",
        f"已追加探索指令：{message[:80]}",
        meta={"message": message[:400]},
    )
    save_session(session)
    return {"status": "success", "session_id": session_id}
