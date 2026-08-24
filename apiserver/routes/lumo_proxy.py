"""
陆墨 persona-aware OpenAI 兼容代理端点

职责：
  1) 提供 /persona/v1/chat/completions 端点，供 NEKO 作为 LLM 上游
  2) 注入陆墨人格（build_system_prompt）+ session 记忆 + RAG 召回 + 附加知识
  3) 返回 OpenAI ChatCompletion 兼容格式（流式 + 非流式）

与 openai_proxy.py 的区别：
  - openai_proxy 是透传代理，不注入人格（供 OpenClaw 使用）
  - lumo_proxy 是 persona-aware 代理，注入陆墨完整人格管线（供 NEKO 使用）

鉴权：
  - 使用 LUMO_PROXY_TOKEN 环境变量（铁律7）
  - 与 require_local_auth（用户登录态）独立，不复用 _access_token
  - hmac.compare_digest 防时序攻击
"""
import asyncio
import hmac
import json
import logging
import os
import re
import sys
import time
import uuid
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

# ============ 铁律7：fail-fast 凭证 ============

_LUMO_PROXY_TOKEN = os.environ.get("LUMO_PROXY_TOKEN", "").strip()
if not _LUMO_PROXY_TOKEN:
    # 铁律7：fail-fast 凭证——token 缺失时所有 /persona 请求返回 503
    logger.error("[lumo_proxy] LUMO_PROXY_TOKEN 未设置，/persona/v1/chat/completions 将拒绝所有请求（503）")


async def require_proxy_token(request: Request) -> dict:
    """跨进程鉴权依赖（NEKO → scratchpad）。

    与 require_local_auth 区别：
    - require_local_auth：用户登录态鉴权（Cookie/Bearer，本地模式可放行）
    - require_proxy_token：进程间共享密钥，强制校验，无放行分支

    用 hmac.compare_digest 防时序攻击。
    """
    if not _LUMO_PROXY_TOKEN:
        raise HTTPException(status_code=503, detail="service unavailable")

    auth_header = request.headers.get("authorization", "")
    token = None
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()

    if not token:
        raise HTTPException(status_code=401, detail="missing credentials")

    if not hmac.compare_digest(token.encode("utf-8"), _LUMO_PROXY_TOKEN.encode("utf-8")):
        # 沈遥 R5：与 lumo_inject_router.py 一致，用 bytes 比较避免非 ASCII token 触发 TypeError
        # 不区分 token 不存在 vs 错误，防信息泄露
        raise HTTPException(status_code=401, detail="invalid credentials")

    # 沈遥 R4：返回值不含 token，防日志/异常链泄露密钥（与 inject 侧对齐）
    return {"auth": "proxy"}


# ============ 请求/响应模型 ============


class ChatMessage(BaseModel):
    role: str
    content: Any  # OpenAI 兼容：content 可为字符串或多模态数组


class ChatCompletionRequest(BaseModel):
    # OpenAI 兼容字段
    model: str = "lumo-persona"
    messages: list[ChatMessage]
    temperature: float | None = None
    stream: bool = False
    max_tokens: int | None = None
    # 陆墨扩展字段
    session_id: str | None = None
    skill: str | None = None
    temporary: bool = False
    # [local-patch] 沈遥 R2：任务类型分流，避免 summary/correction 污染对话历史
    # NEKO 侧需在请求 body 中带 task_type（如 "summary"/"correction"/"vision"/"agent"）
    # 不带则默认 "conversation"，走完整人格注入+RAG+历史写入
    task_type: str | None = "conversation"

    @field_validator('session_id')
    @classmethod
    def validate_session_id(cls, v):
        if v is not None and not re.match(r'^[a-zA-Z0-9_-]{1,64}$', v):
            raise ValueError('非法 session_id')
        return v


# ============ 旁路 RAG 召回（混合架构：GRAG + 本地向量 RAG） ============


async def _query_rag_standalone(question: str) -> str:
    """混合 RAG 召回：多路并行 + 结果融合。

    路径1 (GRAG/summer_memory)：知识图谱五元组召回，擅长关系推理
    路径2 (本地 RAGService)：向量语义检索，擅长事实查询与笔记匹配
    路径3 (语义网旁路)：GRAG 五元组 → RDF 本体规则推理 → 新事实（只读，纯 Python）
    路径4 (化学计算旁路)：ChemFormula 确定性分子量/组成计算（只读，纯 stdlib）

    降级链：任一路径失败不影响其他路径，全部失败返回 ""。
    铁律5：scratchpad 任一组件挂了，文字对话仍可跑。
    """
    # 沈遥终审③修复：使用 asyncio.gather 真正并行召回
    grag_result, vector_result, semantic_result, chem_result = await asyncio.gather(
        _query_grag(question),
        _query_local_rag(question),
        _query_semantic(question),
        _query_chem(question),
        return_exceptions=True,
    )

    rag_sections = []
    for r in (grag_result, vector_result, semantic_result, chem_result):
        if isinstance(r, str) and r:
            rag_sections.append(r)

    # ---- 融合 ----
    if not rag_sections:
        return ""
    return "\n\n".join(rag_sections)


async def _query_grag(question: str) -> str:
    """GRAG 知识图谱召回（summer_memory 远程 / 本地）"""
    try:
        from apiserver.routes.chat import _parse_memory_result
        from summer_memory.memory_client import get_remote_memory_client

        remote_mem = get_remote_memory_client()
        if not remote_mem:
            return ""

        result = await asyncio.wait_for(
            remote_mem.query_memory(question=question, limit=5),
            timeout=3.0,
        )
        content = _parse_memory_result(result)
        if len(content) > 2000:
            content = content[:2000] + "...[truncated]"
        return content
    except TimeoutError:
        logger.warning("[RAG-GRAG] 查询超时（3s），降级跳过")
        return ""
    except Exception as e:
        logger.warning(f"[RAG-GRAG] 降级跳过: {e}")
        return ""


async def _query_local_rag(question: str) -> str:
    """本地向量 RAG 召回（RAGService / SQLite 向量库）"""
    try:
        from rag import get_rag_service

        rag_svc = get_rag_service()
        loop = asyncio.get_running_loop()
        result = await asyncio.wait_for(
            loop.run_in_executor(
                None,
                lambda: rag_svc.query(
                    query_text=question,
                    top_k=5,
                    min_score=0.5,
                    rerank=True,
                ),
            ),
            timeout=5.0,
        )

        chunks = result.get("results", [])
        if not chunks:
            return ""

        lines = []
        for i, c in enumerate(chunks):
            title = c.get("title", "")
            content = c.get("content", "")
            score = c.get("score", 0)
            source_info = f"（来源：{title}）" if title else ""
            # 截取前 300 字符，控制 token 消耗
            snippet = content[:300] + ("..." if len(content) > 300 else "")
            lines.append(f"- [{score:.2f}] {source_info}{snippet}")

        if not lines:
            return ""

        logger.info(f"[RAG-Vector] 召回 {len(lines)} 条笔记片段")
        return (
            "\n\n## 相关研究笔记（向量检索）\n\n"
            "以下是从你的 Obsidian 笔记库中检索到的相关内容，请参考：\n"
            + "\n".join(lines)
        )
    except ImportError:
        logger.warning("[RAG-Vector] RAGService 不可用（rag 模块未安装？）")
        return ""
    except TimeoutError:
        logger.warning("[RAG-Vector] 查询超时（5s），降级跳过")
        return ""
    except Exception as e:
        logger.warning(f"[RAG-Vector] 降级跳过: {e}")
        return ""


async def _query_semantic(question: str) -> str:
    """语义推理召回（旁路）：GRAG 五元组 → RDF 本体规则推理 → 新事实。

    只读 summer_memory，不改其写路径；答案靠规则推，不靠 LLM 猜。
    旁路降级（铁律5）：semantic_web / summer_memory 任一挂了，返回 ""，
    不影响 GRAG 与向量 RAG 主链路。
    """
    try:
        from mcpserver.adapters.semantic_web.bridge import get_bridge

        text = get_bridge().query_semantic(question)
        return text if text else ""
    except Exception as e:  # noqa: BLE001  # 降级边界：语义旁路异常一律吞掉，不影响主链路
        logger.warning(f"[RAG-Semantic] 语义推理降级跳过: {e}")
        return ""


async def _query_chem(question: str) -> str:
    """化学计算召回（旁路）：正则抽化学式 → ChemFormula 确定性分子量/组成。

    只读 ChemFormula 输出（分子量 / 元素组成），不改任何存图/写文件逻辑。
    旁路降级（铁律5）：ChemFormula / casregnum 任一不可用或计算异常，一律返回 ""，
    不影响 GRAG 与向量 RAG 主链路。
    """
    try:
        from mcpserver.adapters.chem_adapter import ChemFormula

        # 从问题文本抽化学式片段（元素符号 + 可选下标），逐段解析
        formulas = re.findall(r"[A-Z][a-z]?(?:\d+)?", question)
        results = []
        for f in formulas:
            try:
                cf = ChemFormula(f)
                results.append(f"{f}: 分子量={cf.formula_weight:.3f}, 组成={dict(cf.element)}")
            except Exception:  # noqa: BLE001  # 单个片段不是合法化学式就跳过，不影响其他片段
                pass
        return "\n".join(results) if results else ""
    except Exception as e:  # noqa: BLE001  # 降级边界：化学旁路异常一律吞掉，不影响主链路
        logger.warning(f"[RAG-Chem] 化学计算降级跳过: {e}")
        return ""


# ============ 辅助函数 ============


def _extract_last_user_message(messages: list[ChatMessage]) -> str:
    """从 OpenAI messages 数组提取最后一条 user 消息的文本内容"""
    for msg in reversed(messages):
        if msg.role == "user":
            if isinstance(msg.content, str):
                return msg.content
            # 多模态数组：提取 text 部分
            if isinstance(msg.content, list):
                parts = []
                for part in msg.content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        parts.append(part.get("text", ""))
                return " ".join(parts)
    return ""


def _to_openai_response(content: str, model: str, reasoning: str = "") -> dict:
    """非流式 OpenAI ChatCompletion 响应格式"""
    message: dict = {"role": "assistant", "content": content}
    if reasoning:
        message["reasoning_content"] = reasoning
    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
    }


# ============ M4.5：视觉透传节点（CUA 的"眼睛"） ============
# NEKO CUA 的 agent 通道是 assistApi=lumo（agent_model=lumo-persona），
# 截图流量是多模态消息，但 persona 主链路只提取文本会丢弃图片部分，
# CUA 永远"看不到"屏幕。本节点检测到图片内容后，绕过人格/RAG/历史，
# 原样转发给视觉上游（默认 qwen3.7-plus，NEKO 已验证可用的视觉模型）。
# 约束：NEKO 零改动，只在陆墨侧加节点；铁律7——凭证只走环境变量，
# fallback 仅读 NEKO 用户已有配置，不新增任何落盘。

_VISION_BASE_URL = os.environ.get(
    "LUMO_VISION_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
).rstrip("/")
_VISION_MODEL = os.environ.get("LUMO_VISION_MODEL", "qwen3.7-plus")

_vision_client = None


def _messages_contain_image(messages: list[ChatMessage]) -> bool:
    """检测消息中是否含 image_url 部分（CUA 截图 / assist 视觉任务）"""
    for msg in messages:
        if isinstance(msg.content, list):
            for part in msg.content:
                if isinstance(part, dict) and part.get("type") == "image_url":
                    return True
    return False


def _resolve_vision_api_key() -> str:
    """视觉上游凭证：优先 LUMO_VISION_API_KEY 环境变量；
    fallback 读 NEKO 用户配置 core_config.json 的 coreApiKey（只读既有数据）。"""
    key = os.environ.get("LUMO_VISION_API_KEY", "").strip()
    if key:
        return key
    try:
        cfg_path = (
            Path(__file__).resolve().parents[2]
            / "carpet" / "N.E.K.O" / "config" / "core_config.json"
        )
        if cfg_path.exists():
            with open(cfg_path, encoding="utf-8") as f:
                core = json.load(f)
            return str(core.get("coreApiKey") or "").strip()
    except Exception as e:
        logger.warning(f"[lumo_proxy vision] 读 NEKO core_config 失败: {e}")
    return ""


def _get_vision_client():
    global _vision_client
    import httpx
    if _vision_client is None or _vision_client.is_closed:
        _vision_client = httpx.AsyncClient(base_url=_VISION_BASE_URL, timeout=120.0)
    return _vision_client


async def _vision_forward(request: ChatCompletionRequest):
    """多模态请求原样透传视觉上游，返回 OpenAI 兼容响应（流式/非流式）。"""
    import httpx
    api_key = _resolve_vision_api_key()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="vision upstream not configured (set LUMO_VISION_API_KEY)",
        )
    body: Dict[str, Any] = {
        "model": _VISION_MODEL,
        "messages": [m.model_dump() for m in request.messages],
        "stream": request.stream,
    }
    if request.temperature is not None:
        body["temperature"] = request.temperature
    if request.max_tokens is not None:
        body["max_tokens"] = request.max_tokens
    headers = {"Authorization": f"Bearer {api_key}"}
    client = _get_vision_client()
    logger.info(
        "[lumo_proxy vision] 透传多模态请求 -> %s（task_type=%s, stream=%s）",
        _VISION_MODEL, request.task_type, request.stream,
    )
    try:
        if request.stream:
            async def _pipe():
                async with client.stream("POST", "/chat/completions", json=body, headers=headers) as resp:
                    resp.raise_for_status()
                    async for chunk in resp.aiter_bytes():
                        yield chunk
            return StreamingResponse(_pipe(), media_type="text/event-stream")
        resp = await client.post("/chat/completions", json=body, headers=headers)
        resp.raise_for_status()
        return JSONResponse(content=resp.json())
    except httpx.HTTPStatusError as e:
        # 不向客户端泄露上游错误详情（可能含 URL/模型名）
        logger.error("[lumo_proxy vision] 上游 HTTP %s: %s", e.response.status_code, e.response.text[:300])
        raise HTTPException(status_code=502, detail="vision upstream error")
    except httpx.HTTPError as e:
        logger.error(f"[lumo_proxy vision] 上游网络错误: {e}")
        raise HTTPException(status_code=502, detail="vision upstream unreachable")


# ============ 路由定义 ============

router = APIRouter(tags=["lumo-proxy"])


@router.post("/persona/v1/chat/completions")
async def persona_chat_completions(
    request: ChatCompletionRequest,
    auth: dict = Depends(require_proxy_token),
):
    """persona-aware OpenAI 兼容端点。

    管线复用 chat.py 的注入逻辑（build_system_prompt + message_manager + RAG + supplement），
    但以旁路方式实现，不修改 chat.py 源码。

    数据流：
      NEKO 输入 → 本端点 → 注入陆墨人格 + session + RAG → 上游 LLM → OpenAI 格式返回
    """
    # M4.5：含图片的多模态请求（CUA 截图）直接透传视觉上游，
    # 不走只提取文本的 persona 链路（否则图片被丢弃，CUA 无法决策）
    if _messages_contain_image(request.messages):
        return await _vision_forward(request)

    # 延迟 import 避免循环依赖
    from apiserver.llm_service import get_llm_service
    from apiserver.message_manager import message_manager
    from apiserver.routes.chat import _supports_function_calling
    from system.config import build_context_supplement, build_system_prompt, get_config

    # [local-patch] 沈遥 R2：task_type 分流
    # conversation 走完整人格注入+RAG+历史写入；其他类型（summary/correction/vision/agent）
    # 走轻量路径，不注入人格、不查 RAG、不写历史，避免污染对话上下文
    is_conversation = (request.task_type or "conversation") == "conversation"

    # 1. 提取最后一条 user 消息
    user_msg = _extract_last_user_message(request.messages)
    if not user_msg.strip():
        raise HTTPException(status_code=400, detail="messages 中无有效 user 消息")

    # 2. session（复用陆墨 session 体系）
    session_id = message_manager.create_session(
        request.session_id, temporary=request.temporary
    )

    # 3. 系统提示词 = 纯人格（仅 conversation 注入，其他任务不注入）
    system_prompt = build_system_prompt() if is_conversation else ""

    # 4. 构建对话消息（人格在 messages[0]）
    messages = message_manager.build_conversation_messages(
        session_id=session_id,
        system_prompt=system_prompt,
        current_message=user_msg,
    )

    # 5. RAG 召回（仅 conversation 查 RAG，其他任务跳过）
    rag_section = await _query_rag_standalone(user_msg) if is_conversation else ""

    # 6. 检测模型是否支持原生 function calling
    current_model = get_config().api.model
    supports_fc = _supports_function_calling(current_model)

    # 7. 附加知识（仅 conversation 附加技能/RAG，其他任务最小化）
    if is_conversation:
        # [M3.1a] 查 NEKO 侧用户状态快照，注入 environment_snapshot（无快照则空串）
        from .lumo_state import get_state_store
        _snapshot = get_state_store().get_snapshot(session_id)

        supplement = build_context_supplement(
            include_skills=True,
            include_tool_instructions=not supports_fc,
            skill_name=request.skill,
            rag_section=rag_section,
            multi_agent_context_section="",
            skills_prompt_override=None,
            skill_instructions_override=None,
            available_mcp_tools_override=None,
            agent_soul_prompt="",
            agent_notebook_prompt="",
            agent_long_term_memory_prompt="",
            environment_snapshot=_snapshot,   # ← M3.1a 新增传参
        )
        messages.append({"role": "system", "content": supplement})

    # 8. 温度
    temperature = request.temperature if request.temperature is not None else get_config().api.temperature

    # 9. 流式 / 非流式分流
    if request.stream:
        return StreamingResponse(
            _stream_persona_response(messages, temperature, request.model, session_id, user_msg, is_conversation),
            media_type="text/event-stream",
        )

    # 非流式
    llm_service = get_llm_service()
    llm_response = await llm_service.chat_with_context_and_reasoning(messages, temperature)

    # 10. 保存对话历史（仅 conversation 写历史，其他任务不污染 session）
    if is_conversation:
        try:
            from apiserver.routes.chat import _save_conversation_and_logs
            _save_conversation_and_logs(session_id, user_msg, llm_response.content)
        except Exception as e:
            logger.warning(f"[lumo_proxy] 保存对话历史失败（非致命）: {e}")

    # 11. OpenAI 兼容响应
    return JSONResponse(
        content=_to_openai_response(
            llm_response.content or "",
            request.model,
            getattr(llm_response, "reasoning_content", "") or "",
        )
    )


async def _stream_persona_response(
    messages: list,
    temperature: float,
    model: str,
    session_id: str,
    user_msg: str,
    is_conversation: bool = True,
) -> AsyncGenerator[str, None]:
    """流式 OpenAI SSE 响应。

    复用 llm_service.stream_chat_with_context，将其 SSE 格式转换为 OpenAI delta 格式。
    """
    from apiserver.llm_service import get_llm_service

    llm_service = get_llm_service()
    complete_text = ""
    # 同一响应的所有 chunk 共享同一 id（OpenAI 标准）
    chunk_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created_ts = int(time.time())

    try:
        async for sse_chunk in llm_service.stream_chat_with_context(
            messages, temperature
        ):
            # llm_service 的 SSE 格式: "data: {json}\n\n"
            # json 结构: {"type": "content"|"reasoning"|"tool_calls_native", "text": "..."}
            # 健壮解析：strip 后按 \n\n split 处理多事件合并
            for event in sse_chunk.split("\n\n"):
                event = event.strip()
                if not event.startswith("data:"):
                    continue
                payload_str = event[5:].strip()  # "data:" 后面可能有空格
                if not payload_str:
                    continue
                try:
                    payload = json.loads(payload_str)
                    chunk_type = payload.get("type")
                    text = payload.get("text", "")

                    if chunk_type == "content" and text:
                        complete_text += text
                        delta = {
                            "id": chunk_id,
                            "object": "chat.completion.chunk",
                            "created": created_ts,
                            "model": model,
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {"content": text},
                                    "finish_reason": None,
                                }
                            ],
                        }
                        yield f"data: {json.dumps(delta, ensure_ascii=False)}\n\n"
                    elif chunk_type == "reasoning" and text:
                        # reasoning_content 透传（DeepSeek-R1 等模型的思考过程）
                        delta = {
                            "id": chunk_id,
                            "object": "chat.completion.chunk",
                            "created": created_ts,
                            "model": model,
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {"reasoning_content": text},
                                    "finish_reason": None,
                                }
                            ],
                        }
                        yield f"data: {json.dumps(delta, ensure_ascii=False)}\n\n"
                except (json.JSONDecodeError, KeyError):
                    # 跳过无法解析的单个 event，不影响后续 event
                    continue

        # 发送结束标记
        finish_delta = {
            "id": chunk_id,
            "object": "chat.completion.chunk",
            "created": created_ts,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {},
                    "finish_reason": "stop",
                }
            ],
        }
        yield f"data: {json.dumps(finish_delta, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    except Exception as e:
        # M2 修复：不向客户端泄露内部异常详情（可能含 URL/端口/模型名）
        logger.exception("[lumo_proxy stream] 流式响应失败")
        error_delta = {
            "error": {"message": "streaming failed", "type": "internal_error"},
        }
        yield f"data: {json.dumps(error_delta, ensure_ascii=False)}\n\n"

    finally:
        # 保存对话历史（仅 conversation 写历史，其他任务不污染 session）
        if is_conversation and complete_text:
            try:
                from apiserver.routes.chat import _save_conversation_and_logs
                _save_conversation_and_logs(session_id, user_msg, complete_text)
            except Exception as e:
                logger.warning(f"[lumo_proxy stream] 保存对话历史失败（非致命）: {e}")
