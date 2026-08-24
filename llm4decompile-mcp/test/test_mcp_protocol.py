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


def _send(proc: subprocess.Popen, payload: dict) -> dict:
    """向 MCP stdio 写入一行 JSON-RPC，并读取下一行响应。"""
    line = json.dumps(payload) + "\n"
    proc.stdin.write(line.encode("utf-8"))
    proc.stdin.flush()
    out = proc.stdout.readline()
    while out.strip() == b"":
        out = proc.stdout.readline()
    return json.loads(out.decode("utf-8"))


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
        time.sleep(1.5)  # 等待 server 就绪

    @classmethod
    def tearDownClass(cls):
        try:
            cls.proc.kill()
        except Exception:
            pass

    def test_01_initialize(self):
        _send(self.proc, {
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        })
        # 随后通常是 notifications/initialized；这里主要验证无崩溃

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
