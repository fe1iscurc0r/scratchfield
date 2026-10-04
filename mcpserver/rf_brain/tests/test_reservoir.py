"""D-02 验收测试：reservoir computing 漂移补偿（≥6 用例）。

覆盖：
  1. reservoir 生成（固定种子可复现、谱半径归一）
  2. reservoir.run 状态矩阵形状 / 输入维度校验
  3. 读出层训练（岭回归拟合线性/正弦目标，误差低）
  4. 漂移模拟（offset 模式 = 常量偏置；漂移分量 = drifted - clean）
  5. 补偿后误差下降（配对补偿 MSE 显著小于漂移后）
  6. 参数扰动鲁棒（不同 seed / ridge，补偿仍有效）
  7. 读出层在线自适应更新（RLS 后误差进一步下降）
  8. 与 D-01 集成（去噪 → RC 补偿端到端）

运行：python -m pytest mcpserver/rf_brain/tests/test_reservoir.py -q
"""
from __future__ import annotations

import numpy as np
import pytest

from mcpserver.rf_brain.denoise import bench, drift, reservoir
from mcpserver.rf_brain.denoise import eval as ev

N = 2000
SR = 1000.0


def _slow_signal(n: int = N, seed: int = 0) -> np.ndarray:
    """慢变传感器信号（2 Hz 主频 + 0.5 Hz 次频，保证标定窗内覆盖多个周期）。"""
    t = np.arange(n) / SR
    return np.sin(2 * np.pi * 2.0 * t) + 0.3 * np.sin(2 * np.pi * 0.5 * t)


# ---------- reservoir 生成 / 状态 ----------

def test_reservoir_generation_reproducible() -> None:
    """固定种子可复现；不同种子产生不同矩阵。"""
    a = reservoir.Reservoir(n_units=32, seed=7)
    b = reservoir.Reservoir(n_units=32, seed=7)
    c = reservoir.Reservoir(n_units=32, seed=8)
    assert np.allclose(a.W, b.W) and np.allclose(a.W_in, b.W_in)
    assert not np.allclose(a.W, c.W)


def test_reservoir_spectral_radius() -> None:
    """循环矩阵谱半径 ≈ 目标值（< 1）。"""
    rc = reservoir.Reservoir(n_units=32, spectral_radius=0.9, seed=1)
    rho = float(np.max(np.abs(np.linalg.eigvals(rc.W))))
    assert abs(rho - 0.9) < 1e-6
    assert rho < 1.0


def test_reservoir_run_shapes_and_validation() -> None:
    """run 返回 (T, n_units)；维度不匹配抛 ValueError。"""
    rc = reservoir.Reservoir(n_units=16, input_dim=1, seed=2)
    states = rc.run(_slow_signal(100))
    assert states.shape == (100, 16)
    assert np.all(np.isfinite(states))
    with pytest.raises(ValueError):
        rc.run(np.zeros((10, 3)))  # 输入维度 3 != input_dim 1


# ---------- 读出层训练 ----------

def test_readout_training_low_error() -> None:
    """读出层拟合慢变正弦目标，预测误差低。"""
    x = _slow_signal(800)
    rc = reservoir.Reservoir(n_units=64, input_dim=1, seed=3)
    states = rc.run(x)
    rc.train_readout(states, x, ridge=1e-6)
    pred = rc.predict(states)
    assert pred.shape == x.shape
    assert ev.mse(x, pred) < 0.01


def test_predict_without_training_raises() -> None:
    """未训练读出层直接 predict 抛 RuntimeError。"""
    rc = reservoir.Reservoir(n_units=16, seed=4)
    with pytest.raises(RuntimeError):
        rc.predict(np.zeros((10, 16)))


# ---------- 漂移模拟 / 补偿 ----------

def test_simulate_drift_offset_is_constant() -> None:
    """offset 模式：漂移分量 ≈ 常量偏置。"""
    clean = _slow_signal(500)
    drifted, drift_comp = drift.simulate_drift(clean, mode="offset", offset=0.5)
    assert np.allclose(drifted, clean + 0.5)
    assert np.allclose(drift_comp, 0.5)


def test_compensation_reduces_error() -> None:
    """配对补偿：补偿后 MSE 显著小于漂移后。"""
    clean = _slow_signal(N)
    drifted, _ = drift.simulate_drift(clean, mode="offset_gain_baseline",
                                      offset=0.2, gain=1.1, baseline_amplitude=0.15, seed=5)
    split = N // 3
    comp = drift.DriftCompensator(reservoir.Reservoir(n_units=64, input_dim=1, seed=5))
    comp.fit(drifted[:split], clean[:split])
    compensated = comp.compensate(drifted)
    m = bench.drift_metrics(clean, drifted, compensated)
    assert m["mse_after"] < m["mse_before"] * 0.5
    assert m["reduction_ratio"] > 1.0


def test_parameter_perturbation_robust() -> None:
    """参数扰动鲁棒：不同 seed 与 ridge，补偿仍有效降低误差。"""
    clean = _slow_signal(N)
    drifted, _ = drift.simulate_drift(clean, mode="offset_gain_baseline",
                                      offset=0.2, gain=1.1, baseline_amplitude=0.15, seed=6)
    split = N // 3
    for rc_seed, ridge in ((6, 1e-6), (99, 1e-4), (6, 1e-2)):
        comp = drift.DriftCompensator(reservoir.Reservoir(n_units=64, input_dim=1, seed=rc_seed),
                                      ridge=ridge)
        comp.fit(drifted[:split], clean[:split])
        compensated = comp.compensate(drifted)
        m = bench.drift_metrics(clean, drifted, compensated)
        assert m["mse_after"] < m["mse_before"], f"seed={rc_seed} ridge={ridge} 未降低误差"


def test_online_update_improves() -> None:
    """RLS 在线自适应更新后，补偿误差进一步下降。"""
    clean = _slow_signal(N)
    drifted, _ = drift.simulate_drift(clean, mode="offset_gain_baseline",
                                      offset=0.2, gain=1.1, baseline_amplitude=0.15, seed=7)
    split = N // 3
    comp = drift.DriftCompensator(reservoir.Reservoir(n_units=64, input_dim=1, seed=7))
    comp.fit(drifted[:split], clean[:split])
    compensated_before = comp.compensate(drifted)
    # 用剩余标定段做在线更新
    comp.update(drifted[split:2 * split], clean[split:2 * split])
    compensated_after = comp.compensate(drifted)
    mse_before = ev.mse(clean, compensated_before)
    mse_after = ev.mse(clean, compensated_after)
    assert mse_after <= mse_before


def test_integration_denoise_then_compensate() -> None:
    """与 D-01 集成：去噪 → RC 补偿端到端跑通并降低整体误差。"""
    e = bench.end_to_end(sample_rate=SR, n=1500, seed=0)
    assert e["denoise"]["gain_db"] > 0.0
    assert e["drift"]["mse_after"] < e["drift"]["mse_before"]
    assert e["compensated"].shape == e["drifted"].shape
