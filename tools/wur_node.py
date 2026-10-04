"""W58-01 ESP32 无源唤醒节点模拟（MagPie 范式：微安级唤醒 + 相位保持）

依据 docs/esp32-wur-node-设计.md：WuR 唤醒无线电（~10µA 常态监听）+ 低功耗 RTC
（32kHz 晶振相位保持）+ 主控 deep-sleep 周期唤醒。原型模拟：
  - 沉睡 / 周期唤醒 / 侦听前导 / 相位保持（对时漂补偿）
  - 能量预算记账（唤醒次数 × 每次功耗 + 常驻功耗 vs 电池容量）
  - mock 电池容量下算出节点理论存活天数（stdout 输出）

纯 numpy，无真机。相位漂移 = RTC 晶振 ppm 误差随时间累积；补偿 = 唤醒时按测量
修正，残余误差 = 漂移 × (1 − 补偿精度)。
"""
from __future__ import annotations

import numpy as np

__all__ = ["WurNode", "energy_budget_ok", "survival_days"]


class WurNode:
    """一个无源唤醒节点。"""

    def __init__(
        self,
        *,
        battery_mah: float = 220.0,      # 电池容量（如 CR2032 ≈ 220 mAh）
        battery_v: float = 3.0,           # 电池电压
        listen_ua: float = 10.0,          # WuR 常态监听电流（µA）
        rtc_ua: float = 1.0,              # RTC 相位保持电流（µA）
        wake_ma: float = 5.0,             # 主控唤醒采样电流（mA）
        wake_ms: float = 5.0,             # 每次唤醒时长（ms）
        wake_interval_s: float = 30.0,    # 唤醒周期（s）
        rtc_drift_ppm: float = 20.0,      # 32kHz 晶振漂移（ppm）
        comp_accuracy: float = 0.95,      # 相位补偿精度（0~1，越高补偿越彻底）
    ) -> None:
        self.battery_j = float(battery_mah) * 1e-3 * battery_v * 3600.0
        self.battery_v = float(battery_v)
        self.listen_ua = float(listen_ua)
        self.rtc_ua = float(rtc_ua)
        self.wake_ma = float(wake_ma)
        self.wake_ms = float(wake_ms)
        self.wake_interval_s = float(wake_interval_s)
        self.rtc_drift_ppm = float(rtc_drift_ppm)
        self.comp_accuracy = float(comp_accuracy)
        self.wakeups = 0

    # ---------- 相位保持 ----------

    def phase_drift_s(self, elapsed_s: float) -> float:
        """RTC 漂移造成的相位误差（秒）。ppm × 10⁻⁶ × 时长。"""
        return self.rtc_drift_ppm * 1e-6 * float(elapsed_s)

    def compensate(self, drift_s: float) -> float:
        """唤醒时补偿相位漂移，返回补偿后残余误差（秒）。"""
        return drift_s * (1.0 - self.comp_accuracy)

    def residual_after_cycle(self) -> float:
        """一个唤醒周期后（先漂移、再补偿）的残余同步误差。"""
        drift = self.phase_drift_s(self.wake_interval_s)
        return self.compensate(drift)

    # ---------- 能量预算 ----------

    def energy_per_cycle_j(self) -> float:
        """一个周期的能耗 = 常驻（WuR+RTC）能耗 + 一次唤醒采样能耗。"""
        idle_ua = self.listen_ua + self.rtc_ua
        idle_j = idle_ua * 1e-6 * self.battery_v * self.wake_interval_s
        wake_j = self.wake_ma * 1e-3 * self.battery_v * (self.wake_ms * 1e-3)
        return idle_j + wake_j

    def wake(self, n: int = 1) -> None:
        """记录 n 次唤醒（能量记账）。"""
        self.wakeups += int(n)

    def energy_used_j(self) -> float:
        """已消耗能量 = 唤醒次数 × 每次唤醒能耗（含常驻分摊）。"""
        return self.wakeups * self.energy_per_cycle_j()


def energy_budget_ok(node: WurNode) -> bool:
    """能量预算是否未超支（已用能量 ≤ 电池容量）。"""
    return node.energy_used_j() <= node.battery_j


def survival_days(node: WurNode) -> float:
    """理论存活天数 = 电池能量 / 日均能耗。"""
    cycles_per_day = 86400.0 / node.wake_interval_s
    daily_j = node.energy_per_cycle_j() * cycles_per_day
    return node.battery_j / daily_j


def simulate(node: WurNode, days: float = 30.0) -> dict:
    """模拟 days 天：计算唤醒次数、能耗、存活天数与残余同步误差。"""
    n_wakeups = int(days * 86400.0 / node.wake_interval_s)
    node.wake(n_wakeups)
    return {
        "wakeups": node.wakeups,
        "energy_used_j": node.energy_used_j(),
        "battery_j": node.battery_j,
        "survival_days": survival_days(node),
        "residual_sync_error_s": node.residual_after_cycle(),
    }


if __name__ == "__main__":
    node = WurNode()
    r = simulate(node, days=30.0)
    print(f"模拟 30 天：唤醒 {r['wakeups']} 次，能耗 {r['energy_used_j']:.2f} J / "
          f"电池 {r['battery_j']:.0f} J，理论存活 {r['survival_days']:.0f} 天，"
          f"残余同步误差 {r['residual_sync_error_s']*1e6:.2f} µs")
