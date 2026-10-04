"""sentinel_link —— LoRaCanary 节点接入 rf_brain 的哨兵网格软件层（卷187）。

模块分工::

    protocol.py     Sentinel-Link v1 协议：帧编解码 + CRC32 + 配置校验（纯 stdlib）
    simulator.py    节点模拟器：N 节点频谱扫描 + 占用事件注入 + chaos 注入
    gateway.py      网关：serial/TCP/file 三源消费 → CRC/去重/重排 → SQLite + EventBus
    occupation.py   占用事件检测（同频点持续高 RSSI）→ 发 sentinel.occupation
    README.md       面向节点固件的协议规范（字段冻结）

无硬件依赖：全部可用模拟器端到端验证（板子 v1.1 打样中）。
"""
from __future__ import annotations

from .protocol import EnvSample, ScanBin, SentinelProtocolError, decode, decode_frame, encode_frame

__all__ = [
    "EnvSample",
    "ScanBin",
    "SentinelProtocolError",
    "decode",
    "decode_frame",
    "encode_frame",
]
