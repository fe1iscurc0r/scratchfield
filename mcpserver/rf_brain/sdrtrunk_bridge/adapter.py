"""sdrtrunk sidecar · rf_brain 解码链接入适配（W-01）

把 sdrtrunk_bridge 注册进 Phase6 解码器注册表（provider 模式）：
- 本模块默认**不自动注册**（保持既有 4 解码器集合稳定，回归测试
  test_phase6 断言 list_decoders == {aprs,psk31,dtmf,pocsag}）。
- 上层（真机/云服）显式调用 register_sdrtrunk_decoder() 完成接入，
  注册后 decode_all() 泛型遍历自动尝试 sdrtrunk，主流程零改动。

设计要点（对齐 decoders/registry.py 契约）：
- decode_fn 签名 (iq, sample_rate, **params) → DecodeResult
- sdrtrunk 是 JVM 进程，输入不是 numpy 符号流而是音频文件；
  因此本适配器约定：通过 params["audio_path"] 传入 WAV 音频文件路径，
  由桥解码后把事件折叠成一条 DecodeResult（payload 携带全部事件）。
- 未给 audio_path 时返回 success=False（“跳过”语义），绝不抛异常。
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from ..decoders.registry import DecodeResult, register_decoder
from .bridge import SdrtrunkBridge, SdrtrunkBridgeError

_REGISTERED = False


def decode_sdrtrunk(iq: np.ndarray, sample_rate: float, **params) -> DecodeResult:
    """通过 sdrtrunk 桥解码商业制式。

    params:
        audio_path: WAV 音频文件路径（必填，否则视为跳过）
        mode: "simulate"（默认）/ "live"
    """
    audio_path = params.get("audio_path")
    if not audio_path:
        return DecodeResult(
            decoder="sdrtrunk",
            success=False,
            message="跳过：未提供 audio_path（sdrtrunk 需 JVM + 音频文件输入）",
        )
    if not Path(audio_path).is_file():
        return DecodeResult(
            decoder="sdrtrunk",
            success=False,
            message=f"音频文件不存在: {audio_path}",
        )
    mode = params.get("mode", "simulate")
    try:
        bridge = SdrtrunkBridge(mode=mode, audio_path=audio_path,
                                sample_rate=int(params.get("sample_rate", 48000)))
        events = bridge.decode_all()
    except SdrtrunkBridgeError as e:
        return DecodeResult(decoder="sdrtrunk", success=False, message=str(e))
    payload = {"events": [ev.to_dict() for ev in events],
               "n_events": len(events)}
    detail = "; ".join(f"{ev.protocol}:{ev.event_type}" for ev in events) or "无事件"
    return DecodeResult(
        decoder="sdrtrunk",
        success=len(events) > 0,
        message=f"sdrtrunk 解码 {len(events)} 条事件: {detail}",
        payload=payload,
    )


def register_sdrtrunk_decoder() -> str:
    """显式注册 sdrtrunk 解码器进注册表（幂等）。

    返回注册名 "sdrtrunk"。接入后 decode_all() 会尝试解码 sdrtrunk。
    """
    global _REGISTERED
    if not _REGISTERED:
        register_decoder(
            "sdrtrunk",
            description="sdrtrunk sidecar（JVM）P25/DMR/NXDN 商业制式解码桥",
            demod_mode="raw",
        )(decode_sdrtrunk)
        _REGISTERED = True
    return "sdrtrunk"


__all__ = ["decode_sdrtrunk", "register_sdrtrunk_decoder",
           "SdrtrunkBridge", "SdrtrunkBridgeError"]
