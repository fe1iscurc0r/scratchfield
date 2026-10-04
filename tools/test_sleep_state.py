# -*- coding: utf-8 -*-
"""LoRaCanary v1.5 · 深度睡眠状态保持 pytest（工单 AB-03 验收「RTC 计数逻辑有测试」）。

镜像对象：firmware/loracanary/loracanary_c3_node/rtc_state.{h,cpp}
（移植自 firmware/sleep_epoch/lowpower.cpp 骨架思路）。
真机项留用户：boot JSON 的 seq/epoch 跨周期递增 + 断电归零实测（README 步骤）。
"""
from loracanary_sleep import (
    NodeCounters,
    RtcPersistence,
    counters_contiguous,
    counters_on_wake,
)


class TestSleepState:
    def test_s01_wake_cycle_keeps_counters(self):
        """S-01 连续 3 次「唤醒→上报→回睡」：seq/epoch 跨唤醒不丢（AB-03 核心）。"""
        rtc = RtcPersistence()  # 出厂上电：RTC 域空
        cur = rtc.load(cold_boot=True)  # 首次冷启动 → 全 0 起
        assert (cur.seq, cur.epoch) == (0, 0)
        rtc.commit(cur)

        for _ in range(3):  # 三轮深睡周期
            nxt = rtc.load(cold_boot=False)  # 定时器热唤醒：保留 RTC 计数并 +1
            assert counters_contiguous(cur, nxt), "热唤醒计数必须恰好各 +1"
            rtc.commit(nxt)  # 回睡前写回（固件 rtc_commit）
            cur = nxt

        assert cur.seq == 3 and cur.wake_count == 3 and cur.epoch == 3

    def test_s02_power_loss_resets_counters(self):
        """S-02 掉电重上电：RTC 清零 → 冷启动从 0 重计（预期语义，不装连续）。"""
        rtc = RtcPersistence()
        cur = rtc.load(cold_boot=True)
        rtc.commit(cur)
        cur = rtc.load(cold_boot=False)
        rtc.commit(cur)
        assert cur.seq == 1

        rtc.power_cycle()  # 拔电重插
        cur = rtc.load(cold_boot=True)
        assert (cur.seq, cur.wake_count, cur.epoch) == (0, 0, 0)

    def test_s03_gap_detection(self):
        """S-03 连续性判定：伪造丢醒（seq 跳变）→ False（网关可据此判异常）。"""
        before = NodeCounters(seq=5, wake_count=5, epoch=5)
        after_ok = NodeCounters(seq=6, wake_count=6, epoch=6)
        after_gap = NodeCounters(seq=8, wake_count=6, epoch=6)
        assert counters_contiguous(before, after_ok) is True
        assert counters_contiguous(before, after_gap) is False

    def test_s04_on_wake_semantics(self):
        """S-04 counters_on_wake 冷/热语义（与 C++ 纯逻辑逐行为对应）。"""
        c = NodeCounters(seq=9, wake_count=9, epoch=9)
        counters_on_wake(c, cold_boot=True)   # 冷启动清零
        assert (c.seq, c.wake_count, c.epoch) == (0, 0, 0)
        counters_on_wake(c, cold_boot=False)  # 热唤醒 +1
        assert (c.seq, c.wake_count, c.epoch) == (1, 1, 1)
