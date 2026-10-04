"""R30 · PT 对称可编程波形发生器原型

灵感：digest-g5-3a 授粉点① · 论文 2608.22958（odd viscosity 的 PT 对称流体力学）。

方案：PT 对称双模振荡器（一模有增益 +γ、一模有损耗 -γ，耦合 κ）可作 SDR 发射端的
**可编程波形发生器**——通过平衡增益/损耗（γ）与耦合（κ）控制波形：

  系统矩阵 [[iω+γ, κ], [κ, iω-γ]]，本征值 λ = iω ± √(κ²-γ²)。
  - PT 未破缺（γ<κ）：√(κ²-γ²) 为实 → 纯振荡（频率 ω±Ω，Ω=√(κ²-γ²)），
    波形稳定不发散——**连续波/单音**；
  - 例外点 EP（γ=κ）：两模简并；
  - PT 破缺（γ>κ）：√ 为虚 → 一模指数增长、一模指数衰减——**脉冲/突发包络**。

故调 γ、κ 即可编程出「稳定振荡」或「可控增长/衰减」两类波形（对应 SDR 的
连续波与脉冲波），且平衡增益/损耗天然控制包络形状。odd viscosity 的耗散无关
输运与此同源（平衡增益/损耗的守恒流）。

运行：python -m mcpserver.rf_brain.prototypes.pt_symmetric_waveform
"""
from __future__ import annotations

import numpy as np


def pt_eigenvalues(gamma: float, kappa: float, omega: float = 0.0) -> tuple[complex, complex]:
    """PT 对称双模系统本征值 λ = iω ± √(γ²-κ²)。

    γ<κ（未破缺）：√ 为虚 → 纯虚本征值 → 稳定振荡（频率 ω±Ω，Ω=√(κ²-γ²)）。
    γ>κ（破缺）：√ 为实 → 本征值含实部 ±Γ（一模增长、一模衰减）。
    """
    disc = gamma ** 2 - kappa ** 2
    if disc >= 0:                       # 破缺：实部 ±Γ
        sq = np.sqrt(disc)
        return omega * 1j + sq, omega * 1j - sq
    else:                               # 未破缺：纯虚 i(ω±Ω)
        sq = np.sqrt(-disc)
        return omega * 1j + 1j * sq, omega * 1j - 1j * sq


def simulate(gamma: float, kappa: float, *, omega: float = 0.0, n: int = 2000,
             dt: float = 0.001, seed: int = 0) -> np.ndarray:
    """模拟 PT 对称双模振荡器（欧拉积分），返回波形（实部）。"""
    rng = np.random.default_rng(seed)
    a1, a2 = 1.0 + 0j, 0.0 + 0j
    M11, M12 = 1j * omega + gamma, 1j * kappa
    M21, M22 = 1j * kappa, 1j * omega - gamma
    out = np.empty(n)
    for i in range(n):
        a1 += dt * (M11 * a1 + M12 * a2)
        a2 += dt * (M21 * a1 + M22 * a2)
        out[i] = (a1 + a2).real
    return out


def envelope_growth(waveform: np.ndarray) -> float:
    """波形包络的末段相对初段能量比（对数），>0 增长、<0 衰减、≈0 稳定。"""
    half = len(waveform) // 2
    e0 = float(np.mean(np.abs(waveform[:100]) ** 2))
    e1 = float(np.mean(np.abs(waveform[-100:]) ** 2))
    return float(np.log(e1 / e0 + 1e-12))


def main() -> None:
    for gamma, kappa in [(0.5, 1.0), (1.0, 1.0), (1.5, 1.0)]:
        lam1, lam2 = pt_eigenvalues(gamma, kappa)
        w = simulate(gamma, kappa)
        g = envelope_growth(w)
        state = "未破缺(稳定振荡)" if gamma < kappa else ("例外点" if gamma == kappa else "破缺(增长/衰减)")
        print(f"γ={gamma} κ={kappa}  {state:<18} 本征值 Re={lam1.real:+.3f} Im={lam1.imag:+.3f} 包络对数增长={g:+.2f}")


if __name__ == "__main__":
    main()
