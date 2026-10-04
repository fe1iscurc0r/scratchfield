"""渠道路由（卷外增补·渠道网关层）——多渠道消息统一入口的 HTTP 面。

端点：
  POST /api/channels/webhook    通用 webhook 消息进入（外部系统 POST JSON）
  GET  /api/channels            渠道状态（received/rejected/ACL）
  POST /api/channels/telegram/send  手动回投（测试/管理用）
"""
from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from apiserver.channels import (
    ChannelMessage,
    get_channel_registry,
    init_channels_from_config,
)

router = APIRouter(prefix="/channels", tags=["channels"])


class WebhookPayload(BaseModel):
    """通用 webhook 消息体（宽松约定）。"""
    sender: str = Field("anonymous", max_length=64)
    content: str = Field(..., min_length=1, max_length=8192)
    reply_url: str = Field("", max_length=512)


@router.post("/webhook")
async def webhook_ingest(
    body: WebhookPayload,
    request: Request,
    _auth: Annotated[dict | None, Depends(_lazy_auth())] = None,
) -> dict:
    """外部消息进入 Lumo（normalize→ACL→message_queue）。"""
    reg = get_channel_registry()
    ch = reg.get("webhook")
    if ch is None:
        # 惰性初始化（api_server 未跑 init 时的独立部署场景）
        init_channels_from_config({})
        ch = reg.get("webhook")
    ok = ch.deliver(body.model_dump())
    return {"ok": ok, "channel": "webhook",
            "hint": "消息已进入对话队列" if ok else "被 ACL 拒绝或格式无效"}


@router.get("")
async def channels_status(
    _auth: Annotated[dict | None, Depends(_lazy_auth())] = None,
) -> dict:
    """全部渠道状态。"""
    return {"ok": True, "channels": get_channel_registry().status()}


class ManualSendRequest(BaseModel):
    channel: str = Field(..., max_length=32)
    reply_to: str = Field(..., max_length=128, description="渠道回投目标（TG=chat_id）")
    text: str = Field(..., max_length=4096)


@router.post("/send")
async def manual_send(
    body: ManualSendRequest,
    _auth: Annotated[dict | None, Depends(_lazy_auth())] = None,
) -> dict:
    """手动回投（测试/管理）。生产回复走 registry.reply_to 自动链路。"""
    reg = get_channel_registry()
    ch = reg.get(body.channel)
    if ch is None:
        return {"ok": False, "reason": "unknown_channel"}
    msg = ChannelMessage(channel=body.channel, sender="manual",
                         content="", reply_to=body.reply_to)
    ok = ch.send_reply(msg, body.text)
    return {"ok": ok}


def _lazy_auth():
    from apiserver.naga_auth import require_local_auth
    return require_local_auth
