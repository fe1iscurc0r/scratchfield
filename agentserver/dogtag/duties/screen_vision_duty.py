"""
军牌系统 — 屏幕感知职责

从 ProactiveVisionConfig 创建 DogTag + executor。
"""

from collections.abc import Callable
from typing import Tuple

from agentserver.dogtag.models import (
    ActivationCondition,
    DogTag,
    DutyStatus,
    TriggerType,
)
from agentserver.dogtag.screen_vision.config import ProactiveVisionConfig


def create_screen_vision_duty(config: ProactiveVisionConfig) -> tuple[DogTag, Callable]:
    """从 ProactiveVisionConfig 创建屏幕感知职责"""

    tag = DogTag(
        duty_id="screen_vision",
        name="屏幕感知",
        description="定时截屏分析，触发规则匹配",
        trigger_type=TriggerType.PERIODIC,
        interval_seconds=config.check_interval_seconds,
        status=DutyStatus.ENABLED if config.enabled else DutyStatus.DISABLED,
        activation=ActivationCondition(
            window_modes=["ball", "compact", "full"],
            active_hours_start=config.quiet_hours_end,    # 安静时段结束 = 活跃开始
            active_hours_end=config.quiet_hours_start,     # 安静时段开始 = 活跃结束
            requires_user_active=config.pause_on_user_inactive,
            inactive_threshold_minutes=config.inactive_threshold_minutes,
        ),
    )

    async def executor():
        from agentserver.dogtag.screen_vision.analyzer import get_proactive_analyzer
        analyzer = get_proactive_analyzer()
        if analyzer:
            await analyzer.analyze_screen()

    return tag, executor
