"""DTMF 解码器（Phase 6 · Goertzel，numpy 实现，禁用 scipy）

DTMF 双音多频：每键 = 行频(697/770/852/941) + 列频(1209/1336/1477/1633)。
接收：512 样本帧（64ms @8kHz）逐帧 Goertzel 求 8 个单频 bin 幅度，
      取行最大 + 列最大 → 按键；相邻帧去重输出拨号序列。

Goertzel 说明：单频点检测等价于该频率的 DFT bin。这里用精确频率（非
整数 bin）的复指数与帧做点积——即 Goertzel 的向量化实现，避免 FFT 的
频率分辨率限制（697Hz 对应 44.6 bin，整数 bin 会明显漏检）。

注册：本模块不主动注册，由 decoders/__init__.py 统一导入触发。
"""
from __future__ import annotations

import numpy as np

ROW_FREQS = [697.0, 770.0, 852.0, 941.0]
COL_FREQS = [1209.0, 1336.0, 1477.0, 1633.0]
_KEYS = ["123A", "456B", "789C", "*0#D"]

MAP: dict[str, tuple[float, float]] = {}          # 键 → (行频, 列频)
for _i in range(4):
    for _j in range(4):
        MAP[_KEYS[_i][_j]] = (ROW_FREQS[_i], COL_FREQS[_j])

FRAME = 512                                        # 64ms @8kHz
STEP = 160                                         # 20ms 步进
THRESHOLD = 5.0                                    # 绝对幅度阈值（保底）
PEAK_RATIO = 5.0                                   # 主峰/次峰比值（双音结构判据）


def goertzel_bin(x: np.ndarray, freq: float, sample_rate: float) -> float:
    """单频点 DFT bin（Goertzel 向量化等价）：x 与 exp(-j2πf·t) 点积取模。"""
    n = x.size
    idx = np.arange(n)
    return float(np.abs(np.sum(x * np.exp(-2j * np.pi * freq / sample_rate * idx))))


def encode_dtmf(keys: str, sample_rate: float = 8000.0, tone_ms: float = 100.0,
                gap_ms: float = 20.0, snr_db: float = 20.0, seed: int = 1) -> np.ndarray:
    """生成 DTMF 模拟帧 IQ：每键 100ms 双音 + 20ms 静音间隔，加高斯噪声。"""
    n_tone = int(sample_rate * tone_ms / 1000)
    n_gap = int(sample_rate * gap_ms / 1000)
    t = np.arange(n_tone) / sample_rate
    parts: list[np.ndarray] = []
    for ch in keys:
        row_f, col_f = MAP[ch]
        tone = 0.5 * np.sin(2 * np.pi * row_f * t) + 0.5 * np.sin(2 * np.pi * col_f * t)
        parts.append(tone)
        parts.append(np.zeros(n_gap))
    x = np.concatenate(parts)
    x /= (np.max(np.abs(x)) + 1e-12)
    rng = np.random.default_rng(seed)
    x = x + rng.standard_normal(x.size) * 10 ** (-snr_db / 20)
    return x.astype(complex)


def decode_dtmf(iq: np.ndarray, sample_rate: float, **params) -> str:
    """DTMF 完整解码，返回按键序列；无有效按键抛 ValueError。"""
    x = np.real(np.asarray(iq))
    n = x.size
    if n < FRAME:
        raise ValueError("信号太短，无法 DTMF 解码")
    threshold = params.get("threshold", THRESHOLD)
    ratio = params.get("peak_ratio", PEAK_RATIO)
    seq: list[str | None] = []
    for start in range(0, n - FRAME + 1, STEP):
        frame = x[start:start + FRAME]
        row_amp = np.array([goertzel_bin(frame, f, sample_rate) for f in ROW_FREQS])
        col_amp = np.array([goertzel_bin(frame, f, sample_rate) for f in COL_FREQS])
        best_r, best_c = float(row_amp.max()), float(col_amp.max())
        # 双音结构判据：行/列主峰必须超过阈值，且显著高于次峰（噪声无突出峰）
        if best_r < threshold or best_c < threshold:
            seq.append(None)
            continue
        row_second = float(np.sort(row_amp)[-2])
        col_second = float(np.sort(col_amp)[-2])
        if best_r < ratio * row_second or best_c < ratio * col_second:
            seq.append(None)
            continue
        seq.append(_KEYS[int(row_amp.argmax())][int(col_amp.argmax())])
    # 相邻帧去重 + 连续两帧一致才输出（一次按键持续多帧；噪声偶发帧不满足）
    out: list[str] = []
    prev: str | None = None
    streak = 0
    for k in seq:
        if k is None:
            prev, streak = None, 0
        elif k == prev:
            streak += 1
            if streak == 2:
                out.append(k)
        else:
            prev, streak = k, 1
    if not out:
        raise ValueError("DTMF 未检出有效按键")
    return "".join(out)
