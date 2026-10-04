#!/usr/bin/env python3
"""
OpenClaw Gateway WebSocket 客户端。

只实现当前 Naga 需要的最小闭环：
1. 完成 Gateway 的 connect.challenge / connect 握手
2. 调用 chat.send
3. 接收 chat / agent 事件
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import sys
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, Dict, Optional

import websockets
from websockets.client import WebSocketClientProtocol

logger = logging.getLogger("openclaw.ws_client")

PROTOCOL_VERSION = 3


class OpenClawWSClient:
    """最小可用的 Gateway WebSocket 客户端。"""

    def __init__(
        self,
        gateway_url: str = "ws://127.0.0.1:20789",
        token: str | None = None,
        on_event: Callable[[dict[str, Any]], Awaitable[None] | None] | None = None,
    ):
        self.gateway_url = gateway_url.replace("http://", "ws://").replace("https://", "wss://")
        self.token = token
        self.on_event = on_event
        self.ws: WebSocketClientProtocol | None = None
        self.pending: dict[str, asyncio.Future] = {}
        self.connected = False
        self._recv_task: asyncio.Task | None = None
        self._instance_id = str(uuid.uuid4())
        self._closing = False

    async def connect(
        self,
        *,
        retries: int = 3,
        retry_interval: float = 1.5,
    ) -> bool:
        """建立 WebSocket 连接并完成 Gateway 握手。

        连接失败、握手超时等瞬态故障（对应上游网关 502/504 类超时）
        自动指数退避重试；握手被明确拒绝（鉴权失败、协议不匹配）
        属于确定性失败，不重试直接返回 False。
        """
        last_error = ""
        for attempt in range(1, retries + 1):
            try:
                self.ws = await websockets.connect(
                    self.gateway_url,
                    max_size=25 * 1024 * 1024,
                    ping_interval=20,
                    ping_timeout=20,
                )

                if not await self._handshake():
                    # 确定性失败（协议/鉴权），重试无意义
                    return False

                self.connected = True
                self._recv_task = asyncio.create_task(self._recv_loop(), name="openclaw-ws-recv")
                logger.info("WebSocket 已连接到 OpenClaw Gateway")
                return True
            except Exception as e:
                last_error = f"{type(e).__name__}: {e}"
                logger.warning(f"WebSocket 连接失败（第 {attempt}/{retries} 次）: {e}")
                await self.close()
                if attempt < retries:
                    backoff = retry_interval * (2 ** (attempt - 1))
                    await asyncio.sleep(backoff)
        logger.error(f"WebSocket 连接失败，已达最大重试次数: {last_error}")
        return False

    async def _handshake(self) -> bool:
        """完成 connect.challenge / connect 握手，失败时清理连接。"""
        try:
            challenge = await self._recv_frame()
            if challenge.get("type") != "event" or challenge.get("event") != "connect.challenge":
                logger.error(f"WebSocket 握手失败，未收到 connect.challenge: {challenge}")
                await self.close()
                return False

            nonce = str((challenge.get("payload") or {}).get("nonce") or "").strip()
            if not nonce:
                logger.error("WebSocket 握手失败，challenge nonce 为空")
                await self.close()
                return False

            params: dict[str, Any] = {
                "minProtocol": PROTOCOL_VERSION,
                "maxProtocol": PROTOCOL_VERSION,
                "client": {
                    "id": "gateway-client",
                    "displayName": "openclaw-tui",
                    "version": "5.1.1",
                    "platform": sys.platform,
                    "mode": "ui",
                    "instanceId": self._instance_id,
                },
                "caps": ["tool-events"],
                "scopes": ["operator.write", "operator.admin"],
            }
            if self.token:
                params["auth"] = {"token": self.token}

            req_id = str(uuid.uuid4())
            await self._send_frame({
                "type": "req",
                "id": req_id,
                "method": "connect",
                "params": params,
            })

            response = await asyncio.wait_for(self._recv_frame(), timeout=10)
            if response.get("type") != "res" or str(response.get("id") or "").strip() != req_id:
                logger.error(f"WebSocket connect 响应异常: {response}")
                await self.close()
                return False
            if not response.get("ok"):
                logger.error(f"WebSocket connect 被拒绝: {response}")
                await self.close()
                return False

            payload = response.get("payload") if isinstance(response, dict) else None
            if not isinstance(payload, dict) or payload.get("type") != "hello-ok":
                logger.error(f"WebSocket connect 响应异常: {response}")
                await self.close()
                return False
            return True
        except Exception as e:
            logger.error(f"WebSocket 握手异常: {e}")
            await self.close()
            raise

    async def _send_frame(self, frame: dict[str, Any]) -> None:
        if not self.ws:
            raise RuntimeError("WebSocket 未连接")
        await self.ws.send(json.dumps(frame, ensure_ascii=False))

    async def _recv_frame(self) -> dict[str, Any]:
        if not self.ws:
            raise RuntimeError("WebSocket 未连接")
        data = await self.ws.recv()
        if isinstance(data, bytes):
            data = data.decode("utf-8", errors="replace")
        return json.loads(data)

    async def _dispatch_event(self, event_frame: dict[str, Any]) -> None:
        if not self.on_event:
            return
        result = self.on_event(event_frame)
        if inspect.isawaitable(result):
            await result

    async def _recv_loop(self) -> None:
        try:
            while self.ws:
                frame = await self._recv_frame()
                frame_type = frame.get("type")
                if frame_type == "res":
                    req_id = str(frame.get("id") or "").strip()
                    future = self.pending.pop(req_id, None)
                    if not future:
                        continue
                    if frame.get("ok"):
                        future.set_result(frame)
                    else:
                        future.set_exception(Exception(((frame.get("error") or {}).get("message")) or "unknown error"))
                elif frame_type == "event":
                    await self._dispatch_event(frame)
        except Exception as e:
            if not self._closing:
                logger.error(f"WebSocket 接收循环异常: {e}")
        finally:
            self.connected = False
            for future in self.pending.values():
                if not future.done():
                    future.set_exception(RuntimeError("gateway closed"))
            self.pending.clear()

    async def request(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.ws or not self.connected:
            raise RuntimeError("gateway not connected")
        req_id = str(uuid.uuid4())
        future = asyncio.get_running_loop().create_future()
        self.pending[req_id] = future
        await self._send_frame({
            "type": "req",
            "id": req_id,
            "method": method,
            "params": params or {},
        })
        return await future

    async def chat_send(
        self,
        *,
        message: str,
        session_key: str,
        timeout_ms: int | None = None,
        thinking: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "sessionKey": session_key,
            "message": message,
            "idempotencyKey": str(uuid.uuid4()),
        }
        if timeout_ms is not None:
            payload["timeoutMs"] = timeout_ms
        if thinking:
            payload["thinking"] = thinking
        response = await self.request("chat.send", payload)
        return (response.get("payload") if isinstance(response, dict) else {}) or {}

    async def chat_inject(
        self,
        *,
        session_key: str,
        message: str,
        label: str | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "sessionKey": session_key,
            "message": message,
        }
        if label:
            payload["label"] = label
        response = await self.request("chat.inject", payload)
        return (response.get("payload") if isinstance(response, dict) else {}) or {}

    async def close(self) -> None:
        self._closing = True
        self.connected = False
        if self._recv_task:
            self._recv_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._recv_task
            self._recv_task = None
        if self.ws:
            with contextlib.suppress(Exception):
                await self.ws.close()
            self.ws = None
        self._closing = False


import contextlib
