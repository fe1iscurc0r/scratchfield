"""agent_server_parts.openclaw —— 自 agentserver/agent_server.py 拆出（工单204 任务一，纯移动）。"""
from __future__ import annotations

from .common import *  # noqa: F401,F403
from .common import Modules, logger  # noqa: F401
from .lifecycle import _start_gateway_if_port_free, app  # noqa: F401
from .search import _local_search_proxy  # noqa: F401

@app.post("/openclaw/send")
async def openclaw_send_message(payload: dict[str, Any]):
    """
    发送消息给 OpenClaw Agent

    使用 POST /hooks/agent 端点
    文档: https://docs.openclaw.ai/automation/webhook

    请求体:
    - message: 消息内容 (必需)
    - task_id: 外部任务ID（可选；用于与调度器task_id对齐）
    - session_key: 会话标识 (可选)
    - name: hook 名称 (可选)
    - channel: 消息通道 (可选)
    - to: 接收者 (可选)
    - model: 模型名称 (可选)
    - wake_mode: 唤醒模式 now/next-heartbeat (可选)
    - deliver: 是否投递 (可选)
    - timeout_seconds: 等待结果超时时间，默认120秒 (可选)
    """
    if not Modules.openclaw_client:
        raise HTTPException(503, "OpenClaw 客户端未就绪")

    message = payload.get("message")
    if not message:
        raise HTTPException(400, "message 不能为空")

    # 如果提供了 task_id 但未提供 session_key，则默认使用 task_id 派生稳定会话键，便于按任务查看中间过程
    task_id = payload.get("task_id")
    session_key = payload.get("session_key")
    if task_id and not session_key:
        session_key = f"naga:task:{task_id}"

    try:
        task = await Modules.openclaw_client.send_message(
            message=message,
            session_key=session_key,
            name=payload.get("name"),
            channel=payload.get("channel"),
            to=payload.get("to"),
            model=payload.get("model"),
            wake_mode=payload.get("wake_mode", "now"),
            deliver=payload.get("deliver", False),
            timeout_seconds=payload.get("timeout_seconds", 120),
            task_id=task_id,
        )

        return {
            "success": task.status.value != "failed",
            "task": task.to_dict(),
            "reply": task.result.get("reply") if task.result else None,
            "replies": task.result.get("replies") if task.result else None,
            "error": task.error,
        }
    except Exception as e:
        logger.error(f"OpenClaw 发送消息失败: {e}")
        raise HTTPException(500, f"发送失败: {e}")


@app.post("/openclaw/wake")
async def openclaw_wake(payload: dict[str, Any]):
    """
    触发 OpenClaw 系统事件

    使用 POST /hooks/wake 端点
    文档: https://docs.openclaw.ai/automation/webhook

    请求体:
    - text: 事件描述 (必需)
    - mode: 触发模式 now/next-heartbeat (可选)
    """
    if not Modules.openclaw_client:
        raise HTTPException(503, "OpenClaw 客户端未就绪")

    text = payload.get("text")
    if not text:
        raise HTTPException(400, "text 不能为空")

    try:
        result = await Modules.openclaw_client.wake(text=text, mode=payload.get("mode", "now"))
        return result
    except Exception as e:
        logger.error(f"OpenClaw 触发事件失败: {e}")
        raise HTTPException(500, f"触发失败: {e}")


@app.post("/openclaw/tools/invoke")
async def openclaw_invoke_tool(payload: dict[str, Any]):
    """
    直接调用 OpenClaw 工具

    使用 POST /tools/invoke 端点
    文档: https://docs.openclaw.ai/gateway/tools-invoke-http-api

    请求体:
    - tool: 工具名称 (必需)
    - args: 工具参数 (可选)
    - action: 动作 (可选)
    - session_key: 会话标识 (可选)
    """
    tool = payload.get("tool")
    if not tool:
        raise HTTPException(400, "tool 不能为空")

    # web_search 拦截：走本地搜索代理，不转发给 OpenClaw
    if tool == "web_search":
        return await _local_search_proxy(payload.get("args") or {})

    if not Modules.openclaw_client:
        raise HTTPException(503, "OpenClaw 客户端未就绪")

    try:
        result = await Modules.openclaw_client.invoke_tool(
            tool=tool, args=payload.get("args"), action=payload.get("action"), session_key=payload.get("session_key")
        )
        return result
    except Exception as e:
        logger.error(f"OpenClaw 工具调用失败: {e}")
        raise HTTPException(500, f"调用失败: {e}")


@app.get("/openclaw/tasks")
async def openclaw_get_local_tasks():
    """获取本地缓存的所有 OpenClaw 任务"""
    if not Modules.openclaw_client:
        raise HTTPException(503, "OpenClaw 客户端未就绪")

    try:
        tasks = Modules.openclaw_client.get_all_tasks()
        return {"success": True, "tasks": [task.to_dict() for task in tasks], "count": len(tasks)}
    except Exception as e:
        logger.error(f"获取 OpenClaw 任务失败: {e}")
        raise HTTPException(500, f"获取失败: {e}")


@app.get("/openclaw/tasks/{task_id}")
async def openclaw_get_task(task_id: str):
    """获取单个 OpenClaw 任务"""
    if not Modules.openclaw_client:
        raise HTTPException(503, "OpenClaw 客户端未就绪")

    try:
        task = Modules.openclaw_client.get_task(task_id)
        if task:
            return {"success": True, "task": task.to_dict()}
        else:
            raise HTTPException(404, f"任务不存在: {task_id}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取 OpenClaw 任务失败: {e}")
        raise HTTPException(500, f"获取失败: {e}")


@app.get("/openclaw/tasks/{task_id}/detail")
async def openclaw_get_task_detail(
    task_id: str,
    include_history: bool = True,
    history_limit: int = 50,
    include_tools: bool = False,
):
    """获取单个 OpenClaw 任务详情（包含本地 events 与可选 sessions_history）"""
    if not Modules.openclaw_client:
        raise HTTPException(503, "OpenClaw 客户端未就绪")

    try:
        task = Modules.openclaw_client.get_task(task_id)
        if not task:
            raise HTTPException(404, f"任务不存在: {task_id}")

        resp: dict[str, Any] = {
            "success": True,
            "task": task.to_dict(),
        }

        if include_history:
            if task.session_key:
                history = await Modules.openclaw_client.get_sessions_history(
                    session_key=task.session_key,
                    limit=history_limit,
                    include_tools=include_tools,
                )
                resp["history"] = history
            else:
                resp["history"] = {"success": True, "messages": [], "note": "task_has_no_session_key"}

        return resp
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取 OpenClaw 任务详情失败: {e}")
        raise HTTPException(500, f"获取失败: {e}")


@app.get("/openclaw/history")
async def openclaw_get_history(
    session_key: str | None = None,
    limit: int = 120,
    include_tools: bool = True,
):
    """
    获取 OpenClaw 历史。

    - session_key 为空：读取当前默认会话的 Gateway sessions_history。
    - session_key 非空：读取对应本地 transcript，供 travel 看板/对话界面查看原始记录。
    """
    normalized_key = str(session_key or "").strip()
    if not normalized_key:
        if not Modules.openclaw_client:
            raise HTTPException(503, "OpenClaw 客户端未就绪")

        try:
            return await Modules.openclaw_client.get_sessions_history(
                session_key=None,
                limit=limit,
                include_tools=include_tools,
            )
        except Exception as e:
            logger.error(f"获取 OpenClaw 默认会话历史失败: {e}")
            raise HTTPException(500, f"获取失败: {e}")

    try:
        if normalized_key.startswith("travel:"):
            parts = normalized_key.split(":")
            agent_id = parts[1] if len(parts) >= 3 and parts[1] != "main" else None
            if agent_id:
                if not Modules.instance_manager:
                    raise HTTPException(503, "实例管理器未就绪")
                inst = await Modules.instance_manager.ensure_running(agent_id)
                if not inst.client:
                    raise HTTPException(503, "干员客户端未就绪")
                history = await inst.client.get_local_session_transcript(
                    session_key=normalized_key,
                    limit=limit,
                )
            else:
                if not Modules.openclaw_client:
                    raise HTTPException(503, "OpenClaw 客户端未就绪")
                history = await Modules.openclaw_client.get_local_session_transcript(
                    session_key=normalized_key,
                    limit=limit,
                )
        else:
            if not Modules.openclaw_client:
                raise HTTPException(503, "OpenClaw 客户端未就绪")
            history = await Modules.openclaw_client.get_local_session_transcript(
                session_key=normalized_key,
                limit=limit,
            )
        return {"success": True, "history": history}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"按 session_key 获取 OpenClaw 历史失败 [{normalized_key}]: {e}")
        raise HTTPException(500, f"获取失败: {e}")


@app.delete("/openclaw/tasks/completed")
async def openclaw_clear_completed_tasks():
    """清理已完成的 OpenClaw 任务"""
    if not Modules.openclaw_client:
        raise HTTPException(503, "OpenClaw 客户端未就绪")

    try:
        Modules.openclaw_client.clear_completed_tasks()
        return {"success": True, "message": "已清理完成的任务"}
    except Exception as e:
        logger.error(f"清理 OpenClaw 任务失败: {e}")
        raise HTTPException(500, f"清理失败: {e}")


@app.get("/openclaw/session")
async def openclaw_get_session():
    """
    获取当前 OpenClaw 调度终端会话信息

    用于在设置界面显示 Naga 调度 OpenClaw 的终端连接状态

    返回:
    - 有活跃会话: session_key, created_at, last_activity, message_count, last_run_id, status
    - 无会话: has_session=False, message="请和 OpenClaw 交互以显示交互终端"
    """
    if not Modules.openclaw_client:
        raise HTTPException(503, "OpenClaw 客户端未就绪")

    try:
        session_info = Modules.openclaw_client.get_session_info()

        if session_info is None:
            return {"has_session": False, "message": "请和 OpenClaw 交互以显示交互终端"}

        return {"has_session": True, "session": session_info}
    except Exception as e:
        logger.error(f"获取 OpenClaw 会话信息失败: {e}")
        raise HTTPException(500, f"获取失败: {e}")


@app.get("/openclaw/status")
async def openclaw_get_status():
    """
    获取 OpenClaw 当前状态

    调用 session_status 工具获取实时状态

    Returns:
        OpenClaw 当前状态文本
    """
    if not Modules.openclaw_client:
        raise HTTPException(503, "OpenClaw 客户端未就绪")

    try:
        result = await Modules.openclaw_client.get_session_status()
        return result
    except Exception as e:
        logger.error(f"获取 OpenClaw 状态失败: {e}")
        raise HTTPException(500, f"获取失败: {e}")


@app.get("/openclaw/gateway/status")
async def openclaw_gateway_status():
    """查询项目网关（OpenClaw Gateway）运行状态与开关配置"""
    runtime = get_embedded_runtime()
    return {
        "success": True,
        "running": runtime.gateway_running,
        "enabled": config.openclaw.enabled,
        "port": config.openclaw.gateway_port,
        "port_in_use": runtime.is_gateway_port_in_use(),
    }


@app.post("/openclaw/gateway/start")
async def openclaw_gateway_start():
    """启动项目网关：先清理端口残留进程，再拉起 Gateway，并同步置 enabled=True"""
    runtime = get_embedded_runtime()
    if runtime.gateway_running:
        config.openclaw.enabled = True
        return {"success": True, "running": True, "message": "网关已在运行"}
    try:
        from agentserver.openclaw.instance_manager import cleanup_port_range
        cleaned = cleanup_port_range()
        if cleaned:
            await asyncio.sleep(1)  # 等端口释放
    except Exception as e:
        logger.warning(f"网关启动前端口清理失败（可忽略）: {e}")
    ok = await _start_gateway_if_port_free(runtime)
    if ok:
        config.openclaw.enabled = True
    return {"success": ok, "running": runtime.gateway_running, "message": "网关启动成功" if ok else "网关启动失败（见后端日志）"}


@app.post("/openclaw/gateway/stop")
async def openclaw_gateway_stop():
    """停止项目网关并同步置 enabled=False（重启后端后不再自启）"""
    runtime = get_embedded_runtime()
    await runtime.stop_gateway()
    config.openclaw.enabled = False
    return {"success": True, "running": runtime.gateway_running, "message": "网关已停止"}


@app.get("/openclaw/install/check")
async def openclaw_check_installation():
    """
    检查 OpenClaw 安装状态

    Returns:
        安装状态信息
    """
    try:
        from agentserver.openclaw import get_openclaw_installer

        installer = get_openclaw_installer()
        status, version = installer.check_installation()

        # 检查 Node.js
        node_ok, node_version = installer.check_node_version()

        return {
            "success": True,
            "status": status.value,
            "version": version,
            "node_ok": node_ok,
            "node_version": node_version,
            "npm_available": installer.check_npm_available(),
        }
    except Exception as e:
        logger.error(f"检查 OpenClaw 安装状态失败: {e}")
        raise HTTPException(500, f"检查失败: {e}")


@app.post("/openclaw/install")
async def openclaw_install(payload: dict[str, Any] = None):
    """
    安装 OpenClaw

    请求体:
    - method: 安装方式（仅支持 "vendor"；npm/script 已废弃，统一走 vendor），默认 "vendor"

    Returns:
        安装结果
    """
    try:
        from agentserver.openclaw import InstallMethod, get_openclaw_installer

        installer = get_openclaw_installer()

        method_str = ((payload or {}).get("method") or "vendor").lower()
        if method_str not in ("vendor", "npm", "script"):
            raise HTTPException(400, f"不支持的安装方式: {method_str}（仅支持 vendor）")
        # npm/script 已废弃，统一归一到 vendor（InstallMethod 枚举仅含 VENDOR/UNKNOWN）
        method = InstallMethod.VENDOR

        result = await installer.install(method)

        return result.to_dict()
    except Exception as e:
        logger.error(f"安装 OpenClaw 失败: {e}")
        raise HTTPException(500, f"安装失败: {e}")


@app.post("/openclaw/setup")
async def openclaw_setup(payload: dict[str, Any] = None):
    """
    初始化 OpenClaw 配置

    请求体:
    - hooks_token: Hooks 认证 token（可选，不传则自动生成）

    Returns:
        初始化结果
    """
    try:
        from agentserver.openclaw import get_openclaw_installer

        installer = get_openclaw_installer()
        hooks_token = (payload or {}).get("hooks_token")

        result = await installer.setup(hooks_token)

        return result.to_dict()
    except Exception as e:
        logger.error(f"初始化 OpenClaw 失败: {e}")
        raise HTTPException(500, f"初始化失败: {e}")


@app.post("/openclaw/gateway/restart")
async def openclaw_restart_gateway():
    """重启 OpenClaw Gateway"""
    try:
        from agentserver.openclaw import get_openclaw_installer

        installer = get_openclaw_installer()
        result = await installer.restart_gateway()

        return result.to_dict()
    except Exception as e:
        logger.error(f"重启 Gateway 失败: {e}")
        raise HTTPException(500, f"重启失败: {e}")


@app.post("/openclaw/gateway/install")
async def openclaw_install_gateway_service():
    """安装 Gateway 为系统服务"""
    try:
        from agentserver.openclaw import get_openclaw_installer

        installer = get_openclaw_installer()
        result = await installer.install_gateway_service()

        return result.to_dict()
    except Exception as e:
        logger.error(f"安装 Gateway 服务失败: {e}")
        raise HTTPException(500, f"安装失败: {e}")


@app.get("/openclaw/doctor")
async def openclaw_doctor():
    """运行 OpenClaw 健康检查"""
    try:
        from agentserver.openclaw import get_openclaw_installer

        installer = get_openclaw_installer()
        result = await installer.run_doctor()

        return result
    except Exception as e:
        logger.error(f"健康检查失败: {e}")
        raise HTTPException(500, f"检查失败: {e}")


@app.get("/openclaw/config")
async def openclaw_get_config():
    """
    获取 OpenClaw 配置摘要

    只返回安全的配置信息，不包含 token 等敏感数据
    """
    try:
        from agentserver.openclaw import get_openclaw_config_manager

        config_manager = get_openclaw_config_manager()
        summary = config_manager.get_current_config_summary()

        return {"success": True, "config": summary}
    except Exception as e:
        logger.error(f"获取 OpenClaw 配置失败: {e}")
        raise HTTPException(500, f"获取失败: {e}")


@app.post("/openclaw/config/set")
async def openclaw_set_config(payload: dict[str, Any]):
    """
    设置 OpenClaw 配置

    只允许修改白名单中的字段

    请求体:
    - field: 字段路径（如 "agents.defaults.model.primary"）
    - value: 新值

    Returns:
        更新结果
    """
    try:
        from agentserver.openclaw import get_openclaw_config_manager

        field = payload.get("field")
        value = payload.get("value")

        if not field:
            raise HTTPException(400, "field 不能为空")

        config_manager = get_openclaw_config_manager()
        result = config_manager.set(field, value)

        return result.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"设置 OpenClaw 配置失败: {e}")
        raise HTTPException(500, f"设置失败: {e}")


@app.post("/openclaw/config/model")
async def openclaw_set_model(payload: dict[str, Any]):
    """
    设置默认模型

    请求体:
    - model: 模型标识符（如 "zai/glm-4.7"）
    - alias: 模型别名（可选）

    Returns:
        更新结果
    """
    try:
        from agentserver.openclaw import get_openclaw_config_manager

        model = payload.get("model")
        alias = payload.get("alias")

        if not model:
            raise HTTPException(400, "model 不能为空")

        config_manager = get_openclaw_config_manager()

        results = []

        # 设置主模型
        result = config_manager.set_primary_model(model)
        results.append(result.to_dict())

        # 设置别名（如果提供）
        if alias:
            alias_result = config_manager.add_model_alias(model, alias)
            results.append(alias_result.to_dict())

        return {"success": all(r["success"] for r in results), "results": results}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"设置模型失败: {e}")
        raise HTTPException(500, f"设置失败: {e}")


@app.post("/openclaw/config/hooks")
async def openclaw_configure_hooks(payload: dict[str, Any]):
    """
    配置 Hooks

    请求体:
    - enabled: 是否启用（可选）
    - token: Hooks token（可选，不传则自动生成）

    Returns:
        更新结果
    """
    try:
        from agentserver.openclaw import get_openclaw_config_manager

        config_manager = get_openclaw_config_manager()
        results = []

        # 启用/禁用
        if "enabled" in payload:
            result = config_manager.set_hooks_enabled(payload["enabled"])
            results.append(result.to_dict())

        # 设置 token
        if "token" in payload:
            token = payload["token"]
        elif payload.get("generate_token"):
            token = config_manager.generate_hooks_token()
        else:
            token = None

        if token:
            result = config_manager.set_hooks_token(token)
            results.append(result.to_dict())

        return {
            "success": all(r["success"] for r in results) if results else True,
            "results": results,
            "token": token,  # 返回生成的 token
        }
    except Exception as e:
        logger.error(f"配置 Hooks 失败: {e}")
        raise HTTPException(500, f"配置失败: {e}")


@app.get("/openclaw/skills")
async def openclaw_list_skills():
    """列出已安装的 Skills"""
    try:
        from agentserver.openclaw import get_openclaw_installer

        installer = get_openclaw_installer()
        skills = await installer.list_skills()

        return {"success": True, "skills": skills}
    except Exception as e:
        logger.error(f"列出 Skills 失败: {e}")
        raise HTTPException(500, f"获取失败: {e}")


@app.post("/openclaw/skills/install")
async def openclaw_install_skill(payload: dict[str, Any]):
    """
    安装 Skill

    请求体:
    - skill: Skill 标识符

    Returns:
        安装结果
    """
    try:
        from agentserver.openclaw import get_openclaw_installer

        skill = payload.get("skill")
        if not skill:
            raise HTTPException(400, "skill 不能为空")

        installer = get_openclaw_installer()
        result = await installer.install_skill(skill)

        return result.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"安装 Skill 失败: {e}")
        raise HTTPException(500, f"安装失败: {e}")


@app.post("/openclaw/skills/enable")
async def openclaw_enable_skill(payload: dict[str, Any]):
    """
    启用/禁用 Skill

    请求体:
    - skill: Skill 名称
    - enabled: 是否启用

    Returns:
        更新结果
    """
    try:
        from agentserver.openclaw import get_openclaw_config_manager

        skill = payload.get("skill")
        enabled = payload.get("enabled", True)

        if not skill:
            raise HTTPException(400, "skill 不能为空")

        config_manager = get_openclaw_config_manager()
        result = config_manager.enable_skill(skill, enabled)

        return result.to_dict()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"启用/禁用 Skill 失败: {e}")
        raise HTTPException(500, f"操作失败: {e}")
