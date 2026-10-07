"""agent_server_parts.session —— 自 agentserver/agent_server.py 拆出（工单204 任务一，纯移动）。"""
from __future__ import annotations

from .common import *  # noqa: F401,F403
from .common import Modules, logger  # noqa: F401

def _track_travel_task(session_id: str, task: asyncio.Task) -> None:
    Modules.travel_tasks[session_id] = task

    def _cleanup(done: asyncio.Task) -> None:
        Modules.travel_tasks.pop(session_id, None)
        try:
            done.result()
        except asyncio.CancelledError:
            logger.info(f"[旅行] 任务已取消: {session_id}")
        except Exception as exc:
            logger.error(f"[旅行] 任务退出异常 [{session_id}]: {exc}")

    task.add_done_callback(_cleanup)


def _spawn_travel_session(session_id: str, *, resumed: bool = False) -> bool:
    existing = Modules.travel_tasks.get(session_id)
    if existing and not existing.done():
        return False
    task = asyncio.create_task(_run_travel_session(session_id, resumed=resumed), name=f"travel:{session_id}")
    _track_travel_task(session_id, task)
    return True


async def _resume_open_travel_sessions() -> None:
    from apiserver.travel_service import list_open_sessions

    sessions = list_open_sessions()
    restored = 0
    for session in sessions:
        if _spawn_travel_session(session.session_id, resumed=True):
            restored += 1
    if restored:
        logger.info(f"[旅行] 已恢复 {restored} 个未完成探索")


def _mark_travel_sessions_interrupted(
    *,
    session_ids: list[str] | None = None,
    reason: str = "interrupted",
) -> list[str]:
    from apiserver.travel_service import (
        get_session_or_none,
        interrupt_open_sessions,
        mark_session_interrupted,
    )

    interrupted_ids: list[str] = []
    if session_ids:
        for session_id in session_ids:
            session = get_session_or_none(session_id)
            if session is None:
                continue
            updated = mark_session_interrupted(session, reason=reason)
            if updated.session_id not in interrupted_ids:
                interrupted_ids.append(updated.session_id)
        return interrupted_ids

    for session in interrupt_open_sessions(reason=reason):
        interrupted_ids.append(session.session_id)
    return interrupted_ids


async def _interrupt_travel_sessions(
    *,
    session_ids: list[str] | None = None,
    reason: str = "interrupted",
) -> list[str]:
    interrupted_ids = _mark_travel_sessions_interrupted(session_ids=session_ids, reason=reason)
    cancelled_tasks: list[asyncio.Task] = []
    for session_id in interrupted_ids:
        task = Modules.travel_tasks.get(session_id)
        if task and not task.done():
            task.cancel()
            cancelled_tasks.append(task)
    if cancelled_tasks:
        await asyncio.gather(*cancelled_tasks, return_exceptions=True)
    return interrupted_ids


async def _run_travel_session(session_id: str, *, resumed: bool = False):
    """旅行主循环协程"""
    from agentserver.travel_notifications import (
        build_travel_full_report_message,
        deliver_travel_completion_notifications,
    )
    from apiserver.travel_service import (
        TravelStatus,
        analyze_history,
        append_progress_event,
        build_forum_post_payload,
        build_quota_warning_prompt,
        build_social_prompt,
        build_travel_prompt,
        build_wrap_up_prompt,
        load_session,
        remove_session_browser_policy,
        save_session,
        set_session_phase,
        sync_session_browser_policy,
    )

    try:
        session = load_session(session_id)
    except FileNotFoundError:
        logger.error(f"旅行 session 不存在: {session_id}")
        return

    travel_client = Modules.openclaw_client
    if session.agent_id:
        if not Modules.instance_manager:
            raise RuntimeError("实例管理器未就绪，无法使用指定干员执行探索")
        inst = await Modules.instance_manager.ensure_running(session.agent_id)
        if not inst.client:
            raise RuntimeError(f"干员 [{inst.name}] 客户端未就绪")
        session.agent_name = inst.name
        travel_client = inst.client
        await Modules.instance_manager.update_browser_preferences(
            session.agent_id,
            visible=session.browser_visible,
            stop_browser_if_changed=False,
        )
    elif travel_client is None:
        raise RuntimeError("OpenClaw 客户端未就绪")

    session_key = f"travel:{session.agent_id or 'main'}:{session_id[:8]}"
    session.openclaw_session_key = session_key
    session.status = TravelStatus.RUNNING
    session.interrupted_at = None
    session.interrupted_reason = None
    if not session.started_at:
        session.started_at = datetime.now().isoformat()
    if resumed:
        session.resume_count += 1
    session.last_heartbeat_at = datetime.now().isoformat()
    set_session_phase(
        session,
        "bootstrapping",
        message=f"已分配给干员 {session.agent_name or session.agent_id or '默认干员'}，准备开始探索。",
        meta={
            "agent_id": session.agent_id,
            "openclaw_session_key": session_key,
            "resumed": resumed,
        },
    )
    sync_session_browser_policy(session)
    await emit_local_telemetry(
        "explore_dispatch_agent",
        {
            "agent_name": session.agent_name,
            "uses_dedicated_agent": bool(session.agent_id),
            "time_limit_minutes": session.time_limit_minutes,
            "credit_limit": session.credit_limit,
        },
        trace_id=f"travel:{session_id}",
        session_id=session_id,
        agent_id=session.agent_id,
    )
    await emit_local_telemetry(
        "openclaw_task_created",
        {
            "openclaw_session_key": session_key,
            "agent_name": session.agent_name,
        },
        trace_id=f"travel:{session_id}",
        session_id=session_id,
        agent_id=session.agent_id,
    )

    logger.info(
        f"[旅行] 开始旅行 session: {session_id}, key={session_key}, "
        f"agent={session.agent_name or session.agent_id or 'default'}"
    )

    def _apply_history_analysis(current_session, analysis) -> None:
        current_session.discoveries = analysis.discoveries
        current_session.social_interactions = analysis.social_interactions
        current_session.credits_used = analysis.credits_used
        current_session.tool_stats = analysis.tool_stats
        current_session.sources = list(getattr(analysis, "sources", []) or [])
        current_session.unique_sources = len(current_session.sources)
        if getattr(analysis, "summary_report_path", None):
            current_session.summary_report_path = analysis.summary_report_path
        if getattr(analysis, "summary_report_title", None):
            current_session.summary_report_title = analysis.summary_report_title

    async def _send_to_travel_client(**kwargs):
        if session.agent_id:
            if not Modules.instance_manager:
                raise RuntimeError("实例管理器未就绪")

            async def _worker(inst):
                if not inst.client:
                    raise RuntimeError(f"干员 [{inst.name}] 客户端未就绪")
                return await inst.client.send_message(**kwargs)

            return await Modules.instance_manager.run_serialized(session.agent_id, _worker)
        return await travel_client.send_message(**kwargs)

    async def _load_travel_history(*, limit: int, include_tools: bool):
        if session.agent_id:
            if not Modules.instance_manager:
                raise RuntimeError("实例管理器未就绪")

            async def _worker(inst):
                if not inst.client:
                    raise RuntimeError(f"干员 [{inst.name}] 客户端未就绪")
                return await inst.client.get_local_session_history(
                    session_key=session_key,
                    limit=limit,
                )

            return await Modules.instance_manager.run_serialized(session.agent_id, _worker)
        return await travel_client.get_local_session_history(
            session_key=session_key,
            limit=limit,
        )

    async def _cleanup_travel_browser(current_session, *, reason: str) -> None:
        cleanup_session_key = str(
            getattr(current_session, "openclaw_session_key", None) or session_key or ""
        ).strip()
        if not cleanup_session_key:
            return

        try:
            if current_session.agent_id:
                if not Modules.instance_manager:
                    raise RuntimeError("实例管理器未就绪")

                async def _worker(inst):
                    if not inst.client:
                        raise RuntimeError(f"干员 [{inst.name}] 客户端未就绪")
                    return await inst.client.invoke_tool(
                        tool="browser",
                        args={"action": "stop"},
                        session_key=cleanup_session_key,
                    )

                result = await Modules.instance_manager.run_serialized(current_session.agent_id, _worker)
            else:
                result = await travel_client.invoke_tool(
                    tool="browser",
                    args={"action": "stop"},
                    session_key=cleanup_session_key,
                )

            if isinstance(result, dict) and result.get("success"):
                logger.info(f"[旅行] 已回收浏览器句柄: session={session_id}, reason={reason}")
            else:
                logger.warning(
                    f"[旅行] 浏览器句柄回收未完全成功: session={session_id}, reason={reason}, result={result}"
                )
        except Exception as cleanup_error:
            logger.warning(
                f"[旅行] 浏览器句柄回收失败: session={session_id}, reason={reason}, error={cleanup_error}"
            )
        finally:
            remove_session_browser_policy(cleanup_session_key)

    try:
        # 发送探索指令
        await _send_to_travel_client(
            message=build_travel_prompt(session),
            session_key=session_key,
            name="NagaTravel",
            timeout_seconds=0,
        )
        set_session_phase(
            session,
            "running",
            message="主探索指令已下发，开始检索最新线索。",
        )

        # 如果想社交，额外发送社交指令
        if session.want_friends:
            await _send_to_travel_client(
                message=build_social_prompt(session),
                session_key=session_key,
                name="NagaTravel",
                timeout_seconds=0,
            )
            append_progress_event(
                session,
                "social_prompt_sent",
                "已追加社交探索指令，会在合适时尝试扩展互动。",
            )
            save_session(session)

        # 监控循环
        start_time = datetime.fromisoformat(session.started_at)
        seen_discovery_urls: set = set()
        seen_social_keys: set = set()

        while True:
            await asyncio.sleep(30)

            # 检查时间限制
            elapsed = (datetime.now() - start_time).total_seconds() / 60
            session.elapsed_minutes = round(elapsed, 1)
            remaining_minutes = max(0.0, session.time_limit_minutes - elapsed)
            remaining_credits = max(0, session.credit_limit - session.credits_used)

            if elapsed >= session.time_limit_minutes:
                logger.info(f"[旅行] 时间到达限制 {session.time_limit_minutes} 分钟")
                break

            # 重新加载 session（可能被外部 cancel）
            try:
                session = load_session(session_id)
            except Exception:
                break

            if session.status == TravelStatus.CANCELLED:
                logger.info(f"[旅行] session 已被取消: {session_id}")
                await _cleanup_travel_browser(session, reason="cancelled")
                return

            if session.status == TravelStatus.INTERRUPTED:
                logger.info(f"[旅行] session 已被中断: {session_id}")
                await _cleanup_travel_browser(session, reason="interrupted")
                return

            previous_discovery_count = len(session.discoveries)

            # 轮询 OpenClaw 获取新消息
            try:
                history = await _load_travel_history(limit=80, include_tools=True)
                messages = history if isinstance(history, list) else history.get("messages", [])

                # 从工具结果和阶段性文本中提炼发现、社交、预算
                analysis = analyze_history(messages)
                _apply_history_analysis(session, analysis)

                existing_activity_ids = {
                    str((event.meta or {}).get("travel_tool_call_id"))
                    for event in session.progress_events
                    if (event.meta or {}).get("travel_tool_call_id")
                }
                for activity_event in getattr(analysis, "activity_events", []) or []:
                    activity_id = str((activity_event.meta or {}).get("travel_tool_call_id") or "")
                    if activity_id and activity_id in existing_activity_ids:
                        continue
                    append_progress_event(
                        session,
                        activity_event.type,
                        activity_event.message,
                        level=activity_event.level,
                        meta=activity_event.meta,
                        timestamp=activity_event.timestamp,
                    )
                    if activity_id:
                        existing_activity_ids.add(activity_id)

                for d in session.discoveries:
                    seen_discovery_urls.add(d.url)

                for s in session.social_interactions:
                    key = f"{s.type}:{s.post_id}:{s.content_preview[:30]}"
                    if key not in seen_social_keys:
                        seen_social_keys.add(key)
                if len(session.discoveries) > previous_discovery_count:
                    append_progress_event(
                        session,
                        "discoveries_updated",
                        f"本轮新增 {len(session.discoveries) - previous_discovery_count} 条发现，累计 {len(session.discoveries)} 条。",
                        meta={
                            "discoveries": len(session.discoveries),
                            "unique_sources": session.unique_sources,
                            "credits_used": session.credits_used,
                        },
                    )
                    await emit_local_telemetry(
                        "openclaw_discovery_added",
                        {
                            "new_discoveries": len(session.discoveries) - previous_discovery_count,
                            "total_discoveries": len(session.discoveries),
                            "unique_sources": session.unique_sources,
                            "credits_used": session.credits_used,
                        },
                        trace_id=f"travel:{session_id}",
                        session_id=session_id,
                        agent_id=session.agent_id,
                    )
                    session.idle_polls = 0
                else:
                    session.idle_polls += 1

            except Exception as e:
                logger.warning(f"[旅行] 轮询历史失败: {e}")

            session.elapsed_minutes = round(elapsed, 1)
            session.last_heartbeat_at = datetime.now().isoformat()

            time_warning_threshold = max(1.0, session.time_limit_minutes * 0.1)
            credit_warning_threshold = max(1, int(session.credit_limit * 0.1))
            warning_trigger: str | None = None
            if not session.time_warning_sent and remaining_minutes <= time_warning_threshold:
                warning_trigger = "time"
            if not session.credit_warning_sent and remaining_credits <= credit_warning_threshold:
                warning_trigger = "both" if warning_trigger == "time" else "credit"
            if warning_trigger:
                try:
                    await _send_to_travel_client(
                        message=build_quota_warning_prompt(
                            session,
                            remaining_minutes=remaining_minutes,
                            remaining_credits=remaining_credits,
                            trigger=warning_trigger,
                        ),
                        session_key=session_key,
                        name="NagaTravel",
                        timeout_seconds=0,
                    )
                    append_progress_event(
                        session,
                        "quota_warning",
                        f"配额接近上限：剩余约 {max(0.0, remaining_minutes):.1f} 分钟，剩余约 {max(0, remaining_credits)} 积分。",
                        level="warn",
                        meta={
                            "trigger": warning_trigger,
                            "remaining_minutes": round(max(0.0, remaining_minutes), 1),
                            "remaining_credits": max(0, remaining_credits),
                        },
                    )
                    if warning_trigger in {"time", "both"}:
                        session.time_warning_sent = True
                    if warning_trigger in {"credit", "both"}:
                        session.credit_warning_sent = True
                except Exception as e:
                    logger.warning(f"[旅行] 发送预算预警失败: {e}")

            # 预算接近上限或长时间无增量时，要求 OpenClaw 开始收束
            wrap_up_threshold = int(session.credit_limit * 0.9)
            hard_stop_threshold = session.credit_limit
            should_request_wrap_up = (
                (
                    (
                        session.credits_used >= wrap_up_threshold
                        or remaining_minutes <= time_warning_threshold
                    )
                    and (len(session.discoveries) > 0 or session.idle_polls >= 1)
                )
                or (session.idle_polls >= 2 and len(session.discoveries) > 0)
            )
            if should_request_wrap_up and not session.wrap_up_sent:
                try:
                    await _send_to_travel_client(
                        message=build_wrap_up_prompt(session),
                        session_key=session_key,
                        name="NagaTravel",
                        timeout_seconds=0,
                    )
                    session.wrap_up_sent = True
                    set_session_phase(
                        session,
                        "wrapping_up",
                        message="探索已进入收束阶段，正在整理最终报告。",
                        meta={
                            "credits_used": session.credits_used,
                            "idle_polls": session.idle_polls,
                            "discoveries": len(session.discoveries),
                        },
                    )
                    logger.info(
                        f"[旅行] 已发送收束指令: {session_id}, credits={session.credits_used}, idle={session.idle_polls}"
                    )
                    await emit_local_telemetry(
                        "explore_wrap_up_requested",
                        {
                            "credits_used": session.credits_used,
                            "credit_limit": session.credit_limit,
                            "idle_polls": session.idle_polls,
                            "discoveries": len(session.discoveries),
                        },
                        trace_id=f"travel:{session_id}",
                        session_id=session_id,
                        agent_id=session.agent_id,
                    )
                except Exception as e:
                    logger.warning(f"[旅行] 发送收束指令失败: {e}")

            if session.credits_used >= hard_stop_threshold:
                append_progress_event(
                    session,
                    "hard_limit",
                    f"已达到积分限制 {session.credits_used}/{session.credit_limit}，准备结束探索。",
                    level="warn",
                )
                logger.info(f"[旅行] 估算积分到达限制 {session.credits_used}/{session.credit_limit}")
                break

            if session.idle_polls >= 4 and len(session.discoveries) > 0:
                append_progress_event(
                    session,
                    "idle_stop",
                    "长时间没有新增发现，准备结束并整理结果。",
                    meta={"idle_polls": session.idle_polls},
                )
                logger.info(f"[旅行] 长时间无新增发现，准备结束: idle_polls={session.idle_polls}")
                break

            save_session(session)

        # 发送收尾指令
        logger.info(f"[旅行] 发送收尾指令: {session_id}")
        set_session_phase(
            session,
            "finalizing",
            message="已发送最终收尾指令，正在等待探索总结。",
        )
        try:
            await _send_to_travel_client(
                message=build_wrap_up_prompt(session),
                session_key=session_key,
                name="NagaTravel",
                timeout_seconds=300,
            )

            # 等待并获取最终回复
            await asyncio.sleep(30)
            history = await _load_travel_history(limit=20, include_tools=False)
            messages = history if isinstance(history, list) else history.get("messages", [])
            # 最后一条 assistant 消息作为 summary
            for msg in reversed(messages):
                role = msg.get("role", "")
                if role == "assistant":
                    session.summary = msg.get("content", "")[:2000]
                    await emit_local_telemetry(
                        "explore_summary_ready",
                        {
                            "summary_chars": len(session.summary or ""),
                        },
                        trace_id=f"travel:{session_id}",
                        session_id=session_id,
                        agent_id=session.agent_id,
                    )
                    break

            # 收尾完成后重新解析完整历史，确保最终总结里的真实 discovery 会落盘。
            final_history = await _load_travel_history(limit=120, include_tools=True)
            final_messages = final_history if isinstance(final_history, list) else final_history.get("messages", [])
            final_analysis = analyze_history(final_messages)
            _apply_history_analysis(session, final_analysis)
        except Exception as e:
            logger.warning(f"[旅行] 收尾指令失败: {e}")
            session.summary = f"旅行完成，共发现 {len(session.discoveries)} 个内容。（收尾指令超时）"

        session.status = TravelStatus.COMPLETED
        session.phase = "completed"
        session.completed_at = datetime.now().isoformat()
        append_progress_event(
            session,
            "completed",
            f"探索已完成：累计 {len(session.discoveries)} 条发现，{session.unique_sources} 个来源。",
            meta={
                "discoveries": len(session.discoveries),
                "unique_sources": session.unique_sources,
                "credits_used": session.credits_used,
                "elapsed_minutes": session.elapsed_minutes,
            },
        )
        save_session(session)
        await _cleanup_travel_browser(session, reason="completed")

        logger.info(
            f"[旅行] 完成: {session_id}, 发现={len(session.discoveries)}, 社交={len(session.social_interactions)}"
        )

        # 论坛功能已下线（apiserver.routes.forum 模块不再提供），post_to_forum 静默忽略

        # 完整版报告回传给用户/通道
        if session.deliver_full_report:
            try:
                set_session_phase(
                    session,
                    "delivering_report",
                    message="正在回传完整探索报告。",
                )
                if not session.deliver_channel and not session.deliver_to:
                    session.full_report_delivery_status = "stored_in_app"
                    save_session(session)
                else:
                    deliver_kwargs = {
                        "message": build_travel_full_report_message(session),
                        "deliver": True,
                        "session_key": session_key,
                        "name": "NagaTravel",
                        "timeout_seconds": 30,
                    }
                    if session.deliver_channel:
                        deliver_kwargs["channel"] = session.deliver_channel
                    if session.deliver_to:
                        deliver_kwargs["to"] = session.deliver_to
                    await _send_to_travel_client(**deliver_kwargs)
                    session.full_report_delivery_status = "delivered"
                append_progress_event(
                    session,
                    "report_delivery",
                    "探索结果已按当前配置完成回传。",
                    meta={"channel": session.deliver_channel or "in_app"},
                )
                save_session(session)
            except Exception as e:
                session.full_report_delivery_status = f"failed:{e}"
                append_progress_event(
                    session,
                    "report_delivery_failed",
                    f"探索结果回传失败：{e}",
                    level="error",
                )
                save_session(session)
                logger.warning(f"[旅行] 完整报告回传失败: {e}")

        try:
            set_session_phase(
                session,
                "notifying",
                message="正在发送探索完成通知。",
            )
            session.notification_delivery_statuses = await deliver_travel_completion_notifications(session, travel_client)
            save_session(session)
            for channel, status in session.notification_delivery_statuses.items():
                await emit_local_telemetry(
                    "notify_delivery_success" if not str(status).startswith("failed:") else "notify_delivery_fail",
                    {
                        "channel": channel,
                        "status": status,
                    },
                    trace_id=f"travel:{session_id}",
                    session_id=session_id,
                    agent_id=session.agent_id,
                )
        except Exception as e:
            logger.warning(f"[旅行] 完成通知发送失败: {e}")

        session.phase = "completed"
        save_session(session)

        await emit_local_telemetry(
            "explore_finish",
            {
                "discoveries": len(session.discoveries),
                "social_interactions": len(session.social_interactions),
                "credits_used": session.credits_used,
                "elapsed_minutes": session.elapsed_minutes,
                "unique_sources": session.unique_sources,
                "forum_post_status": session.forum_post_status,
                "full_report_delivery_status": session.full_report_delivery_status,
                "notification_delivery_statuses": session.notification_delivery_statuses,
            },
            trace_id=f"travel:{session_id}",
            session_id=session_id,
            agent_id=session.agent_id,
        )

    except asyncio.CancelledError:
        try:
            session = load_session(session_id)
            if session.status == TravelStatus.CANCELLED:
                session.phase = "cancelled"
                append_progress_event(
                    session,
                    "cancelled",
                    "探索已取消。",
                    level="warn",
                )
                save_session(session)
                await _cleanup_travel_browser(session, reason="cancelled")
                logger.info(f"[旅行] 协程已取消（已取消态）: {session_id}")
            elif session.status == TravelStatus.INTERRUPTED:
                session.phase = "interrupted"
                save_session(session)
                await _cleanup_travel_browser(session, reason="interrupted")
                logger.info(f"[旅行] 协程已取消（已中断态）: {session_id}")
            else:
                from apiserver.travel_service import mark_session_interrupted

                session = mark_session_interrupted(session, reason="task_cancelled")
                await _cleanup_travel_browser(session, reason="task_cancelled")
                logger.info(f"[旅行] 协程已取消并转为中断态: {session_id}")
        except Exception as inner:
            logger.warning(f"[旅行] 处理取消态失败 [{session_id}]: {inner}")
        raise
    except Exception as e:
        logger.error(f"[旅行] 异常: {e}", exc_info=True)
        try:
            session = load_session(session_id)
            session.status = TravelStatus.FAILED
            session.phase = "failed"
            session.error = str(e)
            session.completed_at = datetime.now().isoformat()
            append_progress_event(
                session,
                "failed",
                f"探索执行失败：{e}",
                level="error",
            )
            save_session(session)
            await _cleanup_travel_browser(session, reason="failed")
            await emit_local_telemetry(
                "explore_fail",
                {
                    "error": e,
                    "discoveries": len(session.discoveries),
                    "credits_used": session.credits_used,
                },
                trace_id=f"travel:{session_id}",
                session_id=session_id,
                agent_id=session.agent_id,
            )
        except Exception:
            pass
