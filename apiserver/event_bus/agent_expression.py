"""工单202 任务四接线：agent 状态 → 情绪 的总线桥。

链路：
    agent 事件（Topics.*）→ 本模块映射 → Topics.EMOTION_REQUESTED
    → bridge.py（已有，`_build_request` 消费 LUMO_EMOTION_REQUESTED）
    → POST /api/lumo/emotion → NEKO 切 Live2D 表情

与壳层同构：`neko-electron-shell/src/agent-state-expression.js` 持有同一套状态机与
映射表（JS 版供 HUD/桌宠本地展示，Python 版供总线注入）。**emotion 收敛到 NEKO
5 标准情绪**——实测 `NEKO/N.E.K.O/main_routers/system_router/emotion.py:401
_normalize_emotion_label` 会把任意标签（165 个别名）归一化到
`angry/happy/neutral/sad/surprised`，自定义标签不可依赖。

开关：`LUMO_AGENT_EXPRESSION=1` 启用（**默认关**——避免每次工具调用都注入情绪）。
铁律：未知主题不猜（返回 None）；无角色名不发（fail closed）。
"""
from __future__ import annotations

import os
from typing import Any, Callable

from .topics import Topics

# ---- 状态（与壳层 STATES 同名，单一词汇） ----------------------------------
STATE_IDLE = "idle"
STATE_THINKING = "thinking"
STATE_WORKING = "working"
STATE_WAIT = "wait"
STATE_ERROR = "error"
STATE_CELEBRATE = "celebrate"

#: NEKO 注入侧可信的情绪集（实测契约，见模块 docstring）
NEKO_STANDARD_EMOTIONS: tuple[str, ...] = (
    "angry", "happy", "neutral", "sad", "surprised",
)

#: 状态 → 表情（emotion ⊆ 标准集；motion/label 供展示层，不经 NEKO 注入）
STATE_EXPRESSION: dict[str, dict[str, str]] = {
    STATE_IDLE: {"emotion": "neutral", "motion": "idle", "label": "待机"},
    STATE_THINKING: {"emotion": "neutral", "motion": "think", "label": "思考中"},
    STATE_WORKING: {"emotion": "neutral", "motion": "working", "label": "执行中"},
    STATE_WAIT: {"emotion": "surprised", "motion": "wait", "label": "等待确认"},
    STATE_ERROR: {"emotion": "sad", "motion": "error", "label": "出错了"},
    STATE_CELEBRATE: {"emotion": "happy", "motion": "celebrate", "label": "完成"},
}

#: agent 事件主题 → 状态。**只列有真实来源的**：
#:   wait 在 apiserver 侧暂无独立主题（confirm_gate 是 TOOL_PRE_EXECUTE 的 waterfall
#:   handler，不发主题）——壳层可用 NEKO 任务态的 blocked/clarify/confirm_required 补齐。
EVENT_TO_STATE: dict[str, str] = {
    Topics.USER_INPUT_RECEIVED: STATE_THINKING,
    Topics.TOOL_PRE_EXECUTE: STATE_WORKING,
    Topics.TOOL_GUARD: STATE_WORKING,
    Topics.TTS_START: STATE_THINKING,
    Topics.DECISION_COMPLETED: STATE_CELEBRATE,
}

_FAILURE_MARKERS = {"error", "failed", "failure"}


def _norm_topic(topic: Any) -> str:
    """枚举/字符串主题统一取字符串值（StrEnum 直接当 str 用）。"""
    return str(getattr(topic, "value", topic) or "").strip()


def _is_failure(payload: Any) -> bool:
    """显式失败标记才判失败（不猜）。"""
    if not isinstance(payload, dict):
        return False
    status = str(payload.get("status") or payload.get("result") or "").lower()
    if status in _FAILURE_MARKERS:
        return True
    if payload.get("ok") is False:
        return True
    return bool(payload.get("error"))


def reduce_state(topic: Any, payload: Any = None) -> str | None:
    """主题 → 状态；未知主题返回 None（**不改写、不猜**）。"""
    key = _norm_topic(topic)
    if not key:
        return None
    if key == _norm_topic(Topics.TOOL_POST_EXECUTE):
        return STATE_ERROR if _is_failure(payload) else STATE_THINKING
    return EVENT_TO_STATE.get(key)


def to_emotion_request(state: str, character: str | None) -> dict[str, Any] | None:
    """状态 + 角色名 → NEKO 注入体；缺任一项返回 None（fail closed）。"""
    name = str(character or "").strip()
    if not name:
        return None
    entry = STATE_EXPRESSION.get(str(state or "").strip())
    if not entry:
        return None
    return {"lanlan_name": name, "emotion": entry["emotion"], "state": str(state)}


def _default_enabled() -> bool:
    """默认关：只有显式 LUMO_AGENT_EXPRESSION=1 才启用注入。"""
    return os.environ.get("LUMO_AGENT_EXPRESSION", "").strip() == "1"


class AgentExpressionBridge:
    """把 agent 事件翻成 EMOTION_REQUESTED 发到总线（可关、可测、零全局依赖）。

    ``emit``：形如 InProcessEventBus.emit(topic, event) 的可调用；
    ``character_provider``：返回当前角色名（None/空则不注入）；
    ``enabled``：None 时读环境变量（默认关）。
    """

    def __init__(self, emit: Callable[[str, Any], None],
                 character_provider: Callable[[], str | None] | None = None,
                 enabled: bool | None = None) -> None:
        self._emit = emit
        self._character_provider = character_provider
        self.enabled = _default_enabled() if enabled is None else bool(enabled)
        self.injected = 0
        self.skipped = 0

    def _character(self) -> str | None:
        if self._character_provider is None:
            return None
        try:
            return self._character_provider()
        except Exception:  # noqa: BLE001 - 角色解析失败按无角色处理（不注入）
            return None

    def on_event(self, topic: Any, payload: Any = None) -> dict[str, Any] | None:
        """处理一个 agent 事件；注入成功返回请求体，否则 None（并计入 skipped）。"""
        if not self.enabled:
            self.skipped += 1
            return None
        state = reduce_state(topic, payload)
        if state is None:
            self.skipped += 1
            return None
        req = to_emotion_request(state, self._character())
        if req is None:
            self.skipped += 1
            return None
        self._emit(Topics.EMOTION_REQUESTED, {
            "emotion": req["emotion"],
            "character": req["lanlan_name"],
            "state": state,
            "source": "agent_expression",
        })
        self.injected += 1
        return req

    def stats(self) -> dict[str, int | bool]:
        return {"enabled": self.enabled, "injected": self.injected, "skipped": self.skipped}
