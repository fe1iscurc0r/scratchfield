# -*- coding: utf-8 -*-
"""语音打断极简 Event 原型（W65-02 · 用户插嘴→立即停 TTS）。

参考 aspen 多线程组件模型（每组件一线程+队列）+ 流式句子分段；这里只做
「打断事件到达后 TTS 停止」的最小 Event 机制。纯标准库。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TTSStream:
    """TTS 流：running 标志 + 已发句段。"""
    running: bool = True
    segments: list[str] = field(default_factory=list)

    def speak(self, segment: str) -> bool:
        """发一个句段；若已停止则拒绝。"""
        if not self.running:
            return False
        self.segments.append(segment)
        return True

    def stop(self) -> None:
        self.running = False


def interrupt(stream: TTSStream) -> bool:
    """打断事件：立即停 TTS。返回是否确实打断了（曾运行）。"""
    was = stream.running
    stream.stop()
    return was


if __name__ == "__main__":
    s = TTSStream()
    s.speak("第一句")
    print("打断前 running:", s.running, "打断:", interrupt(s))
    print("打断后 running:", s.running, "再发句段:", s.speak("第二句"))
