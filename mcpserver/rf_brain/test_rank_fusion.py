"""R69 验收测试：秩特征分布式校准免融合（对缩放/非线性不变的秩特征 + 专家乘积）。

覆盖：
  1. 秩不变性：单调非线性（γ≠1）下秩融合定位稳定，均值融合被失真
  2. 定位误差：未标定传感器融合定位误差较均值融合降 ≥30%
  3. rank_fusion / mean_fusion 边界行为
  4. 坏参数拒绝

运行：python -m pytest mcpserver/rf_brain/test_rank_fusion.py -q
"""
from __future__ import annotations

import numpy as np
import pytest

from . import rank_fusion as rf


def test_rank_invariant_to_nonlinearity():
    """秩融合对单调非线性不变：γ 变化时估计几乎不变。"""
    p = np.linspace(0.1, 0.9, 12)
    y1 = rf.synthesize_measurements(0.5, p, gamma=0.15, seed=0)
    y2 = rf.synthesize_measurements(0.5, p, gamma=1.0, seed=0)
    assert abs(rf.rank_fusion(p, y1) - rf.rank_fusion(p, y2)) < 0.05


def test_rank_fusion_reduces_error_over_30pct():
    """未标定传感器融合定位误差较均值融合降 ≥30%。"""
    r = rf.run_comparison(n_sensors=16, gamma=0.15, trials=300, seed=0)
    assert r["rank_error"] < r["mean_error"]
    assert r["reduction"] >= 0.30, f"误差降幅 {r['reduction']*100:.1f}% 未达 30%"


def test_mean_fusion_centroid():
    """均值融合 = 原始值加权质心（基本语义正确）。"""
    p = np.array([0.2, 0.5, 0.8])
    y = np.array([1.0, 1.0, 1.0])
    assert rf.mean_fusion(p, y) == pytest.approx(np.mean(p))
    # 高测量值传感器权重更大
    y2 = np.array([10.0, 1.0, 1.0])
    assert rf.mean_fusion(p, y2) < 0.5


def test_rejects_empty():
    with pytest.raises(ValueError):
        rf.synthesize_measurements(0.5, np.zeros(0))
