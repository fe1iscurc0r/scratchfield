# -*- coding: utf-8 -*-
"""LoRaCanary v1.5 · C3 深度睡眠 RTC 计数 · Python 镜像（工单 AB-03）。

镜像 firmware/loracanary/loracanary_c3_node/rtc_state.{h,cpp} 的语义：
  - counters_on_wake / counters_contiguous 纯逻辑逐行为对应；
  - RtcPersistence 镜像 RTC_DATA_ATTR 存储域语义：深睡保持、掉电清零、
    软复位残留（RESET 键不清 RTC 段 → 固件用唤醒源判定归零）。

真机项（诚实标注）：RTC 跨深睡不丢的实测留用户——烧录后看 boot JSON 的
seq/epoch 是否跨周期递增、断电重插是否归零。本文件验证逻辑层。
"""


class NodeCounters:
    """与 C++ loracanary::NodeCounters 字段一一对应。"""

    def __init__(self, seq: int = 0, wake_count: int = 0, epoch: int = 0):
        self.seq = seq
        self.wake_count = wake_count
        self.epoch = epoch

    def as_dict(self) -> dict:
        return {"seq": self.seq, "wake_count": self.wake_count,
                "epoch": self.epoch}


def counters_on_wake(c: NodeCounters, cold_boot: bool) -> None:
    """冷启动清零（上电语义），热唤醒各 +1（与 C++ 同名函数一致）。"""
    if cold_boot:
        c.seq = c.wake_count = c.epoch = 0
        return
    c.seq += 1
    c.wake_count += 1
    c.epoch += 1


def counters_contiguous(before: NodeCounters, after: NodeCounters) -> bool:
    """热唤醒连续性：三计数各恰好 +1（丢醒/回退 → False）。"""
    return (after.seq == before.seq + 1
            and after.wake_count == before.wake_count + 1
            and after.epoch == before.epoch + 1)


class RtcPersistence:
    """RTC 存储域镜像（RTC_DATA_ATTR 语义）。

    _store is None ≙ 掉电后 RTC 域清零；power_cycle() 模拟拔电重插。
    软复位残留用 soft_reset_leftover() 模拟（RTC 段不清）——固件侧由
    esp_sleep_get_wakeup_cause() 判冷启动归零，镜像侧同样在 load 处理。
    """

    def __init__(self) -> None:
        self._store: dict | None = {}

    def power_cycle(self) -> None:
        """拔电重插：RTC 慢时钟域失去供电 → 清零。"""
        self._store = None

    def commit(self, c: NodeCounters) -> None:
        self._store = c.as_dict()

    def load(self, cold_boot: bool) -> NodeCounters:
        """唤醒取回：冷启动（含软复位残留）归零，热唤醒保留。"""
        c = NodeCounters(**(self._store or {"seq": 0, "wake_count": 0,
                                            "epoch": 0}))
        if cold_boot:
            # 固件 rtc_load 同款：把残留/清零后的计数归零再推进
            c.seq = c.wake_count = c.epoch = 0
        counters_on_wake(c, cold_boot)
        return c
