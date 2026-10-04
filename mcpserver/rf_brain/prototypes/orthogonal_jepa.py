"""R10 · Orthogonal JEPA 干扰分离最小原型（正交预测分解）

灵感：digest-g1-1 授粉点 · 论文 2608.20065（Orthogonal JEPA）。

核心：接收 IQ 是多个物理过程的叠加（信号 / 干扰 / 多径），把表示分解为**正交的
预测分量**，每个分量对应一个物理过程，避免单一嵌入导致次级信号梯度弱/冲突。

最小原型用频域天然正交性做线性正交投影（零训练、闭式）：
  - 干扰子空间 = 窄带干扰的 sin/cos 基张成的 rank-2 子空间；
  - î = 投影到干扰子空间（正交投影 P_i x）；
  - ŝ = 正交补 (I - P_i) x（信号 + 多径 + 噪声）。
由构造 ⟨î, ŝ⟩ = 0。校验：正交性 + 分量与各自真值的相关性。

真 JEPA（非线性正交编码器 + 潜空间预测）作为扩展，见 docs/orthogonal-jepa-干扰分离-勘察.md。

运行：python -m mcpserver.rf_brain.prototypes.orthogonal_jepa
"""
from __future__ import annotations

import numpy as np


def synthesize_iq(n: int, sr: float, *, seed: int = 0) -> dict:
    """合成受污染 IQ：QPSK 信号 + 窄带干扰 + 多径 + 噪声。

    返回 dict(signal, interference, multipath, noise, x=总和, sr, f_interf)。
    """
    rng = np.random.default_rng(seed)
    t = np.arange(n) / sr

    # QPSK 基带信号（宽带，随机符号序列经脉冲成型近似）
    sym = rng.integers(0, 4, n // 8)
    phase = np.pi / 4 + (np.pi / 2) * sym
    signal = np.repeat(np.exp(1j * phase), 8)[:n] * 0.3

    # 窄带干扰（单音）
    f_interf = 0.11 * sr
    interference = 0.9 * np.exp(1j * 2 * np.pi * f_interf * t)

    # 多径：信号的延迟拷贝
    delay = 3
    multipath = 0.2 * np.roll(signal, delay)
    multipath[:delay] = 0.0

    noise = 0.05 * (rng.standard_normal(n) + 1j * rng.standard_normal(n))
    x = signal + interference + multipath + noise
    return {"signal": signal, "interference": interference, "multipath": multipath,
            "noise": noise, "x": x, "sr": sr, "f_interf": f_interf}


def interference_basis(n: int, sr: float, f_interf: float) -> np.ndarray:
    """窄带干扰子空间的实正交基（sin/cos，rank-2）。"""
    t = np.arange(n) / sr
    c = np.cos(2 * np.pi * f_interf * t)
    s = np.sin(2 * np.pi * f_interf * t)
    B = np.stack([c, s], axis=1)  # (n, 2)，实域；对复信号分别处理实虚部
    Q, _ = np.linalg.qr(B)
    return Q


def orthogonal_decompose(x: np.ndarray, sr: float, f_interf: float) -> tuple[np.ndarray, np.ndarray]:
    """正交分解：î = 干扰子空间投影，ŝ = 正交补。"""
    Q = interference_basis(x.size, sr, f_interf)
    P = Q @ Q.T  # 正交投影算子
    # 复信号按实部/虚部分别投影（子空间为实，逐通道）
    xr, xi = np.real(x), np.imag(x)
    ir = P @ xr
    ii = P @ xi
    i_hat = ir + 1j * ii
    s_hat = x - i_hat
    return s_hat, i_hat


def corr(a: np.ndarray, b: np.ndarray) -> float:
    """复信号的相关性幅值（0..1）。"""
    a = a - a.mean()
    b = b - b.mean()
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    return float(np.abs(np.vdot(a, b)) / denom) if denom > 0 else 0.0


def main() -> None:
    d = synthesize_iq(4096, 1000.0, seed=0)
    s_hat, i_hat = orthogonal_decompose(d["x"], d["sr"], d["f_interf"])
    print(f"正交性 ⟨ŝ,î⟩ 相关 = {corr(s_hat, i_hat):.4f}")
    print(f"ŝ 与真信号相关 = {corr(s_hat, d['signal']):.3f}")
    print(f"î 与真干扰相关 = {corr(i_hat, d['interference']):.3f}")
    print(f"î 与真信号相关（应低） = {corr(i_hat, d['signal']):.3f}")


if __name__ == "__main__":
    main()
