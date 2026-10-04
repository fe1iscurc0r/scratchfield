"""R56 验收测试：轨迹自适应 conformal 信道预测（给 R08 补覆盖率保证）。

覆盖：
  1. 覆盖率：合成信道测试集覆盖率 ≥90%
  2. 区间宽度可控：target_coverage 越高区间越宽
  3. 轨迹自适应：每步分位数沿预测步递增（后步误差大 → 区间更宽）
  4. 坏参数：未校准即预测 / horizon 越界 / target_coverage 越界

运行：python -m pytest mcpserver/rf_brain/test_conformal_channel_pred.py -q
"""
from __future__ import annotations

import numpy as np
import pytest

from . import conformal_channel_pred as ccp

N = 6000
WARMUP, HORIZON = 20, 20


def _measure_coverage(cp: ccp.ConformalChannelPredictor, test: np.ndarray, stride: int = 20) -> float:
    covs = []
    for start in range(0, test.size - WARMUP - HORIZON, stride):
        init = test[start:start + WARMUP]
        truth = test[start + WARMUP:start + WARMUP + HORIZON]
        if truth.size < HORIZON:
            break
        covs.append(cp.predict_interval(init, HORIZON).coverage(truth))
    return float(np.mean(covs))


def _train_and_calibrate(seed: int, target_coverage: float) -> tuple[ccp.ConformalChannelPredictor, np.ndarray]:
    csi = ccp.synthesize_csi(N, num_paths=3, seed=seed)
    train, cal, test = csi[:2000], csi[2000:4000], csi[4000:]
    cp = ccp.ConformalChannelPredictor(seed=seed)
    cp.train(train)
    cp.calibrate(cal, horizon=HORIZON, target_coverage=target_coverage, warmup=WARMUP, stride=5)
    return cp, test


def test_coverage_at_least_90pct():
    """合成信道：target_coverage=0.9 时测试集覆盖率 ≥90%。"""
    cp, test = _train_and_calibrate(seed=0, target_coverage=0.9)
    cov = _measure_coverage(cp, test)
    assert cov >= 0.90, f"覆盖率 {cov:.3f} < 0.90"


def test_interval_width_controllable():
    """区间宽度可控：target_coverage 越高，区间越宽。"""
    cp_lo, _ = _train_and_calibrate(seed=0, target_coverage=0.8)
    cp_hi, _ = _train_and_calibrate(seed=0, target_coverage=0.95)
    init = ccp.synthesize_csi(200, num_paths=3, seed=99)[:WARMUP]
    w_lo = float(cp_lo.predict_interval(init, HORIZON).width.mean())
    w_hi = float(cp_hi.predict_interval(init, HORIZON).width.mean())
    assert w_hi > w_lo, f"高覆盖率区间({w_hi:.2f})未宽于低覆盖率({w_lo:.2f})"


def test_trajectory_adaptive_quantiles_grow():
    """轨迹自适应：每步分位数沿预测步递增（后步误差更大）。"""
    cp, _ = _train_and_calibrate(seed=0, target_coverage=0.9)
    q = cp._quantiles
    assert q.shape == (HORIZON,)
    assert q[0] < q[-1]  # 首步区间窄、末步区间宽


def test_rejects_bad_usage():
    csi = ccp.synthesize_csi(400, num_paths=3, seed=0)
    cp = ccp.ConformalChannelPredictor(seed=0)
    with pytest.raises(RuntimeError):
        cp.predict_interval(csi[:WARMUP], 5)  # 未校准
    cp.train(csi[:200])
    with pytest.raises(ValueError):
        cp.calibrate(csi[200:], horizon=10, target_coverage=1.5)
    cp.calibrate(csi[200:], horizon=10, target_coverage=0.9, warmup=20, stride=5)
    with pytest.raises(ValueError):
        cp.predict_interval(csi[:WARMUP], 11)  # 超过校准 horizon
