"""主循环与对外入口（卷190-A2：从 agentic_tool_loop.py 纯搬移）。"""
#!/usr/bin/env python3
"""
Agentic Tool Loop 核心引擎
实现单LLM agentic loop：模型在对话中发起工具调用，接收结果，再继续推理，直到不再需要工具。
"""

import asyncio
import base64
import ipaddress
import json
import logging
import mimetypes
import re
import socket
import time as _time
from collections.abc import AsyncGenerator
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx

from apiserver import naga_auth
from apiserver.agent_directory import format_agent_directory_text, resolve_agent_descriptor
from apiserver.tool_schemas import resolve_mcp_func_name
from system.config import get_config, get_data_dir, get_server_port

logger = logging.getLogger("apiserver.agentic_tool_loop")  # 保持原日志通道名
from .context import *  # noqa: F401,F403
from .executor import *  # noqa: F401,F403
from .executor_openclaw import *  # noqa: F401,F403
from .executor_search import *  # noqa: F401,F403
from .hooks import *  # noqa: F401,F403
from .markers import *  # noqa: F401,F403
from .parser import *  # noqa: F401,F403
from .planner import *  # noqa: F401,F403


async def execute_pre_search(query: str, count: int = 8) -> str | None:
    """
    前置搜索：在主 LLM 调用前执行搜索，返回格式化的搜索结果文本。
    复用 3-tier 搜索回退链：NagaBusiness → Brave → None
    """
    # 构造虚拟 call dict 供搜索函数使用
    call = {"args": {"query": query, "count": count}}

    if naga_auth.is_authenticated():
        result = await _execute_search_tool(call)
        if result.get("status") == "success" and result.get("result"):
            return result["result"]

    cfg = get_config()
    if cfg.online_search.search_api_key:
        result = await _execute_brave_search(call)
        if result.get("status") == "success" and result.get("result"):
            return result["result"]

    return None  # 无可用搜索源，跳过前置搜索



async def _dispatch_one_call(
    call: dict[str, Any], session_id: str, source_agent_id: str | None
) -> dict[str, Any]:
    """按 agentType 路由到具体执行器（不含 live2d）。"""
    agent_type = call.get("agentType", "")
    if agent_type == "mcp":
        _inject_session_id(call, session_id)
        return await _execute_mcp_call(call, source_agent_id=source_agent_id)
    if agent_type == "openclaw":
        return await _execute_openclaw_call(call, session_id)
    if agent_type in ("tool", "openclaw_tool"):
        return await _execute_openclaw_tool_call(call, source_agent_id=source_agent_id)
    if agent_type == "naga_control":
        return await _execute_control_tool(call)
    logger.warning(f"[AgenticLoop] 未知agentType: {agent_type}, 跳过: {call}")
    return {
        "tool_call": call,
        "result": f"未知 agentType: {agent_type}",
        "status": "error",
        "service_name": "unknown",
        "tool_name": str(call.get("tool_name") or ""),
    }



async def execute_tool_calls(
    tool_calls: list[dict[str, Any]],
    session_id: str,
    source_agent_id: str | None = None,
    max_retries: int | None = None,
) -> list[dict[str, Any]]:
    """按 agentType 分组并行执行工具调用（不包含 live2d）。

    W119-03：每次调用先过 TOOL_PRE_EXECUTE 安全门（审计/敏感/熔断），被 veto 的调用
    不执行、直接返回拦截原因；执行后回填结果（熔断计数 + 审计 post 记录）。

    W121-02：失败重试。可重试失败（超时/连接/执行异常/瞬时错误）在 `max_retries` 内重试，
    重试次数写回结果 `attempts` 字段；策略类失败（安全门 veto、确认门等待、白名单拒绝等）
    一律不重试。`max_retries=None` 时取配置 `agent_loop.max_retries`。

    Returns:
        [{"tool_call": {...}, "result": "...", "status": "success|error", "service_name": "...",
          "tool_name": "...", "attempts": N}]
    """
    loop_cfg = _loop_config()
    if max_retries is None:
        max_retries = int(getattr(loop_cfg, "max_retries", 2))
    retries = max(0, int(max_retries))
    backoff = float(getattr(loop_cfg, "retry_backoff_s", 0.5))

    async def _guarded(call: dict[str, Any]) -> dict[str, Any]:
        # W124-01：Scope 可见性（执行层）
        scope_veto = _run_scope_gate(call, session_id, source_agent_id)
        if scope_veto is not None:
            return scope_veto
        # W124-03 ①：guard 参数校验（被拒不进 pre-execute，更不进执行）
        guard_veto = _run_guard(call, session_id)
        if guard_veto is not None:
            return guard_veto
        veto = await _run_tool_gate(call, session_id, source_agent_id)
        if veto is not None:
            veto["attempts"] = 1
            return veto
        tool_name = str(call.get("tool_name") or call.get("name") or "")
        attempts = 0
        result: dict[str, Any] = {}
        while True:
            attempts += 1
            started = _time.perf_counter()
            ok = False
            try:
                # W120-01：工具调用记一个 span（含 agent_type / 耗时 / 成功与否 / 第几次尝试）
                from apiserver.event_bus.trace import trace_span

                with trace_span(
                    f"tool:{tool_name}" if attempts == 1 else f"tool:{tool_name}#retry{attempts - 1}",
                    tool=tool_name,
                    agent_type=str(call.get("agentType") or ""),
                    session_id=session_id,
                    attempt=attempts,
                ) as span:
                    result = await _dispatch_one_call(call, session_id, source_agent_id)
                    # 外层 ok 维持 W119 口径；失败判定另用 _effective_status（MCP 错误体修正）
                    ok = str(result.get("status")) == "success"
                    span.attributes["status"] = "success" if ok else "error"
                    span.attributes["effective_status"] = _effective_status(result)
            finally:
                try:
                    from apiserver.event_bus.tool_gate import record_tool_result

                    duration_s = _time.perf_counter() - started
                    # W124-03 阶段④：post-execute 事实（审计 + 失败统计，含正交字段）
                    _emit_post_execute(call, result, session_id, duration_s=duration_s, ok=ok)
                    record_tool_result(tool_name, ok, duration_s=duration_s)
                    # W120-04：工具指标（总数/成功/失败/延迟）
                    from apiserver.telemetry import record_tool_metric

                    record_tool_metric(tool=tool_name, ok=ok, duration_ms=duration_s * 1000)
                except Exception:  # noqa: BLE001 - 回填失败不影响工具结果
                    logger.debug("[AgenticLoop] 工具结果回填失败", exc_info=True)

            if not _retryable_failure(result) or attempts > retries:
                break
            logger.warning(
                "[AgenticLoop] 工具 %s 第 %d 次失败，%.1fs 后重试（上限 %d）：%s",
                tool_name, attempts, backoff, retries, str(result.get("result"))[:160],
            )
            if backoff > 0:
                await asyncio.sleep(backoff)

        result = dict(result)
        result["attempts"] = attempts
        if attempts > 1 and _effective_status(result) == "error":
            result["result"] = (
                f"（已重试 {attempts - 1} 次仍失败）{result.get('result', '')}"
            )
        return result

    tasks = [_guarded(call) for call in tool_calls]

    if not tasks:
        return []

    results = await asyncio.gather(*tasks, return_exceptions=True)
    final = []
    for r in results:
        if isinstance(r, Exception):
            final.append(
                {
                    "tool_call": {},
                    "result": f"执行异常: {r}",
                    "status": "error",
                    "service_name": "unknown",
                    "tool_name": "unknown",
                    "attempts": 1,
                }
            )
        else:
            final.append(r)
    return final



# ---------------------------------------------------------------------------
# 格式化
# ---------------------------------------------------------------------------


def format_tool_results_for_llm(results: list[dict[str, Any]]) -> str:
    """将工具执行结果格式化为LLM可理解的文本"""
    parts = []
    total = len(results)
    for idx, r in enumerate(results, 1):
        svc = r.get("service_name", "unknown")
        tool = r.get("tool_name", "")
        status = r.get("status", "unknown")
        result_text = r.get("result", "")
        label = f"{svc}"
        if tool:
            label += f": {tool}"
        parts.append(f"[工具结果 {idx}/{total} - {label} ({status})]\n{result_text}")
    return "\n\n".join(parts)



def format_tool_result_for_display(result: Any) -> Any:
    """保留工具原始结构，并在字符串结果中解开常见 JSON 包装。"""
    if not isinstance(result, str):
        return result

    text = result.strip()
    if not text:
        return ""

    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return result

    if isinstance(parsed, dict):
        if "data" in parsed and parsed.get("status") in {"success", "ok"}:
            return parsed["data"]
        if "result" in parsed:
            return parsed["result"]
    return parsed



# ---------------------------------------------------------------------------
# SSE 辅助
# ---------------------------------------------------------------------------


def _format_sse_event(event_type: str, data: Any) -> str:
    """格式化扩展SSE事件"""
    payload = {"type": event_type}
    if isinstance(data, dict):
        payload.update(data)
    else:
        payload["data"] = data
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"



# ---------------------------------------------------------------------------
# Agentic Loop 核心
# ---------------------------------------------------------------------------


async def run_agentic_loop(
    messages: list[dict[str, Any]],
    session_id: str,
    max_rounds: int | None = None,
    model_override: dict[str, str] | None = None,
    tools: list[dict[str, Any]] | None = None,
    source_agent_id: str | None = None,
) -> AsyncGenerator[str, None]:
    """Agentic tool loop 核心。

    流式输出SSE chunks，包含：
    - content/reasoning chunks（透传自LLM）
    - round_start/tool_calls/tool_results/tool_retry/round_end 事件

    每一轮的content都会完整流式输出（供TTS使用），工具内容不混入content流。

    W121-02：工具结果回注下一轮上下文（native 走 role=tool，兼容期走 user 消息），
    迭代上限取配置 `agent_loop.max_steps`（默认 8，显式传 max_rounds 时以参数为准），
    达上限或连续失败时进入收敛轮并附「已完成 / 未完成」摘要。

    Args:
        messages: 完整的对话消息列表（含system prompt）
        session_id: 会话ID
        max_rounds: 最大循环轮数（None 时取配置 agent_loop.max_steps）
        model_override: 临时模型覆盖参数（用于视觉模型等场景）
        tools: OpenAI function calling schemas（可选，传入时启用原生工具调用）

    Yields:
        SSE格式的data chunks
    """
    from ..llm_service import get_llm_service

    llm_service = get_llm_service()

    _cfg = _loop_config()
    if max_rounds is None:
        max_rounds = int(getattr(_cfg, "max_steps", 8) or 8)
    max_rounds = max(1, int(max_rounds))
    logger.info("[AgenticLoop] 会话 %s 启动：max_steps=%d", session_id, max_rounds)

    consecutive_failures = 0  # 连续全部失败的轮次计数
    needs_summary = False  # 是否需要进行最终总结轮
    summary_reason = "no_tools"  # 收敛原因（写进收敛提示）
    step_ledger: List[dict[str, Any]] = []  # W121-02：每步一行，供收敛摘要
    t_loop_start = _time.monotonic()

    # 卷123 W123-02：活动任务注入（目标/进度/当前步），无任务时零开销
    task_context = _inject_task_context(messages, session_id)
    if task_context:
        logger.info("[AgenticLoop] 已注入任务上下文（会话 %s）", session_id)

    # 卷124 W124-05：技能加载（按意图命中 SKILL.md 才注入，未命中零注入）
    skill_hits = _inject_skill_context(messages, session_id)
    if skill_hits:
        yield _format_sse_event("skills", {"session_id": session_id, "skills": skill_hits})

    # 卷131 W131-04.3：知识驱动自举——loop 开始前检索相关知识注入 rag_section
    # （失败旁路：知识库不可用时零影响，不静默——debug 日志留痕）
    try:
        from ..knowledge_driver import get_knowledge_driver
        _goal = ""
        for _m in reversed(messages):
            if _m.get("role") == "user":
                _goal = str(_m.get("content", ""))[:300]
                break
        _kitems = get_knowledge_driver().query_relevant(_goal, k=3)
        if _kitems:
            _rag_lines = "\n".join(
                f"- [{it.source_type}] {it.title}: {it.content[:120]}" for it in _kitems)
            messages.append({
                "role": "system",
                "content": f"[知识库参考（自动检索）]\n{_rag_lines}",
            })
            logger.info("[AgenticLoop] W131-04 已注入 %d 条相关知识", len(_kitems))
    except Exception as e:
        logger.debug(f"[AgenticLoop] 知识注入跳过（知识库不可用）: {e}")

    for round_num in range(1, max_rounds + 1):
        t_round_start = _time.monotonic()
        # 0. 上下文压缩：每轮开始前检查 token 是否超限
        #    round 1 压缩历史对话，round 2+ 压缩上一轮工具结果膨胀的上下文
        try:
            from ..context_compressor import compress_context
            compress_result = await compress_context(messages)
            if compress_result.compressed:
                messages[:] = compress_result.messages
            for sse_event in compress_result.sse_events:
                yield sse_event
        except Exception as e:
            logger.debug(f"[AgenticLoop] 上下文压缩跳过: {e}")

        # 1. 通知前端开始新一轮
        if round_num > 1:
            yield _format_sse_event("round_start", {"round": round_num})

        # 2. 流式调用LLM，累积完整输出
        complete_text = ""
        complete_reasoning = ""
        native_calls = None  # 原生 function calling 结果
        t_llm_start = _time.monotonic()

        # 总结轮不传 tools（禁止再次工具调用）
        round_tools = tools if round_num <= max_rounds else None

        async for chunk in llm_service.stream_chat_with_context(
            messages,
            get_config().api.temperature,
            model_override=model_override,
            tools=round_tools,
            router_meta={"session_id": session_id, "turn_id": f"{session_id}-r{round_num}",
                         "step_type": _current_step_type(session_id)},
        ):
            if chunk.startswith("data: "):
                try:
                    data_str = chunk[6:].strip()
                    if data_str and data_str != "[DONE]":
                        chunk_data = json.loads(data_str)
                        chunk_type = chunk_data.get("type", "content")
                        chunk_text = chunk_data.get("text", "")

                        if chunk_type == "content":
                            complete_text += chunk_text
                        elif chunk_type == "reasoning":
                            complete_reasoning += chunk_text
                        elif chunk_type == "tool_calls_native":
                            # 原生 function calling：完整 tool_calls JSON
                            try:
                                native_calls = json.loads(chunk_text)
                            except (json.JSONDecodeError, TypeError):
                                logger.warning(f"[AgenticLoop] native tool_calls 解析失败: {chunk_text[:200]}")
                            continue  # 不透传此内部事件给前端
                except Exception:
                    pass

            # 透传所有SSE chunks给前端（content + reasoning）
            yield chunk

        # 3. 从完整输出中解析工具调用
        #    优先使用 native tool calls，回退到文本解析（兼容期）
        t_llm_elapsed = _time.monotonic() - t_llm_start
        logger.info(
            f"[AgenticLoop] Round {round_num} LLM流式输出完成: {t_llm_elapsed:.2f}s, "
            f"content={len(complete_text)}字, reasoning={len(complete_reasoning)}字, "
            f"native_calls={'yes' if native_calls else 'no'}"
        )
        logger.debug(
            f"[AgenticLoop] Round {round_num} complete_text ({len(complete_text)} chars): {complete_text[:300]!r}"
        )

        use_native = False
        if native_calls:
            tool_calls = _convert_native_to_dispatch(native_calls)
            clean_text = complete_text  # native 模式下 content 就是纯文本
            use_native = True
            logger.info(f"[AgenticLoop] Round {round_num}: 使用原生 function calling, {len(tool_calls)} 个工具调用")
        else:
            clean_text, tool_calls = parse_tool_calls_from_text(complete_text)

        # 4. 分离 live2d 和可执行调用
        actionable_calls = [tc for tc in tool_calls if tc.get("agentType") != "live2d"]
        live2d_calls = [tc for tc in tool_calls if tc.get("agentType") == "live2d"]

        # 4a-0. W121-03：本轮若含 [PLAN] 段，单独发 plan 事件（正文保留标记，前端渲染成卡片）
        plan_text = extract_plan_section(complete_text)
        if plan_text:
            yield _format_sse_event("plan", {"round": round_num, "text": plan_text})
            # 卷123 W123-02：按计划建任务（本会话还没有任务时），等用户确认才逐步执行
            plan_task = _maybe_create_task_from_plan(session_id, plan_text, messages)
            if plan_task:
                yield _format_sse_event("task_update", {"session_id": session_id, "applied": plan_task})

        # 4a-2. 卷124 W124-02：模型声明 [SUBAGENT] → 派生子代理（并行）→ 结果聚合回注
        sub_specs = _collect_subagent_specs(complete_text)
        spawned_subagents = False
        if sub_specs:
            sub_results = await _run_subagents(session_id, sub_specs)
            if sub_results:
                spawned_subagents = True
                yield _format_sse_event("subagents", {
                    "session_id": session_id,
                    "results": [{"subagent_id": r.get("subagent_id", ""), "status": r.get("status", ""),
                                 "ok": bool(r.get("ok")), "toolset": r.get("toolset", []),
                                 "result": str(r.get("result") or r.get("error") or "")[:400]}
                                for r in sub_results],
                })
                messages.append({"role": "user", "content": _subagent_results_prompt(session_id)})

        # 4a-3. 卷123 W123-02：把模型声明的 [TASK] 段落库（无工具轮的回合也要落，
        #       否则「只报告步状态、不调工具」的回合会被丢掉）
        task_ops = _collect_task_ops(complete_text)
        if task_ops:
            applied = _apply_task_ops(session_id, task_ops)
            if applied:
                yield _format_sse_event("task_update", {"session_id": session_id, "applied": applied})
                # 卷123 W123-05：有步骤完成 → 步骤边界压缩（历史工具结果收敛成关键结果）
                if any(str(item.get("status") or "") in ("done", "skipped") for item in applied):
                    compacted = _compact_at_step_boundary(messages, session_id)
                    if compacted:
                        yield _format_sse_event("context_compacted", {"session_id": session_id,
                                                                     "dropped": compacted,
                                                                     "reason": "step_boundary"})
                # 卷123 W123-04：任务转入 review → 生成审查汇总并提示用户裁决
                if any(str(item.get("task_status") or "") == "review" for item in applied):
                    review_text = _build_review_prompt(applied)
                    if review_text:
                        yield _format_sse_event("task_review", {"session_id": session_id, "text": review_text})

        # 4a. 如果检测到了任何工具调用，发送 content_clean 让前端替换掉带有工具代码块的原文
        if tool_calls and clean_text != complete_text:
            # 保留工具调用前的简短说明文字（如"让我查一下"），仅移除 ```tool``` 代码块
            yield _format_sse_event("content_clean", {"text": clean_text})

        # 4b. 所有工具调用都先透传给前端，再触发实际执行/动画。
        call_descriptions = []
        for tc in tool_calls:
            desc = {"agentType": tc.get("agentType", "")}
            if tc.get("agentType") == "live2d":
                desc["service_name"] = "live2d"
                if tc.get("action"):
                    desc["tool_name"] = tc["action"]
            if tc.get("service_name"):
                desc["service_name"] = tc["service_name"]
            if tc.get("tool_name"):
                desc["tool_name"] = tc["tool_name"]
            if tc.get("message"):
                desc["message"] = tc["message"][:100]
            call_descriptions.append(desc)
        if call_descriptions:
            yield _format_sse_event("tool_calls", {"calls": call_descriptions})

        # 4c. Live2D 在工具调用已经进入消息流后再异步触发，避免生成正文时频繁变脸。
        if live2d_calls:
            asyncio.create_task(_send_live2d_actions(live2d_calls, session_id))

        # 5. 如果没有可执行的工具调用，循环结束
        #    （本轮派生过子代理则不算「没事可做」——聚合结果已注入，继续下一轮让父对话消化）
        if not actionable_calls and not spawned_subagents:
            # 模型只返回了 live2d 调用而没有文字内容时（Anthropic 常见行为），
            # 需要将 live2d tool call 的结果回注并再调用一轮 LLM 来生成文字回复
            if live2d_calls and not complete_text.strip() and use_native and round_num < max_rounds:
                logger.info(f"[AgenticLoop] Round {round_num}: 模型仅返回 live2d 调用无正文，"
                            f"回注 tool result 继续下一轮获取文字回复")
                assistant_msg = _build_native_assistant_message("", live2d_calls, complete_reasoning)
                messages.append(assistant_msg)
                for c in live2d_calls:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": c.get("_tool_call_id", ""),
                        "content": "已执行",
                    })
                yield _format_sse_event("round_end", {"round": round_num, "has_more": True})
                continue

            t_round_elapsed = _time.monotonic() - t_round_start
            t_total_elapsed = _time.monotonic() - t_loop_start
            logger.info(f"[AgenticLoop] Round {round_num}: 无工具调用，循环结束 "
                        f"(本轮 {t_round_elapsed:.2f}s, 总计 {t_total_elapsed:.2f}s)")
            # 发送本轮结束信号
            yield _format_sse_event("round_end", {"round": round_num, "has_more": False})
            break

        logger.info(f"[AgenticLoop] Round {round_num}: 检测到 {len(actionable_calls)} 个工具调用")

        # 6.5 卷131 W131-02.3：HIL 边界评估——工具执行前过 HILEvaluator
        #     auto_approve → 放行；need_confirm → 前端确认卡（与 W121-03 确认门协同，
        #     已有 pending_confirm 机制的工具不重复拦截）；block → 直接拒执行。
        #     评估器不可用时全部放行（旁路，不阻断 loop——HIL 是增强不是依赖）。
        try:
            from ..hil_evaluator import get_hil_evaluator
            _hil = get_hil_evaluator()
            _allowed_calls = []
            for tc in actionable_calls:
                _tool = tc.get("tool_name") or tc.get("service_name") or ""
                _d = _hil.eval_action(_tool, tc)
                if _d.action == "block":
                    logger.warning("[AgenticLoop] HIL 拦截工具 %s: %s", _tool, _d.reason)
                    yield _format_sse_event("hil_blocked", {
                        "session_id": session_id, "tool": _tool,
                        "reason": _d.reason, "confidence": _d.confidence})
                else:
                    if _d.action == "need_confirm":
                        # 标记给既有确认门链路（不在此重复弹卡片）
                        tc.setdefault("_hil_need_confirm", True)
                    _allowed_calls.append(tc)
            actionable_calls = _allowed_calls
            if not actionable_calls:
                logger.warning("[AgenticLoop] Round {round_num}: 全部工具被 HIL 拦截，进入收敛")
                needs_summary = True
                summary_reason = "hil_blocked"
                yield _format_sse_event("round_end", {"round": round_num, "has_more": True})
                break
        except ImportError:
            pass  # hil_evaluator 未部署 → 行为与卷131 之前完全一致
        except Exception as e:
            logger.debug(f"[AgenticLoop] HIL 评估跳过: {e}")

        # 7. 并行执行工具调用（W121-02：内部含失败重试）
        t_tool_start = _time.monotonic()
        results = await execute_tool_calls(actionable_calls, session_id, source_agent_id=source_agent_id)
        t_tool_elapsed = _time.monotonic() - t_tool_start
        logger.info(f"[AgenticLoop] Round {round_num}: 工具执行完成 {t_tool_elapsed:.2f}s "
                    f"({len(results)} 个工具)")

        # 7a. W121-02：重试可见性（前端可提示「正在重试」）
        retried = [
            {"tool_name": r.get("tool_name", ""), "attempts": r.get("attempts", 1)}
            for r in results
            if int(r.get("attempts") or 1) > 1
        ]
        if retried:
            yield _format_sse_event("tool_retry", {"retries": retried})

        # 7b. 记录步骤清单（收敛摘要用；在计数器更新前记，避免漏记）
        for call_item, result_item in zip(actionable_calls, results):
            step_ledger.append(_step_entry(round_num, call_item, result_item))

        # 7c. 检测连续失败：本轮所有工具是否全部失败（按真实状态判，MCP 错误体算失败）
        all_failed = all(_effective_status(r) == "error" for r in results)
        if all_failed:
            consecutive_failures += 1
            logger.warning(f"[AgenticLoop] Round {round_num}: 本轮所有工具调用失败 (连续 {consecutive_failures} 轮)")
        else:
            consecutive_failures = 0

        # 7d. 卷131 W131-07.3：工具效果写回知识库（结果解析后、回 LLM 前）
        #     失败旁路；评分衰减 0.7*old+0.3*new 在 knowledge_driver 内实现
        try:
            from ..knowledge_driver import get_knowledge_driver
            _kd = get_knowledge_driver()
            for _r in results:
                _kd.tag_tool_outcome(
                    _r.get("tool_name", "unknown"),
                    {"ok": _effective_status(_r) != "error",
                     "error": str(_r.get("result", ""))[:100] if _effective_status(_r) == "error" else ""},
                    task_context=task_context or "",
                )
        except Exception as e:
            logger.debug(f"[AgenticLoop] 工具效果写回跳过: {e}")

        # 7e. 卷131 W131-03.2：每轮结束自动快照（崩溃后可 resume 到本轮回合）
        #     消息存摘要不存全文（loop_checkpoint 内部裁剪+脱敏）
        try:
            from ..loop_checkpoint import get_loop_checkpoint
            get_loop_checkpoint().save(
                session_id, messages, round_num,
                tool_results=[
                    {"tool": r.get("tool_name", "?"),
                     "ok": _effective_status(r) != "error",
                     "brief": str(r.get("result", ""))[:80]}
                    for r in results
                ],
                meta={"summary_reason": summary_reason if needs_summary else ""},
            )
        except Exception as e:
            logger.debug(f"[AgenticLoop] 快照保存跳过: {e}")

        # 8. 通知前端工具结果
        result_summaries = []
        for r in results:
            result_summaries.append(
                {
                    "service_name": r.get("service_name", "unknown"),
                    "tool_name": r.get("tool_name", ""),
                    "status": _effective_status(r),
                    "result": format_tool_result_for_display(r.get("result", "")),
                    "attempts": int(r.get("attempts") or 1),
                }
            )
        yield _format_sse_event("tool_results", {"results": result_summaries})

        # 8a. W121-03：有待确认写操作 → 单独事件（前端可渲染确认卡片并可回落关键词确认）
        pending_items = [r["pending_confirm"] for r in results if isinstance(r.get("pending_confirm"), dict)]
        if pending_items:
            yield _format_sse_event("pending_confirm", {"session_id": session_id, "items": pending_items})

        # 9. 将本轮LLM输出 + 工具结果注入消息历史
        if use_native:
            # 标准 function calling 格式：assistant message + tool messages
            assistant_msg = _build_native_assistant_message(clean_text, actionable_calls, complete_reasoning)
            messages.append(assistant_msg)
            for call_item, result_item in zip(actionable_calls, results):
                messages.append({
                    "role": "tool",
                    "tool_call_id": call_item.get("_tool_call_id", ""),
                    "content": result_item.get("result", ""),
                })
        else:
            # 兼容期：旧格式 user message
            assistant_content = clean_text if clean_text else "(工具调用中)"
            messages.append({"role": "assistant", "content": assistant_content})
            tool_result_text = format_tool_results_for_llm(results)
            messages.append({"role": "user", "content": tool_result_text})

        # ★ 消息队列注入：在工具执行完毕、下一轮 LLM 调用前，注入排队消息
        # 合并到最后一条 user 消息中，避免连续多条 user 破坏角色交替
        try:
            from ..message_queue import get_message_queue
            mq = get_message_queue()
            queued = mq.drain()
            if queued:
                inject_parts = []
                for qm in queued:
                    tag = f"[{qm.source}]" if qm.source != "user" else ""
                    inject_parts.append(f"{tag} {qm.content}".strip())
                inject_text = "\n\n".join(inject_parts)
                # 追加到最后一条 user 消息（即工具结果），保持角色交替
                messages[-1]["content"] += f"\n\n--- 排队消息 ---\n{inject_text}"
                logger.info(
                    f"[AgenticLoop] 注入 {len(queued)} 条排队消息: "
                    f"{[q.source for q in queued]}"
                )
                yield _format_sse_event(
                    "queued_messages",
                    {"count": len(queued), "sources": [q.source for q in queued]},
                )
        except Exception as e:
            logger.debug(f"[AgenticLoop] 消息队列注入跳过: {e}")

        # 9a. 连续失败达到阈值时提前终止，进入总结轮
        if consecutive_failures >= 2:
            logger.warning(f"[AgenticLoop] 连续 {consecutive_failures} 轮工具全部失败，提前终止循环")
            yield _format_sse_event("round_end", {"round": round_num, "has_more": True})
            needs_summary = True
            summary_reason = "consecutive_failures"
            break

        # 发送本轮结束信号
        yield _format_sse_event("round_end", {"round": round_num, "has_more": True})

        t_round_elapsed = _time.monotonic() - t_round_start
        t_total_elapsed = _time.monotonic() - t_loop_start
        logger.info(f"[AgenticLoop] Round {round_num}: 本轮完成 {t_round_elapsed:.2f}s "
                    f"(LLM={t_llm_elapsed:.2f}s + 工具={t_tool_elapsed:.2f}s), "
                    f"总计 {t_total_elapsed:.2f}s，继续下一轮")

    else:
        # max_rounds 用尽
        needs_summary = True
        summary_reason = "max_steps"

    # 最终总结轮：强制 LLM 基于已有工具结果生成回复，不再允许工具调用
    if needs_summary:
        logger.warning("[AgenticLoop] 执行最终总结轮（原因: %s，已记录 %d 步）",
                       summary_reason, len(step_ledger))

        # 总结轮前也检查压缩（多轮工具调用后 context 可能已经很大）
        try:
            from ..context_compressor import compress_context
            compress_result = await compress_context(messages)
            if compress_result.compressed:
                messages[:] = compress_result.messages
            for sse_event in compress_result.sse_events:
                yield sse_event
        except Exception as e:
            logger.debug(f"[AgenticLoop] 总结轮压缩跳过: {e}")

        # 通知前端开始总结轮（重要：触发 api_server 重置 is_tool_event 标记）
        yield _format_sse_event("round_start", {"round": max_rounds + 1, "summary": True})

        # 注入总结指令（W121-02：带已完成 / 未完成清单；配置 converge_hint 可追加自定义要求）
        converge_prompt = build_convergence_prompt(step_ledger, summary_reason, max_rounds)
        extra_hint = str(getattr(_cfg, "converge_hint", "") or "").strip()
        if extra_hint:
            converge_prompt = f"{converge_prompt}\n{extra_hint}"
        messages.append({"role": "user", "content": converge_prompt})

        # 最终总结轮：流式输出（不传 tools，禁止再发起工具调用）
        async for chunk in llm_service.stream_chat_with_context(messages, get_config().api.temperature,
                                                                 model_override=model_override,
                                                                 tools=None):
            yield chunk

        yield _format_sse_event("round_end", {"round": max_rounds + 1, "has_more": False})

    # 卷131 W131-03.1：loop 正常走完（含总结轮）→ 快照可清（安全擦除）
    try:
        from ..loop_checkpoint import get_loop_checkpoint
        get_loop_checkpoint().clear(session_id)
    except Exception:
        pass  # 清理失败不阻断返回（残留快照下次启动会被 resume 检查）

__all__ = ['_dispatch_one_call', '_format_sse_event', 'execute_pre_search', 'execute_tool_calls', 'format_tool_result_for_display', 'format_tool_results_for_llm', 'run_agentic_loop']

# ruff: noqa: F405  # 薄壳模式：星号聚合导入的公共名（导出面由 tools/verify_export_parity.py 钉住）
