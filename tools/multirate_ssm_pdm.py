"""K23 多速率 SSM→ESP32 音频/传感器 DSP（最小原型 + 预算对比）

来源授粉点：round3 digest-g7 2608.28472（Multirate SSM PDM）——多速率状态空间模型
端到端处理脉冲密度调制（PDM）信号。ESP32 音频（PDM 数字麦克风）输出 1-bit 高速率
位流；多速率 SSM 在**高速率段只做轻量抗混叠（CIC 箱平均 = 状态空间累加链）并降采样**，
把昂贵的特征 SSM 挪到**低速率段**运行，从而降低内存与算力。

原型只做四件事（纯 numpy，无真机）：
  1. `pdm_encode`：一阶 Σ-Δ 调制，把浮点信号编码成 1-bit PDM 位流；
  2. `cic_decimate`：CIC 箱平均抗混叠 + 降采样（PDM→PCM 标准前端，多速率 SSM 高速段）；
  3. `ssm_lowpass`：低速率段一阶状态空间低通（特征提取）；
  4. `multirate_ssm`：组合两者；`reconstruction_snr` 重建精度；`budget` 内存/参数预算。

验收口径：评估报告含「参数 / 精度 / 内存预算」对比（见 docs/multirate-ssm-esp32-audio-评估.md）。
"""
from __future__ import annotations

import numpy as np

__all__ = ["pdm_encode", "pdm_encode2", "cic_decimate", "ssm_lowpass", "multirate_ssm", "reconstruction_snr", "budget"]


def pdm_encode(x: np.ndarray, seed: int = 0) -> np.ndarray:
    """一阶 Σ-Δ 调制：浮点信号 → 1-bit PDM 位流（±1）。"""
    x = np.asarray(x, dtype=float)
    del seed  # 保留签名便于与其它生成器对齐（Σ-Δ 本身确定性）
    y = np.zeros_like(x)
    acc = 0.0
    for i in range(x.size):
        acc += x[i]
        bit = 1.0 if acc >= 0.0 else -1.0
        y[i] = bit
        acc -= bit
    return y


def pdm_encode2(x: np.ndarray, seed: int = 0) -> np.ndarray:
    """二阶 Σ-Δ 调制：两级积分器，噪声整形更陡（~15 dB/oct vs 一阶 ~9 dB/oct）。

    同过采样率下 SNR 更高（量化噪声更多被推到高频），代价是两级积分器状态。
    """
    x = np.asarray(x, dtype=float)
    del seed
    y = np.zeros_like(x)
    int1 = 0.0  # 第一级积分器
    int2 = 0.0  # 第二级积分器
    prev = 0.0
    for i in range(x.size):
        int1 += x[i] - prev
        int2 += int1 - prev
        bit = 1.0 if int2 >= 0.0 else -1.0
        y[i] = bit
        prev = bit
    return y


def cic_decimate(pdm: np.ndarray, decim: int, order: int = 1) -> np.ndarray:
    """CIC 抗混叠 + 降采样（PDM→PCM 标准前端）。

    高速率段：`order` 级级联箱平均（CIC）= sinc^order 响应，状态仅 `order·decim` 个
    累加器，等价于多速率 SSM 的积分链；sinc 响应在 k·(Fs/decim) 处有零点，抑制高频
    量化噪声。高阶 Σ-Δ 需配高阶 CIC 才能兑现噪声整形收益（二阶 SDM + sinc^2）。
    """
    pdm = np.asarray(pdm, dtype=float)
    if decim < 1:
        raise ValueError(f"decim 需 >= 1，实际 {decim}")
    if order < 1:
        raise ValueError(f"order 需 >= 1，实际 {order}")
    filt = pdm
    for _ in range(order):
        kernel = np.ones(decim, dtype=float) / decim
        filt = np.convolve(filt, kernel, mode="valid")
    return filt[::decim]


def ssm_lowpass(x: np.ndarray, alpha: float = 0.2) -> np.ndarray:
    """低速率段一阶状态空间低通（离散）：state ← state + α·(u − state)。"""
    x = np.asarray(x, dtype=float)
    out = np.empty_like(x)
    state = 0.0
    for i in range(x.size):
        state = state + alpha * (x[i] - state)
        out[i] = state
    return out


def multirate_ssm(pdm: np.ndarray, decim: int, alpha: float | None = 0.2) -> np.ndarray:
    """多速率 SSM：高速率 CIC 抗混叠降采样 →（可选）低速率一阶 SSM 特征。

    alpha=None 时只做 PDM→PCM 重建（返回低速率包络）；alpha 给定时在其上叠低速率 SSM。
    """
    low = cic_decimate(pdm, decim)
    if alpha is None:
        return low
    return ssm_lowpass(low, alpha)


def reconstruction_snr(est: np.ndarray, ref: np.ndarray) -> float:
    """重建精度：20·log10(rms(ref) / rms(est − ref))，单位 dB。"""
    est = np.asarray(est, dtype=float)
    ref = np.asarray(ref, dtype=float)
    err = est - ref
    denom = float(np.sqrt(np.mean(err**2))) or 1e-12
    sig = float(np.sqrt(np.mean(ref**2))) or 1e-12
    return float(20.0 * np.log10(sig / denom))


def budget(rate_hz: float, decim: int, state_bytes: int = 4) -> dict:
    """单速率 vs 多速率的内存/参数预算（每通道状态缓冲字节）。

    单速率：SSM 特征提取在**全速率**跑，状态缓冲按全速率样本数计。
    多速率：高速率段只留 `decim` 个累加器状态（CIC 积分链），特征 SSM 在低速率
    （rate/decim）跑 → 状态缓冲按低速率样本数计。
    """
    rate_hz = float(rate_hz)
    decim = int(decim)
    single_state = rate_hz * state_bytes                        # 全速率状态缓冲
    multi_hi = decim * state_bytes                              # 高速率 CIC 累加器
    multi_lo = (rate_hz / decim) * state_bytes                  # 低速率特征 SSM 状态
    return {
        "rate_hz": rate_hz,
        "decim": decim,
        "single_rate_state_bytes": single_state,
        "multirate_state_bytes": multi_hi + multi_lo,
        "ssm_params_per_stage": 2,  # 每级一阶 SSM 仅 α + 状态（标量）
        "memory_ratio": (multi_hi + multi_lo) / single_state,
    }
