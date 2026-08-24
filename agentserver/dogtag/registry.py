"""
军牌系统 (DogTag) — 任务注册表

管理所有 DogTag 职责的注册、查询与状态变更。
"""

import logging
from collections.abc import Callable
from typing import Dict, List, Optional

from .models import DogTag, DutyStatus, TriggerType

logger = logging.getLogger(__name__)


class DogTagRegistry:
    """军牌注册表：管理所有职责的元信息与执行器"""

    def __init__(self):
        self._duties: dict[str, DogTag] = {}
        self._executors: dict[str, Callable] = {}  # duty_id → async executor()

    def register(self, tag: DogTag, executor: Callable) -> None:
        """注册一个职责"""
        if tag.duty_id in self._duties:
            logger.warning(f"[DogTag] 职责 '{tag.duty_id}' 已存在，将被覆盖")
        self._duties[tag.duty_id] = tag
        self._executors[tag.duty_id] = executor
        logger.info(f"[DogTag] 注册职责: {tag.duty_id} ({tag.name})")

    def unregister(self, duty_id: str) -> None:
        """移除一个职责"""
        self._duties.pop(duty_id, None)
        self._executors.pop(duty_id, None)
        logger.info(f"[DogTag] 移除职责: {duty_id}")

    def get(self, duty_id: str) -> DogTag | None:
        """获取单个职责"""
        return self._duties.get(duty_id)

    def get_all(self) -> dict[str, DogTag]:
        """获取所有职责"""
        return dict(self._duties)

    def get_active_by_trigger(self, trigger_type: TriggerType) -> list[DogTag]:
        """获取指定触发类型下状态为 ENABLED 的职责"""
        return [
            tag for tag in self._duties.values()
            if tag.trigger_type == trigger_type and tag.status == DutyStatus.ENABLED
        ]

    def get_executor(self, duty_id: str) -> Callable | None:
        """获取职责的执行器"""
        return self._executors.get(duty_id)

    def update_status(self, duty_id: str, status: DutyStatus) -> None:
        """更新职责状态"""
        tag = self._duties.get(duty_id)
        if tag:
            old_status = tag.status
            tag.status = status
            logger.info(f"[DogTag] 职责 '{duty_id}' 状态变更: {old_status.value} → {status.value}")
        else:
            logger.warning(f"[DogTag] 职责 '{duty_id}' 不存在，无法更新状态")


# ======================================================================
# 全局单例
# ======================================================================

_registry: DogTagRegistry | None = None


def get_dogtag_registry() -> DogTagRegistry:
    """获取或创建全局注册表单例"""
    global _registry
    if _registry is None:
        _registry = DogTagRegistry()
    return _registry
