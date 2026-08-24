"""
军牌系统 (DogTag) — 统一调度器

合并 HeartbeatScheduler 的事件驱动逻辑与 ProactiveVisionScheduler 的周期调度逻辑，
用单一主循环管理所有后台职责。
"""

import asyncio
import logging
import time
from datetime import datetime
from datetime import time as dt_time
from typing import Dict, Optional

from .models import DogTag, DutyStatus, TriggerType
from .registry import DogTagRegistry, get_dogtag_registry

logger = logging.getLogger(__name__)


class DogTagScheduler:
    """统一调度器"""

    def __init__(self, registry: DogTagRegistry | None = None):
        self._registry = registry or get_dogtag_registry()

        # 运行状态
        self._running: bool = False
        self._task: asyncio.Task | None = None

        # 全局状态
        self._window_mode: str = "classic"
        self._conversation_active: bool = False
        self._last_user_activity: float = time.time()

        # 事件驱动：duty_id → 倒计时 asyncio.Task
        self._event_countdowns: dict[str, asyncio.Task] = {}

        # 周期任务：duty_id → 上次执行时间
        self._last_check_times: dict[str, float] = {}

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    async def start(self):
        """启动调度器"""
        if self._running:
            logger.warning("[DogTag] 调度器已在运行")
            return

        self._running = True
        self._task = asyncio.create_task(self._main_loop())
        logger.info("[DogTag] 调度器已启动")

    async def stop(self):
        """停止调度器"""
        if not self._running:
            return

        self._running = False

        # 取消所有事件倒计时
        for duty_id, countdown in list(self._event_countdowns.items()):
            if not countdown.done():
                countdown.cancel()
        self._event_countdowns.clear()

        # 取消主循环
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info("[DogTag] 调度器已停止")

    # ------------------------------------------------------------------
    # 主循环：1s tick，遍历 PERIODIC 任务
    # ------------------------------------------------------------------

    async def _main_loop(self):
        """主循环：每秒检查周期任务"""
        while self._running:
            try:
                # 遍历所有 ENABLED 的周期任务
                periodic_duties = self._registry.get_active_by_trigger(TriggerType.PERIODIC)
                for duty in periodic_duties:
                    if self._should_execute(duty):
                        last_time = self._last_check_times.get(duty.duty_id, 0.0)
                        elapsed = time.time() - last_time
                        interval = duty.interval_seconds or 30
                        if elapsed >= interval:
                            await self._execute_duty(duty)

                await asyncio.sleep(1)
            except asyncio.CancelledError:
                logger.info("[DogTag] 主循环被取消")
                break
            except Exception as e:
                logger.error(f"[DogTag] 主循环异常: {e}", exc_info=True)
                await asyncio.sleep(5)

    # ------------------------------------------------------------------
    # 条件检查
    # ------------------------------------------------------------------

    def _should_execute(self, duty: DogTag) -> bool:
        """检查职责是否满足执行条件"""
        # 状态检查
        if duty.status != DutyStatus.ENABLED:
            return False

        activation = duty.activation
        if activation is None:
            return True

        # 窗口模式检查
        if activation.window_modes is not None:
            if self._window_mode not in activation.window_modes:
                return False

        # 活跃时段检查
        if activation.active_hours_start and activation.active_hours_end:
            if not self._is_in_active_hours(
                activation.active_hours_start,
                activation.active_hours_end,
            ):
                return False

        # 用户活跃度检查
        if activation.requires_user_active:
            inactive_duration = time.time() - self._last_user_activity
            threshold = activation.inactive_threshold_minutes * 60
            if inactive_duration > threshold:
                return False

        return True

    @staticmethod
    def _is_in_active_hours(start_str: str, end_str: str) -> bool:
        """检查当前是否在活跃时段"""
        from agentserver.utils import is_time_in_range

        try:
            now = datetime.now().time()
            start = dt_time.fromisoformat(start_str)
            end = dt_time.fromisoformat(end_str)
            return is_time_in_range(now, start, end)
        except ValueError:
            logger.error(f"[DogTag] 时段格式错误: {start_str} - {end_str}")
            return True  # 格式错误时不阻塞

    # ------------------------------------------------------------------
    # 执行
    # ------------------------------------------------------------------

    async def _execute_duty(self, duty: DogTag):
        """执行一个职责"""
        executor = self._registry.get_executor(duty.duty_id)
        if not executor:
            logger.warning(f"[DogTag] 职责 '{duty.duty_id}' 无执行器，跳过")
            return

        try:
            logger.info(f"[DogTag] 执行职责: {duty.duty_id} ({duty.name})")
            self._last_check_times[duty.duty_id] = time.time()
            await executor()
            duty.execution_count += 1
            duty.last_executed_at = datetime.now().isoformat()
            logger.info(
                f"[DogTag] 职责 '{duty.duty_id}' 执行完成 "
                f"(第 {duty.execution_count} 次)"
            )
        except Exception as e:
            logger.error(
                f"[DogTag] 职责 '{duty.duty_id}' 执行失败: {e}",
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # 事件驱动支持
    # ------------------------------------------------------------------

    def on_conversation_started(self):
        """对话开始 → 取消所有事件倒计时"""
        self._conversation_active = True
        cancelled = []
        for duty_id, countdown in list(self._event_countdowns.items()):
            if not countdown.done():
                countdown.cancel()
                cancelled.append(duty_id)
        self._event_countdowns.clear()
        if cancelled:
            logger.info(f"[DogTag] 对话开始，已取消倒计时: {cancelled}")

    def on_conversation_ended(self):
        """对话结束 → 为所有 ENABLED 的 EVENT_DRIVEN 任务启动倒计时"""
        self._conversation_active = False
        event_duties = self._registry.get_active_by_trigger(TriggerType.EVENT_DRIVEN)
        for duty in event_duties:
            # 取消该职责已有的倒计时
            old = self._event_countdowns.get(duty.duty_id)
            if old and not old.done():
                old.cancel()
            task = asyncio.create_task(self._countdown_then_execute(duty))
            self._event_countdowns[duty.duty_id] = task
            delay = duty.delay_seconds or 300
            logger.info(
                f"[DogTag] 对话结束，职责 '{duty.duty_id}' 启动 {delay}s 倒计时"
            )

    async def _countdown_then_execute(self, duty: DogTag):
        """倒计时结束后执行职责"""
        try:
            delay = duty.delay_seconds or 300
            await asyncio.sleep(delay)

            # 再次检查条件
            if self._should_execute(duty) and not self._conversation_active:
                logger.info(
                    f"[DogTag] 职责 '{duty.duty_id}' 倒计时到期，执行"
                )
                await self._execute_duty(duty)
            else:
                logger.info(
                    f"[DogTag] 职责 '{duty.duty_id}' 倒计时到期，"
                    f"但条件不满足或对话已开始，跳过"
                )
        except asyncio.CancelledError:
            logger.info(
                f"[DogTag] 职责 '{duty.duty_id}' 倒计时被取消"
            )
        finally:
            self._event_countdowns.pop(duty.duty_id, None)

    # ------------------------------------------------------------------
    # 手动触发
    # ------------------------------------------------------------------

    async def trigger_once(self, duty_id: str):
        """手动触发一次职责（忽略条件检查）"""
        duty = self._registry.get(duty_id)
        if not duty:
            logger.warning(f"[DogTag] 职责 '{duty_id}' 不存在，无法触发")
            return
        logger.info(f"[DogTag] 手动触发: {duty_id}")
        await self._execute_duty(duty)

    # ------------------------------------------------------------------
    # 全局状态管理
    # ------------------------------------------------------------------

    def set_window_mode(self, mode: str):
        """更新窗口模式，自动暂停/恢复受影响的任务"""
        old_mode = self._window_mode
        self._window_mode = mode

        if old_mode == mode:
            return

        logger.info(f"[DogTag] 窗口模式切换: {old_mode} → {mode}")

        # 检查所有有窗口模式限制的职责，自动 pause/resume
        for duty in self._registry.get_all().values():
            if duty.activation and duty.activation.window_modes is not None:
                should_active = mode in duty.activation.window_modes
                if not should_active and duty.status == DutyStatus.ENABLED:
                    duty.status = DutyStatus.PAUSED
                    logger.info(
                        f"[DogTag] 职责 '{duty.duty_id}' 因窗口模式 "
                        f"'{mode}' 自动暂停"
                    )
                elif should_active and duty.status == DutyStatus.PAUSED:
                    duty.status = DutyStatus.ENABLED
                    logger.info(
                        f"[DogTag] 职责 '{duty.duty_id}' 因窗口模式 "
                        f"'{mode}' 自动恢复"
                    )

    def update_user_activity(self):
        """更新用户活动时间"""
        self._last_user_activity = time.time()

    def reset_check_timer(self, duty_id: str, reason: str = "external_trigger"):
        """重置指定周期任务的检查计时器"""
        self._last_check_times[duty_id] = time.time()
        logger.info(
            f"[DogTag] 职责 '{duty_id}' 检查计时器已重置 (原因: {reason})"
        )

    def get_status(self) -> dict:
        """返回调度器状态 + 所有任务状态"""
        duties_status = {}
        for duty_id, duty in self._registry.get_all().items():
            countdown_active = (
                duty_id in self._event_countdowns
                and not self._event_countdowns[duty_id].done()
            )
            duties_status[duty_id] = {
                "name": duty.name,
                "description": duty.description,
                "trigger_type": duty.trigger_type.value,
                "status": duty.status.value,
                "execution_count": duty.execution_count,
                "last_executed_at": duty.last_executed_at,
                "countdown_active": countdown_active,
            }

        return {
            "running": self._running,
            "window_mode": self._window_mode,
            "conversation_active": self._conversation_active,
            "last_user_activity": datetime.fromtimestamp(
                self._last_user_activity
            ).isoformat(),
            "duties": duties_status,
        }


# ======================================================================
# 全局单例
# ======================================================================

_scheduler: DogTagScheduler | None = None


def create_dogtag_scheduler(
    registry: DogTagRegistry | None = None,
) -> DogTagScheduler:
    """创建调度器单例"""
    global _scheduler
    if _scheduler is not None:
        logger.warning("[DogTag] 调度器已存在，将被替换")
    _scheduler = DogTagScheduler(registry)
    return _scheduler


def get_dogtag_scheduler() -> DogTagScheduler | None:
    """获取调度器单例"""
    return _scheduler
