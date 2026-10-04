"""M3.1b 规则门测试（纯 Python，零 LLM，mock 时间）。"""
from __future__ import annotations

import pytest

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.core]

import time
from unittest import mock

from apiserver.routes.lumo_proactive import ProactiveDecider, ProactiveState


def _daytime():
    """白天 14 点的 struct_time（周日均值）。"""
    return time.struct_time((2026, 8, 16, 14, 0, 0, 6, 228, 0))


def _night():
    """深夜 2 点的 struct_time。"""
    return time.struct_time((2026, 8, 16, 2, 0, 0, 6, 228, 0))


def test_gate_user_active():
    d = ProactiveDecider()
    assert d._gate("s1", "有活动", time.time()) == "PASS_USER_ACTIVE"


def test_gate_cooldown():
    d = ProactiveDecider()
    st = d._states.setdefault("s2", ProactiveState())
    st.last_open_at = time.time()
    st.last_response = "accept"
    assert d._gate("s2", "", time.time()) == "PASS_COOLDOWN"


def test_gate_throttled():
    d = ProactiveDecider()
    st = d._states.setdefault("s3", ProactiveState())
    now = time.time()
    st.opens_this_hour = [now - 10, now - 20, now - 30]
    assert d._gate("s3", "", now) == "PASS_THROTTLED"


def test_gate_silent_hours():
    d = ProactiveDecider()
    with mock.patch("time.localtime", return_value=_night()):
        assert d._gate("s4", "", time.time()) == "PASS_SILENT_HOURS"


def test_gate_pass():
    d = ProactiveDecider()
    st = d._states.setdefault("s5", ProactiveState())
    st.last_open_at = time.time() - 3 * 3600  # 3h 前，冷却已过
    st.last_response = "accept"
    with mock.patch("time.localtime", return_value=_daytime()):
        assert d._gate("s5", "", time.time()) is None


def test_topic_decay():
    d = ProactiveDecider()
    now = time.time()
    # 未推过 → 可推
    assert d._topic_decayed("s6", "topicA", now) is True
    # 刚推过 → 跳过
    d._states["s6"].last_topics["topicA"] = now
    assert d._topic_decayed("s6", "topicA", now) is False
    # 衰减后 → 可推
    d._states["s6"].last_topics["topicA"] = now - 5 * 3600
    assert d._topic_decayed("s6", "topicA", now) is True


def test_check_gate_blocks_without_llm():
    """规则门不通过时 check 直接返回 None，不触发 LLM。"""
    import asyncio
    d = ProactiveDecider()
    result = asyncio.run(d.check("s7", "有活动", "科研提醒"))
    assert result is None


def test_respond_updates_cooldown_bucket():
    d = ProactiveDecider()
    d.respond("s8", "decline")
    assert d._states["s8"].last_response == "decline"
    d.respond("s8", "whatever")  # 非法值 → ignore
    assert d._states["s8"].last_response == "ignore"
