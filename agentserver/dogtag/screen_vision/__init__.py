"""
军牌系统 — 屏幕感知子系统 (Screen Vision)

原 proactive_vision 包的全部功能，现作为 dogtag 的子模块管理。
调度逻辑由 DogTagScheduler 统一接管。
"""

from .analyzer import (
    ProactiveVisionAnalyzer,
    create_proactive_analyzer,
    get_proactive_analyzer,
)
from .config import ProactiveVisionConfig, TriggerRule
from .config_loader import (
    get_default_config,
    load_proactive_config,
    save_proactive_config,
    update_proactive_config,
)
from .metrics import ProactiveVisionMetrics, get_metrics
from .trigger import (
    ProactiveVisionTrigger,
    create_proactive_trigger,
    get_proactive_trigger,
)

__all__ = [
    # 配置
    "ProactiveVisionConfig",
    "TriggerRule",
    "load_proactive_config",
    "save_proactive_config",
    "get_default_config",
    "update_proactive_config",
    # 分析器
    "ProactiveVisionAnalyzer",
    "get_proactive_analyzer",
    "create_proactive_analyzer",
    # 触发器
    "ProactiveVisionTrigger",
    "get_proactive_trigger",
    "create_proactive_trigger",
    # 指标
    "ProactiveVisionMetrics",
    "get_metrics",
]
