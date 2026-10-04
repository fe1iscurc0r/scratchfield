"""sleep_sync.py — 休眠遥测节点 epoch 同步 + 入网时长统计（BRAVO B-02）。

背景：固件侧（firmware/sleep_epoch/）用低功耗 RTC/NVS 保持 epoch_counter + slot_map，
唤醒后对比 epoch 连续性——连续则断点恢复（跳过完整重同步），不连续则触发重同步。
本模块是云服侧配合，负责：

  1. 解析节点上报的 epoch 同步帧（新消息类型 EPOCH = 0x05，向后兼容扩展）；
  2. epoch 失步检测（同节点 gap > 1 或回退 → 标记 resync）；
  3. 入网时长统计（从 CAD 唤醒到首帧上报的耗时）。

向后兼容（硬约束）：
  - 旧节点无 epoch 字段（不发送 0x05 帧）→ 走 dcp.frame.decode 的 REPORT 路径，
    只做入网计时、不做失步检测，绝不崩；
  - 旧 dcp 帧（REPORT/ACK/COMMAND/HEARTBEAT）仍由 dcp.frame.decode 正常解帧；
  - 坏帧（magic/crc/type/长度异常）→ 返回 None，不抛异常。

零新重依赖：纯 Python 标准库（dataclasses/enum）。
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

from mcpserver.rf_brain.dcp.frame import (
    CRC_LEN,
    FRAME_OVERHEAD,
    HEADER_LEN,
    MAGIC,
    MAGIC_LEN,
    TYPE_LEN,
    crc16_modbus,
    decode,
)
from mcpserver.rf_brain.dcp.types import MsgType

# ---- epoch 同步帧协议常量（与 firmware/sleep_epoch/epoch.h 逐字节对齐）----
EPOCH_MSG_TYPE = 0x05          # 新消息类型（BRAVO 扩展；PAPA 枚举不含它）
EPOCH_PAYLOAD_LEN = 8          # node_id(2 LE) + epoch(4 LE) + slot(1) + flags(1)
EPOCH_FLAG_RESYNC = 0x01       # 节点侧检测到 epoch 不连续，请求重同步


class EpochStatus(str, Enum):
    """epoch 失步判定结果。"""
    FIRST = "first"    # 首次上报（无历史基准）
    OK = "ok"          # 连续（gap == 0 或 1）
    RESYNC = "resync"  # 失步（gap > 1 或回退）


# ---------------------------------------------------------------------------
# epoch 帧 payload 编解码
# ---------------------------------------------------------------------------
def build_epoch_payload(node_id: int, epoch: int, slot: int,
                        resync_requested: bool = False) -> bytes:
    """构造 epoch 同步帧 8B payload（与固件 epoch_build_payload 同布局）。"""
    flags = EPOCH_FLAG_RESYNC if resync_requested else 0
    return (
        (int(node_id) & 0xFFFF).to_bytes(2, "little")
        + (int(epoch) & 0xFFFFFFFF).to_bytes(4, "little")
        + bytes([int(slot) & 0xFF, flags])
    )


def parse_epoch_payload(payload: bytes) -> dict[str, Any] | None:
    """解析 8B epoch payload → dict；长度不符 / 非 bytes 返回 None（不抛错）。"""
    if not isinstance(payload, (bytes, bytearray)) or len(payload) != EPOCH_PAYLOAD_LEN:
        return None
    return {
        "node_id": int.from_bytes(payload[0:2], "little"),
        "epoch": int.from_bytes(payload[2:6], "little"),
        "slot": payload[6],
        "resync_requested": bool(payload[7] & EPOCH_FLAG_RESYNC),
    }


def decode_epoch_frame(frame: bytes) -> dict[str, Any] | None:
    """低层解码 epoch 同步帧（type == 0x05）。

    独立于 dcp.frame.decode：后者按 MsgType 枚举校验（0x05 非法 → 返回 None），
    故 epoch 帧需走本路径。magic/crc/type/payload 长度任一失败返回 None。
    """
    if not isinstance(frame, (bytes, bytearray)) or len(frame) < FRAME_OVERHEAD:
        return None
    if bytes(frame[:MAGIC_LEN]) != MAGIC:
        return None
    if frame[MAGIC_LEN] != EPOCH_MSG_TYPE:
        return None
    payload = bytes(frame[HEADER_LEN:-CRC_LEN])
    if len(payload) != EPOCH_PAYLOAD_LEN:
        return None
    crc = int.from_bytes(frame[-CRC_LEN:], "little")
    if crc16_modbus(bytes(frame[MAGIC_LEN:-CRC_LEN])) != crc:
        return None
    fields = parse_epoch_payload(payload)
    if fields is None:
        return None
    fields["seq"] = int.from_bytes(frame[MAGIC_LEN + TYPE_LEN:HEADER_LEN], "little")
    return fields


# ---------------------------------------------------------------------------
# epoch 失步检测 + 入网时长统计（纯函数）
# ---------------------------------------------------------------------------
def check_epoch(last_epoch: int | None, epoch: int) -> EpochStatus:
    """epoch 失步检测：gap > 1 或回退 → RESYNC；连续（gap 0/1）→ OK；无基准 → FIRST。"""
    if last_epoch is None:
        return EpochStatus.FIRST
    if epoch < last_epoch or (epoch - last_epoch) > 1:
        return EpochStatus.RESYNC
    return EpochStatus.OK


def track_join_time(wake_ts: float, first_frame_ts: float) -> float | None:
    """入网时长：从 CAD 唤醒到首帧上报的耗时（秒）。任一缺失或倒序 → None。"""
    if wake_ts is None or first_frame_ts is None:
        return None
    delta = first_frame_ts - wake_ts
    if delta < 0:
        return None
    return delta


@dataclass
class JoinTimeStats:
    """入网时长累计统计（count / total / min / max / avg）。"""
    count: int = 0
    total_s: float = 0.0
    min_s: float | None = None
    max_s: float | None = None

    def record(self, dt: float) -> None:
        if dt is None or dt < 0:
            return
        self.count += 1
        self.total_s += dt
        self.min_s = dt if self.min_s is None else min(self.min_s, dt)
        self.max_s = dt if self.max_s is None else max(self.max_s, dt)

    @property
    def avg_s(self) -> float | None:
        return self.total_s / self.count if self.count else None


# ---------------------------------------------------------------------------
# 云服侧跟踪器
# ---------------------------------------------------------------------------
class SleepSync:
    """节点 epoch 同步跟踪 + 入网时长统计（有状态，可 mock 时钟）。"""

    def __init__(self) -> None:
        self.last_epoch: dict[int, int] = {}
        self.wake_ts: dict[int, float] = {}
        self.join_stats = JoinTimeStats()
        self.resync_count = 0
        self.epoch_frames = 0
        self.legacy_frames = 0

    def mark_wake(self, node_id: int, ts: float | None = None) -> float:
        """记录节点 CAD 唤醒时刻（供入网计时基准）。缺省用单调时钟。"""
        ts = time.monotonic() if ts is None else float(ts)
        self.wake_ts[node_id] = ts
        return ts

    def ingest_epoch_frame(self, frame: bytes, ts: float | None = None) -> dict[str, Any] | None:
        """处理一条 epoch 同步帧：解码 + 失步检测 + 入网时长统计。坏帧返回 None。"""
        ts = time.monotonic() if ts is None else float(ts)

        fields = decode_epoch_frame(frame)
        if fields is None:
            return None

        node_id = fields["node_id"]
        epoch = fields["epoch"]
        self.epoch_frames += 1

        status = check_epoch(self.last_epoch.get(node_id), epoch)
        if status is EpochStatus.RESYNC:
            self.resync_count += 1

        join_s: float | None = None
        if node_id in self.wake_ts:
            join_s = track_join_time(self.wake_ts[node_id], ts)
            if join_s is not None:
                self.join_stats.record(join_s)

        self.last_epoch[node_id] = epoch
        return {
            "has_epoch": True,
            "node_id": node_id,
            "epoch": epoch,
            "slot": fields["slot"],
            "resync_requested": fields["resync_requested"],
            "status": status.value,
            "join_s": join_s,
        }

    def ingest_legacy_frame(self, frame: bytes, ts: float | None = None) -> dict[str, Any] | None:
        """处理旧节点帧（无 epoch 字段）：只做入网计时，不做失步检测，绝不崩。"""
        ts = time.monotonic() if ts is None else float(ts)

        decoded = decode(frame)  # REPORT/ACK/... 由 dcp 链路正常解帧
        if decoded is None:
            return None
        msg_type, seq, _ = decoded
        self.legacy_frames += 1

        # 旧帧无 node_id，join 计时退化为「全局首帧」基准（无 per-node 配对则跳过）
        return {
            "has_epoch": False,
            "type": int(msg_type),
            "seq": seq,
            "join_s": None,
        }

    def ingest(self, frame: bytes, ts: float | None = None) -> dict[str, Any] | None:
        """统一入口：优先按 epoch 帧解析；否则按旧 dcp 帧兼容处理。"""
        if decode_epoch_frame(frame) is not None:
            return self.ingest_epoch_frame(frame, ts)
        return self.ingest_legacy_frame(frame, ts)


__all__ = [
    "EPOCH_MSG_TYPE", "EPOCH_PAYLOAD_LEN", "EPOCH_FLAG_RESYNC",
    "EpochStatus", "JoinTimeStats", "SleepSync",
    "build_epoch_payload", "parse_epoch_payload", "decode_epoch_frame",
    "check_epoch", "track_join_time",
]
