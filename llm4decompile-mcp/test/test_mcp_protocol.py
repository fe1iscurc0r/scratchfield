"""
MCP stdio 协议集成测试。

不依赖真实模型：通过 subprocess 启动 mcp_server.py，用 JSON-RPC over stdio
发送 initialize / tools/list / tools/call(health)，验证：
  1. MCP 握手成功
  2. 三个工具正确列出
  3. health 返回模型未加载状态（无模型路径时）
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path

SERVER = Path(__file__).resolve().parent.parent / "mcp_server.py"


def _send(proc: subprocess.Popen, payload: dict, *, timeout: float = 30.0) -> dict:
    """写入一行 JSON-RPC 请求，按响应中的 "id" 匹配读取对应响应。

    旧实现「盲读一行」在高负载下会与响应流错位（server 启动/处理变慢时
    读到非本请求的行）→ 误报。这里：写请求后循环读行，跳过空行与 id 不匹配的
    杂散/通知行，直到拿到 id 匹配的响应或超时。用带超时的逐行 readline 兼容跨
    平台（select 在 Windows 上不支持文件对象，故不采用）。
    """
    expected_id = payload.get("id")
    line = json.dumps(payload) + "\n"
    proc.stdin.write(line.encode("utf-8"))
    proc.stdin.flush()
    deadline = time.time() + timeout
    while time.time() < deadline:
        out = proc.stdout.readline()
        if out == b"":  # EOF：子进程退出
            raise RuntimeError("MCP server 连接已关闭（子进程退出）")
        s = out.strip()
        if not s:
            continue
        try:
            msg = json.loads(s.decode("utf-8"))
        except json.JSONDecodeError:
            continue  # 跳过非 JSON 杂散行
        if not isinstance(msg, dict):
            continue
        if expected_id is None or msg.get("id") == expected_id:
            return msg
    raise TimeoutError(f"等待 id={expected_id} 的响应超时（{timeout}s）")


def _notify(proc: subprocess.Popen, payload: dict) -> None:
    """发送一条 JSON-RPC 通知（无 id、无响应），写入即返回。"""
    proc.stdin.write((json.dumps(payload) + "\n").encode("utf-8"))
    proc.stdin.flush()


class TestMCPProtocol(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # 用不存在的模型路径启动，验证协议层在无模型时仍可用
        env = dict(os.environ)
        env["LLM4DECOMPILE_MODEL_PATH"] = "/nonexistent/model.gguf"
        cls.proc = subprocess.Popen(
            [sys.executable, str(SERVER), "--config", "nonexistent.yaml"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=env,
            cwd=str(SERVER.parent),
        )
        # 完成官方 SDK 强制的 MCP 握手：initialize → 读响应 → notifications/initialized。
        # 缺少 notifications/initialized 时，服务端停留在未初始化态，后续
        # tools/list / tools/call 会返回带匹配 id 的 error 对象（无 result）。
        cls.init_result = _send(cls.proc, {
            "jsonrpc": "2.0", "id": 0, "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        })
        _notify(cls.proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})

    @classmethod
    def tearDownClass(cls):
        try:
            cls.proc.kill()
        except Exception:
            pass

    def test_01_initialize(self):
        # setUpClass 已完成 initialize 握手，这里验证服务端回了合法 result
        self.assertIn("result", self.init_result)
        self.assertIn("protocolVersion", self.init_result["result"])

    def test_02_list_tools(self):
        resp = _send(self.proc, {
            "jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {},
        })
        tools = resp["result"]["tools"]
        names = {t["name"] for t in tools}
        self.assertEqual(names, {"decompile_binary", "polish_ghidra_output", "health"})

    def test_03_health_not_loaded(self):
        resp = _send(self.proc, {
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "health", "arguments": {}},
        })
        content = resp["result"]["content"][0]["text"]
        self.assertIn("model_loaded", content)
        self.assertIn("not_loaded", content)


if __name__ == "__main__":
    unittest.main(verbosity=2)
