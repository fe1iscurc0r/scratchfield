"""POCSAG 注册包装（Phase 6 · 既有解码器接入注册表）

把 Phase 3 既有的 POCSAG 解调链路（FSK + BCH(31,21) 纠错）包装成
DecoderProvider 注册进注册表，主流程无需感知其内部实现。
"""
from __future__ import annotations

import numpy as np

from ..pocsag import demodulate_and_decode
from .registry import DecodeResult, register_decoder


@register_decoder(
    "pocsag",
    description="POCSAG 寻呼（FSK + BCH 纠错）",
    demod_mode="fsk",
    sample_rate_hz=24000.0,
)
def decode_pocsag(iq: np.ndarray, sample_rate: float, **params) -> DecodeResult:
    """POCSAG 解调+解码：2400 baud FSK → 前导/同步 → BCH 纠错 → 消息。"""
    symbol_rate = float(params.get("symbol_rate", 2400.0))
    msgs = demodulate_and_decode(np.asarray(iq), sample_rate, symbol_rate)
    if not msgs:
        return DecodeResult(decoder="pocsag", success=False, message="未检出 POCSAG 消息")
    lines = [str(m) for m in msgs]
    return DecodeResult(
        decoder="pocsag",
        success=True,
        message=f"POCSAG 解码 {len(msgs)} 条消息: {'; '.join(lines)}",
        payload={"messages": lines},
    )
