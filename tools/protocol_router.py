"""R44 轻量协议路由器（Routed Graph Handoff 授粉 · 结构化/自然语言自适应选择）

来源授粉点：2608.25277v1（Routed Graph Handoff）——155 token LLM 路由器在依赖图
与自然语言间自适应选择，3.2× 压缩无精度损失。迁移到 NEKO/LoRa 网关：边缘节点
部署**规则式**轻量协议路由器（无需 LLM），在结构化通信（状态同步/频谱分配/功率
控制）与自然语言指令之间自适应选择传输格式，目标 ≥3× 通信字节压缩且任务成功率
不降。

结构化消息 → 紧凑二进制 schema（定长字段，struct 打包）；
模糊/异常场景 → 自然语言原样透传（无损）。

纯 Python 标准库实现，无第三方依赖，可离线单元测试。
"""
from __future__ import annotations

import json
import struct
from dataclasses import dataclass

# 消息类型 → (struct 格式串, 字段顺序, 字段取值约束)
#   B=u8, b=i8, H=u16, I=u32；均为小端。
_SCHEMAS: dict[str, tuple[str, tuple[str, ...]]] = {
    "state_sync": ("<BIH", ("node_id", "freq_hz", "seq")),
    "spectrum_alloc": ("<BII", ("node_id", "freq_hz", "bandwidth_hz")),
    "power_ctrl": ("<BbH", ("node_id", "power_dbm", "timeslot")),
}

_TYPE_ID: dict[str, int] = {"state_sync": 1, "spectrum_alloc": 2, "power_ctrl": 3}
_ID_TYPE: dict[int, str] = {v: k for k, v in _TYPE_ID.items()}
_NL_FALLBACK_ID = 255

# 字段取值范围（结构化消息必须落在区间内，否则回退自然语言）
_RANGES: dict[str, tuple[int, int]] = {
    "node_id": (0, 255),
    "freq_hz": (0, 2**32 - 1),
    "seq": (0, 2**16 - 1),
    "bandwidth_hz": (0, 2**32 - 1),
    "power_dbm": (-128, 127),
    "timeslot": (0, 2**16 - 1),
}


@dataclass
class Routed:
    """路由结果。"""

    format: str                 # "binary"（结构化）| "nl"（自然语言回退）
    msg_type: str | None        # binary 时为消息类型
    payload: bytes              # binary 时为紧凑编码；nl 时为 UTF-8 文本
    nl_text: str | None = None  # nl 时保留原文（任务成功 = 语义无损透传）

    @property
    def n_bytes(self) -> int:
        return len(self.payload)


@dataclass
class Decoded:
    """解码结果（route 的对称收端）。"""

    format: str          # "binary" | "nl"
    msg_type: str | None # binary 时为消息类型
    fields: dict | None  # binary 时为还原出的字段
    text: str | None     # nl 时为原文


def _nl_baseline_bytes(fields: dict) -> int:
    """自然语言/JSON 基线字节数（用于压缩率对比）。"""
    return len(json.dumps(fields, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


class ProtocolRouter:
    """规则式轻量协议路由器。"""

    def _match_schema(self, message) -> str | None:
        """若 message 能无损映射到某结构化 schema，返回该类型；否则 None。"""
        if not isinstance(message, dict):
            return None
        for msg_type, (_, fields) in _SCHEMAS.items():
            if set(message.keys()) != set(fields):
                continue
            if all(self._in_range(k, message[k]) for k in fields):
                return msg_type
        return None

    @staticmethod
    def _in_range(key: str, value) -> bool:
        lo, hi = _RANGES[key]
        if isinstance(value, bool) or not isinstance(value, int):
            return False
        return lo <= value <= hi

    # ---------- 编码 / 解码 ----------

    def encode_structured(self, msg_type: str, **fields) -> bytes:
        if msg_type not in _SCHEMAS:
            raise ValueError(f"未知消息类型 {msg_type!r}")
        fmt, order = _SCHEMAS[msg_type]
        for k in order:
            if k not in fields or not self._in_range(k, fields[k]):
                raise ValueError(f"字段 {k} 缺失或超范围: {fields.get(k)!r}")
        values = tuple(int(fields[k]) for k in order)
        return bytes([_TYPE_ID[msg_type]]) + struct.pack(fmt, *values)

    def decode_structured(self, data: bytes) -> tuple[str, dict]:
        data = bytes(data)
        if not data:
            raise ValueError("空载荷，无法解码")
        tid = data[0]
        if tid == _NL_FALLBACK_ID:
            raise ValueError("这是自然语言回退载荷，请用 decode_nl")
        msg_type = _ID_TYPE.get(tid)
        if msg_type is None:
            raise ValueError(f"未知类型字节 {tid}")
        fmt, order = _SCHEMAS[msg_type]
        values = struct.unpack(fmt, data[1:])
        return msg_type, dict(zip(order, values))

    @staticmethod
    def encode_nl(text: str) -> bytes:
        return bytes([_NL_FALLBACK_ID]) + text.encode("utf-8")

    @staticmethod
    def decode_nl(data: bytes) -> str:
        return bytes(data[1:]).decode("utf-8")

    def decode(self, data: bytes) -> Decoded:
        """自动分发解码：按载荷首字节区分结构化二进制 vs 自然语言回退。"""
        data = bytes(data)
        if not data:
            raise ValueError("空载荷，无法解码")
        if data[0] == _NL_FALLBACK_ID:
            return Decoded(format="nl", msg_type=None, fields=None, text=self.decode_nl(data))
        msg_type, fields = self.decode_structured(data)
        return Decoded(format="binary", msg_type=msg_type, fields=fields, text=None)

    # ---------- 路由 ----------

    def route(self, message) -> Routed:
        """自适应路由：结构化 → 二进制；自然语言/模糊 → 自然语言透传。"""
        if isinstance(message, str):
            return Routed(format="nl", msg_type=None, payload=self.encode_nl(message), nl_text=message)
        msg_type = self._match_schema(message)
        if msg_type is not None:
            payload = self.encode_structured(msg_type, **message)
            return Routed(format="binary", msg_type=msg_type, payload=payload)
        # 模糊/异常（dict 但不匹配任何 schema）→ 自然语言兜底，JSON 序列化保留语义
        text = json.dumps(message, ensure_ascii=False, separators=(",", ":"))
        return Routed(format="nl", msg_type=None, payload=self.encode_nl(text), nl_text=text)


def compression_ratio(message) -> float | None:
    """结构化消息的二进制压缩率（相对 JSON 基线）。非结构化返回 None。"""
    router = ProtocolRouter()
    r = router.route(message)
    if r.format != "binary" or not isinstance(message, dict):
        return None
    return float(_nl_baseline_bytes(message)) / float(r.n_bytes)
