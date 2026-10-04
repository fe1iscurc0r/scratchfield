"""R19 验收测试：LLM 语义编排原型。

覆盖：
  1. 指令集 ≥ 8 条
  2. 文本 → 意图：监听/告警/低功耗等语义正确识别
  3. 意图 → 策略：含权重/阈值/功率等字段
  4. 未知意图回退到默认监听；未知指令抛错

运行：python -m pytest mcpserver/rf_brain/prototypes/test_llm_spectrum_orchestrator.py -q
"""
from __future__ import annotations

import pytest

from . import llm_spectrum_orchestrator as lso


def test_instruction_set_size():
    assert len(lso.INSTRUCTION_SET) >= 8


def test_text_to_intent_mapping():
    assert lso.map_text("紧急告警")[0] == "emergency_alert"
    assert lso.map_text("降低功耗")[0] == "low_power"
    assert lso.map_text("监听 433MHz")[0] == "listen_band"
    assert lso.map_text("检测干扰")[0] == "detect_interference"


def test_policy_fields():
    cmd, policy = lso.map_text("优先送达")
    assert "weight" in policy
    assert "tx_power_dbm" in policy


def test_emergency_policy_max_reliability():
    cmd, policy = lso.map_text("紧急告警")
    assert policy["weight"] == 1.0
    assert policy["immediate"] is True
    assert policy["retry"] >= 2


def test_fallback_and_unknown_command():
    # 未知文本回退到默认监听
    cmd, _ = lso.map_text("随机无意义文本xyz")
    assert cmd == "listen_band"
    # 未知指令抛错
    with pytest.raises(ValueError):
        lso.map_command("nonexistent_command")
