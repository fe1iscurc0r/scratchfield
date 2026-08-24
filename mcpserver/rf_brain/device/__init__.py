"""IC-705 / SDR 输入抽象（Phase 7 · 真机集成前置）

导入本包即注册全部输入源（ic705 / wav / sim）。主流程只消费
create_source(kind, **kw) → AudioSource.read() → AudioFrame，
不感知具体后端——provider 注册表模式，与 decoders/ 注册表同构。

新增输入后端 = 新模块（继承 AudioSource + 实现协议）+ 一行
@register_source 注册，主流程零改动。

依赖无关：本包顶层不 import 任何音频采集库（pyaudio/sounddevice 均不
强依赖）；本机无音频库时包仍可导入，离线源（WAV / 仿真）照常可用。
"""
from __future__ import annotations

from . import ic705, sim, wavfile  # noqa: F401  触发注册
from .base import AudioFrame, AudioSource, iq_from_audio
from .registry import create_source, list_sources, register_source

__all__ = [
    "AudioFrame", "AudioSource", "iq_from_audio",
    "create_source", "list_sources", "register_source",
    "ic705", "wavfile", "sim",
]
