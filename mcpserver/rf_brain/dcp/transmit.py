"""dcp 帧协议 · 可靠传输：超时重传 + LRU 去重（纯逻辑，传输层可 mock）。

参考 dcp arXiv 2605.26159（MIT）独立实现。

设计：
  - Transmitter：编码发送 → 等 ACK → 超时重传（retries 次）；transport 只暴露
    send(frame) / recv(timeout) 两个原语，真实 LoRa/串口/测试 mock 各自实现。
  - Deduplicator：LRU 去重（按 seq），接收侧防重复处理；容量可配，满时淘汰最旧。
"""
from __future__ import annotations

from collections import OrderedDict
from typing import Protocol

from .frame import decode, encode
from .types import MsgType


class Transport(Protocol):
    """可 mock 的传输层原语：send 发一帧，recv 阻塞等一帧（超时返回 None）。"""

    def send(self, frame: bytes) -> None: ...

    def recv(self, timeout: float) -> bytes | None: ...


class Deduplicator:
    """LRU 去重（按 seq）：已见过返回 True 并刷新，未见记入返回 False。"""

    def __init__(self, capacity: int = 1024) -> None:
        self._seen: "OrderedDict[int, bool]" = OrderedDict()
        self.capacity = max(capacity, 1)
        self.seen_count = 0  # 累计去重命中次数（测试/统计用）

    def is_duplicate(self, seq: int) -> bool:
        if seq in self._seen:
            self._seen.move_to_end(seq)
            self.seen_count += 1
            return True
        self._seen[seq] = True
        if len(self._seen) > self.capacity:
            self._seen.popitem(last=False)
        return False

    def __len__(self) -> int:
        return len(self._seen)


class Transmitter:
    """超时重传发送器：send_with_retry 编码一帧并等 ACK，超时重传 retries 次。"""

    def __init__(self, transport: Transport, *, retries: int = 3, timeout: float = 1.0) -> None:
        self.transport = transport
        self.retries = retries
        self.timeout = timeout
        self._seq = 0
        self.tx_attempts = 0  # 累计发送次数（含重传），测试断言重传行为

    def next_seq(self) -> int:
        self._seq = (self._seq + 1) & 0xFFFF
        return self._seq

    def send_with_retry(self, msg_type: int | MsgType, payload: bytes,
                        seq: int | None = None) -> bool:
        """编码发送 + 等 ACK + 超时重传。收到对应 seq 的 ACK 返回 True，否则 False。"""
        seq = seq if seq is not None else self.next_seq()
        frame = encode(msg_type, seq, payload)
        for _ in range(self.retries + 1):
            self.tx_attempts += 1
            self.transport.send(frame)
            ack = self.transport.recv(self.timeout)
            if ack is not None and _is_ack_for(ack, seq):
                return True
        return False


def _is_ack_for(frame: bytes, seq: int) -> bool:
    """判断收到的帧是否是对 seq 的 ACK（type==ACK 且 seq 回显匹配）。"""
    decoded = decode(frame)
    if decoded is None:
        return False
    msg_type, ack_seq, _ = decoded
    return msg_type == MsgType.ACK and ack_seq == seq


__all__ = ["Transport", "Deduplicator", "Transmitter"]
