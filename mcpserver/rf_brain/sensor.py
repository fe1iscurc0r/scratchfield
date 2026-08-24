"""射频大脑 · 信号合成（Phase 1 · M1 仿真数据源）

纯 numpy 合成 GFSK / FSK / OOK 三种调制信号，作为 M1 闭环的输入源。
M2 换真 SDR 时，此模块被 liquid-dsp / RTL-SDR 替换，接口保持 generate_iq() 不变。

协议无关：本模块只负责产出 IQ 样本，不关心上层怎么解。
"""
from __future__ import annotations

import numpy as np


def generate_iq(
    modulation: str,
    sample_rate: float = 2_000_000.0,
    center_freq: float = 433_920_000.0,
    duration: float = 0.002,               # 2ms → 4096 样本
    snr_db: float = 20.0,
    symbol_rate: float = 48_000.0,
    seed: int = 42,
) -> np.ndarray:
    """合成一路调制信号（复基带 IQ），叠加高斯噪声到指定 SNR。

    返回：复数 ndarray，长度 = int(sample_rate * duration)。
    """
    rng = np.random.default_rng(seed)
    n = int(sample_rate * duration)
    t = np.arange(n) / sample_rate

    # 随机比特流
    n_symbols = max(1, int(duration * symbol_rate))
    bits = rng.integers(0, 2, n_symbols)
    samples_per_symbol = n / n_symbols
    symbol_idx = np.floor(np.arange(n) / samples_per_symbol).astype(int)
    bit_seq = bits[symbol_idx]

    mod = modulation.upper()
    if mod in ("GFSK", "FSK"):
        # 频偏 ±deviation，GFSK 加高斯脉冲成形（BT≈0.5）
        deviation = symbol_rate / 2.0
        freq = (2 * bit_seq - 1) * deviation
        if mod == "GFSK":
            # 真高斯成形：样本级 NRZ 频轨迹直接卷高斯核（跨 3 符号，BT≈0.5），
            # 把硬切换的瞬时频率轨迹平滑成连续坡道——
            # 这是 Phase 4 相位轨迹判据能区分 GFSK/FSK 的前提。
            sps = samples_per_symbol
            span = int(3 * sps)
            if span % 2 == 0:
                span += 1
            k = np.arange(-(span // 2), span // 2 + 1)
            # 高斯频脉冲：sigma 由 BT 换算（BT=0.5 → B≈0.5/T）
            sigma = np.sqrt(np.log(2) / 2) / (np.pi * 0.5) * sps
            gauss = np.exp(-(k**2) / (2 * sigma**2))
            gauss /= gauss.sum()
            freq = np.convolve(freq, gauss, mode="same")
        phase = 2 * np.pi * np.cumsum(freq) / sample_rate
        iq = np.exp(1j * phase)
    elif mod == "OOK":
        # 幅度键控：1 = 载波，0 = 无
        iq = bit_seq.astype(complex)
    else:
        raise ValueError(f"不支持的调制方式: {modulation}")

    # 归一化信号功率到 1，再按 SNR 加噪声
    iq /= np.sqrt(np.mean(np.abs(iq) ** 2) + 1e-12)
    noise_power = 10 ** (-snr_db / 10)
    noise = (rng.standard_normal(n) + 1j * rng.standard_normal(n)) * np.sqrt(noise_power / 2)
    return iq + noise


def noise_only(sample_rate: float = 2_000_000.0, duration: float = 0.002, seed: int = 7) -> np.ndarray:
    """纯噪声（无有效信号），用于验证 '无有效信号' 判定路径。"""
    rng = np.random.default_rng(seed)
    n = int(sample_rate * duration)
    return (rng.standard_normal(n) + 1j * rng.standard_normal(n)) / np.sqrt(2)
