"""sdrtrunk sidecar（W-01）· rf_brain P6 多协议解码桥

sdrtrunk（JVM）→ 结构化 JSON → mcpserver 工具总线。

模块:
- schema.py   统一事件 JSON schema（协议无关 + payload 协议细节）
- bridge.py   JVM 子进程桥 / 模拟桥（simulate 模式供无 JVM 环境验收）
- adapter.py  可选注册进 Phase6 解码器注册表（默认不注册，保持既有集合稳定）
"""
from __future__ import annotations

from .bridge import SdrtrunkBridge, SdrtrunkBridgeError, simulate_decode, validate_required_fields
from .schema import (
    EVENT_TYPES,
    REQUIRED_FIELDS,
    SCHEMA_NAME,
    SCHEMA_VERSION,
    SUPPORTED_PROTOCOLS,
    SdrtrunkEvent,
    parse_json_line,
    validate_event,
)

__all__ = [
    "SdrtrunkBridge", "SdrtrunkBridgeError", "simulate_decode",
    "validate_required_fields", "SdrtrunkEvent", "parse_json_line",
    "validate_event", "REQUIRED_FIELDS", "SUPPORTED_PROTOCOLS",
    "EVENT_TYPES", "SCHEMA_NAME", "SCHEMA_VERSION",
]
