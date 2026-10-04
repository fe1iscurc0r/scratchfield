"""PF054 授粉落地：电磁孪生稀疏重建（eess.SP 2608.20813 / 20846）

授粉点：电磁孪生（EM Twin）= 用**稀疏信道证据**重建无线状态——少量测量/探测
样本，利用信号在合适基下的稀疏性（点散射体、少数径、频谱空洞）做压缩感知
重建，回答通信查询（"此处信道如何？"）。

本模块（纯 numpy，复用 cs_frontend 的测量矩阵）：
  - ISTA（迭代软阈值）：凸松弛类稀疏恢复，与 PF022 的 OMP（贪婪类）互补
  - 支撑集评估：恢复支撑 vs 真支撑（散射体定位正确率）
  - PSNR 评估：重建质量
  - 二维电磁场演示：稀疏点散射体场从少量测量重建（对应电磁孪生"稀疏证据→场"）

验收：一维稀疏信号 M≈4K 时 PSNR > 25dB / 支撑集准确率 > 90%；
     二维场 NcT≥8 恢复 NCC ≥ 0.9；pytest 全绿。
"""
from __future__ import annotations

import numpy as np

from mcpserver.rf_brain.cs_frontend import measurement_matrix, ncc

# ---------------------------------------------------------------------------
# ISTA（迭代软阈值）稀疏恢复
# ---------------------------------------------------------------------------

def soft_threshold(x: np.ndarray, tau: float) -> np.ndarray:
    """软阈值（ISTA 的收缩算子）：sign(x)·max(|x|-τ, 0)。"""
    return np.sign(x) * np.maximum(np.abs(x) - float(tau), 0.0)


def ista_recover(y: np.ndarray, a: np.ndarray, k: int | None = None,
                 *, lam: float | None = None, max_iter: int = 500,
                 tol: float = 1e-5) -> np.ndarray:
    """ISTA 稀疏恢复：x = argmin ½||Ax-y||² + λ||x||₁。

    步长取 1/σ_max(A)²（Lipschitz 常数保证收敛）。
    λ 缺省时按 k-稀疏度启发式给定（k 也缺省时用测量数/3）。
    """
    y = np.asarray(y, dtype=float)
    a = np.asarray(a, dtype=float)
    if y.ndim != 1:
        raise ValueError("测量必须为一维")
    if a.shape[0] != y.size:
        raise ValueError(f"测量数 {y.size} 与矩阵行数 {a.shape[0]} 不一致")

    n = a.shape[1]
    if k is None:
        k = max(int(np.ceil(y.size / 3.0)), 1)
    if lam is None:
        # 启发式：λ 与最大相关度成比例，随测量数下降（更多测量 → 更小正则）
        lam = float(0.05 * np.max(np.abs(a.T @ y)) / max(np.sqrt(k), 1.0)
                    * np.sqrt(float(y.size) / n))
    step = 1.0 / (np.linalg.norm(a, 2) ** 2 + 1e-12)

    x = np.zeros(n)
    at_y = a.T @ y
    at_a = a.T @ a
    for _ in range(int(max_iter)):
        grad = at_a @ x - at_y
        x_new = soft_threshold(x - step * grad, float(step * lam))
        if float(np.linalg.norm(x_new - x)) <= tol * float(np.linalg.norm(x) + 1e-12):
            x = x_new
            break
        x = x_new
    # 两步去偏（经典 CS 技巧）：取 top-k 支撑做 LS，消除 L1 偏置
    k_est = min(int(k), n)
    support = np.argsort(np.abs(x))[-k_est:]
    support = support[np.abs(x[support]) > tol]
    if support.size:
        x_ls, *_ = np.linalg.lstsq(a[:, support], y, rcond=None)
        x = np.zeros(n)
        x[support] = x_ls
    return x


# ---------------------------------------------------------------------------
# 支撑集 / 质量评估
# ---------------------------------------------------------------------------

def support_accuracy(x_true: np.ndarray, x_hat: np.ndarray,
                     tol: float = 1e-3, k: int | None = None) -> float:
    """支撑集准确率：恢复支撑与真支撑的 Jaccard 相似度。

    真支撑 = |x|>tol；恢复支撑 = 前 k 大系数（k 缺省时用真支撑数）。
    用"前 k 大"而非绝对阈值：ISTA 的 L1 偏置会留下大量小系数，
    绝对阈值会把这些杂散都算进支撑，虚低准确率。
    """
    x_true = np.asarray(x_true, dtype=float)
    x_hat = np.asarray(x_hat, dtype=float)
    if x_true.size != x_hat.size or x_true.size == 0:
        return 0.0
    s_true = set(np.flatnonzero(np.abs(x_true) > tol).tolist())
    if k is None:
        k = len(s_true)
    k = max(int(k), 1)
    s_hat = set(np.argsort(np.abs(x_hat))[-k:].tolist())
    if not s_true:
        return 1.0 if not s_hat else 0.0
    inter = len(s_true & s_hat)
    union = len(s_true | s_hat)
    return float(inter) / float(union) if union else 1.0


def psnr_db(x_true: np.ndarray, x_hat: np.ndarray,
            peak: float | None = None) -> float:
    """峰值信噪比（dB）：20log10(peak / RMSE)。"""
    x_true = np.asarray(x_true, dtype=float)
    x_hat = np.asarray(x_hat, dtype=float)
    if x_true.size == 0 or x_hat.size != x_true.size:
        return 0.0
    if peak is None:
        peak = float(np.max(np.abs(x_true))) if x_true.size else 1.0
    rmse = float(np.sqrt(np.mean((x_true - x_hat) ** 2)))
    if rmse < 1e-12:
        return 99.0
    return 20.0 * np.log10(max(peak, 1e-12) / rmse)


# ---------------------------------------------------------------------------
# 二维电磁场演示（稀疏点散射体场）
# ---------------------------------------------------------------------------

def sparse_field_2d(size: int = 32, n_scatterers: int = 4, *,
                    seed: int = 0, gaussian: bool = False) -> np.ndarray:
    """合成二维稀疏电磁场：点散射体（对应电磁孪生的稀疏证据场景）。

    gaussian=True 时给散射体加高斯弥散（模拟有限尺寸散射体）；缺省为
    真点目标（稀疏场重建的基准场景，对应论文点目标模型）。
    """
    rng = np.random.default_rng(seed)
    field = np.zeros((size, size))
    idx = rng.choice(size * size, size=n_scatterers, replace=False)
    if not gaussian:
        for i in idx:
            field.ravel()[i] = 1.0 + 0.5 * rng.random()
        return field
    for i in idx:
        r, c = divmod(int(i), size)
        rr, cc = np.mgrid[0:size, 0:size]
        field += np.exp(-((rr - r) ** 2 + (cc - c) ** 2) / 2.0)
    return field


def measure_field_2d(field: np.ndarray, n_measurements: int, *,
                     seed: int = 0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """二维场压缩测量：随机投影测量（每测量覆盖全场，天然命中稀疏成分）。

    对应电磁孪生"稀疏证据"：传感器/探测对全场做随机加权（硬件上可用
    随机相位调制实现）。返回 (测量值, 测量矩阵行化索引保留, 采样率说明)。
    """
    field = np.asarray(field, dtype=float)
    if field.ndim != 2:
        raise ValueError("必须为二维场")
    h, w = field.shape
    n = h * w
    rng = np.random.default_rng(seed)
    a = rng.choice(np.array([-1.0, 1.0]), size=(n_measurements, n))
    y = a @ field.ravel()
    return y, a, np.full((h, w), float(n_measurements) / n)


def reconstruct_field_2d(values: np.ndarray, meas: np.ndarray,
                         shape: tuple[int, int], *, k_est: int | None = None,
                         max_iter: int = 800) -> np.ndarray:
    """二维场稀疏重建：ISTA 从随机投影测量恢复（点散射体场在空间域稀疏）。

    values = 测量值，meas = 测量矩阵 (m, n)。完整电磁孪生语义：稀疏证据
    → 稀疏场。
    """
    h, w = shape
    n = h * w
    if k_est is None:
        k_est = max(int(n * 0.005), 1)   # 默认 0.5% 稀疏度
    a = np.asarray(meas, dtype=float)
    if a.ndim != 2 or a.shape[1] != n:
        raise ValueError(f"测量矩阵须为 (m, {n})")
    lam = float(0.05 * np.max(np.abs(a.T @ values)) / max(np.sqrt(k_est), 1.0))
    x = ista_recover(np.asarray(values, dtype=float), a, k=k_est,
                     lam=lam, max_iter=max_iter)
    return x.reshape(h, w)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    n, k = 256, 8
    rng = np.random.default_rng(3)
    x = np.zeros(n)
    x[rng.choice(n, k, replace=False)] = rng.standard_normal(k) * 2.0
    for nct in (8, 4):
        m = max(n // nct, k * 2)
        a = measurement_matrix(n, m, seed=1)
        y = a @ x
        x_hat = ista_recover(y, a, k=k)
        print(f"[1D] NcT={nct} (M={m}): PSNR={psnr_db(x, x_hat):.1f} dB  "
              f"支撑准确率={support_accuracy(x, x_hat):.2%}  NCC={ncc(x, x_hat):.3f}")

    field = sparse_field_2d(32, 4, seed=0)
    vals, meas, info = measure_field_2d(field, 128, seed=1)   # 12.5% 采样
    rec = reconstruct_field_2d(vals, meas, field.shape)
    print(f"[2D] 稀疏场重建: 采样率={128/(32*32):.1%}, "
          f"NCC={ncc(field.ravel(), rec.ravel()):.3f}, "
          f"PSNR={psnr_db(field.ravel(), rec.ravel()):.1f} dB, "
          f"支撑准确率={support_accuracy(field.ravel(), rec.ravel(), k=4):.2%}")


if __name__ == "__main__":
    main()
