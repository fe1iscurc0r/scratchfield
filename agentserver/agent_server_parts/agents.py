"""agent_server_parts.agents —— 自 agentserver/agent_server.py 拆出（工单204 任务一，纯移动）。"""
from __future__ import annotations

from .common import *  # noqa: F401,F403
from .common import Modules, logger  # noqa: F401
from .lifecycle import app  # noqa: F401

async def _process_openclaw_task(instruction: str, session_id: str | None = None) -> dict[str, Any]:
    """通过 OpenClaw 执行任务"""
    try:
        if not Modules.openclaw_client:
            return {
                "success": False,
                "error": "OpenClaw 客户端未初始化",
                "task_type": "openclaw",
                "instruction": instruction,
            }

        logger.info(f"开始通过 OpenClaw 执行任务: {instruction}")

        task = await Modules.openclaw_client.send_message(
            message=instruction,
            session_key=session_id,
            name="陆墨",
        )

        logger.info(f"OpenClaw 任务完成: {instruction}, 状态: {task.status.value}")
        return {
            "success": task.status.value == "completed",
            "result": task.to_dict(),
            "task_type": "openclaw",
            "instruction": instruction,
        }

    except Exception as e:
        logger.error(f"OpenClaw 任务失败: {e}")
        return {"success": False, "error": str(e), "task_type": "openclaw", "instruction": instruction}


@app.post("/openclaw/config")
async def configure_openclaw(payload: dict[str, Any]):
    """配置 OpenClaw 连接

    请求体:
    - gateway_url: Gateway 地址 (默认从 config.openclaw.gateway_url 读取)
    - token: 认证 token
    - timeout: 超时时间
    - default_model: 默认模型
    - default_channel: 默认通道
    """
    try:
        from agentserver.openclaw import OpenClawConfig as ClientOpenClawConfig

        openclaw_config = ClientOpenClawConfig(
            gateway_url=payload.get("gateway_url", config.openclaw.gateway_url),
            token=payload.get("token"),
            hooks_path=payload.get("hooks_path", "/hooks"),
            timeout=payload.get("timeout", config.openclaw.timeout),
            default_model=payload.get("default_model"),
            default_channel=payload.get("default_channel", "last"),
        )
        set_openclaw_config(openclaw_config)
        Modules.openclaw_client = get_openclaw_client()

        logger.info(f"OpenClaw 配置更新: {openclaw_config.gateway_url}")

        return {"success": True, "message": "OpenClaw 配置已更新", "gateway_url": openclaw_config.gateway_url}
    except Exception as e:
        logger.error(f"OpenClaw 配置失败: {e}")
        raise HTTPException(500, f"配置失败: {e}")


@app.get("/openclaw/instances")
async def list_instances():
    """列出所有干员（通讯录），不管进程是否在跑"""
    if not Modules.instance_manager:
        raise HTTPException(503, "实例管理器未就绪")
    return {"instances": Modules.instance_manager.list_agents()}


@app.get("/openclaw/agents")
async def list_agents():
    """列出通讯录中所有干员（不管进程是否在跑）"""
    if not Modules.instance_manager:
        raise HTTPException(503, "实例管理器未就绪")
    return {"agents": Modules.instance_manager.list_agents()}


@app.post("/openclaw/agents")
async def create_agent(payload: dict[str, Any]):
    """新建干员（写 manifest + 创建目录，不启动进程）"""
    if not Modules.instance_manager:
        raise HTTPException(503, "实例管理器未就绪")

    name = payload.get("name")
    character_template = (payload.get("character_template") or payload.get("characterTemplate") or "").strip() or None
    engine = (payload.get("engine") or "openclaw").strip() or "openclaw"
    telemetry_props = {
        "engine": engine,
        "name_length": len(str(name or "")),
        "has_character_template": bool(character_template),
    }
    try:
        inst = Modules.instance_manager.create_agent(
            name,
            character_template=character_template,
            engine=engine,
        )
        await emit_local_telemetry(
            "agent_create",
            {
                **telemetry_props,
                "created_agent_id": inst.id,
            },
            agent_id=inst.id,
        )
        return {
            "id": inst.id,
            "name": inst.name,
            "running": inst.running,
            "character_template": inst.character_template,
            "engine": inst.engine,
        }
    except Exception as e:
        await emit_local_telemetry(
            "agent_create_fail",
            {
                **telemetry_props,
                "error": e,
            },
        )
        logger.error(f"创建干员失败: {e}")
        raise HTTPException(500, f"创建失败: {e}")


@app.get("/openclaw/agents/{agent_id}/settings")
async def get_agent_settings(agent_id: str):
    """读取干员设置（名字 / 引擎 / 人设 / SOUL.md）。"""
    if not Modules.instance_manager:
        raise HTTPException(503, "实例管理器未就绪")

    settings = Modules.instance_manager.get_agent_settings(agent_id)
    if settings is None:
        raise HTTPException(404, "干员不存在")
    return settings


@app.put("/openclaw/agents/{agent_id}/settings")
async def update_agent_settings(agent_id: str, payload: dict[str, Any]):
    """更新干员设置（名字 / 引擎 / 人设 / SOUL.md）。"""
    if not Modules.instance_manager:
        raise HTTPException(503, "实例管理器未就绪")

    name = payload.get("name")
    if name is not None:
        name = str(name).strip()
        if not name:
            raise HTTPException(400, "name 不能为空")

    engine = payload.get("engine")
    if engine is not None:
        engine = str(engine).strip()

    update_character_template = "character_template" in payload or "characterTemplate" in payload
    character_template = payload.get("character_template")
    if character_template is None and "characterTemplate" in payload:
        character_template = payload.get("characterTemplate")
    if character_template is not None:
        character_template = str(character_template).strip() or None

    update_soul_content = "soul_content" in payload or "soulContent" in payload
    soul_content = payload.get("soul_content")
    if soul_content is None and "soulContent" in payload:
        soul_content = payload.get("soulContent")
    if soul_content is not None:
        soul_content = str(soul_content)

    telemetry_props = {
        "changed_fields": sorted(
            field
            for field, changed in (
                ("name", name is not None),
                ("engine", engine is not None),
                ("character_template", update_character_template),
                ("soul_content", update_soul_content),
            )
            if changed
        ),
        "name_length": len(name or "") if name is not None else None,
        "engine": engine,
        "has_character_template": bool(character_template) if update_character_template else None,
        "soul_content_chars": len(soul_content or "") if update_soul_content else None,
    }

    try:
        settings = await Modules.instance_manager.update_agent_settings(
            agent_id,
            name=name,
            character_template=character_template,
            update_character_template=update_character_template,
            engine=engine,
            soul_content=soul_content,
            update_soul_content=update_soul_content,
        )
    except ValueError as exc:
        await emit_local_telemetry(
            "agent_settings_update_fail",
            {
                **telemetry_props,
                "error": str(exc),
                "status_code": 400,
            },
            agent_id=agent_id,
        )
        raise HTTPException(400, str(exc))
    except Exception as exc:
        await emit_local_telemetry(
            "agent_settings_update_fail",
            {
                **telemetry_props,
                "error": exc,
            },
            agent_id=agent_id,
        )
        logger.error(f"更新干员设置失败: {exc}")
        raise HTTPException(500, f"更新失败: {exc}")

    if settings is None:
        await emit_local_telemetry(
            "agent_settings_update_fail",
            {
                **telemetry_props,
                "status_code": 404,
                "error": "干员不存在",
            },
            agent_id=agent_id,
        )
        raise HTTPException(404, "干员不存在")
    await emit_local_telemetry("agent_settings_update", telemetry_props, agent_id=agent_id)
    return settings


@app.delete("/openclaw/agents/{agent_id}")
async def delete_agent(agent_id: str, delete_data: bool = True):
    """从通讯录删除干员 + 停止进程 + 可选删数据"""
    if not Modules.instance_manager:
        raise HTTPException(503, "实例管理器未就绪")

    try:
        await Modules.instance_manager.destroy_agent_async(agent_id, delete_data=delete_data)
        await emit_local_telemetry(
            "agent_delete",
            {
                "delete_data": bool(delete_data),
            },
            agent_id=agent_id,
        )
        return {"success": True}
    except Exception as e:
        await emit_local_telemetry(
            "agent_delete_fail",
            {
                "delete_data": bool(delete_data),
                "error": e,
            },
            agent_id=agent_id,
        )
        logger.error(f"删除干员失败: {e}")
        raise HTTPException(500, f"删除失败: {e}")


@app.put("/openclaw/agents/{agent_id}/name")
async def rename_agent(agent_id: str, payload: dict[str, Any]):
    """重命名干员（通讯录 + 目录）"""
    if not Modules.instance_manager:
        raise HTTPException(503, "实例管理器未就绪")
    new_name = (payload.get("name") or "").strip()
    if not new_name:
        await emit_local_telemetry(
            "agent_rename_fail",
            {
                "name_length": 0,
                "status_code": 400,
                "error": "name 不能为空",
            },
            agent_id=agent_id,
        )
        raise HTTPException(400, "name 不能为空")
    ok = Modules.instance_manager.rename_agent(agent_id, new_name)
    if not ok:
        await emit_local_telemetry(
            "agent_rename_fail",
            {
                "name_length": len(new_name),
                "status_code": 404,
                "error": "干员不存在",
            },
            agent_id=agent_id,
        )
        raise HTTPException(404, "干员不存在")
    await emit_local_telemetry(
        "agent_rename",
        {
            "name_length": len(new_name),
        },
        agent_id=agent_id,
    )
    return {"success": True, "name": new_name}


@app.get("/openclaw/agents/{agent_id}/history")
async def get_agent_history(agent_id: str, limit: int = 50):
    """获取干员对话历史（自动 ensure_running 启动进程）"""
    if not Modules.instance_manager:
        raise HTTPException(503, "实例管理器未就绪")
    inst = Modules.instance_manager.get_instance(agent_id)
    if inst is None:
        raise HTTPException(404, "干员不存在")
    if inst.engine != "openclaw":
        return {"messages": []}

    # 按需启动进程（需要 Gateway 运行才能查询 session 历史）
    if not inst.running or not inst.client:
        try:
            inst = await Modules.instance_manager.ensure_running(agent_id)
        except Exception as e:
            logger.warning(f"启动干员 [{agent_id}] 以获取历史失败: {e}")
            return {"messages": []}

    session_key = inst.client._default_session_key
    if not session_key:
        logger.warning(f"干员 [{inst.name}] session_key 为空，无法获取历史")
        return {"messages": []}

    try:
        logger.info(f"获取干员 [{inst.name}] 历史: session_key={session_key}, limit={limit}")
        history = await inst.client.get_local_session_history(
            session_key=session_key,
            limit=limit,
        )
        if history.get("success"):
            messages = [
                msg for msg in history.get("messages", [])
                if isinstance(msg, dict) and msg.get("role") in ("user", "assistant")
            ]
            logger.info(f"解析后有效消息: {len(messages)} 条")
            return {"messages": messages}
        logger.warning(f"获取干员 [{inst.name}] 历史失败: {history.get('error', 'unknown')}")
        return {"messages": []}
    except Exception as e:
        logger.warning(f"获取干员 [{inst.name}] 历史失败: {e}", exc_info=True)
        return {"messages": []}


@app.get("/openclaw/agents/{agent_id}/runtime")
async def get_agent_runtime(agent_id: str, wake: bool = False):
    """解析指定干员当前运行时；wake=true 时若未启动则按需唤醒。"""
    if not Modules.instance_manager:
        raise HTTPException(503, "实例管理器未就绪")

    try:
        runtime = await Modules.instance_manager.resolve_runtime(agent_id, wake=wake)
        return {"success": True, "runtime": runtime}
    except RuntimeError as exc:
        detail = str(exc)
        status = 404 if "不存在" in detail else 409
        raise HTTPException(status, detail)
    except Exception as exc:
        logger.error(f"解析干员运行时失败 [{agent_id}]: {exc}")
        raise HTTPException(500, f"解析运行时失败: {exc}")


@app.post("/openclaw/agents/{agent_id}/send")
async def send_to_agent(agent_id: str, payload: dict[str, Any]):
    """向指定干员发送消息（同步等待结果），内部自动 ensure_running。"""
    if not Modules.instance_manager:
        raise HTTPException(503, "实例管理器未就绪")

    message = payload.get("message", "")
    if not message:
        raise HTTPException(400, "message 不能为空")

    timeout = int(payload.get("timeout_seconds", 120) or 120)
    session_key = payload.get("session_key")
    name = payload.get("name")

    result = await Modules.instance_manager.send_message(
        agent_id,
        message,
        timeout=timeout,
        session_key=session_key,
        name=name,
    )
    if not result.get("success", False) and "error" in result:
        logger.warning(f"发送消息到干员 [{agent_id}] 失败: {result.get('error')}")
    return result


@app.post("/openclaw/agents/{agent_id}/stream")
async def stream_to_agent(agent_id: str, payload: dict[str, Any]):
    """向干员发送消息（SSE 流式输出），内部自动 ensure_running"""
    import json as _json

    from fastapi.responses import StreamingResponse

    if not Modules.instance_manager:
        raise HTTPException(503, "实例管理器未就绪")

    message = payload.get("message", "")
    if not message:
        raise HTTPException(400, "message 不能为空")

    timeout = payload.get("timeout_seconds", 120)

    async def event_stream():
        async for chunk in Modules.instance_manager.send_message_stream(agent_id, message, timeout):
            yield f"data: {_json.dumps(chunk, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
