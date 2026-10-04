"""Bern2Edge Bernstein 多项式网络最小原型（K19 · ESP32 端侧评估）。

依据 docs/paper-round2-2026-08-30/digests/digest-g1-2-2026-08-30.md 中
2608.20497v1（Bern2Edge：Bernstein 多项式激活 LUT 边缘部署，FPGA 99.8% 延迟减少）。

Bernstein 多项式网络：特征映射用 Bernstein 基
    B_{i,n}(x) = C(n,i) · x^i · (1-x)^{n-i},  x ∈ [0,1]
其性质对端侧非常友好：
  - 有界（0 ≤ B_{i,n}(x) ≤ 1），天然适配定点/LUT；
  - 单位分解（Σ_i B_{i,n}(x) = 1），数值稳定；
  - 全多项式，可在离线阶段对量化后的 x 逐点查表，运行时无 exp/pow。

与 OTA-ELM（tools/elm_train.py 的随机隐层 + 伪逆 + sigmoid LUT 思路）对比：
  - 参数量 / 精度 / 部署预算（LUT 大小 + 每推理 MACs）

原型（numpy）用一维函数逼近做诚实对比，非真机（按 spec：只出方案/原型 + 预算表）。

运行：
  python tools/bern2edge.py
"""
from __future__ import annotations

import math

import numpy as np

# LUT 量化点数（与 OTA-ELM 的 256 级 sigmoid LUT 对齐）
LUT_BINS = 256


# ---------- Bernstein 多项式网络 ----------

def bernstein_basis(n: int, x: np.ndarray) -> np.ndarray:
    """Bernstein 基 B_{i,n}(x)，i=0..n。x: (m,) → 返回 (n+1, m)。"""
    x = np.clip(x, 0.0, 1.0)
    B = np.zeros((n + 1, x.shape[0]))
    for i in range(n + 1):
        c = math.comb(n, i)
        B[i] = c * (x ** i) * ((1.0 - x) ** (n - i))
    return B


def bernstein_fit(x: np.ndarray, y: np.ndarray, n: int) -> np.ndarray:
    """最小二乘拟合：beta s.t. Σ_i beta_i B_{i,n}(x) ≈ y。"""
    B = bernstein_basis(n, x)  # (n+1, m)
    return np.linalg.lstsq(B.T, y, rcond=None)[0]


def bernstein_predict(beta: np.ndarray, n: int, x: np.ndarray) -> np.ndarray:
    return bernstein_basis(n, x).T @ beta


def bernstein_lut(n: int, bins: int = LUT_BINS) -> np.ndarray:
    """离线生成 Bernstein 基 LUT：(n+1, bins)，运行时查表即可。"""
    xq = np.linspace(0.0, 1.0, bins)
    return bernstein_basis(n, xq)


# ---------- OTA-ELM（最小复现，用于对比） ----------

def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-z))


def elm_fit(x: np.ndarray, y: np.ndarray, nh: int, seed: int = 0):
    """随机隐层 + 伪逆输出（ELM）。x:(m,) → 返回 (W,b,beta)。"""
    rng = np.random.default_rng(seed)
    W = rng.normal(0, 1.0, (1, nh))
    b = rng.normal(0, 1.0, (nh,))
    H = _sigmoid(x.reshape(-1, 1) @ W + b)
    beta = np.linalg.pinv(H) @ y
    return W, b, beta


def elm_predict(W: np.ndarray, b: np.ndarray, beta: np.ndarray, x: np.ndarray) -> np.ndarray:
    H = _sigmoid(x.reshape(-1, 1) @ W + b)
    return H @ beta


# ---------- 对比 ----------

def compare(seed: int = 0) -> dict:
    """在目标函数上对比 Bernstein 网络与 OTA-ELM 的参数/精度/部署预算。"""
    rng = np.random.default_rng(seed)
    # 目标函数：平滑非线性响应（rf 相关：一个高斯峰 + 线性趋势）
    x = np.linspace(0.0, 1.0, 200)
    y = 0.8 * np.exp(-((x - 0.4) ** 2) / 0.02) + 0.3 * x

    n = 10          # Bernstein 阶数
    nh = 12         # ELM 隐层宽度（调到与 Bernstein 相近容量）

    beta_b = bernstein_fit(x, y, n)
    y_b = bernstein_predict(beta_b, n, x)
    W, b, beta_e = elm_fit(x, y, nh, seed)
    y_e = elm_predict(W, b, beta_e, x)

    mse_b = float(np.mean((y_b - y) ** 2))
    mse_e = float(np.mean((y_e - y) ** 2))

    # 参数量：Bernstein = n+1 个系数；ELM = W(1×nh) + b(nh) + beta(nh) = 3·nh
    params_b = n + 1
    params_e = 3 * nh

    # LUT 大小（字节）：Bernstein = (n+1)×bins；ELM = sigmoid bins
    lut_b = (n + 1) * LUT_BINS
    lut_e = LUT_BINS

    # 每推理 MACs：Bernstein = n+1（查表后累加）；ELM = 2·nh（隐层 + 输出）
    macs_b = n + 1
    macs_e = 2 * nh

    return {
        "bernstein": {"mse": mse_b, "params": params_b, "lut": lut_b, "macs": macs_b},
        "elm": {"mse": mse_e, "params": params_e, "lut": lut_e, "macs": macs_e},
    }


def main() -> int:
    c = compare()
    b, e = c["bernstein"], c["elm"]
    print("=== Bern2Edge vs OTA-ELM（1D 函数逼近） ===")
    print(f"{'':<14}{'Bernstein':>12}{'OTA-ELM':>12}")
    print(f"{'精度 MSE':<14}{b['mse']:>12.6f}{e['mse']:>12.6f}")
    print(f"{'参数量':<14}{b['params']:>12}{e['params']:>12}")
    print(f"{'LUT(字节)':<14}{b['lut']:>12}{e['lut']:>12}")
    print(f"{'每推理 MACs':<14}{b['macs']:>12}{e['macs']:>12}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
