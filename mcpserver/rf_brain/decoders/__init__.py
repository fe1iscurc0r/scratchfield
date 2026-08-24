"""多协议解码器库（Phase 6 · provider 注册表）

导入本包即触发全部解码器注册（aprs / psk31 / dtmf / pocsag）。
主流程只消费 registry 的 decode / decode_all / list_decoders，
不感知具体协议——注册表模式，禁止在主流程写协议分支。

新增协议 = 新模块（提供纯算法 decode 函数）+ 本文件一行 @register_decoder 包装。
各解码器模块保持协议算法纯净（抛 ValueError），注册包装统一转成
DecodeResult，异常不外泄——主流程必须健壮。
"""
from __future__ import annotations

import numpy as np

from . import aprs, psk31, dtmf, pocsag_wrapper  # noqa: F401
from .registry import (
    DecodeResult,
    DecoderProvider,
    decode,
    decode_all,
    get_decoder,
    list_decoders,
    register_decoder,
    unregister_decoder,
)


@register_decoder(
    "aprs",
    description="APRS/AX.25 UI（AFSK1200 · Bell 202）",
    demod_mode="afsk",
    sample_rate_hz=48000.0,
)
def _decode_aprs(iq: np.ndarray, sample_rate: float, **params) -> DecodeResult:
    try:
        text = aprs.decode_afsk1200(np.asarray(iq), sample_rate, **params)
    except ValueError as e:
        return DecodeResult(decoder="aprs", success=False, message=str(e))
    return DecodeResult(decoder="aprs", success=True, message=text,
                        payload={"text": text})


@register_decoder(
    "psk31",
    description="PSK31（31.25bd BPSK + Varicode）",
    demod_mode="bpsk",
    sample_rate_hz=8000.0,
)
def _decode_psk31(iq: np.ndarray, sample_rate: float, **params) -> DecodeResult:
    try:
        text = psk31.decode_psk31(np.asarray(iq), sample_rate, **params)
    except ValueError as e:
        return DecodeResult(decoder="psk31", success=False, message=str(e))
    return DecodeResult(decoder="psk31", success=True, message=text,
                        payload={"text": text})


@register_decoder(
    "dtmf",
    description="DTMF 双音多频（Goertzel）",
    demod_mode="dtmf",
    sample_rate_hz=8000.0,
)
def _decode_dtmf(iq: np.ndarray, sample_rate: float, **params) -> DecodeResult:
    try:
        keys = dtmf.decode_dtmf(np.asarray(iq), sample_rate, **params)
    except ValueError as e:
        return DecodeResult(decoder="dtmf", success=False, message=str(e))
    return DecodeResult(decoder="dtmf", success=True, message=keys,
                        payload={"digits": keys})


__all__ = [
    "DecodeResult", "DecoderProvider", "decode", "decode_all",
    "get_decoder", "list_decoders", "register_decoder",
    "unregister_decoder",
    "aprs", "psk31", "dtmf", "pocsag_wrapper",
]
