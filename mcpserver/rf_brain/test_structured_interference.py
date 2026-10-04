"""R57 验收测试：结构化 RF 干扰抑制（承接 R03 滤波链）。

覆盖：
  1. classify_interference：窄带/脉冲/宽带三类干扰正确分类
  2. suppress_structured：合成多类干扰抑制后保真度较 R03 提升 ≥15%
  3. 谱减法：宽带噪声被压低、信号保留
  4. 坏参数拒绝

运行：python -m pytest mcpserver/rf_brain/test_structured_interference.py -q
"""
from __future__ import annotations

import numpy as np
import pytest

from . import rfi_mitigation as rfi
from . import structured_interference as si


def test_classify_interference_detects_all_types():
    x, _ = si.mixed_interference_signal(seed=0)
    profile = si.classify_interference(x, 4000.0, prominence_db=20.0, pulse_k=2.0)
    # 窄带：应检出 500Hz 干扰
    assert any(abs(p - 500.0) < 2.0 for p in profile.narrowband_hz)
    # 脉冲：掩码应命中脉冲突发区间（非空且集中）
    assert bool(profile.pulse_mask.any())
    burst = slice(8000, 8200)
    assert profile.pulse_mask[burst].mean() > 0.5
    # 宽带：噪声底估计为正
    assert profile.wideband_level > 0.0


def test_suppress_structured_beats_r03_by_15pct():
    """合成多类干扰：结构化抑制保真度较 R03（仅窄带陷波）提升 ≥15%。"""
    x, s = si.mixed_interference_signal(seed=0)
    r03 = rfi.mitigate_rfi(x, 4000.0, reference=s, prominence_db=20.0)
    st = si.suppress_structured(x, 4000.0, reference=s, prominence_db=20.0)
    improvement = 10.0 ** ((st.fidelity_db - r03.snr_after_db) / 10.0)
    assert improvement >= 1.15, f"保真度提升 {improvement:.2f}× 未达 1.15×"


def test_spectral_subtraction_reduces_wideband():
    """谱减法压低宽带噪声底，保留带内弱信号。"""
    rng = np.random.default_rng(0)
    n = 8000
    t = np.arange(n) / 4000.0
    s = 0.3 * np.sin(2.0 * np.pi * 800.0 * t)
    x = s + 0.4 * rng.standard_normal(n)
    cleaned = si._spectral_subtract(x, noise_level=float(np.median(np.abs(np.fft.rfft(x)) ** 2)))
    # 谱减法后，残差相对参考的误差应小于原始信号
    assert np.mean((cleaned - s) ** 2) < np.mean((x - s) ** 2)


def test_rejects_bad_input():
    with pytest.raises(ValueError):
        si.classify_interference(np.zeros((2, 10)), 4000.0)
