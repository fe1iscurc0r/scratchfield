"""M3.1a 反向事件状态感知层测试（纯 Python，零 LLM）。"""
from __future__ import annotations

import time

from apiserver.routes.lumo_state import LumoStateStore, _STATE_TTL_SECONDS


def test_update_and_render():
    s = LumoStateStore()
    s.update("s1", "user_input", {"text": "帮我查一下木质素水凝胶", "confidence": 1.0})
    s.update("s1", "tts_end", {"interrupted": True})
    s.mark_error("s1", "fatal", "tts_engine_down")
    snap = s.get_snapshot("s1")
    assert "木质素" in snap
    assert "打断" in snap
    assert "fatal:tts_engine_down" in snap


def test_ttl_expired_returns_empty():
    s = LumoStateStore()
    s.update("s2", "user_action", {"action": "stop_playback"})
    s._states["s2"].last_action_at = time.time() - _STATE_TTL_SECONDS - 1
    assert s.get_snapshot("s2") == ""


def test_error_mark_independent():
    s = LumoStateStore()
    s.mark_error("s3", "warn", "asr_retry")
    assert "asr_retry" in s.get_snapshot("s3")


def test_unknown_session_returns_empty():
    s = LumoStateStore()
    assert s.get_snapshot("nonexistent") == ""


def test_asr_low_confidence_not_recorded():
    s = LumoStateStore()
    s.update("s4", "asr_result", {"text": "低置信度", "confidence": 0.3})
    assert "低置信度" not in s.get_snapshot("s4")


def test_asr_high_confidence_recorded():
    s = LumoStateStore()
    s.update("s5", "asr_result", {"text": "高置信度", "confidence": 0.8})
    assert "高置信度" in s.get_snapshot("s5")


def test_tts_interrupted_without_error():
    """tts_end(interrupted=True) 单独发生（无 error 事件）也应渲染打断行。"""
    s = LumoStateStore()
    s.update("s6", "tts_end", {"interrupted": True})
    assert "打断" in s.get_snapshot("s6")


def test_tts_start_clears_interrupted():
    s = LumoStateStore()
    s.update("s7", "tts_end", {"interrupted": True})
    s.update("s7", "tts_start", {})
    assert "打断" not in s.get_snapshot("s7")


def test_gc_removes_stale():
    s = LumoStateStore()
    s.update("s8", "user_action", {"action": "stop_playback"})
    s._states["s8"].last_action_at = time.time() - _STATE_TTL_SECONDS - 1
    s.gc()
    assert "s8" not in s._states
