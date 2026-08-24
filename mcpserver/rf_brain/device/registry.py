"""输入源注册表（Phase 7 · provider 模式，与 decoders/registry.py 同构）

- 每个输入后端 = 一个 AudioSource 子类，通过 @register_source 声明式注册
- 主流程只消费 create_source(kind, **kw)，不感知具体后端
- 新增后端 = 新模块 + 一行注册，主流程零改动
"""
from __future__ import annotations

from typing import Callable

from .base import AudioSource

_SOURCES: dict[str, type[AudioSource]] = {}


def register_source(cls: type[AudioSource]) -> type[AudioSource]:
    """类装饰器：把 AudioSource 子类登记进全局注册表（按 cls.name）。"""
    key = cls.name
    if key in _SOURCES:
        raise ValueError(f"输入源重复注册: {key}")
    _SOURCES[key] = cls
    return cls


def list_sources() -> list[str]:
    """已注册输入源名单（按注册顺序）。"""
    return list(_SOURCES)


def create_source(kind: str, **kwargs) -> AudioSource:
    """工厂：按注册名构造输入源。

    参数:
        kind: 注册名（"ic705" / "wav" / "sim"）。
        kwargs: 传给后端构造函数（如 wav 的 path、ic705 的 capture_fn）。

    返回:
        未 open 的 AudioSource 实例（由调用方 open() 后 read()）。

    异常:
        KeyError - 未注册的后端名。
    """
    if kind not in _SOURCES:
        raise KeyError(f"未注册的输入源: {kind}，可选: {list_sources()}")
    return _SOURCES[kind](**kwargs)
