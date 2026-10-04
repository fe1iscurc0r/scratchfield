"""PF029 授粉落地：可变形匹配滤波 x 可解释 DSP → SDR 自校准接收链

授粉点：2608.31149 + 2608.30826 —— "有界变形 + 理论基线"思想。
经典匹配滤波/解调器保持原样，用轻量模型（本模块用解析校正，KAN/MLP 留
扩展位）从物理可解释状态描述符（载频偏移、信噪比）预测低维修正量，形变
本身即失配程度的可测指标。对 ESP32 级接收机：一次离线学习后可在温度漂移、
阻抗失配、符号率偏差等非理想条件下自适应，EVM 中位数显著下降。

本模块做**解析式自校准接收链**（纯 numpy）：
  - 匹配滤波：本地参考 × 接收信号 → 相关（矩形成形对应滑动平均）
  - 失配建模：载频偏移 CFO / 幅度失配 / AWGN
  - 状态描述符：BPSK 平方律 CFO 估计（可解释、确定性、零训练）
  - 低维修正：符号域相位去旋转（一个复数旋转）
  - 验收：失配下 EVM/符号错误率显著下降；pytest 全绿

设计取舍：论文用 KAN/MLP 学低维修正；本原型用解析式（CFO 估计 → 相位旋转）
实现同一"低维状态 → 校正量"思想，确定性、可直接量化为定点。
"""
from __future__ import annotations

import numpy as np

# ---------------------------------------------------------------------------
# 状态描述符提取（可解释指标）
# ---------------------------------------------------------------------------

def estimate_cfo_bpsk(iq: np.ndarray, sps: int) -> float:
    """BPSK 平方律 CFO 估计（归一化，相对符号率）。

    原理：接收信号 x[n] = b[n]·e^{j2πCFO·n/sps}（b=±1）。平方后 b²=1（去调制），
    剩下纯 CFO 旋转 e^{j4πCFO·n/sps}。相邻样本相位差 = 4πCFO/sps，
    对整段相位做线性拟合斜率 → CFO。确定性、零训练、可解释（"失配可测"）。
    """
    iq = np.asarray(iq, dtype=complex)
    if iq.size < 8:
        return 0.0
    sq = iq * iq
    phase = np.unwrap(np.angle(sq))
    n = np.arange(phase.size, dtype=float)
    # 线性拟合：phase ≈ k·n，k = 4π·CFO/sps
    k = float(np.polyfit(n, phase, 1)[0])
    return k * int(sps) / (4.0 * np.pi)


def estimate_snr(iq: np.ndarray, ref: np.ndarray) -> float:
    """信噪比估计（dB）：符号级最近星座投影残差法（EVM 式）。

    对每个匹配滤波软符号取最近星座点（BPSK: ±A），
    信号功率 = E|proj|²，噪声功率 = E|syms - proj|²（残差即噪声）。
    无噪声时残差≈0 → SNR 趋于高值（钳位 99dB）。
    """
    iq = np.asarray(iq, dtype=complex)
    ref = np.asarray(ref, dtype=complex)
    if iq.size == 0 or ref.size == 0 or ref.size > iq.size:
        return 0.0
    sps = int(ref.size)
    corr = np.correlate(iq, ref.conj(), mode="valid")
    n_out = max(int(corr.size // sps) - 1, 1)
    syms = corr[: n_out * sps : sps]
    if syms.size == 0:
        return 0.0
    re = np.real(syms)
    proj = np.sign(re) * float(np.mean(np.abs(syms)))   # 最近星座点（BPSK ±A）
    sig = float(np.mean(np.abs(proj) ** 2))
    noise = float(np.mean(np.abs(syms - proj) ** 2))
    if sig <= 1e-12:
        return 0.0
    snr = 10.0 * np.log10(sig / max(noise, 1e-12))
    return min(snr, 99.0)   # 无噪声钳位


# ---------------------------------------------------------------------------
# 低维修正（可解释：相位去旋转）
# ---------------------------------------------------------------------------

def derotate_symbols(syms: np.ndarray, cfo: float, sps: int,
                     start_offset: int = 0) -> np.ndarray:
    """符号域 CFO 补偿：乘 e^{-j·2π·CFO·(start + n·sps)/sps}。"""
    n = np.arange(syms.size)
    idx = start_offset + n * int(sps)
    return syms * np.exp(-1j * 2.0 * np.pi * cfo * idx / int(sps))


# ---------------------------------------------------------------------------
# 匹配滤波解调
# ---------------------------------------------------------------------------

def matched_filter_demod(iq: np.ndarray, ref: np.ndarray, n_symbols: int,
                         sps: int, *, self_calibrate: bool = True) -> np.ndarray:
    """匹配滤波符号判决（BPSK，矩形成形）。

    采样点：矩形脉冲的相关峰在符号末尾（sps-1, 2sps-1, ...）。
    自校准：估 CFO → 符号域去旋转 → 判决（"形变可测、低维修正"）。
    """
    iq = np.asarray(iq, dtype=complex)
    ref = np.asarray(ref, dtype=complex)
    corr = np.correlate(iq, ref.conj(), mode="valid")
    n_out = min(int(corr.size // sps), n_symbols)
    # 符号起点采样：corr[k]=sum(iq[k..k+sps-1])，k=i*sps 时窗口正好覆盖符号 i
    starts = np.arange(n_out) * sps
    syms = corr[starts].copy()
    if self_calibrate:
        cfo = estimate_cfo_bpsk(iq, sps)
        # 去旋转相位用符号中心 (i*sps + sps/2)
        syms = derotate_symbols(syms, cfo, sps, start_offset=sps // 2)
    return np.sign(np.real(syms))


def matched_filter_soft(iq: np.ndarray, ref: np.ndarray, n_symbols: int,
                        sps: int, *, self_calibrate: bool = True) -> np.ndarray:
    """匹配滤波软符号值（供 EVM 评估；判决用 matched_filter_demod）。"""
    iq = np.asarray(iq, dtype=complex)
    ref = np.asarray(ref, dtype=complex)
    corr = np.correlate(iq, ref.conj(), mode="valid")
    n_out = min(int(corr.size // sps), n_symbols)
    starts = np.arange(n_out) * sps
    syms = corr[starts].copy()
    if self_calibrate:
        cfo = estimate_cfo_bpsk(iq, sps)
        syms = derotate_symbols(syms, cfo, sps, start_offset=sps // 2)
    return syms


def evm_db(ideal: np.ndarray, measured: np.ndarray) -> float:
    """误差向量幅度（dB）：EVM = ||measured - ideal|| / ||ideal||。"""
    ideal = np.asarray(ideal, dtype=float)
    measured = np.asarray(measured, dtype=float)
    if ideal.size == 0 or ideal.size != measured.size:
        return float("inf")
    denom = float(np.linalg.norm(ideal))
    if denom < 1e-12:
        return float("inf")
    return 20.0 * np.log10(float(np.linalg.norm(measured - ideal)) / denom)


# ---------------------------------------------------------------------------
# 合成失配信号
# ---------------------------------------------------------------------------

def synthesize_mismatch(n_symbols: int, sps: int, *, cfo: float = 0.0,
                        amplitude_mismatch: float = 1.0, noise: float = 0.0,
                        seed: int = 0) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """合成带失配的 BPSK 信号（矩形成形）。返回 (iq, bits, ref)。"""
    rng = np.random.default_rng(seed)
    bits = rng.choice(np.array([-1.0, 1.0]), size=n_symbols)
    t = np.arange(n_symbols * sps)
    base = np.repeat(bits, sps)
    sig = base * np.exp(1j * 2.0 * np.pi * cfo * t / sps)   # CFO 旋转
    sig = sig * amplitude_mismatch                          # 幅度失配
    if noise > 0:
        sig = sig + noise * (rng.standard_normal(sig.size)
                             + 1j * rng.standard_normal(sig.size))
    ref = np.ones(sps)                                      # 本地参考（矩形）
    return sig.astype(complex), bits, ref.astype(complex)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    n_sym, sps = 64, 16
    cfo_hz = 0.05  # 归一化 CFO（相对符号率）
    iq, bits, ref = synthesize_mismatch(n_sym, sps, cfo=cfo_hz, noise=0.2, seed=0)
    rx_plain = matched_filter_demod(iq, ref, n_sym, sps, self_calibrate=False)
    rx_cal = matched_filter_demod(iq, ref, n_sym, sps, self_calibrate=True)
    soft_plain = matched_filter_soft(iq, ref, n_sym, sps, self_calibrate=False)
    soft_cal = matched_filter_soft(iq, ref, n_sym, sps, self_calibrate=True)
    n = min(rx_plain.size, rx_cal.size, bits.size)
    cfo_est = estimate_cfo_bpsk(iq, sps)
    norm = float(np.mean(np.abs(soft_cal[:n]))) + 1e-12
    ideal_evm = bits[:n].astype(float) * norm
    print(f"CFO 估计 = {cfo_est:.4f} (真值 {cfo_hz})")
    print(f"SNR 估计 = {estimate_snr(iq, ref):.1f} dB")
    print(f"未校准 符号错误率 = {np.mean(rx_plain[:n] != bits[:n]):.2%}  "
          f"EVM = {evm_db(ideal_evm, np.real(soft_plain[:n])):.1f} dB")
    print(f"自校准 符号错误率 = {np.mean(rx_cal[:n] != bits[:n]):.2%}  "
          f"EVM = {evm_db(ideal_evm, np.real(soft_cal[:n])):.1f} dB")


if __name__ == "__main__":
    main()
