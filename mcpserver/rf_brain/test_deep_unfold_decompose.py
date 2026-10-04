"""R52 验收测试：IDSD 深度展开信号分解（替代固定阈值 CFAR）。

覆盖：
  1. soft_threshold：软阈值收缩语义
  2. DeepUnfoldDecomposer：合成干扰场景分量分离精度较 CFAR 提升 ≥20%
  3. 参数量 <100K（ESP32 毫秒级窗口可行）
  4. Nesterov 加速：FISTA 比 ISTA 更少层数收敛
  5. recon_snr / 坏参数拒绝

运行：python -m pytest mcpserver/rf_brain/test_deep_unfold_decompose.py -q
"""
from __future__ import annotations

import numpy as np
import pytest

from . import deep_unfold_decompose as dud

N = 256


def _synthetic_interference(n: int = N, seed: int = 7,
                            n_components: int = 8, amp: float = 2.0,
                            floor: float = 0.8, sigma: float = 0.25):
    """合成干扰场景：稀疏信号分量 + 恒定宽带干扰底 + 白噪声。

    返回 (x, s_true)。s_true 为稀疏非负分量（「信号」），floor 为宽带干扰底
    （非稀疏，恒定），CFAR 检测后保留原始幅度 → 把 floor 也带进恢复分量，
    IDSD 稀疏先验则把 floor 压进残差。
    """
    rng = np.random.default_rng(seed)
    s_true = np.zeros(n, dtype=float)
    positions = rng.choice(n, size=n_components, replace=False)
    s_true[positions] = amp
    x = s_true + floor + sigma * rng.standard_normal(n)
    return x, s_true


# ============ 1. 软阈值 ============


def test_soft_threshold():
    z = np.array([-3.0, -0.5, 0.0, 0.5, 3.0])
    out = dud.soft_threshold(z, 1.0)
    assert np.allclose(out, [-2.0, 0.0, 0.0, 0.0, 2.0])


# ============ 2. 分量分离精度：IDSD vs CFAR ============


def test_idsd_beats_cfar_component_separation():
    """合成干扰场景分量分离精度较 CFAR 提升 ≥20%（重建 SNR 线性比 ≥1.2）。"""
    x, s_true = _synthetic_interference(seed=7)
    # IDSD：软阈值估计（λ 高于干扰底 0.8 + 噪声，低于信号幅度 2.0）
    dec = dud.DeepUnfoldDecomposer(n_layers=8, lambd=1.1, mu=1.0)
    s_id = dec.decompose(x).signal
    # CFAR：固定阈值检测，恢复分量 = 检测点原始幅度
    s_cfar = dud.cfar_component(x, k=3.0)

    snr_id = dud.recon_snr(s_true, s_id)
    snr_cfar = dud.recon_snr(s_true, s_cfar)
    assert snr_id >= 1.2 * snr_cfar, (
        f"IDSD SNR {snr_id:.2f} 未较 CFAR {snr_cfar:.2f} 提升 ≥20%"
    )


def test_idsd_recovers_support_without_false_alarm_on_floor():
    """稀疏分量被正确保留，宽带干扰底被压入残差（不产生大面积假阳性）。"""
    x, s_true = _synthetic_interference(seed=7)
    dec = dud.DeepUnfoldDecomposer(n_layers=8, lambd=1.1, mu=1.0)
    res = dec.decompose(x)
    # 8 个信号分量应全部出现在恢复分量中
    assert int(np.count_nonzero(res.signal > 0.5)) >= 8
    # 残差 = 干扰底 + 噪声（均值约等于 floor）
    assert abs(float(res.residual.mean()) - 0.8) < 0.1


# ============ 3. 参数量 / 收敛性 ============


def test_params_under_limit():
    assert dud.DeepUnfoldDecomposer(n_layers=8).num_params < 100_000
    assert dud.DeepUnfoldDecomposer(n_layers=100).num_params < 100_000


def test_decompose_converges_and_residual_sums():
    x, _ = _synthetic_interference(seed=7)
    dec = dud.DeepUnfoldDecomposer(n_layers=200, lambd=1.1, mu=1.0, tol=1e-6)
    res = dec.decompose(x)
    assert res.signal.shape == x.shape
    assert res.residual.shape == x.shape
    assert np.allclose(res.signal + res.residual, x)  # identity 字典恒等式


# ============ 4. Nesterov 加速 ============


def _lasso_cost(x: np.ndarray, s: np.ndarray, d: np.ndarray | None, lambd: float) -> float:
    """LASSO 目标：0.5||x - D·s||² + λ||s||₁（identity 时 D=None）。"""
    r = x - s if d is None else x - d @ s
    return 0.5 * float(np.dot(r, r)) + lambd * float(np.abs(s).sum())


def test_nesterov_accelerates_convergence():
    """Nesterov 动量（FISTA）在过完备字典下比 ISTA 更快逼近同一最优解。

    过完备字典使数据项 DᵀD 奇异（弱凸），ISTA 子线性收敛 O(1/k)，
    FISTA 外推 O(1/k²)——固定 K=100 层时 FISTA 目标值严格更低。
    """
    rng = np.random.default_rng(0)
    n, m = 128, 256
    D = rng.standard_normal((n, m)) / np.sqrt(n)
    x = rng.standard_normal(n)
    lam = 0.2
    mu = 1.0 / float(np.linalg.norm(D, 2) ** 2)  # 1 / Lipschitz 常数

    ista = dud.DeepUnfoldDecomposer(n_layers=100, lambd=lam, mu=mu, nesterov=False, tol=0.0, dictionary=D)
    fista = dud.DeepUnfoldDecomposer(n_layers=100, lambd=lam, mu=mu, nesterov=True, tol=0.0, dictionary=D)
    c_ista = _lasso_cost(x, ista.decompose(x).signal, D, lam)
    c_fista = _lasso_cost(x, fista.decompose(x).signal, D, lam)
    assert c_fista < c_ista, f"Nesterov 未加速：FISTA {c_fista:.6f} vs ISTA {c_ista:.6f}"


# ============ 5. 坏参数 / 边界 ============


def test_recon_snr_perfect_and_bad():
    s = np.array([1.0, 2.0, 3.0])
    assert dud.recon_snr(s, s) == float("inf")
    assert dud.recon_snr(s, np.zeros(3)) < dud.recon_snr(s, s * 0.9)


def test_rejects_bad_params():
    with pytest.raises(ValueError):
        dud.DeepUnfoldDecomposer(n_layers=0)
    with pytest.raises(ValueError):
        dud.DeepUnfoldDecomposer(lambd=-1.0)
    with pytest.raises(ValueError):
        dud.DeepUnfoldDecomposer(mu=0.0)
    with pytest.raises(ValueError):
        dud.DeepUnfoldDecomposer(dictionary=np.ones(10))  # 非 2D 字典
    with pytest.raises(ValueError):
        dud.DeepUnfoldDecomposer().decompose(np.zeros(0))
