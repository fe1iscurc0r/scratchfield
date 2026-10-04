"""sleep_sync 测试：epoch 解析 / 失步检测 / 统计累积 / 兼容旧帧 / 异常帧容错。"""

from __future__ import annotations

from mcpserver.rf_brain.dcp import Battery, MsgType, build_report_payload, encode
from mcpserver.rf_brain.sleep_sync import (
    EPOCH_FLAG_RESYNC,
    EPOCH_MSG_TYPE,
    EPOCH_PAYLOAD_LEN,
    EpochStatus,
    JoinTimeStats,
    SleepSync,
    build_epoch_payload,
    check_epoch,
    decode_epoch_frame,
    parse_epoch_payload,
    track_join_time,
)


def _epoch_frame(node_id: int, epoch: int, slot: int,
                 resync: bool = False, seq: int = 1) -> bytes:
    return encode(EPOCH_MSG_TYPE, seq, build_epoch_payload(node_id, epoch, slot, resync))


# ---------- 1. epoch 解析 ----------

def test_epoch_payload_roundtrip() -> None:
    """8B payload 编解码往返 + 定长校验。"""
    p = build_epoch_payload(0x1234, 0xDEADBEEF, 5, resync_requested=True)
    assert len(p) == EPOCH_PAYLOAD_LEN == 8
    fields = parse_epoch_payload(p)
    assert fields is not None
    assert fields["node_id"] == 0x1234
    assert fields["epoch"] == 0xDEADBEEF
    assert fields["slot"] == 5
    assert fields["resync_requested"] is True
    assert (p[7] & EPOCH_FLAG_RESYNC) != 0


def test_decode_epoch_frame_roundtrip() -> None:
    """epoch 帧低层解码：magic/type/seq/payload 全对齐。"""
    frame = _epoch_frame(0x0102, 42, 3, resync=False, seq=7)
    fields = decode_epoch_frame(frame)
    assert fields is not None
    assert fields["node_id"] == 0x0102
    assert fields["epoch"] == 42
    assert fields["slot"] == 3
    assert fields["resync_requested"] is False
    assert fields["seq"] == 7


def test_parse_payload_bad_length_returns_none() -> None:
    """payload 长度不符 → parse 返回 None（降级不抛错）。"""
    assert parse_epoch_payload(b"\x00\x01") is None
    assert parse_epoch_payload(b"") is None
    assert parse_epoch_payload("not-bytes") is None  # type: ignore[arg-type]


# ---------- 2. 失步检测 ----------

def test_check_epoch_statuses() -> None:
    """失步检测：首次 / 连续（gap 0/1）/ 失步（gap>1 或回退）。"""
    assert check_epoch(None, 10) is EpochStatus.FIRST
    assert check_epoch(9, 10) is EpochStatus.OK        # gap = 1
    assert check_epoch(10, 10) is EpochStatus.OK       # gap = 0（同 epoch 重读）
    assert check_epoch(8, 10) is EpochStatus.RESYNC    # gap = 2
    assert check_epoch(1, 100) is EpochStatus.RESYNC   # gap 巨大
    assert check_epoch(10, 5) is EpochStatus.RESYNC    # 回退（掉电复位）


# ---------- 3. 统计累积 ----------

def test_track_join_time() -> None:
    """入网时长：正常差值 / 缺失 / 倒序。"""
    assert track_join_time(100.0, 103.5) == 3.5
    assert track_join_time(None, 103.5) is None   # type: ignore[arg-type]
    assert track_join_time(100.0, None) is None   # type: ignore[arg-type]
    assert track_join_time(105.0, 103.5) is None  # 倒序


def test_join_stats_accumulate() -> None:
    """JoinTimeStats：count / min / max / avg 累积正确。"""
    stats = JoinTimeStats()
    assert stats.avg_s is None  # 空态
    stats.record(3.0)
    stats.record(5.0)
    stats.record(1.0)
    assert stats.count == 3
    assert stats.min_s == 1.0
    assert stats.max_s == 5.0
    assert stats.avg_s == 3.0
    # 非法值（负 / None）不计数
    stats.record(-1.0)
    assert stats.count == 3


# ---------- 4. 兼容旧帧 ----------

def test_legacy_report_frame_compat() -> None:
    """旧节点无 epoch 字段：REPORT 帧经 ingest 不崩，has_epoch=False。"""
    ss = SleepSync()
    payload = build_report_payload(25.0, 50, Battery.OK, -85.0, "C",
                                   "acurite-tower", 4660)
    report = encode(MsgType.REPORT, seq=1, payload=payload)
    result = ss.ingest(report)
    assert result is not None
    assert result["has_epoch"] is False
    assert result["type"] == int(MsgType.REPORT)
    assert ss.legacy_frames == 1
    assert ss.epoch_frames == 0


def test_legacy_ack_frame_compat() -> None:
    """旧节点 ACK 帧（0 payload）同样兼容，不崩。"""
    ss = SleepSync()
    ack = encode(MsgType.ACK, seq=2)
    result = ss.ingest(ack)
    assert result is not None
    assert result["has_epoch"] is False
    assert result["type"] == int(MsgType.ACK)


# ---------- 5. 异常帧容错 ----------

def test_bad_frame_tolerance() -> None:
    """magic / crc / 短帧 / 类型错 → decode_epoch_frame 返回 None，不抛错。"""
    good = _epoch_frame(1, 5, 0)

    bad_magic = bytearray(good)
    bad_magic[0] = 0x4D
    bad_magic[1] = 0x52
    assert decode_epoch_frame(bytes(bad_magic)) is None

    bad_crc = bytearray(good)
    bad_crc[5] ^= 0xFF  # 翻转 payload 首字节
    assert decode_epoch_frame(bytes(bad_crc)) is None

    assert decode_epoch_frame(b"") is None
    assert decode_epoch_frame(b"\xd0\xcc\x05") is None  # 过短
    assert decode_epoch_frame("nope") is None  # type: ignore[arg-type]

    # 非 epoch 类型（REPORT）→ None
    report = encode(MsgType.REPORT, 1, build_report_payload(
        25.0, 50, Battery.OK, -85.0, "C", "acurite-tower", 1))
    assert decode_epoch_frame(report) is None


# ---------- 端到端 ----------

def test_sleepsync_end_to_end_resync() -> None:
    """端到端：唤醒→首帧计时→失步标记 resync→累计计数。"""
    ss = SleepSync()
    # 节点 1 首次上报（FIRST）+ 入网计时
    ss.mark_wake(1, ts=100.0)
    r1 = ss.ingest(_epoch_frame(1, epoch=10, slot=0), ts=102.0)
    assert r1 is not None
    assert r1["status"] == EpochStatus.FIRST.value
    assert r1["join_s"] == 2.0
    assert ss.join_stats.count == 1

    # 节点 1 连续上报（gap=1 → OK）
    r2 = ss.ingest(_epoch_frame(1, epoch=11, slot=0), ts=104.0)
    assert r2 is not None and r2["status"] == EpochStatus.OK.value

    # 节点 1 失步（gap>1 → RESYNC），resync_count 递增
    r3 = ss.ingest(_epoch_frame(1, epoch=15, slot=0), ts=106.0)
    assert r3 is not None and r3["status"] == EpochStatus.RESYNC.value
    assert ss.resync_count == 1
    assert ss.epoch_frames == 3
