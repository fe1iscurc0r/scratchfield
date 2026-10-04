# -*- coding: utf-8 -*-
"""agent-65 七个 NEKO 参考原型测试（W65-01~07 验收硬线，合并单文件）。"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from cozo_trial import MockCozo, trial_plan
from expression_protocol import extract_expressions, map_expression, render_actions
from mcp_client_manager import MCPClientManager
from pet_profile import PetProfile, map_event, pet_dir
from soul_container import SoulContainer
from vad_state_machine import TurnDetector, VADStateMachine
from voice_interrupt_event import TTSStream, interrupt


# ---- W65-01 表情协议 ----
def test_expression_extract_and_map():
    assert "happy" in extract_expressions("你好 <<happy>>")
    assert map_expression("happy") == "smile"
    assert map_expression("unknown") == "neutral"


def test_expression_render_actions():
    assert ("happy", "smile") in render_actions("<<happy>>")


# ---- W65-02 语音打断 ----
def test_voice_interrupt_stops_tts():
    s = TTSStream()
    assert s.speak("句1") is True
    assert interrupt(s) is True
    assert s.speak("句2") is False  # 打断后不再发


def test_voice_interrupt_idempotent():
    s = TTSStream()
    interrupt(s)
    assert interrupt(s) is False  # 已停止，再次打断返回 False


# ---- W65-03 滞后 VAD ----
def test_vad_start_lag_configurable():
    v = VADStateMachine(start_frames=3, stop_frames=5)
    for _ in range(2):
        v.feed(True)
    assert v.state == "silence"  # 未达 N 帧
    v.feed(True)
    assert v.state == "speech"   # 达 N 帧起录


def test_vad_stop_lag_configurable():
    v = VADStateMachine(start_frames=1, stop_frames=3)
    v.feed(True)
    assert v.state == "speech"
    for _ in range(3):
        v.feed(False)
    assert v.state == "silence"  # 达 M 帧停录


def test_turn_detector_cancel_resume():
    t = TurnDetector()
    t.push("a")
    t.cancel()
    assert t.queue == [] and t.cancelled is True
    t.resume()
    assert t.cancelled is False


# ---- W65-04 桌宠 pet-id ----
def test_pet_dir_isolation():
    assert pet_dir("tom") == "pets/tom"
    assert pet_dir("jerry") == "pets/jerry"


def test_pet_event_mapping():
    p = PetProfile("tom")
    assert p.react("click")["action"] == "poke"
    assert p.react("unknown")["action"] == "idle"


# ---- W65-05 MCP 客户端管理面 ----
def test_mcp_server_state_transition():
    m = MCPClientManager()
    sid = m.register("fs")
    assert m.transition("fs", "connecting") is True
    assert m.transition("fs", "active") is True
    assert m.transition("fs", "connecting") is False  # active 不可回 connecting


def test_mcp_short_id_unique():
    m = MCPClientManager()
    a = m.register("a")
    b = m.register("b")
    assert a != b and m.resolve(a) == "a"
    assert m.is_short_id_unique() is True


# ---- W65-06 灵魂容器 ----
def test_soul_container_mode_switch():
    s = SoulContainer.from_dict({"soul": "温柔助手", "depth_prompt": "chat"})
    assert s.set_mode("work") is True
    assert s.depth_prompt == "work"
    assert s.set_mode("bad") is False
    assert "工作模式" in s.prompt()


# ---- W65-07 cozo 试路径 ----
def test_cozo_mock_read_write():
    c = MockCozo()
    c.create_table("mem")
    c.put("mem", "k", "v")
    assert c.get("mem", "k") == "v"


def test_cozo_trial_plan_has_decision_tree():
    plan = trial_plan()
    assert "path_a" in plan and "path_c" in plan
    assert "先 A 后 C" in plan["decision"]
