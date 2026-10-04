"""R15 验收测试：事件触发稀疏计算原型。

覆盖：
  1. 能量门控：正确区分活跃帧与静默帧
  2. 事件触发成本：静默帧不做全量 FFT（只付门控代价）
  3. 计算削减：稀疏流下事件触发成本显著低于全量
  4. 单调性：占空比越低，削减比例越高

运行：python -m pytest mcpserver/rf_brain/prototypes/test_event_triggered_sparse.py -q
"""
from __future__ import annotations

import pytest

from . import event_triggered_sparse as ets


def test_energy_gate_detects_activity():
    frames = ets.synthesize_stream(100, 64, duty=0.2, seed=0)
    # 有信号的帧应判活跃，纯噪声帧应判静默
    for f in frames:
        assert ets.energy_gate(f) == (f.max() >= -60.0)


def test_quiet_frames_only_gate_cost():
    frames = ets.synthesize_stream(100, 64, duty=0.0, seed=0)  # 全静默
    cost = ets.event_triggered_cost(frames)
    # 静默流：每帧只付门控代价，无 FFT
    assert cost == pytest.approx(100 * 0.05, rel=1e-6)


def test_compute_reduction_sparse():
    frames = ets.synthesize_stream(1000, 256, duty=0.02, seed=0)
    full = ets.always_on_cost(frames)
    et = ets.event_triggered_cost(frames)
    assert et < full * 0.5  # 稀疏流下至少省一半


def test_reduction_monotonic_with_duty():
    frames_low = ets.synthesize_stream(500, 128, duty=0.01, seed=0)
    frames_high = ets.synthesize_stream(500, 128, duty=0.5, seed=0)
    r_low = 1 - ets.event_triggered_cost(frames_low) / ets.always_on_cost(frames_low)
    r_high = 1 - ets.event_triggered_cost(frames_high) / ets.always_on_cost(frames_high)
    assert r_low > r_high
