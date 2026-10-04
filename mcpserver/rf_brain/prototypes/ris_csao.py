"""R07 · RIS 相位闭合解原型（CS-AO 交替优化）

灵感：digest-gx-2 授粉点① · 论文 18458（Joint Beamforming and RIS Phase-Shift
Design）。CS-AO 把"满足通信 QoS 约束下的传感波束增益最大化"这个非凸（单位模
|θ_n|=1）问题分解为可**闭合求解**的子问题，比 SCA/SDR 加速 50-120×。

本原型落地一个最小 RIS 模型：
  - N 个反射单元，半波长间距，馈源在 broadside（φ_in=0）。
  - 反射系数 c_n = e^{jθ_n}（单位模）。朝 φ 方向的阵列响应 g_n(φ)=e^{jπ(n-1)sinφ}。
  - 目标：max G(φ_t)  s.t.  G(φ_u) ≥ γ   （G 为归一化波束增益 0..N）。

CS-AO 闭合解思路：加权目标 c^H(g_t g_t^H + λ g_u g_u^H)c 在单位模约束下，
其解为 c_n = exp(j·arg(g_t,n* + λ·g_u,n*))（相位对齐到两方向的加权组合），
故只需对 λ 做单调二分即可同时满足 QoS 且最大化目标增益——每步 O(N)，闭合无迭代内环。

对比基准：随机相位、无约束上限（纯对准目标）、简单 SCA（逐次凸逼近投影）。

复杂度（浮点/定点）：
  - CS-AO：每 λ 一次 O(N) 相位计算，二分 ~30 次 → O(30N)；每元素一次 arg/exp。
  - SDR 基准：半定规划 O(N^3.5) 量级，且需 SDP 求解器。
  - 定点化：相位表量化（如 2^b 档，b=8 即 256 相位档），arg→查表，exp→CORDIC，
    无需浮点；N=64、b=8 时整表 < 64×8 bit。

运行：python -m mcpserver.rf_brain.prototypes.ris_csao
"""
from __future__ import annotations

import numpy as np


def ris_steering(N: int, phi_rad: float) -> np.ndarray:
    """RIS 阵列响应 g_n(φ) = e^{jπ(n-1)sinφ}（馈源 broadside）。"""
    n = np.arange(N)
    return np.exp(1j * np.pi * n * np.sin(phi_rad))


def ris_gain(c: np.ndarray, g: np.ndarray) -> float:
    """归一化波束增益 G(φ) = (1/N)|g^T c|²。"""
    N = g.size
    return float(np.abs(np.dot(g, c)) ** 2 / N)


def cs_ao(N: int, phi_t: float, phi_u: float, gamma: float, *, max_iter: int = 60) -> dict:
    """CS-AO：对 λ 二分，闭合解 c = phase(g_t* + λ·g_u*)，满足 G(φ_u) ≥ γ。

    返回 dict(phases, target_gain, user_gain, iters, satisfied)。
    """
    g_t = ris_steering(N, phi_t)
    g_u = ris_steering(N, phi_u)

    def solve(lam: float) -> np.ndarray:
        return np.exp(1j * np.angle(np.conj(g_t) + lam * np.conj(g_u)))

    lo, hi = 0.0, 1.0
    # 扩界直到 hi 能满足 QoS（纯用户对准）
    while ris_gain(solve(hi), g_u) < gamma and hi < 1e6:
        hi *= 2.0

    c = solve(lo)
    for _ in range(max_iter):
        mid = 0.5 * (lo + hi)
        c_mid = solve(mid)
        if ris_gain(c_mid, g_u) >= gamma:
            c, hi = c_mid, mid
        else:
            lo = mid
    return {
        "phases": c,
        "target_gain": ris_gain(c, g_t),
        "user_gain": ris_gain(c, g_u),
        "satisfied": ris_gain(c, g_u) >= gamma - 1e-9,
    }


def sca_baseline(N: int, phi_t: float, phi_u: float, gamma: float, *, iters: int = 200, step: float = 0.1) -> dict:
    """简单 SCA 基准：投影梯度交替（线性化用户约束 → 相位投影）。"""
    g_t = ris_steering(N, phi_t)
    g_u = ris_steering(N, phi_u)
    c = np.conj(g_t)  # 初始对准目标
    for _ in range(iters):
        if ris_gain(c, g_u) >= gamma:
            break
        # 沿用户方向旋转相位一步（提升 G_u），再归一化
        grad = np.conj(g_u) * np.conj(np.dot(g_u, c))  # ∂G_u/∂c*
        c = c + step * grad
        c = np.exp(1j * np.angle(c))  # 投影回单位模
    return {
        "phases": c,
        "target_gain": ris_gain(c, g_t),
        "user_gain": ris_gain(c, g_u),
        "satisfied": ris_gain(c, g_u) >= gamma - 1e-9,
    }


def main() -> None:
    N = 64
    phi_t, phi_u = np.radians(10.0), np.radians(-25.0)
    print(f"RIS N={N}  目标 φ_t=10°  用户 φ_u=-25°\n")
    print(f"{'方案':<14}{'目标增益':>10}{'用户增益':>10}{'满足QoS':>8}")
    for gamma in (0.0, 0.3 * N, 0.6 * N):
        r = cs_ao(N, phi_t, phi_u, gamma)
        print(f"{f'CS-AO(γ={gamma:.0f})':<14}{r['target_gain']:>10.1f}{r['user_gain']:>10.1f}{str(r['satisfied']):>8}")
    # 随机基准
    rng = np.random.default_rng(0)
    c_rand = np.exp(1j * rng.uniform(0, 2 * np.pi, N))
    print(f"{'随机':<14}{ris_gain(c_rand, ris_steering(N, phi_t)):>10.1f}"
          f"{ris_gain(c_rand, ris_steering(N, phi_u)):>10.1f}{'False':>8}")
    # 无约束上限
    c_ub = np.conj(ris_steering(N, phi_t))
    print(f"{'无约束上限':<14}{ris_gain(c_ub, ris_steering(N, phi_t)):>10.1f}"
          f"{ris_gain(c_ub, ris_steering(N, phi_u)):>10.1f}{'—':>8}")


if __name__ == "__main__":
    main()
