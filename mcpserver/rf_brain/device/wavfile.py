"""WAV 文件回放源（Phase 7 · 离线输入/测试）

标准库 wave 实现，零第三方依赖。支持 16-bit PCM（单声道/立体声，
立体声取左声道），返回 AudioFrame。用于：真机录音回放、解码器回归测试、
CI 环境无声卡时的全链路验证。
"""
from __future__ import annotations

import wave
from pathlib import Path
from typing import Any

import numpy as np

from .base import AudioFrame, AudioSource
from .registry import register_source

_SUPPORTED_SAMPWIDTH = 2  # 16-bit PCM


@register_source
class WavFileSource(AudioSource):
    """WAV 文件输入源。

    参数:
        path: WAV 文件路径（.wav）。采样率/声道数取自文件头。
        center_freq_hz: 可选。该录音对应的射频频率；非 None 时须过
                        amateur_bands 白名单（构造时校验）。
    """

    name = "wav"
    description = "WAV 文件离线回放（标准库 wave，零依赖）"

    def __init__(self, path: str | Path, center_freq_hz: float | None = None):
        self.path = Path(path)
        if not self.path.is_file():
            raise FileNotFoundError(f"WAV 文件不存在: {self.path}")
        self.center_freq_hz = center_freq_hz
        if center_freq_hz is not None:
            from ..amateur_bands import assert_allowed_freq
            assert_allowed_freq(center_freq_hz)  # 白名单，与 rsba1_adapter 对齐
        self._wf: wave.Wave_read | None = None
        self._sample_rate = 0.0
        self._offset = 0

    # ---- AudioSource 协议 ------------------------------------------
    def open(self) -> None:
        if self._wf is not None:  # 重复 open 幂等：先释放旧句柄
            self.close()
        try:
            wf = wave.open(str(self.path), "rb")
        except wave.Error as e:
            raise RuntimeError(f"无法打开 WAV 文件 {self.path}: {e}") from e
        try:
            if wf.getsampwidth() != _SUPPORTED_SAMPWIDTH:
                raise RuntimeError(
                    f"仅支持 16-bit PCM WAV（sampwidth=2），实际 "
                    f"{wf.getsampwidth()}（{self.path}）")
            self._wf = wf
            self._sample_rate = float(wf.getframerate())
        except Exception:
            wf.close()  # 校验失败必须关闭句柄，避免泄漏
            raise

    def close(self) -> None:
        if self._wf is not None:
            self._wf.close()
            self._wf = None
        self._offset = 0

    def read(self, max_samples: int | None = None) -> AudioFrame:
        if self._wf is None:
            raise RuntimeError("未 open()，请先 open() 或使用 with 语句")
        n = self._wf.getnframes() - self._offset
        if n <= 0:
            raise StopIteration("WAV 已读完")
        if max_samples is not None:
            n = min(n, int(max_samples))
        raw = self._wf.readframes(n)
        self._offset += n
        arr = np.frombuffer(raw, dtype="<i2").astype(np.float64) / 32768.0
        if self._wf.getnchannels() > 1:
            arr = arr[:: self._wf.getnchannels()]  # 取左声道
        return AudioFrame(
            samples=arr,
            sample_rate=self._sample_rate,
            center_freq_hz=self.center_freq_hz,
            meta={"source": "wav", "path": str(self.path)},
        )

    def info(self) -> dict[str, Any]:
        base = super().info()
        base["path"] = str(self.path)
        base["center_freq_hz"] = self.center_freq_hz
        return base
