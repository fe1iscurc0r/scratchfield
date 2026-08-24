"""M3.1b 主动搭话时机决策器 — 规则门先筛（零 LLM），LLM 只在过门后介入。

参考 N.E.K.O. proactive_chat：reason_code 门控 + 半衰期衰减 + 三档冷却。
本实现只读 lumo_state（M3.1a），非侵入。speak 通道调用留待联调（SPEC 待联调假设）。
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("ProactiveDecider")

# ── 冷却/频率/静默配置（参考 N.E.K.O. proactive_settings，可调）──
COOLDOWN_ACCEPT_SECONDS = 2 * 3600      # 接受后 2h 静默
COOLDOWN_DECLINE_SECONDS = 5 * 3600     # 拒绝后 5h 静默
COOLDOWN_IGNORE_SECONDS = 30 * 60       # 无回应 30min 静默
MAX_PER_HOUR = 3                        # 每小时最多 3 次主动搭话
SILENT_START_HOUR = 23                  # 静默期开始
SILENT_END_HOUR = 7                     # 静默期结束
TOPIC_HALF_LIFE_SECONDS = 4 * 3600      # 话题半衰期 4h（防复读）

# 主动搭话用轻量模型（同 intent_router.ROUTER_MODEL）
PROACTIVE_MODEL = "gpt-4.1-nano"


@dataclass
class ProactiveState:
    """单 session 的主动搭话状态（内存态，与 lumo_state 同风格）。"""
    last_open_at: float = 0.0
    last_response: str = "ignore"          # accept / decline / ignore
    opens_this_hour: list[float] = field(default_factory=list)
    last_topics: dict[str, float] = field(default_factory=dict)  # topic_hash -> ts


class ProactiveDecider:
    """规则门 + LLM 决策 + 冷却状态。非线程安全，仅在 asyncio 单线程使用。"""

    def __init__(self) -> None:
        self._states: dict[str, ProactiveState] = {}

    # ── 阶段 A：规则门（纯 Python，零 LLM）──

    def _gate(self, sid: str, snapshot: str, now: float) -> Optional[str]:
        """过五道门，返回 None=通过，否则返回 reason_code（可审计）。"""
        st = self._states.setdefault(sid, ProactiveState())

        # ① 冷却门
        cooldown = {
            "accept": COOLDOWN_ACCEPT_SECONDS,
            "decline": COOLDOWN_DECLINE_SECONDS,
            "ignore": COOLDOWN_IGNORE_SECONDS,
        }.get(st.last_response, COOLDOWN_IGNORE_SECONDS)
        if now - st.last_open_at < cooldown:
            return "PASS_COOLDOWN"

        # ② 频率门
        st.opens_this_hour = [t for t in st.opens_this_hour if now - t < 3600]
        if len(st.opens_this_hour) >= MAX_PER_HOUR:
            return "PASS_THROTTLED"

        # ③ 状态门：用户活跃中（快照非空 = 最近有活动）→ 不打扰
        if snapshot:
            return "PASS_USER_ACTIVE"

        # ④ 静默门：深夜不打扰
        hour = time.localtime(now).tm_hour
        if hour >= SILENT_START_HOUR or hour < SILENT_END_HOUR:
            return "PASS_SILENT_HOURS"

        return None  # 通过所有门

    def _topic_decayed(self, sid: str, topic_hash: str, now: float) -> bool:
        """话题半衰期衰减：返回 True=可推，False=刚推过（跳过）。"""
        st = self._states.setdefault(sid, ProactiveState())
        last = st.last_topics.get(topic_hash, 0.0)
        if last and (now - last) < TOPIC_HALF_LIFE_SECONDS:
            return False  # 未衰减，跳过
        return True

    # ── 阶段 B：LLM 决策（过门后才触发，单次）──

    async def _llm_decide(self, prompt: str) -> dict:
        """轻量 LLM 判定「开口/不开口」。任何异常降级为不开（不崩溃）。"""
        try:
            import litellm
            from system.llm_params import get_llm_params, build_model_name
            resp = await litellm.acompletion(
                model=build_model_name(PROACTIVE_MODEL, model_type="router"),
                messages=[{"role": "system", "content": prompt}],
                temperature=0,
                max_tokens=120,
                **get_llm_params(model_type="router"),
            )
            import json
            raw = resp.choices[0].message.content or "{}"
            try:
                return json.loads(raw)
            except Exception:
                return {"open": False, "text": ""}
        except Exception as e:
            logger.warning(f"[ProactiveDecider] LLM 决策失败，降级为不开: {e}")
            return {"open": False, "text": ""}

    # ── 主入口：一次「主动搭话检查」──

    async def check(self, sid: str, snapshot: str, topic: str) -> Optional[dict]:
        """规则门 → 话题衰减 → LLM 决策 → 返回行动（或 None=不搭话）。"""
        now = time.time()
        reason = self._gate(sid, snapshot, now)
        if reason:
            logger.debug(f"[ProactiveDecider] {sid} 门不通过: {reason}")
            return None

        topic_hash = topic[:32]
        if not self._topic_decayed(sid, topic_hash, now):
            logger.debug(f"[ProactiveDecider] {sid} 话题未衰减，跳过")
            return None

        prompt = (
            "你是陆墨，一个主动陪伴用户的 AI 搭档。判断是否该主动说话。\n"
            f"候选话题：{topic}\n"
            '只输出 JSON：{"open": true/false, "text": "要说的内容"}\n'
            '若话题不值得主动开口，输出 {"open": false}。'
        )
        decision = await self._llm_decide(prompt)
        if not decision.get("open"):
            return None

        st = self._states.setdefault(sid, ProactiveState())
        st.last_open_at = now
        st.opens_this_hour.append(now)
        st.last_topics[topic_hash] = now
        return {"text": decision.get("text", ""), "topic": topic}

    async def on_user_input(self, event) -> None:
        """EventBus v2 消费者入口：USER_INPUT_RECEIVED 事件 → 主动搭话检查。

        与 lumo_state 解耦：本方法自行读状态快照（state 消费者先注册、emit 时
        先同步更新，此处快照必为最新）。error 事件不触发（与旧硬编码行为一致）。
        """
        if getattr(event, "event_type", None) == "error":
            return
        from .lumo_state import get_state_store
        sid = event.neko_session
        snapshot = get_state_store().get_snapshot(sid)
        await self.check(sid, snapshot, "科研提醒")

    def respond(self, sid: str, response: str) -> None:
        """用户回应（accept/decline/ignore）→ 更新冷却。"""
        st = self._states.setdefault(sid, ProactiveState())
        st.last_response = response if response in ("accept", "decline") else "ignore"

    # ── 定时器兜底 ──

    async def _periodic_check(self, interval: int = 300) -> None:
        """每 5 分钟兜底检查一次（无事件时也能主动）。"""
        from .lumo_state import get_state_store
        store = get_state_store()
        while True:
            await asyncio.sleep(interval)
            for sid in list(self._states.keys()):
                try:
                    snap = store.get_snapshot(sid)
                    await self.check(sid, snap, "科研提醒")
                except Exception:
                    pass


_decider = ProactiveDecider()


def get_decider() -> ProactiveDecider:
    return _decider
