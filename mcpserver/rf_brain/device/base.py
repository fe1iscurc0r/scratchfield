"""IC-705 / SDR 输入抽象 · 音频源接口（Phase 7 · 真机集成前置）

=================================================================
接口文档（验收标准 4：IC-705 输入抽象接口文档完整）
=================================================================

设计目标
--------
Phase 1-6 的输入是 numpy 仿真复数 IQ（sensor.generate_iq）。真机阶段
IC-705 通过 USB 以 USB Audio Class 枚举成"声卡"，输出的是**解调后的
实音频流**（基带实信号，典型 48kHz 单声道）。本包把"实音频帧"抽象成
统一输入源，主流程只消费 AudioSource.read() → AudioFrame，不感知后端。

架构（provider 注册表，与 decoders/ 注册表同构）
--------------------------------------------------
    device/                  # 本包
    ├── base.py              # AudioFrame / AudioSource / iq_from_audio（本文件）
    ├── registry.py          # register_source / create_source / list_sources
    ├── ic705.py             # Ic705UsbAudioSource —— IC-705 USB 声卡后端
    ├── wavfile.py           # WavFileSource —— WAV 文件离线回放（测试/回放）
    └── sim.py               # SimulatedSource —— numpy 仿真注入（延续 Phase 1-6）

数据流
------
    采集后端(USB声卡/WAV/仿真) → AudioSource.read() → AudioFrame
        → frame.to_iq()（实音频→复基带，Hilbert）→ decoders.decode_all(iq, sr)
    主流程零改动：新增输入后端 = 新模块 + 一行 @register_source。

设计约束（本包不可违背）
------------------------
1. 依赖无关：本包顶层禁止 import pyaudio / sounddevice / soundcard 等任何
   音频采集库。真实采集后端通过 AudioSource 构造时注入的 capture 回调接入；
   本机未装音频库时包仍可导入，离线源（WAV / 仿真）照常可用。
2. 频段白名单：任何携带射频频率的源（center_freq_hz），构造/校验时必须过
   amateur_bands.assert_allowed_freq（业余频段，与 rsba1_adapter 对齐——
   rsba1_adapter.ic705_set_freq 同走 civ_commands.assert_allowed_freq）。
3. 主流程只消费 create_source(kind, **kw)，禁止硬编码后端分支。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, ClassVar

import numpy as np


def iq_from_audio(x: np.ndarray, sample_rate: float) -> np.ndarray:
    """实音频 → 复基带（analytic signal，Hilbert 单边带）。

    声卡输出是实信号，AFSK/BPSK 相位解调需要复数。用 FFT 构造解析信号：
    正频率分量加倍、负频率清零，把实谱折叠成复基带 IQ。DTMF/POCSAG 等
    仅需幅度的协议对 IQ 同样适用（解码器内部取实部，见 decoders/dtmf.py）。

    参数:
        x: 1D float 实音频样本（-1.0 ~ 1.0）。
        sample_rate: 采样率（Hz），仅用于文档标注，不影响变换本身。

    返回:
        complex ndarray，长度 = x.size。实部 = 原始信号，虚部 = Hilbert 变换。
    """
    x = np.asarray(x, dtype=float)
    n = x.size
    if n == 0:
        return np.zeros(0, dtype=complex)
    X = np.fft.fft(x)
    H = np.zeros(n)
    H[0] = 1.0                      # DC 保持
    if n % 2 == 0:
        H[1:n // 2] = 2.0           # 正频加倍（Nyquist bin 保持 1）
        H[n // 2] = 1.0
    else:
        H[1:(n + 1) // 2] = 2.0
    return np.fft.ifft(X * H)


@dataclass(frozen=True)
class AudioFrame:
    """一帧音频输入（输入抽象的统一定义，主流程唯一消费形态）。

    属性:
        samples:      1D float 实音频样本（声卡标称幅度 -1.0 ~ 1.0）。
        sample_rate:  采样率（Hz）。IC-705 USB 声卡典型 48000。
        center_freq_hz: 射频中心频率（Hz），即 IC-705 当前 VFO 频率；
                      None = 不涉及射频（WAV/仿真回放）。非 None 时必须
                     在业余频段白名单内（各后端在构造时经
                     assert_allowed_freq 校验；若直接构造 AudioFrame，
                     由调用方自行保证）。
        meta:         附加元数据（时间戳、IC-705 模式/滤波器、源名称等）。

    方法:
        to_iq():      实音频 → 复基带 IQ（analytic signal），可直接喂
                      decoders.decode / decode_all。
    """
    samples: np.ndarray
    sample_rate: float
    center_freq_hz: float | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_iq(self) -> np.ndarray:
        """转复基带 IQ（Hilbert），供解码器注册表消费。"""
        return iq_from_audio(self.samples, self.sample_rate)

    def info(self) -> dict[str, Any]:
        """人类可读的帧摘要（日志/调试用）。"""
        return {
            "samples": int(self.samples.size),
            "duration_s": round(self.samples.size / self.sample_rate, 4),
            "sample_rate": float(self.sample_rate),
            "center_freq_hz": self.center_freq_hz,
            "meta": self.meta,
        }


class AudioSource(ABC):
    """音频输入源抽象基类。所有后端（USB 声卡 / WAV / 仿真）实现同一协议。

    生命周期: open() → read()* → close()。支持 with 语句（__enter__/__exit__
    自动 open/close）。

    新增后端 = 继承本类 + 实现 name/description/open/close/read + 一行
    @register_source 装饰器（见 registry.py），主流程零改动。
    """

    name: ClassVar[str] = "base"                 # 注册名（工厂键）
    description: ClassVar[str] = ""              # 人类可读描述

    @abstractmethod
    def open(self) -> None:
        """打开采集后端（声卡设备 / 文件句柄 / 仿真预热）。失败抛 RuntimeError。"""

    @abstractmethod
    def close(self) -> None:
        """释放后端资源。幂等，close() 后可再次 open()。"""

    @abstractmethod
    def read(self, max_samples: int | None = None) -> AudioFrame:
        """读取一帧音频。

        参数:
            max_samples: 单帧最大样本数（None = 后端默认整块）。对连续流，
                         后端应内部切块，保证单帧不超限。
        返回:
            AudioFrame。EOF 时抛 StopIteration。
        """

    def info(self) -> dict[str, Any]:
        """后端静态信息（设备/文件描述、采样率等）。"""
        return {"name": self.name, "description": self.description}

    # ---- with 支持 -------------------------------------------------
    def __enter__(self) -> "AudioSource":
        self.open()
        return self

    def __exit__(self, *exc) -> None:
        self.close()
