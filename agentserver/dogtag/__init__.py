"""
军牌系统 (DogTag) — 统一后台任务调度

将心跳检查和屏幕感知等后台职责纳入统一的任务队列池管理。
心跳的 checklist、prompt、config、执行器均已归入本包。
屏幕感知的 analyzer、trigger、metrics、config 均已归入 screen_vision 子包。
"""

# 核心模型
# Checklist
from .checklist import (
    ChecklistItem,
    HeartbeatChecklist,
    add_item,
    batch_update,
    get_pending_items,
    load_checklist,
    remove_item,
    save_checklist,
    update_item,
)

# 心跳执行器
from .duties.heartbeat_duty import (
    HeartbeatExecutor,
    create_heartbeat_duty,
    create_heartbeat_executor,
    get_heartbeat_executor,
)

# 心跳配置
from .heartbeat_config import (
    HeartbeatConfig,
    load_heartbeat_config,
    save_heartbeat_config,
)

# 心跳 prompt
from .heartbeat_prompt import HEARTBEAT_CHECKLIST, HEARTBEAT_SYSTEM_PROMPT
from .models import ActivationCondition, DogTag, DutyStatus, TriggerType

# 注册表
from .registry import DogTagRegistry, get_dogtag_registry

# 调度器
from .scheduler import DogTagScheduler, create_dogtag_scheduler, get_dogtag_scheduler

# 屏幕感知
from .screen_vision import (
    ProactiveVisionAnalyzer,
    ProactiveVisionConfig,
    ProactiveVisionTrigger,
    TriggerRule,
    create_proactive_analyzer,
    create_proactive_trigger,
    get_proactive_analyzer,
    get_proactive_trigger,
    load_proactive_config,
    save_proactive_config,
)

__all__ = [
    # 核心模型
    "DogTag",
    "TriggerType",
    "DutyStatus",
    "ActivationCondition",
    # 注册表
    "DogTagRegistry",
    "get_dogtag_registry",
    # 调度器
    "DogTagScheduler",
    "create_dogtag_scheduler",
    "get_dogtag_scheduler",
    # 心跳配置
    "HeartbeatConfig",
    "load_heartbeat_config",
    "save_heartbeat_config",
    # 心跳 prompt
    "HEARTBEAT_SYSTEM_PROMPT",
    "HEARTBEAT_CHECKLIST",
    # 心跳执行器
    "HeartbeatExecutor",
    "get_heartbeat_executor",
    "create_heartbeat_executor",
    "create_heartbeat_duty",
    # Checklist
    "ChecklistItem",
    "HeartbeatChecklist",
    "load_checklist",
    "save_checklist",
    "add_item",
    "update_item",
    "remove_item",
    "get_pending_items",
    "batch_update",
    # 屏幕感知
    "ProactiveVisionConfig",
    "TriggerRule",
    "load_proactive_config",
    "save_proactive_config",
    "ProactiveVisionAnalyzer",
    "get_proactive_analyzer",
    "create_proactive_analyzer",
    "ProactiveVisionTrigger",
    "get_proactive_trigger",
    "create_proactive_trigger",
]
