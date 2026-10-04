"""R29 · 频谱事件长历史查询原型（环状强制记忆）

灵感：digest-g2-4b 授粉点① · 论文 2608.26794（Ring Forcing，环状训练强制从远处
历史检索）。核心：把「物体持久性」与「记忆容量」解耦——近期事件全量保留，更早的
事件按时间桶压缩归档，在**固定内存预算**下扩展历史查询跨度。

对 SDR：不存每次 FFT 快照，而是存「完成的频谱事件」（信号出现→干扰→消失）。
查询「最近 5 个事件」用全量近期缓存；查询「过去某时段发生了什么」用归档摘要，
历史跨度远超朴素环形缓存的容量上限。

原型：
  - RingForcedMemory：近期全量 deque + 归档时间桶计数
  - recent_events(n)：近期全量
  - count_between(t0, t1)：长历史计数（近期 + 归档）

运行：python -m mcpserver.rf_brain.prototypes.ring_forced_memory
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass


@dataclass
class Event:
    timestamp: float
    event_type: str


class RingForcedMemory:
    """环状强制记忆：近期全量 + 归档压缩，固定内存扩展历史跨度。"""

    def __init__(self, capacity: int = 10, bucket_seconds: float = 60.0) -> None:
        self.capacity = capacity
        self.bucket_seconds = bucket_seconds
        self.recent: deque[Event] = deque(maxlen=capacity)   # 近期全量
        self.archive: dict[int, int] = {}                    # 归档：桶起始 → 事件计数

    def push(self, event: Event) -> None:
        if len(self.recent) == self.capacity:
            self._archive(self.recent.popleft())
        self.recent.append(event)

    def _archive(self, event: Event) -> None:
        bucket = int(event.timestamp // self.bucket_seconds)
        self.archive[bucket] = self.archive.get(bucket, 0) + 1

    def recent_events(self, n: int = 10) -> list[Event]:
        return list(self.recent)[-n:]

    def count_between(self, t0: float, t1: float) -> int:
        """长历史计数：近期全量 + 归档桶（跨过容量上限）。"""
        count = sum(1 for e in self.recent if t0 <= e.timestamp <= t1)
        b0, b1 = int(t0 // self.bucket_seconds), int(t1 // self.bucket_seconds)
        count += sum(c for b, c in self.archive.items() if b0 <= b <= b1)
        return count


def main() -> None:
    mem = RingForcedMemory(capacity=10, bucket_seconds=60.0)
    for i in range(1000):
        mem.push(Event(timestamp=float(i), event_type="appear"))
    print(f"近期最近 5 个事件时间戳 = {[int(e.timestamp) for e in mem.recent_events(5)]}")
    print(f"长历史 [0, 200) 事件数 = {mem.count_between(0, 200)}（朴素环形缓存为 0）")
    print(f"长历史 [800, 1000) 事件数 = {mem.count_between(800, 1000)}")


if __name__ == "__main__":
    main()
