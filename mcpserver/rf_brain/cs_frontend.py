"""PF022 授粉落地：采样端内嵌压缩（CS-SAR 压缩感知前端模拟）

授粉点：2608.28847 CS-SAR ADC —— 压缩感知不放在数字后处理，而是直接内嵌进
采样网络（伪随机极性调制 + 电荷域累加），一个测量值编码多个时域样本，
NcT=4 仍保点目标 NCC 0.98。

对 ESP32 / 便携 SDR 的启发：把随机调制 + 累加做进 ADC/前端（或模拟域），
可在采样率与内存不变甚至更低的情况下捕获宽带信号（射频包络、超声、振动）。

本模块做**纯软件模拟**（真实 ADC 留硬件侧）：
  - 测量矩阵 A = 随机 ±1 极性（Rademacher），对应伪随机极性调制
  - 测量 y = A @ x（电荷域累加 = 矩阵乘的硬件实现）
  - OMP 稀疏恢复：从 M 个测量恢复 N 点稀疏信号（M << N，压缩比 NcT=N/M）
  - 验收：点目标（稀疏脉冲）NcT=4 时 NCC ≥ 0.95；pytest 全绿

注：A@x 在软件模拟里是矩阵乘（教学用途）；硬件实现用开关电容累加是零乘法
    纯加法——本模块 focus 在压缩感知的**采样-恢复语义**，非硬件精确模型。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# ---------------------------------------------------------------------------
# 测量（采样端内嵌压缩模拟）
# ---------------------------------------------------------------------------

def measurement_matrix(n: int, m: int, *, seed: int = 0) -> np.ndarray:
    """随机 ±1 极性测量矩阵（Rademacher，对应伪随机极性调制）。

    形状 (m, n)，m 个测量、n 点信号。±1 系数 → 硬件上只需开关切换 + 累加。
    """
    if not (0 < m <= n):
        raise ValueError(f"测量数 m 须在 (0, n] 内，实际 m={m}, n={n}")
    rng = np.random.default_rng(seed)
    return rng.choice(np.array([-1.0, 1.0]), size=(m, n))


def compress(x: np.ndarray, a: np.ndarray) -> np.ndarray:
    """采样端内嵌压缩：y = A @ x（电荷域累加的软件语义）。"""
    x = np.asarray(x, dtype=float)
    if x.ndim != 1:
        raise ValueError("输入必须为一维")
    if x.size != a.shape[1]:
        raise ValueError(f"信号长度 {x.size} 与测量矩阵列数 {a.shape[1]} 不一致")
    return a @ x


# ---------------------------------------------------------------------------
# OMP 稀疏恢复
# ---------------------------------------------------------------------------

def omp_recover(y: np.ndarray, a: np.ndarray, k: int | None = None,
                tol: float = 1e-6, max_iter: int | None = None) -> np.ndarray:
    """正交匹配追踪：从压缩测量 y 恢复稀疏信号 x（支撑集迭代）。

    每次选与残差最相关的原子（内积最大），正交投影后更新残差。
    k 为稀疏度先验（缺省用 tol 收敛判据）。
    """
    y = np.asarray(y, dtype=float)
    a = np.asarray(a, dtype=float)
    if y.ndim != 1:
        raise ValueError("测量必须为一维")
    if a.shape[0] != y.size:
        raise ValueError(f"测量数 {y.size} 与矩阵行数 {a.shape[0]} 不一致")

    n = a.shape[1]
    if k is None:
        k = int(np.ceil(y.size / 3.0)) if y.size > 1 else 1
    if max_iter is None:
        max_iter = k * 2
    k = min(int(k), n)
    max_iter = min(int(max_iter), n)

    r = y.copy()
    x = np.zeros(n)
    support: list[int] = []
    for _ in range(max_iter):
        if len(support) >= k:
            break
        if float(np.linalg.norm(r)) <= tol:
            break
        # 相关度：|A^T r|
        corr = np.abs(a.T @ r)
        # 跳过已入选原子（重复支撑会退化最小二乘）
        order = np.argsort(corr)[::-1]
        idx = None
        for cand in order:
            if int(cand) not in support:
                idx = int(cand)
                break
        if idx is None:
            break
        support.append(idx)
        # 最小二乘在当前支撑集上，更新残差
        as_ = a[:, support]
        x_s, *_ = np.linalg.lstsq(as_, y, rcond=None)
        r = y - as_ @ x_s
    if support:
        as_ = a[:, support]
        x_s, *_ = np.linalg.lstsq(as_, y, rcond=None)
        x[support] = x_s
    return x


def ncc(x: np.ndarray, x_hat: np.ndarray) -> float:
    """归一化互相关（NCC）：恢复质量指标，1.0 = 完美。"""
    x = np.asarray(x, dtype=float)
    x_hat = np.asarray(x_hat, dtype=float)
    if x.size == 0 or x_hat.size != x.size:
        return 0.0
    denom = float(np.linalg.norm(x) * np.linalg.norm(x_hat))
    if denom < 1e-12:
        return 0.0
    return float(np.dot(x, x_hat) / denom)


# ---------------------------------------------------------------------------
# 合成稀疏信号
# ---------------------------------------------------------------------------

def sparse_pulse_signal(n: int, k: int, *, seed: int = 0,
                        amplitude: float = 1.0) -> np.ndarray:
    """k-稀疏脉冲信号（点目标模型：少量非零脉冲 + 零背景）。"""
    if k < 1 or k >= n:
        raise ValueError(f"稀疏度 k 须在 [1, n) 内，实际 k={k}, n={n}")
    rng = np.random.default_rng(seed)
    x = np.zeros(n)
    idx = rng.choice(n, size=k, replace=False)
    x[idx] = amplitude * rng.standard_normal(k)
    return x


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    n = 256
    k = 6                       # 稀疏度
    x = sparse_pulse_signal(n, k, seed=0)
    for nct in (8, 4, 2):       # 压缩比 N/M
        m = max(n // nct, k * 2)
        a = measurement_matrix(n, m, seed=1)
        y = compress(x, a)
        x_hat = omp_recover(y, a, k=k)
        print(f"NcT={nct} (M={m}): NCC = {ncc(x, x_hat):.4f}")


if __name__ == "__main__":
    main()
