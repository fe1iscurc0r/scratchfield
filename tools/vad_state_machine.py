# -*- coding: utf-8 -*-
"""滞后 VAD 状态机参考实现（W65-03 · silence↔speech 滞后起停录）。

4 状态滞后：silence → speech 需连续 N 帧起录，speech → silence 需 M 帧停录；
turn_detector 给话轮边界 + 打断。起录/停录滞后帧数可配。纯标准库。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class VADStateMachine:
    """滞后 VAD：按帧喂入语音活动标志（voice=True/False）。"""
    start_frames: int = 3   # N：连续 N 帧 voice 才起录
    stop_frames: int = 5    # M：连续 M 帧非 voice 才停录
    state: str = "silence"
    _count: int = 0

    def feed(self, voice: bool) -> str:
        """喂一帧，返回当前状态。"""
        if self.state == "silence":
            if voice:
                self._count += 1
                if self._count >= self.start_frames:
                    self.state = "speech"
                    self._count = 0
            else:
                self._count = 0
        else:  # speech
            if not voice:
                self._count += 1
                if self._count >= self.stop_frames:
                    self.state = "silence"
                    self._count = 0
            else:
                self._count = 0
        return self.state


class TurnDetector:
    """话轮边界 + 打断队列（cancel/resume）。"""
    def __init__(self) -> None:
        self.queue: list[str] = []
        self.cancelled = False

    def push(self, turn: str) -> None:
        self.queue.append(turn)

    def cancel(self) -> None:
        self.cancelled = True
        self.queue.clear()

    def resume(self) -> None:
        self.cancelled = False


if __name__ == "__main__":
    v = VADStateMachine(start_frames=3, stop_frames=5)
    seq = [True, True, True, False, False, False, False, False]
    for i, vf in enumerate(seq):
        print(f"帧{i} voice={vf} → state={v.feed(vf)}")
