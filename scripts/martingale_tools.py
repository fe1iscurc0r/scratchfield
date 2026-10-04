#!/usr/bin/env python3
"""I05 鞅论/信息几何统计工具（numpy 原型）。

把 concentration inequality + PAC-Bayes + Ville 链式分解做成一个工具库。
参考 digest-g9 授粉点 ①（2608.20337v1）：非负鞅的信息流变分恒等式把
Azuma-Hoeffding / PAC-Bayes / Ville 统一到同一框架，tail bound 可链式分解为
每步条件散度。

仅 numpy；`python scripts/martingale_tools.py` 打印示例。
"""
from __future__ import annotations

import numpy as np


def azuma_hoeffding(diffs: np.ndarray, c: float, t: float) -> float:
    """Azuma-Hoeffding：有界鞅差分序列的尾界。

    P(|Σ diffs| ≥ t) ≤ 2·exp(-t² / (2·Σ c_i²))
    """
    n = len(diffs)
    bound = 2.0 * np.exp(-(t ** 2) / (2.0 * n * c ** 2))
    return float(min(1.0, bound))


def ville_bound(process: np.ndarray, lam: float, a: float) -> float:
    """Ville 上鞅交叉界：非负上鞅 M_n，P(sup_n M_n ≥ a) ≤ 1/a。

    给定乘性权重过程 W_n（非负鞅），lam 为指数倾斜参数，返回
    P(sup_n e^{lam·W_n} ≥ a) 的界。
    """
    m = np.max(process)
    return float(min(1.0, np.exp(-lam * (a - m))))


def pac_bayes_kl_bound(emp_err: float, kl_qp: float, n: int, delta: float) -> float:
    """PAC-Bayes（Gibbs tilt 几何）：经验误差 + KL 正则的上界。

    gen_err ≤ kl⁻¹(emp_err + (kl_qp + log(1/δ)) / n) 的近似（用 Pinsker 上界）。
    """
    slack = (kl_qp + np.log(1.0 / delta)) / n
    # Pinsker: KL(p||q) ≥ 2(p-q)² → p ≤ q + sqrt(2·slack) 的一阶近似
    return float(min(1.0, emp_err + np.sqrt(2.0 * slack)))


def chain_kl(step_kls: np.ndarray) -> tuple[float, np.ndarray]:
    """链式 KL 分解：总散度 = Σ 每步条件散度（tail bound 的逐项松弛来源）。"""
    total = float(step_kls.sum())
    return total, np.cumsum(step_kls)


def demo() -> None:
    rng = np.random.default_rng(0)
    diffs = rng.normal(0, 1, 100)
    print("Azuma-Hoeffding P(|S|≥15):", round(azuma_hoeffding(diffs, c=1.0, t=15.0), 4))

    process = np.exp(rng.normal(0, 1, 200).cumsum() * 0.1)
    print("Ville crossing bound:", round(ville_bound(process, lam=1.0, a=5.0), 4))

    print("PAC-Bayes gen bound:", round(pac_bayes_kl_bound(0.1, kl_qp=0.5, n=1000, delta=0.05), 4))

    total, cum = chain_kl(np.array([0.2, 0.1, 0.3]))
    print("Chain KL total:", total, "cumsum:", cum.tolist())


if __name__ == "__main__":
    demo()
