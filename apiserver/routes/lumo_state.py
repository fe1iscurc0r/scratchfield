"""NEKO 反向事件 → 用户状态快照（短时，内存态，零 LLM）。

与 message_manager 解耦：状态快照是「最近几分钟用户在 NEKO 侧做了什么」的
短时感知，不需要跨重启持久化，因此独立内存 dict + TTL 清理。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

# 快照 TTL：超过此秒数的状态视为过期，get_snapshot 返回空串
_STATE_TTL_SECONDS = 600  # 10 分钟
# 注入文本里 user_input/asr_result 的截断长度（控 token）
_TEXT_SNIPPET_LEN = 120


@dataclass
class LumoState:
    last_user_input: str | None = None       # 最近用户输入文本（截断）
    last_user_input_at: float | None = None
    last_action: str | None = None           # 最近 UI 操作（switch_character/stop_playback/...）
    last_action_at: float | None = None
    tts_interrupted: bool | None = None      # 最近一次 TTS 是否被打断
    tts_interrupted_at: float | None = None  # 打断时间戳（精确 TTL，不再借用）
    last_error: str | None = None            # "severity:error_type"
    last_error_at: float | None = None

    def _fresh(self, ts: float | None) -> bool:
        return ts is not None and (time.time() - ts) <= _STATE_TTL_SECONDS

    def render(self) -> str:
        """渲染为注入 environment_snapshot 的文本；全部过期返回空串。"""
        lines: list[str] = []
        if self._fresh(self.last_user_input_at) and self.last_user_input:
            lines.append(f"- 最近输入：「{self.last_user_input}」")
        if self._fresh(self.last_action_at) and self.last_action:
            lines.append(f"- 最近操作：{self.last_action}")
        if self.tts_interrupted and self._fresh(self.tts_interrupted_at):
            lines.append("- 语音：上次播放被用户打断")
        if self._fresh(self.last_error_at) and self.last_error:
            lines.append(f"- 身体状态：{self.last_error}（已上报异常）")
        if not lines:
            return ""
        return "【NEKO 侧用户状态】\n" + "\n".join(lines)


class LumoStateStore:
    """进程内快照存储，key = session_id。非线程安全，仅在 asyncio 单线程下使用。"""

    def __init__(self) -> None:
        self._states: dict[str, LumoState] = {}

    def _get(self, session_id: str) -> LumoState:
        return self._states.setdefault(session_id, LumoState())

    def update(self, session_id: str, event_type: str, payload: dict) -> None:
        """按 event_type 分流更新状态。无 LLM，纯字段写入。"""
        st = self._get(session_id)
        now = time.time()
        if event_type == "user_input":
            text = (payload.get("text") or "")[:_TEXT_SNIPPET_LEN]
            st.last_user_input = text
            st.last_user_input_at = now
        elif event_type == "asr_result":
            # 与 user_input 冗余，只在 voice 来源时补一条（confidence 低不覆盖）
            if (payload.get("confidence") or 0) >= 0.5:
                text = (payload.get("text") or "")[:_TEXT_SNIPPET_LEN]
                st.last_user_input = text
                st.last_user_input_at = now
        elif event_type == "user_action":
            st.last_action = payload.get("action") or payload.get("detail")
            st.last_action_at = now
        elif event_type == "tts_end":
            if payload.get("interrupted"):
                st.tts_interrupted = True
                st.tts_interrupted_at = now
        elif event_type == "tts_start":
            st.tts_interrupted = False
            st.tts_interrupted_at = None
        # error 走 mark_error，不在此分支

    def on_user_input(self, event) -> None:
        """EventBus v2 消费者入口：USER_INPUT_RECEIVED 事件 → 状态快照。

        由总线分发调用（本模块不感知生产者在哪，生产者也不知道本消费者）。
        error 事件走 mark_error（打降级标记），其余按 event_type 走 update。
        零 LLM，纯字段写入。主动搭话决策由 lumo_proactive 各自订阅总线触发。
        """
        if getattr(event, "event_type", None) == "error":
            self.mark_error(event.neko_session, event.severity, event.error_type)
        else:
            self.update(event.neko_session, event.event_type, event.model_dump())

    def mark_error(self, session_id: str, severity: str, error_type: str) -> None:
        st = self._get(session_id)
        st.last_error = f"{severity}:{error_type}"
        st.last_error_at = time.time()

    def get_snapshot(self, session_id: str) -> str:
        st = self._states.get(session_id)
        if not st:
            return ""
        return st.render()

    def gc(self) -> None:
        """清理 TTL 过期条目，防内存无界增长。可挂到低频定时器或懒触发。"""
        cutoff = time.time() - _STATE_TTL_SECONDS
        stale = [k for k, v in self._states.items()
                 if not (v._fresh(v.last_user_input_at) or v._fresh(v.last_action_at)
                         or v._fresh(v.last_error_at) or v._fresh(v.tts_interrupted_at))]
        for k in stale:
            del self._states[k]


# 模块级单例（与 message_manager 单例同风格）
_state_store = LumoStateStore()


def get_state_store() -> LumoStateStore:
    return _state_store
