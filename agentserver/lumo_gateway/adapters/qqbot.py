"""QQ 官方 Bot API v2 适配器：WS 收事件 + REST 出站（M1：C2C 私聊直连）。

协议要点（QQ 官方机器人开放平台 api.sgroup.qq.com，v2）：
  - 网关 WS：wss://api.sgroup.qq.com
  - 鉴权头：Authorization: Bot {appid}.{token}
  - Identify(op 2)：d.token = "Bot {appid}.{token}"，d.intents = 位掩码
  - Hello(op 10)：d.heartbeat_interval(ms) → 心跳(op 1) 周期发送
  - Dispatch(op 0)：t 事件名 → C2C_MESSAGE_CREATE（私聊）/ GROUP_AT_MESSAGE_CREATE（群@）

intent 位掩码（按最新文档）：
  INTENT_GROUP_AND_C2C_EVENT = 1 << 25
  —— 覆盖 C2C_MESSAGE_CREATE（私聊）与 GROUP_AT_MESSAGE_CREATE（群@）两类事件。

健壮性（照 SPEC-11 风险#5）：
  - msg_id 去重：LRU 缓存（容量可配），防重投
  - WS 断线指数退避重连：1s → 2s → 4s … 封顶 60s，随机 jitter
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
from collections import OrderedDict
from typing import Any

import httpx
import websockets

from ..models import InboundMessage, OutboundMessage
from .base import PlatformAdapter

logger = logging.getLogger("lumo_gateway.adapters.qqbot")

# QQ 官方机器人开放平台 API v2 网关（可经 QQ_WS_ENDPOINT 覆盖，测试用）
DEFAULT_WS_ENDPOINT = "wss://api.sgroup.qq.com"
WS_ENDPOINT = os.environ.get("QQ_WS_ENDPOINT", DEFAULT_WS_ENDPOINT).strip() or DEFAULT_WS_ENDPOINT
REST_BASE = os.environ.get("QQ_REST_BASE", "https://api.sgroup.qq.com").rstrip("/")

# ---------- intent 位掩码（QQ 官方文档值） ----------
# 1 << 25 == INTENT_GROUP_AND_C2C_EVENT：群与 C2C 事件（覆盖以下两类）
INTENT_GROUP_AND_C2C_EVENT = 1 << 25
DEFAULT_INTENTS = INTENT_GROUP_AND_C2C_EVENT

# ---------- 事件名常量（Dispatch t 字段） ----------
EVENT_C2C_MESSAGE_CREATE = "C2C_MESSAGE_CREATE"
EVENT_GROUP_AT_MESSAGE_CREATE = "GROUP_AT_MESSAGE_CREATE"
_EVENT_HANDLED = {EVENT_C2C_MESSAGE_CREATE, EVENT_GROUP_AT_MESSAGE_CREATE}

# ---------- OP 常量 ----------
OP_DISPATCH = 0
OP_HEARTBEAT = 1
OP_IDENTIFY = 2
OP_HEARTBEAT_ACK = 11
OP_HELLO = 10


def reconnect_delay(attempt: int, base: float = 1.0, cap: float = 60.0) -> float:
    """指数退避：base * 2^(attempt-1)，封顶 cap，加 jitter（0~0.5s）。"""
    raw = base * (2 ** max(attempt - 1, 0))
    return min(raw, cap) + random.uniform(0, 0.5)


class QQBotAdapter(PlatformAdapter):
    """QQ Bot API v2：WS 收事件（C2C 私聊）+ REST 出站回复。"""

    name = "qqbot"

    def __init__(
        self,
        app_id: str,
        client_secret: str,
        bot_token: str | None = None,
        *,
        intents: int = DEFAULT_INTENTS,
        dedup_cache: int = 1024,
        retry_base: float = 1.0,
        retry_max: float = 60.0,
        ws_endpoint: str = WS_ENDPOINT,
    ) -> None:
        super().__init__()
        self.app_id = app_id
        self.client_secret = client_secret
        # 密钥仅存内存，不落盘；未单独配 bot token 时用 client_secret 拼 Bot 头
        self.bot_token = (bot_token or client_secret).strip()
        self.intents = intents
        self.ws_url = ws_endpoint
        self._ws: Any = None  # websockets ClientConnection
        self._hb_task: asyncio.Task | None = None
        self._stopping = False
        self._last_s: int | None = None
        self._hb_interval: float = 30.0
        self._http: httpx.AsyncClient | None = None
        # msg_id 去重 LRU
        self._dedup: "OrderedDict[str, bool]" = OrderedDict()
        self._dedup_max = max(dedup_cache, 1)
        self._retry_base = retry_base
        self._retry_max = retry_max
        self._last_error = ""

    # ---------- 鉴权 / HTTP ----------

    def _auth_header(self) -> str:
        return f"Bot {self.app_id}.{self.bot_token}"

    def _get_http(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(timeout=15.0)
        return self._http

    # ---------- msg_id 去重（LRU） ----------

    def _is_dup(self, msg_id: str) -> bool:
        """msg_id 已见 → True（并刷新 LRU 位置）；未见 → 记入缓存。"""
        if not msg_id:
            return False
        if msg_id in self._dedup:
            self._dedup.move_to_end(msg_id)
            return True
        self._dedup[msg_id] = True
        if len(self._dedup) > self._dedup_max:
            self._dedup.popitem(last=False)
        return False

    # ---------- WS 生命周期 ----------

    async def connect(self) -> bool:
        """连接 QQ 网关 WS 并完成 Hello → Identify 握手。"""
        try:
            self._ws = await websockets.connect(self.ws_url, max_size=25 * 1024 * 1024)
            await self._handshake()
            self.connected = True
            self._last_error = ""
            logger.info("[qqbot] WS 已连接并完成握手（%s）", self.ws_url)
            return True
        except Exception as e:  # noqa: BLE001  # 连接失败返回 False，由 run() 退避重连
            self.connected = False
            self._last_error = str(e)
            logger.error("[qqbot] WS 连接失败: %s", e)
            await self.close()
            return False

    async def _handshake(self) -> None:
        """Hello(op10) → 记录心跳间隔 → Identify(op2) → Ready 确认。"""
        hello = await self._recv_frame()
        if hello.get("op") != OP_HELLO:
            raise RuntimeError(f"未收到 Hello 帧: {hello}")
        hb_ms = (hello.get("d") or {}).get("heartbeat_interval") or 30000
        self._hb_interval = float(hb_ms) / 1000.0
        await self._send_frame({
            "op": OP_IDENTIFY,
            "d": {
                "token": self._auth_header(),
                "intents": self.intents,
                "shard": [0, 1],
            },
        })
        # Identify 后第一条 dispatch 为 READY（op 0, t=READY）
        ready = await self._recv_frame()
        if ready.get("op") != OP_DISPATCH or ready.get("t") != "READY":
            raise RuntimeError(f"Identify 未收到 READY 帧: {ready}")
        self._hb_task = asyncio.create_task(self._heartbeat_loop(), name="lumo-gateway-qq-heartbeat")

    async def _send_frame(self, frame: dict[str, Any]) -> None:
        if not self._ws:
            raise RuntimeError("WS 未连接")
        await self._ws.send(json.dumps(frame, ensure_ascii=False))

    async def _recv_frame(self) -> dict[str, Any]:
        if not self._ws:
            raise RuntimeError("WS 未连接")
        data = await self._ws.recv()
        if isinstance(data, bytes):
            data = data.decode("utf-8", errors="replace")
        return json.loads(data)

    async def _heartbeat_loop(self) -> None:
        while not self._stopping:
            await asyncio.sleep(self._hb_interval)
            if not self._ws:
                break
            try:
                await self._send_frame({"op": OP_HEARTBEAT, "d": self._last_s})
            except Exception as e:  # noqa: BLE001
                logger.error("[qqbot] 心跳发送失败: %s", e)
                break

    # ---------- 入站事件 ----------

    async def _dispatch(self, frame: dict[str, Any]) -> None:
        """Dispatch(op 0)：按事件名分发，C2C/群@ 消息归一化后投递。"""
        t = frame.get("t")
        if t not in _EVENT_HANDLED:
            return
        d = frame.get("d") or {}
        msg_id = str(d.get("id") or "")
        if self._is_dup(msg_id):
            logger.debug("[qqbot] 去重命中 msg_id=%s，跳过", msg_id)
            return
        author = d.get("author") or {}
        user_id = str(author.get("id") or "") or str(d.get("author_openid") or "")
        if not user_id:
            logger.warning("[qqbot] %s 事件缺 user_id，跳过", t)
            return
        content = str(d.get("content") or "")
        if t == EVENT_C2C_MESSAGE_CREATE:
            inbound = InboundMessage(
                platform="qq", msg_id=msg_id, user_id=user_id,
                group_id=None, content=content, raw=d,
            )
        else:  # GROUP_AT_MESSAGE_CREATE
            group_id = str(d.get("group_openid") or "")
            inbound = InboundMessage(
                platform="qq", msg_id=msg_id, user_id=user_id,
                group_id=group_id or None, content=content, raw=d,
            )
        await self.emit(inbound)

    async def _recv_loop(self) -> None:
        """接收循环：阻塞读帧，按 op 分发；连接断开抛异常向上（触发重连）。"""
        while self._ws and not self._stopping:
            frame = await self._recv_frame()
            op = frame.get("op")
            if op == OP_DISPATCH:
                self._last_s = frame.get("s") or self._last_s
                await self._dispatch(frame)
            elif op == OP_HELLO:  # 服务端主动重连时可能重发 Hello
                self._hb_interval = float((frame.get("d") or {}).get("heartbeat_interval") or 30000) / 1000.0
            elif op == OP_HEARTBEAT_ACK:
                pass

    # ---------- 常驻 / 出站 ----------

    async def run(self) -> None:
        """常驻任务：连接 → 收消息 → 断线指数退避重连（SPEC-11 风险#5）。"""
        attempt = 0
        while not self._stopping:
            ok = await self.connect()
            if ok:
                attempt = 0
                try:
                    await self._recv_loop()
                except Exception as e:  # noqa: BLE001  # 接收循环异常 → 退避重连
                    logger.error("[qqbot] 接收循环退出: %s", e)
            else:
                attempt += 1
            if self._stopping:
                break
            delay = reconnect_delay(attempt, self._retry_base, self._retry_max)
            logger.warning("[qqbot] %s 后重连（第 %d 次）", f"{delay:.1f}s", attempt)
            await asyncio.sleep(delay)
        await self.close()

    async def send(self, outbound: OutboundMessage) -> bool:
        """REST 出站回复：C2C → /v2/users/{user_id}/messages；群 → /v2/groups/{group_id}/messages。"""
        if outbound.group_id:
            url = f"{REST_BASE}/v2/groups/{outbound.group_id}/messages"
        else:
            url = f"{REST_BASE}/v2/users/{outbound.user_id}/messages"
        body: dict[str, Any] = {"msg_type": 0, "content": outbound.content}
        if outbound.msg_id:
            body["msg_id"] = outbound.msg_id
        headers = {"Authorization": self._auth_header()}
        try:
            client = self._get_http()
            resp = await client.post(url, json=body, headers=headers)
            resp.raise_for_status()
            return True
        except Exception as e:  # noqa: BLE001  # 出站失败不抛（降级纪律）
            logger.error("[qqbot] 出站发送失败: %s", e)
            return False

    async def close(self) -> None:
        self._stopping = True
        self.connected = False
        if self._hb_task:
            self._hb_task.cancel()
            try:
                await self._hb_task
            except asyncio.CancelledError:
                pass
            self._hb_task = None
        if self._ws:
            try:
                await self._ws.close()
            except Exception:  # noqa: BLE001
                pass
            self._ws = None
        if self._http:
            try:
                await self._http.aclose()
            except Exception:  # noqa: BLE001
                pass
            self._http = None
