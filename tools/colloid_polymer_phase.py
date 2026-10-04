"""M161 胶体-聚合物混合物热力学相行为（从 RDF 预测）· 最小原型。

授粉源：round4 2608.29124（A route to the thermodynamics of colloid-polymer
mixtures：从径向分布函数 g(r) 直接预测胶体-聚合物混合物热力学相行为的液体态理论框架）。

核心机制（液体态理论，承接 M21 熵/Frenesy 平衡热力学的互补）：
  径向分布函数 g(r) ──傅里叶变换──> 结构因子 S(q)；
  q→0 的 S(0) = 等温压缩率 = 1 + 4πρ∫[g(r)-1]r²dr。
  聚合物导致的「耗散吸引（depletion）」使 g(r) 在粒子接触附近 >1（粒子聚集），
  S(0) 随之增大，逼近 spinodal（相分离失稳）。

本原型（简化，诚实标注）：
  - 合成 g(r) = 硬核(r<σ=0) + 耗散吸引(1 + c·exp(-(r-σ)/ξ))，c=耗散强度（聚合物浓度代理）；
  - 算 S(0) 随 c 的变化，找 S(0) 发散的相分离（spinodal）阈值；
  - 演示「RDF → 压缩率 → 相行为」的预测链路。真实体系需以实测/模拟 g(r) 替换。

验收：S(0) 随耗散强度单调上升，且能定位相分离阈值（见 test_colloid_polymer_phase.py）。
纯 numpy，无外部依赖。
"""
from __future__ import annotations

import numpy as np


def radial_distribution(r: np.ndarray, sigma: float = 1.0, depletion: float = 0.0,
                        xi: float = 0.3) -> np.ndarray:
    """合成 g(r)：r<σ 硬核=0；r≥σ = 1 + depletion·exp(-(r-σ)/ξ)。

    depletion=0 退化为纯硬球（g 在接触处从 0 跳到 1）；depletion>0 时接触附近
    g>1，模拟聚合物耗散导致的粒子聚集。
    """
    g = np.ones_like(r, dtype=float)
    hard = r < sigma
    g[hard] = 0.0
    soft = r >= sigma
    g[soft] += depletion * np.exp(-(r[soft] - sigma) / xi)
    return g


def compressibility(g: np.ndarray, r: np.ndarray, rho: float) -> float:
    """等温压缩率 S(0) = 1 + 4πρ∫[g(r)-1]r²dr（结构因子 q→0 极限）。"""
    integrand = (g - 1.0) * r ** 2
    return 1.0 + 4.0 * np.pi * rho * float(np.trapezoid(integrand, r))


def compressibility_vs_depletion(depletions, sigma=1.0, xi=0.3, rho=0.4,
                                 rmax=8.0, n=2000):
    """对一列耗散强度算 S(0)，返回 (depletions, S0)。"""
    r = np.linspace(1e-6, rmax, n)
    S0 = [compressibility(radial_distribution(r, sigma, d, xi), r, rho)
          for d in depletions]
    return np.asarray(depletions, dtype=float), np.asarray(S0, dtype=float)


def find_spinodal(depletions, S0, threshold=10.0):
    """S(0) 首次超过阈值 = 进入相分离（spinodal）；返回对应耗散强度或 None。"""
    over = threshold < S0
    if not over.any():
        return None
    return float(depletions[np.argmax(over)])


def run_demo() -> None:
    deps = np.linspace(0.0, 6.0, 61)
    deps, S0 = compressibility_vs_depletion(deps, rho=0.4)
    spin = find_spinodal(deps, S0)
    print(f"[M161] 耗散强度范围: {deps[0]:.1f} ~ {deps[-1]:.1f}")
    print(f"[M161] S(0) 范围: {S0[0]:.3f} ~ {S0[-1]:.3f}（随耗散单调上升）")
    print(f"[M161] 相分离(spinodal)阈值: 耗散强度 ≈ {spin if spin is not None else '未达阈值'}")


if __name__ == "__main__":
    run_demo()
