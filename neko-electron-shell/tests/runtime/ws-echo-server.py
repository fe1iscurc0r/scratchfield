#!/usr/bin/env python
"""本地 WebSocket 回显服务（WO-278 运行时工装用）。

不依赖 NEKO 后端：只做 `收到的文本 → 'echo:' + 原文` 回显，
用来验证「渲染进程 → IPC → 主进程真 WS → 回显 → IPC → 渲染进程」这条链路。
"""

from __future__ import annotations

import argparse
import asyncio

import websockets


async def handler(ws):
    try:
        async for message in ws:
            await ws.send("echo:" + (message if isinstance(message, str) else message.decode()))
    except websockets.ConnectionClosed:
        pass


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=18765)
    args = ap.parse_args()
    async with websockets.serve(handler, "127.0.0.1", args.port):
        print(f"[ws-echo] listening ws://127.0.0.1:{args.port}/echo", flush=True)
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
