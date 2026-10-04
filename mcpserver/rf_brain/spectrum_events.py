"""射频大脑 · 事件驱动频谱缓存（R01）

把"逐帧 FFT"升级为"事件驱动"：检测信号出现 / 消失 / 突发干扰，固化为事件记录，
支持"当前主干扰源是什么"这类查询而无须回扫历史帧。内存固定预算（环形缓存有界）。

组件：
  - SpectrumEvent        事件 schema（时间/频点/类型/持续/强度），NDJSON 兼容总线
  - EventRingBuffer      固定预算环形缓存（deque maxlen）
  - SpectrumEventDetector 能量跳变（出现）/ 跌落（消失）/ 突发判定（滞回 + 谱段匹配）
  - SpectrumEventCache    查询 API（current_interferers / recent_events）

事件类型（event_type）：
  - "appear"   信号出现（能量跳升越过阈值）
  - "vanish"   信号消失（能量跌落越过阈值），duration_s 为其存活时长
  - "burst"    突发干扰（出现到消失极短、能量高），duration_s 为尖峰时长
  - "interferer" 由 current_interferers() 聚合出的"当前活跃源"视图

与现有总线兼容：as_dict() / to_ndjson() 输出一行 JSON；`src="rf_brain"` 与
SentinelReport 的 "sentinel" 等来源区分。不依赖任何硬件，纯 numpy，可离线单测。
"""
from __future__ import annotations

import json
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Iterable, Optional

import numpy as np

# --------------------------------------------------------------------------- #
# 事件 schema
# --------------------------------------------------------------------------- #

@dataclass
class SpectrumEvent:
    """频谱事件记录（固化后的事件，NDJSON 兼容）。

    字段与总线逐字段对齐；`as_dict()` 保证 JSON 可序列化。
    """
    timestamp: float          # epoch 秒（事件发生时刻）
    freq_hz: float            # 事件中心频率（Hz）
    event_type: str           # appear | vanish | burst | interferer
    duration_s: float = 0.0   # 持续时长（秒）；appear 为 0
    strength_dbm: float = 0.0 # 强度（归一化 dB，峰值 0 dB）
    bandwidth_hz: float = 0.0 # 谱段宽度（Hz），相邻 bins 聚合而成
    src: str = "rf_brain"

    VALID_TYPES = ("appear", "vanish", "burst", "interferer")

    def __post_init__(self) -> None:
        if self.event_type not in self.VALID_TYPES:
            raise ValueError(f"未知事件类型: {self.event_type!r}")

    def as_dict(self) -> dict:
        """回原为可 JSON 序列化的 dict（保真入库/回读）。"""
        return {
            "src": self.src,
            "event_type": self.event_type,
            "timestamp": self.timestamp,
            "freq_hz": self.freq_hz,
            "duration_s": self.duration_s,
            "strength_dbm": self.strength_dbm,
            "bandwidth_hz": self.bandwidth_hz,
        }

    def to_ndjson(self) -> str:
        """序列化为一条 NDJSON 行（含换行）。"""
        return json.dumps(self.as_dict(), ensure_ascii=False) + "\n"

    @classmethod
    def from_ndjson(cls, line: str) -> "SpectrumEvent":
        """解析并校验一条 NDJSON 行；非法输入抛 ValueError。"""
        if not line or not line.strip():
            raise ValueError("空行")
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            raise ValueError(f"坏 JSON: {e}") from e
        if not isinstance(obj, dict):
            raise ValueError("NDJSON 行必须是 JSON 对象")
        if obj.get("src") != "rf_brain":
            raise ValueError(f"非 rf_brain 来源: {obj.get('src')!r}")
        ev = cls(
            timestamp=cls._require_float(obj, "timestamp"),
            freq_hz=cls._require_float(obj, "freq_hz"),
            event_type=obj.get("event_type", ""),
            duration_s=cls._require_float(obj, "duration_s"),
            strength_dbm=cls._require_float(obj, "strength_dbm"),
            bandwidth_hz=cls._require_float(obj, "bandwidth_hz"),
        )
        return ev

    @staticmethod
    def _require_float(obj: dict, key: str) -> float:
        v = obj.get(key)
        if v is None or isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ValueError(f"{key} 必须是数字: {v!r}")
        return float(v)


# --------------------------------------------------------------------------- #
# 固定预算环形缓存
# --------------------------------------------------------------------------- #

class EventRingBuffer:
    """固定预算事件环形缓存（内存有界，最旧事件自动淘汰）。"""

    def __init__(self, capacity: int = 1024) -> None:
        if capacity <= 0:
            raise ValueError(f"capacity 必须 > 0，实际 {capacity}")
        self.capacity = int(capacity)
        self._events: deque[SpectrumEvent] = deque(maxlen=self.capacity)

    def __len__(self) -> int:
        return len(self._events)

    def push(self, event: SpectrumEvent) -> None:
        self._events.append(event)

    def recent(self, n: int = 10) -> list[SpectrumEvent]:
        """最近 n 条事件（时间正序，旧→新）。"""
        n = int(n)
        if n <= 0:
            return []
        return list(self._events)[-n:]

    def all(self) -> list[SpectrumEvent]:
        return list(self._events)

    def clear(self) -> None:
        self._events.clear()


# --------------------------------------------------------------------------- #
# 事件检测器（能量跳变 / 消失 / 突发）
# --------------------------------------------------------------------------- #

@dataclass
class _Span:
    """一段连续活跃谱段（内部状态，供相邻帧匹配）。"""
    lo_bin: int
    hi_bin: int
    center_hz: float
    bandwidth_hz: float
    peak_db: float
    appear_ts: float


class SpectrumEventDetector:
    """把连续频谱帧转换为事件流。

    滞回判定：能量 >= appear_threshold_db 判定为"出现"，< vanish_threshold_db
    判定为"消失"（中间带保持上一状态，抑制抖动）。相邻活跃 bins 聚合成一个
    谱段（一个干扰源 = 一个事件，而非逐 bin 刷事件）。相邻帧按谱段 bin 重叠
    匹配，新谱段 → appear，消失谱段 → vanish（存活短于 burst_max_duration_s
    且能量高的谱段 → burst）。
    """

    def __init__(
        self,
        *,
        appear_threshold_db: float = -60.0,
        vanish_threshold_db: float = -75.0,
        burst_max_duration_s: float = 0.5,
        burst_min_strength_db: float = -30.0,
        min_span_bins: int = 1,
    ) -> None:
        if appear_threshold_db < vanish_threshold_db:
            raise ValueError("appear_threshold_db 必须 >= vanish_threshold_db（滞回）")
        self.appear_threshold_db = float(appear_threshold_db)
        self.vanish_threshold_db = float(vanish_threshold_db)
        self.burst_max_duration_s = float(burst_max_duration_s)
        self.burst_min_strength_db = float(burst_min_strength_db)
        self.min_span_bins = max(1, int(min_span_bins))
        self._active: list[_Span] = []

    @property
    def active_count(self) -> int:
        return len(self._active)

    def process_frame(
        self,
        freqs: Iterable[float],
        db: Iterable[float],
        timestamp: float | None = None,
    ) -> list[SpectrumEvent]:
        """处理一帧频谱，返回本帧新产生的事件列表。

        参数:
            freqs:     频率轴（Hz），与 db 等长，单调递增。
            db:        归一化功率谱（dB，峰值 0 dB，向下钳位）。
            timestamp: 帧时刻（epoch 秒）；缺省用 time.time()。

        返回:
            新事件列表（appear/vanish/burst）。事件只在本帧产生一次。
        """
        freqs = np.asarray(freqs, dtype=float)
        db = np.asarray(db, dtype=float)
        if freqs.size == 0 or freqs.size != db.size:
            raise ValueError("freqs 与 db 必须非空且等长")
        now = time.time() if timestamp is None else float(timestamp)

        # 滞回活跃 mask：>= appear 置活；< vanish 置死；中间带沿用上一帧状态
        prev_active = np.zeros(freqs.size, dtype=bool)
        for s in self._active:
            prev_active[s.lo_bin:s.hi_bin + 1] = True
        mask = db >= self.appear_threshold_db
        mask[~mask & (db >= self.vanish_threshold_db)] = prev_active[~mask & (db >= self.vanish_threshold_db)]

        spans = self._extract_spans(freqs, db, mask, now)
        events = self._match(spans, now)

        self._active = spans
        return events

    def _extract_spans(self, freqs, db, mask, now) -> list[_Span]:
        """活跃 bins → 连续谱段（含峰值与出现时刻，复用上一帧的 appear_ts）。"""
        spans: list[_Span] = []
        idx = np.flatnonzero(mask)
        if idx.size == 0:
            return spans
        # 切分连续段
        splits = np.flatnonzero(np.diff(idx) > 1) + 1
        for seg in np.split(idx, splits):
            lo, hi = int(seg[0]), int(seg[-1])
            if hi - lo + 1 < self.min_span_bins:
                continue
            peak = float(db[lo:hi + 1].max())
            center = float(freqs[lo:hi + 1].mean())
            bandwidth = float(freqs[hi] - freqs[lo])
            # 复用上一帧同谱段的出现时刻（保持 duration 计算连续）
            appear_ts = now
            for s in self._active:
                if _overlap((lo, hi), (s.lo_bin, s.hi_bin)):
                    appear_ts = s.appear_ts
                    break
            spans.append(_Span(lo, hi, center, bandwidth, peak, appear_ts))
        return spans

    def _match(self, spans: list[_Span], now: float) -> list[SpectrumEvent]:
        """相邻帧谱段匹配 → 新谱段 appear / 消失谱段 vanish|burst。"""
        events: list[SpectrumEvent] = []
        # 消失：上一帧有、本帧无
        for prev in self._active:
            matched = any(_overlap((s.lo_bin, s.hi_bin), (prev.lo_bin, prev.hi_bin)) for s in spans)
            if matched:
                continue
            duration = now - prev.appear_ts
            if duration <= self.burst_max_duration_s and prev.peak_db >= self.burst_min_strength_db:
                events.append(SpectrumEvent(now, prev.center_hz, "burst",
                                            duration_s=duration, strength_dbm=prev.peak_db,
                                            bandwidth_hz=prev.bandwidth_hz))
            else:
                events.append(SpectrumEvent(now, prev.center_hz, "vanish",
                                            duration_s=duration, strength_dbm=prev.peak_db,
                                            bandwidth_hz=prev.bandwidth_hz))
        # 出现：本帧有、上一帧无
        for s in spans:
            matched = any(_overlap((s.lo_bin, s.hi_bin), (p.lo_bin, p.hi_bin)) for p in self._active)
            if matched:
                continue
            events.append(SpectrumEvent(now, s.center_hz, "appear",
                                        duration_s=0.0, strength_dbm=s.peak_db,
                                        bandwidth_hz=s.bandwidth_hz))
        return events


def _overlap(a: tuple[int, int], b: tuple[int, int]) -> bool:
    """闭区间 [lo,hi] 是否重叠。"""
    return not (a[1] < b[0] or b[1] < a[0])


# --------------------------------------------------------------------------- #
# 查询 API（缓存）
# --------------------------------------------------------------------------- #

class SpectrumEventCache:
    """事件驱动频谱缓存：检测器 + 环形缓冲 + 活跃源视图。

    用法：
        cache = SpectrumEventCache()
        for freqs, db in stream:
            cache.ingest_frame(freqs, db)
        cache.current_interferers()   # 当前主干扰源（按强度降序）
        cache.recent_events(10)       # 最近 10 条事件
    """

    def __init__(
        self,
        capacity: int = 1024,
        *,
        appear_threshold_db: float = -60.0,
        vanish_threshold_db: float = -75.0,
        burst_max_duration_s: float = 0.5,
    ) -> None:
        self.detector = SpectrumEventDetector(
            appear_threshold_db=appear_threshold_db,
            vanish_threshold_db=vanish_threshold_db,
            burst_max_duration_s=burst_max_duration_s,
        )
        self.buffer = EventRingBuffer(capacity)

    def ingest_frame(
        self,
        freqs: Iterable[float],
        db: Iterable[float],
        timestamp: float | None = None,
    ) -> list[SpectrumEvent]:
        """吞入一帧频谱，检测事件并入环形缓存，返回本帧新事件。"""
        events = self.detector.process_frame(freqs, db, timestamp)
        for ev in events:
            self.buffer.push(ev)
        return events

    def recent_events(self, n: int = 10) -> list[SpectrumEvent]:
        """最近 n 条事件（时间正序，旧→新）。"""
        return self.buffer.recent(n)

    def current_interferers(self, now: float | None = None) -> list[SpectrumEvent]:
        """当前活跃干扰源（未消失），按强度降序，返回 interferer 视图。"""
        now = time.time() if now is None else float(now)
        out: list[SpectrumEvent] = []
        for s in self.detector._active:
            out.append(SpectrumEvent(
                now, s.center_hz, "interferer",
                duration_s=now - s.appear_ts,
                strength_dbm=s.peak_db,
                bandwidth_hz=s.bandwidth_hz,
            ))
        out.sort(key=lambda e: e.strength_dbm, reverse=True)
        return out

    def __len__(self) -> int:
        return len(self.buffer)
