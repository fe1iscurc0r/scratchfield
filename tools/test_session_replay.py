"""session_replay 验收硬线（84号 A2）。"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcpserver.orchestration.session_replay import (  # noqa: E402
    capture_session,
    replay_session,
    summarize_failure,
)


def _trace_path(tmp_path) -> str:
    return str(tmp_path / "trace.json")


def test_capture_roundtrip(tmp_path):
    """capture → 落盘 → replay 内容一致（调用序 + 成功标志 + 累计耗时）。"""
    steps = [
        {"call": "parse_input", "input": "x", "output": "y", "ok": True, "duration_ms": 10},
        {"call": "query_db", "ok": True, "duration_ms": 20},
    ]
    p = capture_session(steps, _trace_path(tmp_path))
    replay = replay_session(p)
    assert [s["call"] for s in replay] == ["parse_input", "query_db"]
    assert all(s["ok"] for s in replay)
    assert all(s["status"] == "ok" for s in replay)
    assert replay[1]["elapsed_ms"] == 30.0


def test_failure_located(tmp_path):
    """构造含失败步 trace → summarize 能指出失败步 + 前 3 步上下文。"""
    steps = [
        {"call": "a", "ok": True},
        {"call": "b", "ok": True},
        {"call": "c", "ok": True},
        {"call": "d", "ok": False, "error": "boom"},
    ]
    p = capture_session(steps, _trace_path(tmp_path))
    s = summarize_failure(p)
    assert s["failed_index"] == 3
    assert s["failed_call"] == "d"
    assert s["context_before"] == ["a", "b", "c"]
    assert "boom" in s["summary"]


def test_empty_trace_rejected(tmp_path):
    """空 trace → summarize 明确报错；损坏 JSON → replay 明确报错。"""
    p = capture_session([], _trace_path(tmp_path))
    with pytest.raises(ValueError, match="空 trace"):
        summarize_failure(p)

    bad = tmp_path / "bad.json"
    bad.write_text("{ not json", encoding="utf-8")
    with pytest.raises(ValueError, match="损坏"):
        replay_session(str(bad))
