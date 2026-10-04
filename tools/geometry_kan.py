"""Geometry-Constrained KAN 最小原型（K21 · ESP32 可解释推理评估）。

依据 docs/paper-round2-2026-08-30/digests/digest-g1-4-2026-08-30.md 中
2608.25807（Geometry-Constrained Kolmogorov-Arnold Networks）：
KAN 用「可学习的单变量边函数」（B 样条）替代固定激活 + 线性权重；「几何约束」
则对边函数施加几何性质（此处用单调性）以提升可解释性与稳健性。

原型（numpy，无新依赖）：
  - 边函数 φ(x) = Σ_i c_i · h_i(x)，h_i 为线性 B 样条（hat）基
  - 无约束拟合：最小二乘（闭式）
  - 几何约束：PAVA 把系数投影为非递减 → φ 严格单调
  - 与 OTA-ELM 对比参数/精度；可解释性 = 系数即函数在结点处的值，直接可读

对比对象：单变量单调非线性目标（如 log(1+3x)），物理上「单调」是可解释先验。

运行：
  python tools/geometry_kan.py
"""
from __future__ import annotations

import numpy as np

# ---------- KAN 边函数（线性 B 样条 / hat 基） ----------

def hat_basis(x: np.ndarray, knots: np.ndarray) -> np.ndarray:
    """hat 基：knots 为升序结点（含两端），返回 (m, G+1) 基矩阵，行和=1。"""
    G = len(knots) - 1
    m = x.shape[0]
    H = np.zeros((m, G + 1))
    for j in range(G + 1):
        if j == 0:
            # 左端半 hat：x ∈ [k0, k1]
            H[:, j] = np.clip((knots[1] - x) / (knots[1] - knots[0]), 0.0, 1.0)
        elif j == G:
            # 右端半 hat：x ∈ [k_{G-1}, k_G]
            H[:, j] = np.clip((x - knots[G - 1]) / (knots[G] - knots[G - 1]), 0.0, 1.0)
        else:
            left = np.clip((x - knots[j - 1]) / (knots[j] - knots[j - 1]), 0.0, 1.0)
            right = np.clip((knots[j + 1] - x) / (knots[j + 1] - knots[j]), 0.0, 1.0)
            H[:, j] = np.minimum(left, right)
    return H


def kan_fit(x: np.ndarray, y: np.ndarray, knots: np.ndarray) -> np.ndarray:
    """无约束最小二乘拟合 hat 基 → 系数 c。"""
    H = hat_basis(x, knots)
    return np.linalg.lstsq(H, y, rcond=None)[0]


def kan_predict(c: np.ndarray, x: np.ndarray, knots: np.ndarray) -> np.ndarray:
    return hat_basis(x, knots) @ c


def pava_monotone(c: np.ndarray) -> np.ndarray:
    """PAVA（Pool Adjacent Violators）：把系数投影成非递减序列（几何约束）。"""
    blocks = []
    for v in c.tolist():
        blocks.append([float(v), 1])
        while len(blocks) >= 2 and blocks[-2][0] / blocks[-2][1] > blocks[-1][0] / blocks[-1][1]:
            s, n = blocks.pop()
            blocks[-1][0] += s
            blocks[-1][1] += n
    res = []
    for s, n in blocks:
        res.extend([s / n] * n)
    return np.array(res)


# ---------- OTA-ELM（最小复现，用于对比） ----------

def _sigmoid(z: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-z))


def elm_fit(x: np.ndarray, y: np.ndarray, nh: int, seed: int = 0):
    rng = np.random.default_rng(seed)
    W = rng.normal(0, 1.0, (1, nh))
    b = rng.normal(0, 1.0, (nh,))
    H = _sigmoid(x.reshape(-1, 1) @ W + b)
    beta = np.linalg.pinv(H) @ y
    return W, b, beta


def elm_predict(W: np.ndarray, b: np.ndarray, beta: np.ndarray, x: np.ndarray) -> np.ndarray:
    return _sigmoid(x.reshape(-1, 1) @ W + b) @ beta


# ---------- 对比 ----------

def compare(seed: int = 0) -> dict:
    """在单调目标 log(1+3x) 上对比 KAN（无约束/几何约束）与 OTA-ELM。

    拟合用带噪数据，评估用无噪数据——用于观察「几何约束（单调性）既保证
    单调、又抑制过拟合」这一可解释性收益。
    """
    rng = np.random.default_rng(seed)
    x = np.linspace(0.0, 1.0, 200)
    y_clean = np.log(1.0 + 3.0 * x)
    y_noisy = y_clean + rng.normal(0.0, 0.10, x.shape)

    knots = np.linspace(0.0, 1.0, 20)  # 19 段，20 系数（足够灵活以观察过拟合）
    nh = 10                            # ELM 隐层

    c_free = kan_fit(x, y_noisy, knots)
    c_mono = pava_monotone(c_free)
    y_free = kan_predict(c_free, x, knots)
    y_mono = kan_predict(c_mono, x, knots)

    W, b, beta = elm_fit(x, y_noisy, nh, seed)
    y_elm = elm_predict(W, b, beta, x)

    def mse(yhat):
        return float(np.mean((yhat - y_clean) ** 2))

    return {
        "kan_free": {"mse": mse(y_free),
                     "monotone": bool(np.all(np.diff(c_free) >= -1e-9)),
                     "params": len(knots)},
        "kan_geo": {"mse": mse(y_mono),
                    "monotone": bool(np.all(np.diff(c_mono) >= -1e-9)),
                    "params": len(knots)},
        "elm": {"mse": mse(y_elm), "params": 3 * nh},
    }


def main() -> int:
    c = compare()
    print("=== Geometry-KAN vs OTA-ELM（单调目标 log(1+3x)） ===")
    for name, r in c.items():
        mono = f" 单调={r.get('monotone','-')}" if 'monotone' in r else ""
        print(f"{name:<10} MSE={r['mse']:.6f} 参数={r['params']}{mono}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
