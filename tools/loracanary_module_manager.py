"""LoRaCanary · 模块管理器 Python 镜像（S13，与 C++ 状态机同语义）。

镜像 firmware/loracanary/module_manager/module_manager.{h,cpp} 的纯逻辑状态机：
自检评分 → 连续失败推进 → 回滚(A/B 槽位切换) → 隔离(QUARANTINED)。
C++ 在 ESP32 真机运行；本镜像用于主机 pytest 真实验证状态机行为（C++ 侧在
Windows 无主机编译器无法运行，只能编译验证），与 tools/loracanary_sleep.py
镜像 rtc_state.{h,cpp} 是同一套方法论。

语义必须与 C++ 保持逐字段一致；改动任一侧需同步另一侧（pytest 守卫）。
纯标准库，无 LLM/网络调用。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

K_PASS_THRESHOLD = 50

# 模块生命周期状态（与 ModuleState 枚举对齐）
INACTIVE = "INACTIVE"
ACTIVE = "ACTIVE"
FAILED = "FAILED"
ROLLED_BACK = "ROLLED_BACK"
QUARANTINED = "QUARANTINED"


@dataclass
class HardwareFeedback:
    power_ok: bool = True
    spi_ok: bool = True
    i2c_ok: bool = True
    gpio_ok: bool = True
    vcc_mv: float = 3300.0
    rssi_dbm: int = -60
    bus_error_count: int = 0
    watchdog_resets: int = 0


@dataclass(frozen=True)
class ModuleVersion:
    major: int = 1
    minor: int = 0
    slot: int = 0


@dataclass
class ModuleDescriptor:
    id: str
    active: ModuleVersion
    prev: ModuleVersion
    self_check: Callable[[HardwareFeedback], int] | None = None
    fail_threshold: int = 3
    # 运行期状态
    health_score: int = 0
    consecutive_fails: int = 0
    state: str = ACTIVE
    epoch: int = 0


@dataclass
class RollbackDecision:
    rolled: list = field(default_factory=list)
    quarantined: list = field(default_factory=list)


class ModuleManager:
    """与 C++ ModuleManager 同语义的状态机。"""

    def __init__(self) -> None:
        self._modules: list[ModuleDescriptor] = []

    def register_module(self, m: ModuleDescriptor) -> None:
        if self.find(m.id) is not None:
            return  # 重复 id 不覆盖
        d = ModuleDescriptor(
            id=m.id, active=m.active, prev=m.prev, self_check=m.self_check,
            fail_threshold=m.fail_threshold,
        )
        d.state = ACTIVE if m.self_check else INACTIVE  # 无回调=仅登记不体检
        self._modules.append(d)

    def run_health_check(self, fb: HardwareFeedback) -> None:
        for m in self._modules:
            if m.self_check is None or m.state == QUARANTINED:
                continue
            m.health_score = m.self_check(fb)
            if m.health_score < K_PASS_THRESHOLD:
                m.consecutive_fails += 1
            else:
                m.consecutive_fails = 0  # 一次合格清零（滞回）

    def evaluate_and_rollback(self) -> RollbackDecision:
        d = RollbackDecision()
        for m in self._modules:
            if m.consecutive_fails < m.fail_threshold:
                continue
            if m.state == ACTIVE:
                m.state = FAILED
                if self.rollback(m.id):
                    d.rolled.append(m.id)
            elif m.state == ROLLED_BACK:
                if self.quarantine(m.id):
                    d.quarantined.append(m.id)
        return d

    def rollback(self, id: str) -> bool:
        m = self.find(id)
        if m is None or m.state == QUARANTINED:
            return False
        if m.active == m.prev:  # 单版本无回滚目标
            m.state = FAILED
            return False
        m.active, m.prev = m.prev, m.active
        m.consecutive_fails = 0
        m.state = ROLLED_BACK
        m.epoch += 1
        return True

    def quarantine(self, id: str) -> bool:
        m = self.find(id)
        if m is None:
            return False
        m.state = QUARANTINED
        m.consecutive_fails = 0
        return True

    def find(self, id: str) -> ModuleDescriptor | None:
        for m in self._modules:
            if m.id == id:
                return m
        return None

    def snapshot(self) -> list[ModuleDescriptor]:
        return list(self._modules)
