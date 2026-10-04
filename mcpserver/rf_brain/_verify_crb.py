"""验证 CRB 公式：数值 FIM vs ML 估计蒙特卡洛方差对拍。"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from mcpserver.rf_brain.doa import estimate_doa, synthesize_snapshots, ula_steering_vector

M, D_NORM, K, SNR_DB, THETA = 8, 0.5, 256, 30.0, 30.0
SNR_LIN = 10 ** (SNR_DB / 10.0)


def steering_deriv(theta_deg, n_elements, d_norm):
    theta = np.deg2rad(theta_deg)
    m = np.arange(n_elements, dtype=float)
    a = np.exp(-2j * np.pi * d_norm * m * np.sin(theta))
    return (-2j * np.pi * d_norm * np.cos(theta) * m) * a


def numeric_fim(n_snapshot, snr_linear, theta_deg, coeff=1.0):
    a = ula_steering_vector([theta_deg], M, D_NORM).ravel()
    ap = steering_deriv(theta_deg, M, D_NORM)
    sig2 = 1.0
    noise2 = sig2 / snr_linear
    R = sig2 * np.outer(a, a.conj()) + noise2 * np.eye(M)
    dR = sig2 * (np.outer(ap, a.conj()) + np.outer(a, ap.conj()))
    Rinv = np.linalg.inv(R)
    fim = n_snapshot * coeff * np.real(np.trace(Rinv @ dR @ Rinv @ dR))
    return fim


def ml_estimate(x, grid):
    """ML 估计：最大化 a^H R_est a（确定性模型近似）。"""
    cov = x @ x.conj().T / x.shape[1]
    A = ula_steering_vector(grid, M, D_NORM)
    vals = np.real(np.sum(A.conj() * (cov @ A), axis=0))
    return float(grid[np.argmax(vals)])


if __name__ == "__main__":
    grid = np.linspace(-90, 90, 18001)
    # 1) 数值 FIM（两种系数约定）
    for coeff in (1.0, 2.0):
        fim = numeric_fim(K, SNR_LIN, THETA, coeff)
        print(f"coeff={coeff}: FIM={fim:.3e} → σ(°)={np.rad2deg(1/np.sqrt(fim)):.6f}")
    # 2) ML 蒙特卡洛方差
    errs_ml, errs_music = [], []
    for i in range(500):
        x = synthesize_snapshots([THETA], n_elements=M, n_snapshot=K, snr_db=SNR_DB, seed=5000 + i)
        errs_ml.append(ml_estimate(x, grid) - THETA)
        errs_music.append(float(estimate_doa(x, n_sources=1).doas_deg[0]) - THETA)
    print(f"ML    RMSE(°)={np.sqrt(np.mean(np.square(errs_ml))):.6f}")
    print(f"MUSIC RMSE(°)={np.sqrt(np.mean(np.square(errs_music))):.6f}")
