"""IC-705 USB 声卡输入源（Phase 7 · 真机集成前置）

真机接入（任务 7.1）：
    IC-705 经 USB 以 USB Audio Class 枚举为系统声卡，输出**解调后的
    实音频流**（基带实信号，48kHz 单声道典型）。本类把该流包装成
    AudioFrame 供下游消费；射频频率（center_freq_hz）与 rsba1_adapter
    的 CI-V 频率保持一致，构造/读帧时过业余白名单校验（同一道闸门：
    rsba1_adapter.ic705_set_freq → civ_commands.assert_allowed_freq）。

依赖无关（硬约束）：
    本模块顶层不 import 任何音频采集库。采集后端两种接法——
    a) capture_fn 回调（推荐）：用户在适配器里实现，每次调用返回一段
       1D float 声卡采样。底层用 pyaudio / sounddevice / 系统命令皆可，
       本类不感知；本机未装音频库也能导入、离线/仿真链路照常工作。
    b) 无回调时懒加载 pyaudio（仅当已安装），从默认输入设备读取——
       import 失败抛 RuntimeError（人类可读），绝不静默空返回。

与 CI-V 的关系：本类只管音频流；频率设置/读取走 rsba1_adapter 的
ic705_set_freq/ic705_read_freq（同样白名单强制）。真机闭环时上层组合：
    1) rsba1_adapter.ic705_set_freq(freq)    → 设 VFO（白名单已强制）
    2) Ic705UsbAudioSource(capture_fn=...)   → 读该频率解调音频
    3) frame.to_iq() → decoders.decode_all() → 解码/告警
"""
from __future__ import annotations

import logging
from typing import Any, Callable

import numpy as np

from .base import AudioFrame, AudioSource
from .registry import register_source

logger = logging.getLogger(__name__)

_DEFAULT_SAMPLE_RATE = 48000.0    # IC-705 USB 声卡典型
_DEFAULT_CHUNK = 4096             # 单帧样本数


def _lazy_pyaudio_stream(chunk: int, rate: float, device_index: int | None = None):
    """懒加载 pyaudio 并打开输入流（仅当用户已安装）。

    device_index: pyaudio 输入设备索引；None = 系统默认输入设备。
    返回 (pyaudio_instance, stream)；任一失败抛 RuntimeError 人类可读错误。
    """
    try:
        import pyaudio  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "未安装 pyaudio，无法读取声卡。请 pip install pyaudio，或改用 "
            "capture_fn 回调注入采集后端（依赖无关设计）。") from e
    pa = pyaudio.PyAudio()
    try:
        kwargs = {"format": pyaudio.paFloat32, "channels": 1, "rate": int(rate),
                  "input": True, "frames_per_buffer": chunk}
        if device_index is not None:
            kwargs["input_device_index"] = device_index
        stream = pa.open(**kwargs)
    except Exception as e:
        pa.terminate()
        raise RuntimeError(f"打开输入设备失败: {e}") from e
    return pa, stream


@register_source
class Ic705UsbAudioSource(AudioSource):
    """IC-705 USB 声卡输入源。

    参数:
        capture_fn: 可选。采集回调 () -> np.ndarray（1D float 声卡样本）。
                    提供后本类不接触任何音频库（依赖无关）。未提供时懒加载
                    pyaudio 读取默认输入设备。
        sample_rate: 采样率（Hz），默认 48000（IC-705 USB 声卡典型）。
        center_freq_hz: 可选。IC-705 当前 VFO 频率；非 None 时构造即过
                        amateur_bands.assert_allowed_freq（与 rsba1_adapter
                        同一道白名单闸门）。
        device_index: 可选。pyaudio 输入设备索引（默认系统默认设备）。
        chunk: 单帧最大样本数，默认 4096。
    """

    name = "ic705"
    description = "IC-705 USB 声卡输入（capture 回调注入或懒加载 pyaudio）"

    def __init__(
        self,
        capture_fn: Callable[[], np.ndarray] | None = None,
        sample_rate: float = _DEFAULT_SAMPLE_RATE,
        center_freq_hz: float | None = None,
        device_index: int | None = None,
        chunk: int = _DEFAULT_CHUNK,
    ):
        if center_freq_hz is not None:
            from ..amateur_bands import assert_allowed_freq
            assert_allowed_freq(center_freq_hz)  # 白名单强制，与 rsba1_adapter 对齐
        self._capture_fn = capture_fn
        self.sample_rate = float(sample_rate)
        self.center_freq_hz = center_freq_hz
        self.device_index = device_index
        self.chunk = int(chunk)
        self._pa = None
        self._stream = None

    # ---- AudioSource 协议 ------------------------------------------
    def open(self) -> None:
        if self._capture_fn is None and self._pa is None:
            self._pa, self._stream = _lazy_pyaudio_stream(
                self.chunk, self.sample_rate, device_index=self.device_index)

    def close(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception as e:  # 关流失败不阻断
                logger.warning("关闭 pyaudio 流异常: %r", e)
            self._stream = None
        if self._pa is not None:
            try:
                self._pa.terminate()
            except Exception as e:
                logger.warning("终止 pyaudio 异常: %r", e)
            self._pa = None

    def read(self, max_samples: int | None = None) -> AudioFrame:
        if self._capture_fn is not None:
            samples = np.asarray(self._capture_fn(), dtype=float)
            if samples.size == 0:
                raise RuntimeError("capture_fn 返回空帧（无音频数据），请检查采集后端")
            if not np.all(np.isfinite(samples)):
                raise RuntimeError("capture_fn 返回含 NaN/Inf 的样本，请检查采集后端")
        else:
            if self._stream is None:
                raise RuntimeError("未 open()，请先 open() 或使用 with 语句")
            raw = self._stream.read(self.chunk, exception_on_overflow=False)
            samples = np.frombuffer(raw, dtype=np.float32).astype(np.float64)
        if max_samples is not None:
            samples = samples[:int(max_samples)]
        return AudioFrame(
            samples=samples,
            sample_rate=self.sample_rate,
            center_freq_hz=self.center_freq_hz,
            meta={"source": "ic705", "device_index": self.device_index},
        )

    def info(self) -> dict[str, Any]:
        base = super().info()
        base["sample_rate"] = self.sample_rate
        base["center_freq_hz"] = self.center_freq_hz
        base["backend"] = "capture_fn" if self._capture_fn is not None else "pyaudio(lazy)"
        return base
