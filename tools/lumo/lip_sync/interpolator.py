"""双目标插值平滑器 + 播放进度驱动（handcrafted 蒸馏批 W100-01 原创实现）。

设计参考：handcrafted-persona-engine 的 EaseInOutQuad + Lerp 指数平滑（无 LICENSE，
仅蒸馏不融合）——本实现按蒸馏文档 A2/A4 的设计思想从零编写。

两层平滑（蒸馏文档 A2）：
    1. 音素间过渡：当前音素 → 下一音素，EaseInOutQuad 缓动 + 逐维 Lerp。
    2. 参数逼近：每维向目标 Lerp(current, target, SMOOTHING_FACTOR*dt)，
       SMOOTHING_FACTOR=35（说话快跟手）。
空闲回归：NEUTRAL_RETURN_FACTOR=15（闭嘴慢），NEUTRAL_THRESHOLD=0.02 防抖。
鼓腮特例：CHEEK_PUFF_DECAY_FACTOR=80（爆发性动作快收）。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .pinyin_poses import NEUTRAL_POSE, get_pose

SMOOTHING_FACTOR = 35.0
NEUTRAL_RETURN_FACTOR = 15.0
NEUTRAL_THRESHOLD = 0.02
CHEEK_PUFF_DECAY_FACTOR = 80.0

_POSE_KEYS = tuple(NEUTRAL_POSE.keys())


def ease_in_out_quad(t: float) -> float:
    """EaseInOutQuad：t∈[0,1] → 缓入缓出。"""
    t = max(0.0, min(1.0, t))
    if t < 0.5:
        return 2.0 * t * t
    return 1.0 - ((-2.0 * t + 2.0) ** 2) / 2.0


def lerp_pose(a: dict, b: dict, t: float) -> dict:
    """逐维线性插值（PhonemePose.Lerp 等价）。"""
    return {k: a[k] + (b[k] - a[k]) * t for k in _POSE_KEYS}


@dataclass
class TimedPhoneme:
    phoneme: str
    start: float
    end: float


@dataclass
class LipSyncSmoother:
    """双目标插值平滑器：输入 (时间, 音素时间轴)，输出每帧 9 维参数。"""

    smoothing_factor: float = SMOOTHING_FACTOR
    neutral_return_factor: float = NEUTRAL_RETURN_FACTOR
    neutral_threshold: float = NEUTRAL_THRESHOLD
    cheek_puff_decay_factor: float = CHEEK_PUFF_DECAY_FACTOR

    _current: dict = field(default_factory=lambda: dict(NEUTRAL_POSE), init=False)
    _target: dict = field(default_factory=lambda: dict(NEUTRAL_POSE), init=False)
    _next: dict = field(default_factory=lambda: dict(NEUTRAL_POSE), init=False)
    _interp_t: float = field(default=1.0, init=False)
    _active: list[TimedPhoneme] = field(default_factory=list, init=False)
    _index: int = field(default=0, init=False)

    def set_timeline(self, timed: list[TimedPhoneme]) -> None:
        """设置音素时间轴（单调不重叠），并把插值状态对准首音素。"""
        self._active = list(timed)
        self._index = 0
        if self._active:
            self._current = get_pose(self._active[0].phoneme)
            self._target = dict(self._current)
            self._next = (
                get_pose(self._active[1].phoneme) if len(self._active) > 1
                else dict(self._current)
            )
        self._interp_t = 1.0

    def _find_index_at_time(self, t: float) -> int:
        """播放进度 → 当前音素索引（快速路径 + 线性搜索，1ms 容差）。"""
        n = len(self._active)
        if n == 0:
            return 0
        # 快速路径：当前索引仍在区间
        if 0 <= self._index < n:
            cur = self._active[self._index]
            if cur.start <= t < cur.end + 0.001:
                return self._index
        for i in range(n):
            p = self._active[i]
            if p.start <= t < p.end + 0.001:
                return i
        return n - 1 if t >= self._active[-1].end else 0

    def update(self, t: float, dt: float) -> dict:
        """按实际播放位置 t 推进一帧，返回 9 维参数（Live2D Cubism 参数名）。"""
        if not self._active:
            return self._advance_towards(dict(NEUTRAL_POSE), dt)
        idx = self._find_index_at_time(t)
        if idx != self._index:
            # 音素切换：进入「当前→下一」双目标插值
            self._index = idx
            self._current = dict(self._target)
            self._target = get_pose(self._active[idx].phoneme)
            self._next = (
                get_pose(self._active[idx + 1].phoneme) if idx + 1 < len(self._active)
                else dict(self._target)
            )
            self._interp_t = 0.0

        phoneme = self._active[idx]
        dur = phoneme.end - phoneme.start
        if dur > 0:
            self._interp_t = min(1.0, (t - phoneme.start) / dur)

        eased = ease_in_out_quad(self._interp_t)
        frame_target = lerp_pose(self._target, self._next, eased)
        return self._advance_towards(frame_target, dt)

    def _advance_towards(self, target: dict, dt: float) -> dict:
        """指数平滑逼近目标；空闲回归用更慢因子；鼓腮特例快衰减。"""
        for k in _POSE_KEYS:
            value = self._current[k]
            goal = target[k]
            if k == "CheekPuff":
                # 鼓腮：目标显著时按跟手系数上升，否则快速衰减回 0
                if goal > self.neutral_threshold:
                    factor = self.smoothing_factor
                else:
                    factor = self.cheek_puff_decay_factor
            else:
                dist = abs(goal - value)
                if dist < self.neutral_threshold and abs(goal) < self.neutral_threshold:
                    factor = self.neutral_return_factor  # 近中性：闭嘴慢
                else:
                    factor = self.smoothing_factor
            value += (goal - value) * min(1.0, factor * dt)
            if k == "CheekPuff" and goal <= self.neutral_threshold and value < 0.001:
                value = 0.0
            self._current[k] = value
        return dict(self._current)

    def snapshot(self) -> dict:
        return dict(self._current)


def build_timeline_from_words(words: list[dict]) -> list[TimedPhoneme]:
    """词级时间 → 音素级时间（均分，忽略重音/音长符号 ˈˌː）。

    words: [{"phonemes": "ni3hao3", "start": 0.0, "end": 0.5}, ...]
    """
    timeline: list[TimedPhoneme] = []
    last_end = 0.0
    for w in words:
        chars = [
            c for c in w.get("phonemes", "")
            if c not in "ˈˌː0123456789 .-"
        ]
        if not chars:
            continue
        start = max(last_end, float(w.get("start", last_end)))
        end = max(start, float(w.get("end", start)))
        per = (end - start) / len(chars)
        for i, ch in enumerate(chars):
            timeline.append(TimedPhoneme(ch, start + i * per, start + (i + 1) * per))
        last_end = end
    return timeline
