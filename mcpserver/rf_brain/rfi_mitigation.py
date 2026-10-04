"""射频大脑 · RFI 缓解模块（R03）

SPOTLIGHT（arXiv 2608.19102）双极化 RFI 实时缓解思路的工程落地：
天线级电压域预滤波（VOLT）+ 梁形成后统计滤波（STRIPE）→ 误检率↓98%、S/N↑2.7×。

本模块把"双极化协同抑制"与"子带阈值 + 时域累积"落地为 SDR 频谱后处理滤波链：

  - detect_rfi_dual_channel  双通道能量比检测 RFI（极化域：RFI 偏振 → 单通道能量集中）
  - detect_rfi_narrowband    窄带峰检测（单通道兜底，子带阈值）
  - notch_biquad / notch_filter   2 阶 Butterworth 带阻（陷波 biquad）
  - butterworth_bandstop     2 阶 Butterworth 带阻滤波链入口
  - adaptive_notch           LMS 单频自适应对消（时域累积跟踪）
  - mitigate_rfi             端到端：检测 RFI 频点 → 陷波滤波链 → 清洗信号

纯 numpy，无硬件依赖，可离线单测。不碰 NEKO。
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

# --------------------------------------------------------------------------- #
# 频谱 / 检测
# --------------------------------------------------------------------------- #

def power_spectrum(signal: np.ndarray, sample_rate: float) -> tuple[np.ndarray, np.ndarray]:
    """实信号 → 单边功率谱（Hz, 功率），不做归一化（保留绝对量级供阈值判定）。"""
    x = np.asarray(signal, dtype=float)
    if x.ndim != 1 or x.size == 0:
        raise ValueError("signal 必须为非空一维实信号")
    n = x.size
    X = np.fft.rfft(x)
    freqs = np.fft.rfftfreq(n, 1.0 / float(sample_rate))
    power = np.abs(X) ** 2
    return freqs.astype(float), power


def detect_rfi_narrowband(
    signal: np.ndarray,
    sample_rate: float,
    *,
    prominence_db: float = 20.0,
) -> list[float]:
    """窄带峰检测：把显著高于噪声底的局部谱峰判为 RFI 频点。

    RFI 是窄带强干扰（能量集中在少数 bin），噪声是宽带的。用稳健中位数估计
    噪声底，超过 `prominence_db` 的局部极大值 → 干扰频点列表。
    """
    freqs, power = power_spectrum(signal, sample_rate)
    noise = float(np.median(power))
    if noise <= 0.0:
        noise = 1e-12
    thresh = noise * (10.0 ** (prominence_db / 10.0))
    cand = np.flatnonzero(power > thresh)
    peaks: list[float] = []
    for i in cand:
        if i == 0 or i == power.size - 1:
            continue
        if power[i] >= power[i - 1] and power[i] >= power[i + 1]:
            peaks.append(float(freqs[i]))
    return peaks


def detect_rfi_dual_channel(
    ch_a: np.ndarray,
    ch_b: np.ndarray,
    sample_rate: float,
    *,
    imbalance_db: float = 6.0,
) -> tuple[np.ndarray, np.ndarray]:
    """双通道能量比检测 RFI（极化域）。

    SPOTLIGHT 的核心观察：RFI 通常强偏振，在两路正交极化通道中能量严重不对称；
    而待观测信号（天空/宽带）近似非偏振，两通道能量接近。因此对每 bin 计算
    双通道能量比，比值失衡且总能量够高的 bin 判为 RFI。

    返回 (freqs, mask)：mask 为 bool 数组，True 表示该 bin 判为 RFI。
    """
    fa, pa = power_spectrum(np.asarray(ch_a, dtype=float), sample_rate)
    fb, pb = power_spectrum(np.asarray(ch_b, dtype=float), sample_rate)
    if fa.size != fb.size:
        raise ValueError("两通道长度不一致，无法逐 bin 比较")
    pa_db = 10.0 * np.log10(pa + 1e-12)
    pb_db = 10.0 * np.log10(pb + 1e-12)
    imbalance = np.abs(pa_db - pb_db)
    # 能量须够高（真实干扰，而非噪声涨落）
    above_floor = (pa_db > -90.0) | (pb_db > -90.0)
    mask = (imbalance > float(imbalance_db)) & above_floor
    return fa, mask


# --------------------------------------------------------------------------- #
# 滤波链
# --------------------------------------------------------------------------- #

def notch_biquad(f0: float, sample_rate: float, bw_hz: float) -> tuple[np.ndarray, np.ndarray]:
    """2 阶 Butterworth 带阻（陷波）biquad 系数。

    参数:
        f0:          陷波中心频率（Hz）。
        sample_rate: 采样率（Hz）。
        bw_hz:       -3dB 带宽（Hz）。

    返回:
        (b, a) 分子/分母系数（长度 3）。
    """
    sr = float(sample_rate)
    f0 = float(f0)
    bw = float(bw_hz)
    if not (0.0 < f0 < sr / 2.0):
        raise ValueError(f"陷波频率越界: {f0}（须在 0..{sr/2} Hz）")
    if bw <= 0.0:
        raise ValueError(f"带宽必须 > 0: {bw}")
    w0 = 2.0 * np.pi * f0 / sr
    # 极半径 r：带宽越窄越接近 1（陷得越深、越窄）
    r = 1.0 - np.pi * bw / sr
    r = float(np.clip(r, 0.0, 0.9999))
    b = np.array([1.0, -2.0 * np.cos(w0), 1.0])
    a = np.array([1.0, -2.0 * r * np.cos(w0), r * r])
    return b, a


def _biquad_lfilter(b: np.ndarray, a: np.ndarray, x: np.ndarray) -> np.ndarray:
    """直接 II 型转置 biquad 滤波（2 阶，纯 numpy）。"""
    b = np.asarray(b, dtype=float)
    a = np.asarray(a, dtype=float)
    x = np.asarray(x, dtype=float)
    a0 = a[0]
    b = b / a0
    a = a / a0
    n = x.size
    y = np.zeros(n)
    z1 = z2 = 0.0
    b0, b1, b2 = b[0], b[1], b[2]
    a1, a2 = a[1], a[2]
    for i in range(n):
        xi = x[i]
        yi = b0 * xi + z1
        z1 = b1 * xi - a1 * yi + z2
        z2 = b2 * xi - a2 * yi
        y[i] = yi
    return y


def notch_filter(signal: np.ndarray, sample_rate: float, f0: float, bw_hz: float) -> np.ndarray:
    """对信号施加单频陷波（2 阶 Butterworth 带阻）。"""
    b, a = notch_biquad(f0, sample_rate, bw_hz)
    return _biquad_lfilter(b, a, signal)


def butterworth_bandstop(
    signal: np.ndarray,
    sample_rate: float,
    f0: float,
    bw_hz: float,
) -> np.ndarray:
    """2 阶 Butterworth 带阻滤波（滤波链入口）。

    高阶可通过级联多次调用实现；此处按 SPOTLIGHT"电压域预滤波"的实时约束
    取 2 阶（足够对单音窄带干扰），避免群延迟过长。
    """
    return notch_filter(signal, sample_rate, f0, bw_hz)


def adaptive_notch(
    signal: np.ndarray,
    sample_rate: float,
    f0: float,
    *,
    mu: float = 0.01,
) -> np.ndarray:
    """LMS 单频自适应陷波（自适应对消器）。

    以 f0 处的正交参考（sin/cos）重构干扰分量，用 LMS 在线跟踪其幅度与相位，
    从输入中减去。相比固定陷波，可自适应于干扰幅度/相位的慢漂移（STRIPE 的
    "时域累积"精神）。纯 numpy 逐样本循环（原型用）。
    """
    x = np.asarray(signal, dtype=float)
    n = x.size
    t = np.arange(n) / float(sample_rate)
    r1 = np.sin(2.0 * np.pi * f0 * t)
    r2 = np.cos(2.0 * np.pi * f0 * t)
    w1 = w2 = 0.0
    y = np.zeros(n)
    two_mu = 2.0 * float(mu)
    for i in range(n):
        e = x[i] - (w1 * r1[i] + w2 * r2[i])
        w1 += two_mu * e * r1[i]
        w2 += two_mu * e * r2[i]
        y[i] = e
    return y


# --------------------------------------------------------------------------- #
# 端到端缓解
# --------------------------------------------------------------------------- #

@dataclass
class RFIResult:
    """RFI 缓解结果。"""
    cleaned: np.ndarray                     # 清洗后信号
    detected_freqs_hz: list[float] = field(default_factory=list)  # 检测到的干扰频点
    snr_before_db: float = 0.0              # 相对参考信号的 S/N（dB）
    snr_after_db: float = 0.0

    @property
    def snr_improvement(self) -> float:
        """S/N 提升倍数（线性，after/before）。"""
        return 10.0 ** ((self.snr_after_db - self.snr_before_db) / 10.0)


def _snr_db(signal: np.ndarray, reference: np.ndarray) -> float:
    """相对参考信号的 S/N：P(参考) / P(残差)，单位 dB。"""
    s = np.asarray(signal, dtype=float)
    r = np.asarray(reference, dtype=float)
    sp = float(np.mean(r ** 2))
    rp = float(np.mean((s - r) ** 2))
    if rp <= 0.0:
        return 200.0  # 完美对齐（残差为 0）
    return 10.0 * np.log10(sp / rp + 1e-12)


def mitigate_rfi(
    signal: np.ndarray,
    sample_rate: float,
    *,
    reference: np.ndarray | None = None,
    prominence_db: float = 20.0,
    notch_bw_hz: float | None = None,
    adaptive: bool = False,
    mu: float = 0.01,
) -> RFIResult:
    """端到端 RFI 缓解：检测干扰频点 → 陷波滤波链 → 清洗信号。

    参数:
        signal:        受污染信号（含窄带干扰）。
        sample_rate:   采样率（Hz）。
        reference:     可选，无干扰的干净参考（用于 S/N 计算）。
        prominence_db: 窄带峰检测的显著度阈值（dB）。
        notch_bw_hz:   陷波带宽（Hz）；缺省 = 采样率/1000（窄陷波）。
        adaptive:      是否用自适应陷波（LMS）替代固定陷波。

    返回:
        RFIResult（cleaned 信号、检测频点、S/N 提升）。
    """
    x = np.asarray(signal, dtype=float)
    sr = float(sample_rate)
    bw = float(notch_bw_hz) if notch_bw_hz else sr / 1000.0

    freqs = detect_rfi_narrowband(x, sr, prominence_db=prominence_db)

    cleaned = x.copy()
    for f0 in freqs:
        if adaptive:
            cleaned = adaptive_notch(cleaned, sr, f0, mu=mu)
        else:
            cleaned = notch_filter(cleaned, sr, f0, bw)

    result = RFIResult(cleaned=cleaned, detected_freqs_hz=freqs)
    if reference is not None:
        result.snr_before_db = _snr_db(x, reference)
        result.snr_after_db = _snr_db(cleaned, reference)
    return result
