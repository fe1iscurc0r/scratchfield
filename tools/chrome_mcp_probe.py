"""chrome-devtools-mcp stdio 驱动脚本（W103-03 实测用 · 一次性验收工具）。

流程：initialize → tools/list → tools/call（list_pages 或截图）。
Chrome 需先以 --remote-debugging-port 启动（或由 server 自动拉起）。
"""
from __future__ import annotations

import json
import subprocess
import sys
import time


def _rpc(proc, payload: dict, timeout: float = 120.0):
    proc.stdin.write((json.dumps(payload) + "\n").encode())
    proc.stdin.flush()
    # 逐行读响应（JSON-RPC 通知会穿插，取 id 匹配的那条）
    deadline = time.time() + timeout
    while time.time() < deadline:
        line = proc.stdout.readline()
        if not line:
            break
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if msg.get("id") == payload["id"]:
            return msg
    raise TimeoutError(f"未收到 id={payload['id']} 的响应")


def main() -> int:
    proc = subprocess.Popen(
        ["npx.cmd", "-y", "chrome-devtools-mcp@latest"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    try:
        init = _rpc(proc, {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                           "params": {"protocolVersion": "2024-11-05",
                                      "capabilities": {},
                                      "clientInfo": {"name": "raman-probe", "version": "0"}}})
        tools = _rpc(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
        tool_names = [t["name"] for t in tools.get("result", {}).get("tools", [])]
        print("initialize server:", init.get("result", {}).get("serverInfo", {}).get("name"))
        print("工具数:", len(tool_names))
        print("前 8 工具:", tool_names[:8])
        # 实测调用：列出页面（若 Chrome 已带调试端口启动则返回真实页面列表）
        call = _rpc(proc, {"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                           "params": {"name": "list_pages", "arguments": {}}})
        text = ""
        for c in call.get("result", {}).get("content", []):
            if c.get("type") == "text":
                text += c["text"]
        print("list_pages 输出(前 300):", text[:300] or "(空)")
        return 0
    except Exception as e:
        print(f"实测异常: {type(e).__name__}: {e}")
        return 1
    finally:
        proc.stdin.close()
        proc.wait(timeout=30)


if __name__ == "__main__":
    sys.exit(main())
