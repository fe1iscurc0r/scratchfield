"""R26 验收测试：信道模型偏差检测原型。

覆盖：
  1. 完整模型：含 trend+harmonic 的数据上残差低（正确建模）
  2. 偏差模型：残差显著高于完整模型（偏差被检出）
  3. 因果干预：移除 harmonic 后偏差模型残差骤降（定位偏差来源）
  4. 完整模型：干预前后残差均低（鲁棒、无偏差）

运行：python -m pytest mcpserver/rf_brain/prototypes/test_channel_bias_detect.py -q
"""
from __future__ import annotations

import pytest

from . import channel_bias_detect as cbd


@pytest.fixture(scope="module")
def d():
    return cbd.synthesize(400, seed=0)


def test_full_model_low_residual(d):
    assert cbd.residual(d["y"], cbd.fit_full(d)) < 1.0  # 噪声方差 ~0.09


def test_biased_model_high_residual(d):
    r_trend = cbd.residual(d["y"], cbd.fit_trend_only(d))
    r_full = cbd.residual(d["y"], cbd.fit_full(d))
    assert r_trend > 5 * r_full  # 偏差模型残差远大于完整模型


def test_intervention_reveals_bias(d):
    d_no = cbd.intervene_remove_harmonic(d)
    r_before = cbd.residual(d["y"], cbd.fit_trend_only(d))
    r_after = cbd.residual(d_no["y"], cbd.fit_trend_only(d_no))
    assert r_after < 0.2 * r_before  # 移除 harmonic 后偏差模型残差骤降


def test_full_model_robust_to_intervention(d):
    d_no = cbd.intervene_remove_harmonic(d)
    r1 = cbd.residual(d["y"], cbd.fit_full(d))
    r2 = cbd.residual(d_no["y"], cbd.fit_full(d_no))
    assert r1 < 1.0 and r2 < 1.0  # 完整模型在两种条件下都精确
