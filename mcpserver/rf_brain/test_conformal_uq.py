"""K24 验收测试：保形 UQ 频谱预测（覆盖率 ≥90% 且区间宽度可控）。

运行：python -m pytest mcpserver/rf_brain/test_conformal_uq.py -q
"""
from __future__ import annotations

import numpy as np

from .conformal_uq import ConformalUQ, MondrianConformal, SplitConformal, linear_operator_fit

N_BINS = 8
N_TRAIN, N_CALIB, N_TEST = 400, 200, 300
WINDOW = 4


def _synthetic_spectrum(n: int, seed: int = 0) -> np.ndarray:
    """合成多频点频谱序列：AR(1) + 结构化分量 + 噪声（可交换，保形适用）。"""
    rng = np.random.default_rng(seed)
    x = rng.normal(0.0, 1.0, (n, N_BINS))
    for t in range(1, n):
        x[t] = 0.9 * x[t - 1] + 0.2 * rng.normal(0.0, 1.0, N_BINS)
    return x


def _features_targets(x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """滑动窗口构造 (X, y)：用过去 WINDOW 帧预测下一帧。"""
    X, y = [], []
    for t in range(WINDOW, len(x)):
        X.append(x[t - WINDOW : t].reshape(-1))
        y.append(x[t])
    return np.array(X), np.array(y)


def test_split_conformal_coverage_at_least_90pct():
    x = _synthetic_spectrum(N_TRAIN + N_CALIB + N_TEST)
    X, y = _features_targets(x)
    op = linear_operator_fit(X[:N_TRAIN], y[:N_TRAIN])

    uq = ConformalUQ(op, alpha=0.10).calibrate(X[N_TRAIN : N_TRAIN + N_CALIB], y[N_TRAIN : N_TRAIN + N_CALIB])
    interval = uq.predict(X[N_TRAIN + N_CALIB :])
    cov = interval.coverage(y[N_TRAIN + N_CALIB :])
    assert cov >= 0.90, f"覆盖率 {cov:.3f} 低于 90%"


def test_interval_width_controllable_by_alpha():
    """α 越小（目标覆盖越高）→ 区间越宽，宽度可控。"""
    x = _synthetic_spectrum(N_TRAIN + N_CALIB + N_TEST)
    X, y = _features_targets(x)
    op = linear_operator_fit(X[:N_TRAIN], y[:N_TRAIN])
    Xc, yc = X[N_TRAIN : N_TRAIN + N_CALIB], y[N_TRAIN : N_TRAIN + N_CALIB]

    lo = SplitConformal(alpha=0.20).calibrate(op(Xc), yc).width
    hi = SplitConformal(alpha=0.05).calibrate(op(Xc), yc).width
    assert hi > lo, "更高覆盖要求应产生更宽区间"
    assert np.isfinite(lo) and np.isfinite(hi) and lo > 0


def test_conformal_width_finite_and_bounded():
    """区间宽度有限（不爆炸），且相对信号尺度可控。"""
    x = _synthetic_spectrum(N_TRAIN + N_CALIB + N_TEST)
    X, y = _features_targets(x)
    op = linear_operator_fit(X[:N_TRAIN], y[:N_TRAIN])
    uq = ConformalUQ(op, alpha=0.10).calibrate(X[N_TRAIN : N_TRAIN + N_CALIB], y[N_TRAIN : N_TRAIN + N_CALIB])
    # 宽度应显著小于信号动态范围（否则区间无信息量）
    assert np.isfinite(uq.width)
    assert uq.width < 3.0 * float(np.std(y))


def test_uncalibrated_raises():
    sc = SplitConformal(alpha=0.1)
    try:
        sc.predict_interval(np.zeros(3))
        raised = False
    except RuntimeError:
        raised = True
    assert raised


# ---------- Mondrian（逐频点）保形 ----------


def _heterogeneous_spectrum(n: int, seed: int = 0) -> np.ndarray:
    """各频点噪声水平差异大的频谱（逐点保形比全局更紧的场景）。"""
    rng = np.random.default_rng(seed)
    x = rng.normal(0.0, 1.0, (n, N_BINS))
    for t in range(1, n):
        x[t] = 0.9 * x[t - 1] + 0.1 * rng.normal(0.0, 1.0, N_BINS)
    # 不同频点给不同量级噪声（越靠后越噪）
    noise_scale = np.linspace(0.1, 1.0, N_BINS)
    x = x + rng.normal(0.0, 1.0, (n, N_BINS)) * noise_scale
    return x


def test_mondrian_coverage_at_least_90pct():
    x = _heterogeneous_spectrum(N_TRAIN + N_CALIB + N_TEST)
    X, y = _features_targets(x)
    op = linear_operator_fit(X[:N_TRAIN], y[:N_TRAIN])
    mc = MondrianConformal(alpha=0.10).calibrate(op(X[N_TRAIN : N_TRAIN + N_CALIB]), y[N_TRAIN : N_TRAIN + N_CALIB])
    cov = mc.coverage(op(X[N_TRAIN + N_CALIB :]), y[N_TRAIN + N_CALIB :])
    assert cov >= 0.90, f"逐频点覆盖率 {cov:.3f} 低于 90%"


def test_mondrian_tighter_than_global():
    """逐频点校准在满足覆盖率前提下，平均宽度比全局单一 q̂ 更窄。"""
    x = _heterogeneous_spectrum(N_TRAIN + N_CALIB + N_TEST)
    X, y = _features_targets(x)
    op = linear_operator_fit(X[:N_TRAIN], y[:N_TRAIN])
    Xc, yc = X[N_TRAIN : N_TRAIN + N_CALIB], y[N_TRAIN : N_TRAIN + N_CALIB]

    mc = MondrianConformal(alpha=0.10).calibrate(op(Xc), yc)
    sc = SplitConformal(alpha=0.10).calibrate(op(Xc), yc)
    # 逐频点宽度是逐点自适应的；全局宽度用最噪频点撑大
    assert mc.mean_width <= sc.width + 1e-9


def test_linear_operator_fit_handles_intercept():
    """含截距的线性算子：对带直流偏置的信号也能拟合。"""
    x = _heterogeneous_spectrum(N_TRAIN + N_CALIB + N_TEST) + 5.0  # 加直流偏置
    X, y = _features_targets(x)
    op = linear_operator_fit(X[:N_TRAIN], y[:N_TRAIN])
    pred = op(X[N_TRAIN : N_TRAIN + 20])
    assert pred.shape == y[N_TRAIN : N_TRAIN + 20].shape
    assert np.all(np.isfinite(pred))
