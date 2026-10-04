"""链路可靠度 EWMA 估计：丢包率滑动平均（纯标准库）。

EWMA：reliability_t = α·sample_t + (1-α)·reliability_{t-1}
  - sample = 1（收包成功）/ 0（丢包），初始 reliability = 1（假设初始可靠）
  - loss_rate = 1 - reliability
  - α 可配（默认 0.3），α 越大对新样本越敏感

另有 LossWindow（固定窗口滑动丢包率）作窗口管理对照：窗口外样本自动淘汰，
避免历史样本永久占据权重。
"""
from __future__ import annotations

from collections import deque


class EWMAReliability:
    """单条链路的 EWMA 可靠度估计。"""

    def __init__(self, alpha: float = 0.3, init_reliability: float = 1.0) -> None:
        if not (0.0 < alpha <= 1.0):
            raise ValueError("alpha 必须在 (0, 1]")
        if not (0.0 <= init_reliability <= 1.0):
            raise ValueError("init_reliability 必须在 [0, 1]")
        self.alpha = alpha
        self.reliability = init_reliability
        self.samples = 0
        self.lost_count = 0

    def update_ewma(self, sample: float) -> float:
        """核心 EWMA 更新：sample ∈ [0,1]（1=成功 0=丢包），返回新可靠度。"""
        self.reliability = self.alpha * sample + (1.0 - self.alpha) * self.reliability
        self.samples += 1
        if sample == 0.0:
            self.lost_count += 1
        return self.reliability

    def on_success(self) -> float:
        """收包成功钩子（sample=1）。"""
        return self.update_ewma(1.0)

    def on_loss(self) -> float:
        """丢包钩子（sample=0）。"""
        return self.update_ewma(0.0)

    @property
    def loss_rate(self) -> float:
        """丢包率 = 1 - 可靠度。"""
        return 1.0 - self.reliability


class LossWindow:
    """固定窗口滑动丢包率（窗口外样本自动淘汰，deque maxlen 实现）。"""

    def __init__(self, window: int = 32) -> None:
        if window < 1:
            raise ValueError("window 必须 >= 1")
        self.window = window
        self._samples: deque[bool] = deque(maxlen=window)

    def add(self, success: bool) -> None:
        self._samples.append(bool(success))

    @property
    def loss_rate(self) -> float:
        if not self._samples:
            return 0.0
        return 1.0 - (sum(self._samples) / len(self._samples))

    def __len__(self) -> int:
        return len(self._samples)


__all__ = ["EWMAReliability", "LossWindow"]
