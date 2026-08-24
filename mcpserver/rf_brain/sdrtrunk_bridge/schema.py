"""sdrtrunk sidecar · 统一事件 JSON schema（W-01）

sdrtrunk（JVM）解码 P25/DMR/NXDN 商业制式后，经 sidecar 桥把解码事件
归一化为本模块定义的统一 JSON schema，供 mcpserver 工具总线消费。

本 schema 与 rf_brain 既有 Phase6 numpy 解码链互补：
- 纯 numpy 解码器（aprs/psk31/dtmf/pocsag）→ DecodeResult（decoders/registry.py）
- 商业制式（P25/DMR，需 JVM）→ SdrtrunkEvent（本模块）

设计原则：协议无关。payload 内保留协议细节（NAC/CC/TG/unit/加密标志），
顶层字段全部协议无关，方便下游（决策层/总线）无脑消费。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

SCHEMA_NAME = "sdrtrunk-event"
SCHEMA_VERSION = "1.0"

# 验收断言所需的必填字段（grep/assert 目标）
REQUIRED_FIELDS = (
    "schema", "version", "source", "ts",
    "protocol", "event_type", "frequency_hz",
    "talkgroup", "from_radio", "to_alias", "details", "payload",
)

# sdrtrunk 支持的协议（sdrtrunk 官方 wiki：P25P1/P25P2/DMR/NXDN/LTR/MPT1327 等）
SUPPORTED_PROTOCOLS = ("P25P1", "P25P2", "DMR", "NXDN", "LTR", "MPT1327")

# 事件类型：对齐 sdrtrunk CallEvent 语义（CallEvents wiki 表格）
EVENT_TYPES = (
    "call_start", "call_end", "group_call", "call_alert", "emergency",
    "encrypted_call", "message", "frame", "register", "status", "error",
)


@dataclass
class SdrtrunkEvent:
    """统一解码事件。

    顶层字段协议无关；payload 装协议细节。
    """
    protocol: str                       # P25P1 / P25P2 / DMR / NXDN ...
    event_type: str                     # call_start / frame / message ...
    frequency_hz: int                   # 信道频率
    ts: str                             # ISO8601
    details: str = ""                   # 人类可读描述
    talkgroup: int | None = None        # TGID（组呼）
    from_radio: int | None = None       # 来源电台 ID
    to_alias: str | None = None         # 目标别名（若有）
    payload: dict[str, Any] = field(default_factory=dict)  # 协议细节
    source: str = "sdrtrunk"
    schema: str = SCHEMA_NAME
    version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["schema"] = self.schema
        d["version"] = self.version
        d["source"] = self.source
        return d

    def to_json(self, **kw: Any) -> str:
        import json
        kw.setdefault("ensure_ascii", False)
        kw.setdefault("sort_keys", True)
        return json.dumps(self.to_dict(), **kw)


def validate_event(ev: dict[str, Any]) -> tuple[bool, str]:
    """字段完整性校验（验收断言用）。

    返回 (ok, 缺失字段列表)。
    """
    missing = [f for f in REQUIRED_FIELDS if f not in ev]
    if missing:
        return False, f"缺失字段: {missing}"
    if ev.get("protocol") not in SUPPORTED_PROTOCOLS:
        return False, f"未知协议: {ev.get('protocol')!r}"
    if ev.get("event_type") not in EVENT_TYPES:
        return False, f"未知事件类型: {ev.get('event_type')!r}"
    return True, "ok"


def parse_json_line(line: str) -> SdrtrunkEvent | None:
    """解析单行 JSON 事件；非 JSON 行返回 None（桥容忍日志噪音）。"""
    import json
    try:
        data = json.loads(line)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict) or data.get("schema") != SCHEMA_NAME:
        return None
    try:
        return SdrtrunkEvent(
            protocol=str(data["protocol"]),
            event_type=str(data["event_type"]),
            frequency_hz=int(data["frequency_hz"]),
            ts=str(data["ts"]),
            details=str(data.get("details", "")),
            talkgroup=data.get("talkgroup"),
            from_radio=data.get("from_radio"),
            to_alias=data.get("to_alias"),
            payload=data.get("payload") or {},
        )
    except (KeyError, TypeError, ValueError):
        return None
