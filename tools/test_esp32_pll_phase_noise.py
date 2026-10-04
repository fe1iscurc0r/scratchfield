# -*- coding: utf-8 -*-
"""esp32_pll_phase_noise 测试（W61-05 验收：高 Q 参考 → 带内相位噪声更低）。"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from esp32_pll_phase_noise import REF_FLOOR, compare_ref_oscillators, pll_phase_noise


def test_high_q_reference_lower_in_band_noise():
    c = compare_ref_oscillators(loop_bw=1000.0, div_ratio=100.0, offsets=[100.0, 1000.0, 10000.0])
    # 带内（100Hz）处，OCXO < TCXO < XTAL
    assert c["OCXO"][0] < c["TCXO"][0] < c["XTAL"][0]


def test_in_band_dominated_by_reference():
    # 带内由参考主导：换参考会改变带内噪声，带外（10kHz）三者趋同（都由 VCO 主导）
    c = compare_ref_oscillators(loop_bw=1000.0, div_ratio=100.0, offsets=[100.0, 1000.0, 10000.0])
    assert abs(c["OCXO"][2] - c["XTAL"][2]) < 1e-9  # 带外同 VCO 主导


def test_div_ratio_amplifies_in_band():
    a = pll_phase_noise(-140.0, -100.0, 1000.0, 10.0, [100.0])[0]
    b = pll_phase_noise(-140.0, -100.0, 1000.0, 100.0, [100.0])[0]
    assert b > a  # 分频比越大，带内噪声放大越多（20log10(N)）


def test_compare_returns_all_refs():
    c = compare_ref_oscillators()
    assert set(c) == set(REF_FLOOR)
