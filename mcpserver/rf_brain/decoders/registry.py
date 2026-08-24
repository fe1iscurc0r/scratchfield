"""解码器注册表（Phase 6 · provider 模式）

架构（参考 dsh 的 bundle 插件声明式注册）：
- 每个解码器 = 一个 DecoderProvider，通过 @register_decoder 声明式注册
- 主流程只消费注册表（decode_all 泛型遍历），不感知具体协议
- 新增协议：新写一个模块 + 一行装饰器注册即可，主流程零改动

禁止在主流程写 if/elif 协议分支——这是本注册表存在的意义。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np


@dataclass(frozen=True)
class DecodeResult:
    """单解码器输出。"""
    decoder: str                 # 注册名（如 "aprs"/"psk31"/"dtmf"/"pocsag"）
    success: bool
    message: str                 # 人类可读结果或失败原因
    payload: dict[str, Any] | None = None


@dataclass(frozen=True)
class DecoderProvider:
    """注册表条目：解码器元数据 + 可调用体。"""
    name: str
    description: str
    demod_mode: str              # afsk / bpsk / dtmf / fsk ...（供上层调度参考）
    decode_fn: Callable[..., DecodeResult]
    sample_rate_hz: float | None = None   # 建议采样率（None = 任意）


_DECODERS: dict[str, DecoderProvider] = {}


def register_decoder(name: str | None = None, *, description: str = "",
                     demod_mode: str = "raw", sample_rate_hz: float | None = None):
    """声明式注册装饰器：把 decode 函数登记进全局注册表。

    用法：
        @register_decoder("aprs", description="APRS/AX.25 AFSK1200", demod_mode="afsk")
        def decode(iq, sample_rate, **params): ...
    """
    def wrap(fn: Callable) -> Callable:
        key = name or fn.__name__
        if key in _DECODERS:
            raise ValueError(f"解码器重复注册: {key}")
        _DECODERS[key] = DecoderProvider(
            name=key, description=description, demod_mode=demod_mode,
            decode_fn=fn, sample_rate_hz=sample_rate_hz,
        )
        return fn
    return wrap


def list_decoders() -> list[str]:
    """已注册解码器名单（按注册顺序）。"""
    return list(_DECODERS)


def unregister_decoder(name: str) -> bool:
    """注销一个解码器（幂等）：不存在返回 False，成功注销返回 True。

    主要用于测试隔离/动态接入场景——显式注册的解码器（如 sdrtrunk
    sidecar）测试完毕必须注销，避免污染全局注册表破坏 P6 四解码器集合。
    """
    return _DECODERS.pop(name, None) is not None


def get_decoder(name: str) -> DecoderProvider:
    if name not in _DECODERS:
        raise KeyError(f"未注册的解码器: {name}，可选: {list_decoders()}")
    return _DECODERS[name]


def decode(name: str, iq: np.ndarray, sample_rate: float, **params: Any) -> DecodeResult:
    """按注册名调用单个解码器；未注册或抛异常都转成失败的 DecodeResult。"""
    try:
        provider = get_decoder(name)
    except KeyError as e:
        return DecodeResult(decoder=name, success=False, message=str(e))
    try:
        return provider.decode_fn(np.asarray(iq), sample_rate, **params)
    except Exception as e:  # 解码器内部异常不向外抛——主流程必须健壮
        return DecodeResult(decoder=name, success=False, message=f"解码异常: {e!r}")


def decode_all(iq: np.ndarray, sample_rate: float, **params: Any) -> list[DecodeResult]:
    """主流程泛型入口：对注册表内全部解码器逐一尝试，无任何协议分支。

    新增协议 = 新模块 + @register_decoder 一行注册；此函数与主流程无需改动。
    """
    return [decode(name, np.asarray(iq), sample_rate, **params)
            for name in list_decoders()]
