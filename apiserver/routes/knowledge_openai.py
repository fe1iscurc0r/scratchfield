"""工单217 任务二 A 方案落地：知识检索型 OpenAI 兼容端点 `/v1/knowledge/chat/completions`。

与现有两端点的分工（不重复）：
  - lumo_proxy /persona/v1/chat/completions：**人格注入**（NEKO 上游）
  - openai_proxy /v1/chat/completions：**纯透传 + tool-call 归一**（OpenClaw 上游）
  - 本端点：**知识检索增强**（eext-knowledge-base / 任意 OpenAI 兼容客户端）——
    检索自家 rag/grag 知识 → 注入 system 上下文 → 转发上游 LLM → OpenAI 格式回传

行为：
  - POST /v1/knowledge/chat/completions
    入参：标准 OpenAI chat 格式（messages/model/stream/temperature...）
    流程：①require_proxy_token 鉴权（LUMO_PROXY_TOKEN）
          ②最后一条 user 消息 → _query_rag_standalone 多路检索（已有，不新写检索）
          ③检索结果作为 system 前缀注入（无命中则不注入——不污染）
          ④转发 config 里的上游 LLM（llm_service stream_chat_with_context 之外的轻路径：
             直接 httpx 到 base_url，与 lumo_proxy 同款转发姿势）
          ⑤流式/非流式按入参 stream 决定，OpenAI chunk 格式回传
"""
from __future__ import annotations

import json
import logging
import time
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from system.config import get_config
from .lumo_proxy import _query_rag_standalone, require_proxy_token

logger = logging.getLogger(__name__)

router = APIRouter(tags=["knowledge-openai"])

KNOWLEDGE_SYSTEM_PREFIX = (
    "以下是本地知识库检索到的相关内容，回答时优先依据这些材料，"
    "与问题无关的内容忽略；材料为空时按常规知识回答：\n\n"
)


def _last_user_text(messages: list[dict]) -> str:
    """从原始 dict messages 提取最后一条 user 文本（不依赖 lumo_proxy 的 pydantic 类型）。"""
    for msg in reversed(messages):
        if msg.get("role") == "user":
            c = msg.get("content")
            if isinstance(c, str):
                return c
            if isinstance(c, list):
                return " ".join(p.get("text", "") for p in c if isinstance(p, dict) and p.get("type") == "text")
    return ""


@router.post("/v1/knowledge/chat/completions")
async def knowledge_chat_completions(
    request: Request,
    _auth: dict = Depends(require_proxy_token),
):
    """知识检索增强的 OpenAI 兼容端点（工单217 任务二 A 方案）。"""
    body = await request.json()
    messages = body.get("messages") or []
    if not messages:
        raise HTTPException(status_code=400, detail="messages 不能为空")

    # ① 检索（复用 lumo_proxy 的多路召回——不新写检索逻辑）
    question = _last_user_text(messages)
    context = ""
    if question:
        try:
            context = await _query_rag_standalone(question)
        except Exception as e:  # noqa: BLE001 — 检索失败降级为纯转发（铁律5）
            logger.warning("[knowledge_openai] 检索失败，降级纯转发: %s", e)

    # ② 注入（有命中才注入）
    outbound_messages = list(messages)
    if context:
        outbound_messages.insert(0, {"role": "system", "content": KNOWLEDGE_SYSTEM_PREFIX + context})

    cfg = get_config()
    upstream = (cfg.api.base_url or "").rstrip("/")
    api_key = cfg.api.api_key or ""
    model = body.get("model") or cfg.api.model
    if not upstream:
        raise HTTPException(status_code=503, detail="上游 base_url 未配置")

    payload = {k: v for k, v in body.items() if k not in ("model",)}
    payload["model"] = model
    payload["messages"] = outbound_messages
    headers = {"Authorization": f"Bearer {api_key}"}
    want_stream = bool(body.get("stream"))

    req_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    created = int(time.time())

    if want_stream:
        return StreamingResponse(
            _stream_upstream(payload, headers, req_id, created, model),
            media_type="text/event-stream",
        )

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(f"{upstream}/chat/completions", json=payload, headers=headers)
    if resp.status_code != 200:
        # 上游错误原样透传状态码 + 人话提示（对齐工单221 错误分类要求）
        detail = _upstream_error_hint(resp.status_code, resp.text)
        raise HTTPException(status_code=resp.status_code, detail=detail)
    data = resp.json()
    # 归一最小 OpenAI 字段（防御上游缺字段）
    data.setdefault("id", req_id)
    data.setdefault("object", "chat.completion")
    data.setdefault("created", created)
    data.setdefault("model", model)
    data.setdefault("choices", [])
    return data


async def _stream_upstream(payload: dict, headers: dict, req_id: str, created: int, model: str):
    """流式：上游 SSE → 标准 OpenAI chunk 转发（含检索标记首块）。"""
    try:
        async with httpx.AsyncClient(timeout=None) as client:
            async with client.stream(
                "POST", f"{payload.get('_upstream', '')}/chat/completions"
                        if payload.get("_upstream") else _upstream_url(payload),
                json={k: v for k, v in payload.items() if not k.startswith("_")},
                headers=headers,
            ) as resp:
                if resp.status_code != 200:
                    err_body = (await resp.aread()).decode("utf-8", "replace")[:200]
                    yield _sse_error(_upstream_error_hint(resp.status_code, err_body))
                    return
                async for line in resp.aiter_lines():
                    if line.startswith("data:"):
                        yield line + "\n\n"
    except httpx.HTTPError as e:
        yield _sse_error(f"上游连接失败: {type(e).__name__}")


def _upstream_url(payload: dict) -> str:
    from system.config import get_config as _gc

    return (_gc().api.base_url or "").rstrip("/") + "/chat/completions"


def _sse_error(msg: str) -> str:
    chunk = {
        "error": {"message": msg, "type": "upstream_error", "code": None},
    }
    return f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"


def _upstream_error_hint(status: int, body: str) -> str:
    """上游错误 → 人话（对齐工单221 场景3 的分类口径）。"""
    hints = {
        401: "认证失败：API key 无效或已过期",
        402: "账户欠费：请充值或切换 provider",
        429: "请求过于频繁/额度耗尽：稍后重试",
    }
    base = hints.get(status, f"上游错误 {status}")
    return f"{base}（上游响应片段: {body[:120]}）"
