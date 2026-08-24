"""
军牌系统 (DogTag) — 数据模型

定义统一后台任务调度的核心数据结构。
"""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class TriggerType(str, Enum):
    """任务触发类型"""
    EVENT_DRIVEN = "event_driven"   # 事件触发（对话结束 → 延迟 → 执行）
    PERIODIC = "periodic"           # 周期执行（每 N 秒检查一次）


class DutyStatus(str, Enum):
    """职责状态"""
    ENABLED = "enabled"
    DISABLED = "disabled"
    PAUSED = "paused"               # 条件不满足时暂停（如经典模式）


class ActivationCondition(BaseModel):
    """激活条件"""
    window_modes: list[str] | None = Field(
        default=None,
        description="限定窗口模式，如 ['ball','compact','full']；None 表示不限",
    )
    active_hours_start: str | None = Field(
        default=None,
        description="活跃时段开始，如 '08:00'",
    )
    active_hours_end: str | None = Field(
        default=None,
        description="活跃时段结束，如 '23:00'",
    )
    requires_user_active: bool = Field(
        default=False,
        description="是否要求用户活跃",
    )
    inactive_threshold_minutes: int = Field(
        default=10,
        description="用户不活跃阈值（分钟）",
    )


class DogTag(BaseModel):
    """军牌：一个后台职责的元信息"""
    duty_id: str
    name: str
    description: str
    trigger_type: TriggerType
    interval_seconds: int | None = Field(
        default=None,
        description="周期任务的间隔（秒）",
    )
    delay_seconds: int | None = Field(
        default=None,
        description="事件任务的延迟（秒）",
    )
    status: DutyStatus = DutyStatus.DISABLED
    activation: ActivationCondition | None = None
    execution_count: int = 0
    last_executed_at: str | None = None
