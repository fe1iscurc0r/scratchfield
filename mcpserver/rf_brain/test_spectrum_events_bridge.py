"""K09 验收测试：spectrum_events MCP 桥注册。

覆盖：
  1. manifest 含 spectrum_events.* 三个命令且 JSON 合法
  2. ingest_frame → appear 事件
  3. current_interferers 返回活跃源（interferer 视图）
  4. recent_events 返回最近 N 条
  5. 未知工具 fail-fast
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import numpy as np

from .spectrum_events_bridge import SpectrumEventsBridge, reset_cache


def _run(bridge, tool_name, **params):
    return asyncio.run(bridge.handle_handoff({**{"tool_name": tool_name}, **params}))


def _freqs(n: int = 201) -> list[float]:
    return np.linspace(-1000.0, 1000.0, n).tolist()


def _floor(n: int = 201, db: float = -100.0) -> list[float]:
    return [db] * n


def test_manifest_registered():
    p = Path(__file__).with_name("agent-manifest.json")
    manifest = json.loads(p.read_text(encoding="utf-8"))
    cmds = {c["command"] for c in manifest["capabilities"]["invocationCommands"]}
    assert {"spectrum_events.ingest_frame", "spectrum_events.current_interferers",
            "spectrum_events.recent_events"} <= cmds


def test_bridge_query_flow():
    reset_cache()
    bridge = SpectrumEventsBridge()
    freqs = _freqs()

    # 噪声底 → 无事件
    out = json.loads(_run(bridge, "spectrum_events.ingest_frame", freqs=freqs, db=_floor()))
    assert out["result"]["new_events"] == []

    # 强音 → appear
    db = _floor()
    db[100] = 0.0
    out = json.loads(_run(bridge, "spectrum_events.ingest_frame", freqs=freqs, db=db))
    assert out["result"]["new_events"][0]["event_type"] == "appear"

    # 当前干扰源
    out = json.loads(_run(bridge, "spectrum_events.current_interferers"))
    assert out["status"] == "ok"
    assert len(out["result"]["interferers"]) == 1
    assert out["result"]["interferers"][0]["event_type"] == "interferer"

    # 最近事件
    out = json.loads(_run(bridge, "spectrum_events.recent_events", limit=5))
    assert out["status"] == "ok"
    assert len(out["result"]["events"]) >= 1


def test_unknown_tool_failfast():
    reset_cache()
    out = json.loads(_run(SpectrumEventsBridge(), "spectrum_events.nope"))
    assert out["status"] == "error"
