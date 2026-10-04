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

from . import (  # noqa: F401  # noqa: F401
    aprs,
    dtmf,
    ft4,
    ft8,
    ook,  # noqa: F401
    pocsag_wrapper,
    psk31,
    sstv,
    wspr,
)
from .ook import acurite, kerui, nexus, pulse_demod  # noqa: F401
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


# --------------------------------------------------------------------------- #
# OOK 433MHz 传感器解码器（脉冲序列输入）
#
# 与 IQ 调制解码器不同：OOK 解码的输入是「脉冲序列」（固件在 SX1278 包络层
# 已提取好），通过 params["pulses"] 传入；不传 pulses 时退回对 IQ 做包络提取。
# 成功判据 = 帧校验通过（acurite 加和+偶校验、nexus const nibble、kerui 无校验
# 故单帧不判成功，由固件层 25 次重复帧一致性确认）。
# --------------------------------------------------------------------------- #

def _ook_pulses(iq: np.ndarray, sample_rate: float, params: dict):
    """取脉冲序列：优先 params["pulses"]，否则对 IQ 做包络提取。"""
    pulses = params.get("pulses")
    if pulses is None:
        pulses = pulse_demod.extract_pulses(np.asarray(iq), sample_rate)
    return pulses


@register_decoder(
    "acurite",
    description="Acurite 592TXR/Tower 温湿度（OOK-PWM 56bit）",
    demod_mode="ook",
    sample_rate_hz=250000.0,
)
def _decode_acurite(iq: np.ndarray, sample_rate: float, **params) -> DecodeResult:
    try:
        data = acurite.decode_acurite_pulses(_ook_pulses(iq, sample_rate, params))
    except ValueError as e:
        return DecodeResult(decoder="acurite", success=False, message=str(e))
    ok = data["crc_ok"] is True
    msg = (f"acurite id={data['id']} ch={data['channel']} "
           f"T={data['temperature']}C H={data['humidity']}% "
           f"bat={data['battery']}") if ok else "acurite 校验失败"
    return DecodeResult(decoder="acurite", success=ok, message=msg, payload=data)


@register_decoder(
    "nexus",
    description="Nexus TH 温湿度（OOK-PPM 36bit）",
    demod_mode="ook",
    sample_rate_hz=250000.0,
)
def _decode_nexus(iq: np.ndarray, sample_rate: float, **params) -> DecodeResult:
    try:
        data = nexus.decode_nexus_pulses(_ook_pulses(iq, sample_rate, params))
    except ValueError as e:
        return DecodeResult(decoder="nexus", success=False, message=str(e))
    ok = data["crc_ok"] is True
    msg = (f"nexus id={data['id']} ch={data['channel']} "
           f"T={data['temperature']}C H={data['humidity']}% "
           f"bat={data['battery']}") if ok else "nexus const nibble 校验失败"
    return DecodeResult(decoder="nexus", success=ok, message=msg, payload=data)


@register_decoder(
    "kerui",
    description="Kerui/EV1527 门磁·PIR·遥控（OOK-PWM 24bit）",
    demod_mode="ook",
    sample_rate_hz=250000.0,
)
def _decode_kerui(iq: np.ndarray, sample_rate: float, **params) -> DecodeResult:
    try:
        data = kerui.decode_kerui_pulses(_ook_pulses(iq, sample_rate, params))
    except ValueError as e:
        return DecodeResult(decoder="kerui", success=False, message=str(e))
    # EV1527 无校验位，单帧无法确认——由固件层重复帧一致性投票确认
    msg = (f"kerui id={data['id']} cmd={data['cmd']}"
           if data["crc_ok"] is True else
           "kerui 无校验位（需重复帧一致性确认）")
    return DecodeResult(decoder="kerui", success=data["crc_ok"] is True,
                        message=msg, payload=data)


# --------------------------------------------------------------------------- #
# WSPR / FT8 弱信号模式（K1JT 协议族）
# --------------------------------------------------------------------------- #

@register_decoder(
    "wspr",
    description="WSPR 弱信号传播报告（4-FSK + K=32 卷积码，162 符号）",
    demod_mode="fsk",
    sample_rate_hz=12000.0,
)
def _decode_wspr(iq: np.ndarray, sample_rate: float, **params) -> DecodeResult:
    try:
        info = wspr.decode_wspr(np.asarray(iq), sample_rate, **params)
    except ValueError as e:
        return DecodeResult(decoder="wspr", success=False, message=str(e))
    return DecodeResult(
        decoder="wspr",
        success=True,
        message=(f"wspr {info['callsign']} {info['grid']} "
                 f"{info['power_dbm']}dBm snr={info['snr_db']}dB"),
        payload=info,
    )


@register_decoder(
    "ft8",
    description="FT8 弱信号数字模式（8-GFSK + LDPC(174,91) + CRC14，79 符号）",
    demod_mode="fsk",
    sample_rate_hz=12000.0,
)
def _decode_ft8(iq: np.ndarray, sample_rate: float, **params) -> DecodeResult:
    try:
        info = ft8.decode_ft8(np.asarray(iq), sample_rate, **params)
    except ValueError as e:
        return DecodeResult(decoder="ft8", success=False, message=str(e))
    return DecodeResult(
        decoder="ft8",
        success=True,
        message="; ".join(str(d) for d in info["decodes"]),
        payload=info,
    )


@register_decoder(
    "ft4",
    description="FT4 弱信号数字模式（4-GFSK + LDPC(174,91) + CRC14，105 符号，骨架）",
    demod_mode="fsk",
    sample_rate_hz=24000.0,
)
def _decode_ft4(iq: np.ndarray, sample_rate: float, **params) -> DecodeResult:
    try:
        info = ft4.decode_ft4(np.asarray(iq), sample_rate, **params)
    except ValueError as e:
        return DecodeResult(decoder="ft4", success=False, message=str(e))
    return DecodeResult(
        decoder="ft4",
        success=True,
        message="; ".join(str(d) for d in info["decodes"]),
        payload=info,
    )


# --------------------------------------------------------------------------- #
# SSTV 慢扫描电视（音频输入，输出灰度图 PNG）
# --------------------------------------------------------------------------- #

@register_decoder(
    "sstv",
    description="SSTV 慢扫描电视（VIS 识别 + 行解码 → PIL 灰度图 PNG）",
    demod_mode="fm",
    sample_rate_hz=None,
)
def _decode_sstv(iq: np.ndarray, sample_rate: float, **params) -> DecodeResult:
    # SSTV 走音频（实数）输入；IQ 复信号只取实部兼容
    audio = np.real(np.asarray(iq))
    out_dir = params.pop("out_dir", None)
    try:
        info = sstv.decode_sstv(audio, float(sample_rate), out_dir=out_dir)
    except ValueError as e:
        return DecodeResult(decoder="sstv", success=False, message=str(e))
    return DecodeResult(
        decoder="sstv",
        success=True,
        message=f"sstv {info['mode']} {info['width']}x{info['height']} → {info['png']}",
        payload=info,
    )


__all__ = [
    "DecodeResult", "DecoderProvider", "decode", "decode_all",
    "get_decoder", "list_decoders", "register_decoder",
    "unregister_decoder",
    "aprs", "psk31", "dtmf", "pocsag_wrapper", "ook",
    "wspr", "ft8", "sstv", "ft4",
]
