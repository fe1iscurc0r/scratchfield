"""仿真注入源（Phase 7 · 延续 Phase 1-6 的 numpy 仿真输入）

把 Phase 6 解码器的"音频域仿真生成器"包装成 AudioSource，使既有仿真
信号无缝进入新输入抽象（read → to_iq → decode_all）。默认合成 DTMF
拨号串（decoders/dtmf.encode_dtmf 本就是实音频），可注入自定义
gen_fn 合成 APRS/PSK31/POCSAG 音频帧。
"""
from __future__ import annotations

from typing import Any, Callable

import numpy as np

from ..decoders import dtmf as _dtmf
from .base import AudioFrame, AudioSource
from .registry import register_source

_DEFAULT_DIGITS = "12345"


def _default_gen(sample_rate: float, n: int, digits: str, snr_db: float, seed: int) -> np.ndarray:
    """默认帧生成器：DTMF 拨号串 + 高斯噪声（返回 real float 音频）。

    n: 请求样本数。合成结果超出时截断到 n（保证 AudioSource.read 的
    max_samples / duration_s 契约成立）。
    """
    iq = _dtmf.encode_dtmf(digits, sample_rate=sample_rate, snr_db=snr_db, seed=seed)
    x = np.real(iq)
    return x[:n] if x.size > n else x


@register_source
class SimulatedSource(AudioSource):
    """numpy 仿真注入源（无真实硬件时验证全链路）。

    参数:
        gen_fn: 可选。帧生成回调 gen_fn(sample_rate, n_samples) -> 1D float
                ndarray（一段实音频）。默认合成 DTMF "12345"。
        sample_rate: 采样率（Hz），默认 8000（DTMF/PSK31 域）。
        duration_s: 每帧时长（秒），默认 2.0。
        center_freq_hz: 可选。仿真对应的射频频率；非 None 时过白名单校验。
        seed: 噪声随机种子（可复现）。
    """

    name = "sim"
    description = "numpy 仿真注入源（默认 DTMF 拨号，可注入自定义 gen_fn）"

    def __init__(
        self,
        gen_fn: Callable[[float, int], np.ndarray] | None = None,
        sample_rate: float = 8000.0,
        duration_s: float = 2.0,
        center_freq_hz: float | None = None,
        seed: int = 1,
        digits: str = _DEFAULT_DIGITS,
        snr_db: float = 20.0,
    ):
        if center_freq_hz is not None:
            from ..amateur_bands import assert_allowed_freq
            assert_allowed_freq(center_freq_hz)  # 白名单，与 rsba1_adapter 对齐
        self._gen_fn = gen_fn or (lambda sr, n: _default_gen(sr, n, digits, snr_db, seed))
        self.sample_rate = float(sample_rate)
        self.duration_s = float(duration_s)
        self.center_freq_hz = center_freq_hz
        self._n = max(1, int(self.sample_rate * self.duration_s))

    # ---- AudioSource 协议 ------------------------------------------
    def open(self) -> None:
        pass  # 无资源，幂等

    def close(self) -> None:
        pass

    def read(self, max_samples: int | None = None) -> AudioFrame:
        n = self._n if max_samples is None else min(self._n, int(max_samples))
        samples = np.asarray(self._gen_fn(self.sample_rate, n), dtype=float)
        if samples.size == 0:
            raise RuntimeError("gen_fn 返回空帧（无音频数据），请检查仿真生成器")
        if not np.all(np.isfinite(samples)):
            raise RuntimeError("gen_fn 返回含 NaN/Inf 的样本，请检查仿真生成器")
        return AudioFrame(
            samples=samples,
            sample_rate=self.sample_rate,
            center_freq_hz=self.center_freq_hz,
            meta={"source": "sim", "duration_s": self.duration_s},
        )

    def info(self) -> dict[str, Any]:
        base = super().info()
        base["sample_rate"] = self.sample_rate
        base["center_freq_hz"] = self.center_freq_hz
        return base
