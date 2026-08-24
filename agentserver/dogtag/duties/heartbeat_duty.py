"""
军牌系统 — 心跳职责

包含心跳的完整执行逻辑（LLM 调用、checklist 解析、UI 推送）
以及从 HeartbeatConfig 创建 DogTag + executor 的工厂函数。
"""

import logging
import re
import time
from collections.abc import Callable
from datetime import datetime
from typing import Optional, Tuple

import httpx

from agentserver.dogtag.heartbeat_config import HeartbeatConfig
from agentserver.dogtag.heartbeat_prompt import HEARTBEAT_CHECKLIST, HEARTBEAT_SYSTEM_PROMPT
from agentserver.dogtag.models import (
    ActivationCondition,
    DogTag,
    DutyStatus,
    TriggerType,
)

logger = logging.getLogger(__name__)

# HEARTBEAT_OK 标记 — 响应中包含此标记且长度 ≤ ack_max_chars 时静默丢弃
_ACK_MARKER = "HEARTBEAT_OK"

# checklist 指令正则
_RE_ADD_ITEM = re.compile(r"^\[ADD_ITEM\]\s*(.+)$", re.MULTILINE)
_RE_DONE_ITEM = re.compile(r"^\[DONE_ITEM\]\s*(\S+)$", re.MULTILINE)
_RE_DISMISS_ITEM = re.compile(r"^\[DISMISS_ITEM\]\s*(\S+)$", re.MULTILINE)


class HeartbeatExecutor:
    """心跳执行器：LLM 调用 → checklist 解析 → UI 推送"""

    def __init__(self, config: HeartbeatConfig):
        self.config = config
        self._last_heartbeat_time: float = 0.0
        self._last_heartbeat_result: str | None = None
        self._heartbeat_count: int = 0
        self._http_client: httpx.AsyncClient | None = None

    def _get_http_client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=5.0, proxy=None)
        return self._http_client

    async def close(self):
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
            self._http_client = None

    # ------------------------------------------------------------------
    # 心跳执行
    # ------------------------------------------------------------------

    async def perform_heartbeat(self):
        """执行一次心跳：调用 LLM → 解析指令 → 推送 UI"""
        logger.info("[Heartbeat] 执行心跳检查...")
        self._heartbeat_count += 1
        self._last_heartbeat_time = time.time()

        try:
            response = await self._call_llm()
            self._last_heartbeat_result = response

            self._parse_checklist_commands(response)

            display_text = self._strip_commands(response)

            is_ack = (
                _ACK_MARKER in display_text
                and len(display_text) <= self.config.ack_max_chars
            )

            if is_ack:
                logger.info("[Heartbeat] LLM 回复 HEARTBEAT_OK，静默丢弃")
            else:
                logger.info(f"[Heartbeat] LLM 有内容推送 ({len(display_text)} chars)")
                await self._notify_ui(display_text)
        except Exception as e:
            logger.error(f"[Heartbeat] 心跳执行失败: {e}", exc_info=True)

    async def _call_llm(self) -> str:
        """调用 Naga LLM"""
        from agentserver.dogtag.checklist import get_pending_items
        from apiserver.llm_service import get_llm_service
        from apiserver.message_manager import message_manager

        llm = get_llm_service()

        system_content = HEARTBEAT_SYSTEM_PROMPT
        session_id = self._get_active_session_id()

        if session_id:
            compress = message_manager.get_session_compress(session_id)
            if compress:
                system_content += (
                    f"\n\n以下是历史对话的压缩记录：\n<compress>\n{compress}\n</compress>"
                )

        messages = [{"role": "system", "content": system_content}]

        if session_id:
            session_msgs = message_manager.get_messages(session_id)
            session_msgs = [m for m in session_msgs if m.get("role") != "info"]
            messages.extend(session_msgs)
            logger.info(f"[Heartbeat] 注入会话 {session_id} 的 {len(session_msgs)} 条消息")

        prompt_text = self.config.prompt.strip() or HEARTBEAT_CHECKLIST

        pending = get_pending_items()
        if pending:
            lines = ["\n\n当前待处理事项 (Checklist)："]
            for item in pending:
                tag = f"[{item.priority}]" if item.priority != "normal" else ""
                lines.append(f"- [{item.id}] {tag} {item.content}")
            prompt_text += "\n".join(lines)

        messages.append({"role": "user", "content": prompt_text})

        return await llm.chat_with_context(messages, temperature=0.3)

    @staticmethod
    def _get_active_session_id() -> str | None:
        """获取最近活跃的会话 ID"""
        try:
            from apiserver.message_manager import message_manager

            candidates = [
                (sid, s)
                for sid, s in message_manager.sessions.items()
                if s.get("messages")
            ]
            if not candidates:
                return None
            candidates.sort(
                key=lambda x: x[1].get("last_activity", ""), reverse=True
            )
            return candidates[0][0]
        except Exception as e:
            logger.warning(f"[Heartbeat] 获取活跃会话失败: {e}")
            return None

    # ------------------------------------------------------------------
    # Checklist 指令解析
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_checklist_commands(response: str):
        """解析 LLM 响应中的 checklist 操作指令并执行"""
        from agentserver.dogtag.checklist import add_item, batch_update, update_item

        with batch_update():
            for match in _RE_ADD_ITEM.finditer(response):
                content = match.group(1).strip()
                if content:
                    add_item(content, source="llm")
                    logger.info(f"[Heartbeat] LLM 新增 checklist: {content[:50]}")

            for match in _RE_DONE_ITEM.finditer(response):
                item_id = match.group(1).strip()
                if item_id:
                    update_item(item_id, status="done")
                    logger.info(f"[Heartbeat] LLM 完成 checklist: {item_id}")

            for match in _RE_DISMISS_ITEM.finditer(response):
                item_id = match.group(1).strip()
                if item_id:
                    update_item(item_id, status="dismissed")
                    logger.info(f"[Heartbeat] LLM 忽略 checklist: {item_id}")

    @staticmethod
    def _strip_commands(response: str) -> str:
        """移除指令行，返回面向用户的纯文本"""
        lines = response.splitlines()
        clean = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("[ADD_ITEM]"):
                continue
            if stripped.startswith("[DONE_ITEM]"):
                continue
            if stripped.startswith("[DISMISS_ITEM]"):
                continue
            clean.append(line)
        return "\n".join(clean).strip()

    # ------------------------------------------------------------------
    # UI 推送
    # ------------------------------------------------------------------

    async def _notify_ui(self, response: str):
        """推送心跳结果：通过 api_server /queue/push 统一路由"""
        try:
            from system.config import get_server_port

            api_port = get_server_port("api_server")
            client = self._get_http_client()
            resp = await client.post(
                f"http://localhost:{api_port}/queue/push",
                json={"content": response, "source": "heartbeat"},
            )
            if resp.status_code == 200:
                result = resp.json()
                logger.info(f"[Heartbeat] 推送结果: {result.get('status', 'unknown')}")
            else:
                logger.warning(f"[Heartbeat] 推送返回 {resp.status_code}")
        except Exception as e:
            logger.warning(f"[Heartbeat] 推送失败: {e}")

    # ------------------------------------------------------------------
    # 手动触发 / 状态
    # ------------------------------------------------------------------

    async def trigger_once(self):
        """手动触发一次心跳"""
        logger.info("[Heartbeat] 手动触发心跳")
        await self.perform_heartbeat()

    def get_status(self) -> dict:
        """返回执行器运行状态"""
        return {
            "enabled": self.config.enabled,
            "mode": "event_driven",
            "post_conversation_delay_minutes": self.config.post_conversation_delay_minutes,
            "last_heartbeat_time": (
                datetime.fromtimestamp(self._last_heartbeat_time).isoformat()
                if self._last_heartbeat_time
                else None
            ),
            "heartbeat_count": self._heartbeat_count,
            "last_result_preview": (
                self._last_heartbeat_result[:200]
                if self._last_heartbeat_result
                else None
            ),
        }


# ======================================================================
# 全局单例
# ======================================================================

_executor: HeartbeatExecutor | None = None


def get_heartbeat_executor() -> HeartbeatExecutor | None:
    """获取执行器单例"""
    return _executor


def create_heartbeat_executor(config: HeartbeatConfig) -> HeartbeatExecutor:
    """创建并注册执行器单例"""
    global _executor
    if _executor is not None:
        logger.warning("[Heartbeat] 执行器已存在，将被替换")
    _executor = HeartbeatExecutor(config)
    return _executor


# ======================================================================
# DogTag 工厂
# ======================================================================


def create_heartbeat_duty(config: HeartbeatConfig) -> tuple[DogTag, Callable]:
    """从 HeartbeatConfig 创建心跳职责"""

    tag = DogTag(
        duty_id="heartbeat",
        name="心跳检查",
        description="对话结束后审查待办清单",
        trigger_type=TriggerType.EVENT_DRIVEN,
        delay_seconds=config.post_conversation_delay_minutes * 60,
        status=DutyStatus.ENABLED if config.enabled else DutyStatus.DISABLED,
        activation=ActivationCondition(
            active_hours_start=config.active_hours_start,
            active_hours_end=config.active_hours_end,
        ),
    )

    async def executor():
        hb = get_heartbeat_executor()
        if hb:
            await hb.perform_heartbeat()

    return tag, executor
