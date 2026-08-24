"""memory hooks — agentmemory 6-hook 生命周期钩子注册表（旁路）。

授粉源：agentmemory（Apache-2.0）的 lifecycle hooks 模式——记忆系统在
prefetch / turn 同步 / 会话结束 / 压缩前 / 写入 / 提示词组装 六个时机
挂载扩展，不侵入宿主主流程。

落地（F-01）：NEKO 版 6 钩子，事件时机对齐现有生命周期组件：
  - prefetch          → recall.py 检索前（预取候选）
  - sync_turn         → post_turn 每轮写路径之后（轮同步）
  - on_session_end    → lifecycle/policy.py BackgroundWriter.submit_session_summary
                        同时机（会话归档）
  - on_pre_compress   → compaction_v2.should_compress / summarize_branches 之前
                        （压缩前抢救原文）
  - on_memory_write   → FactStore 写入后（联动索引卡，见 install_default_wiring）
  - system_prompt_block → 系统提示词组装时注入记忆块（聚合文本）

设计约束：
  - 默认关闭：NEKO_MEMORY_HOOKS=0（缺省）时 emit 全部短路，现行为零变化；
    =1/true 才启用
  - 幂等：同名 hook 重复 register 为替换语义，不重复触发
  - fail-safe：单个 hook 抛异常只记日志，不打断其余 hook 与宿主流程
  - 旁路零侵入：不修改 FactStore / recent.py / 桌宠壳任何文件，
    由调用方（或 install_default_wiring）在合适时机 emit

License: Apache-2.0（机制同源 agentmemory；实现独立）。
"""
from __future__ import annotations

import logging
import os
import threading
from typing import Any, Callable, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

# 6 钩子事件（固定顺序 = 生命周期序：检索前 → 轮同步 → 会话尾 → 压缩前 → 写入 → 提示词）
HOOK_EVENTS: tuple[str, ...] = (
    "prefetch",
    "sync_turn",
    "on_session_end",
    "on_pre_compress",
    "on_memory_write",
    "system_prompt_block",
)

_ENV_SWITCH = "NEKO_MEMORY_HOOKS"


def hooks_enabled() -> bool:
    """总开关：NEKO_MEMORY_HOOKS ∈ {1,true,yes,on} 才启用，默认关闭。"""
    return os.environ.get(_ENV_SWITCH, "0").strip().lower() in ("1", "true", "yes", "on")


HookFn = Callable[..., Any]


class MemoryHooks:
    """钩子注册表 + 触发器。线程安全；register 幂等（同名替换）。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._hooks: Dict[str, Dict[str, HookFn]] = {e: {} for e in HOOK_EVENTS}

    # ------------------------------------------------------------ 注册
    def register(self, event: str, fn: HookFn, name: Optional[str] = None) -> str:
        """登记钩子。name 缺省取 fn.__name__；同名重复登记为替换（幂等）。"""
        if event not in HOOK_EVENTS:
            raise ValueError(f"未知钩子事件 {event!r}，可选: {HOOK_EVENTS}")
        if not callable(fn):
            raise TypeError("fn 必须 callable")
        key = name or getattr(fn, "__name__", f"hook_{id(fn):x}")
        with self._lock:
            existing = self._hooks[event].get(key)
            self._hooks[event][key] = fn
        if existing is not None and existing is not fn:
            logger.debug("[memory-hooks] %s/%s 同名替换", event, key)
        return key

    def unregister(self, event: str, name: str) -> bool:
        """按名移除。返回是否真的移除了。"""
        with self._lock:
            return self._hooks[event].pop(name, None) is not None

    def list_hooks(self, event: Optional[str] = None) -> Dict[str, List[str]]:
        """列出已登记钩子名（调试/自省用）。"""
        with self._lock:
            events = (event,) if event else HOOK_EVENTS
            return {e: sorted(self._hooks[e]) for e in events if e in self._hooks}

    # ------------------------------------------------------------ 触发
    def emit(self, event: str, **payload: Any) -> List[Any]:
        """触发事件，返回各 hook 返回值列表（登记序）。

        总开关关闭时直接返回空列表（零行为变化）；单个 hook 异常不传染。
        """
        if event not in HOOK_EVENTS:
            raise ValueError(f"未知钩子事件 {event!r}，可选: {HOOK_EVENTS}")
        if not hooks_enabled():
            return []
        with self._lock:
            items = list(self._hooks[event].items())
        results: List[Any] = []
        for name, fn in items:
            try:
                results.append(fn(**payload))
            except Exception as exc:  # noqa: BLE001 — fail-safe：hook 挡异常
                logger.warning("[memory-hooks] %s/%s 执行失败（忽略）: %s", event, name, exc)
        return results

    def emit_system_prompt_block(self, session_id: str) -> str:
        """便捷聚合：收集 system_prompt_block 各 hook 返回的文本块。

        各 hook 返回 str（或 None/忽略），非 str 返回值跳过；
        结果按登记序拼接为提示词可注入的多行文本。
        """
        parts = [
            r for r in self.emit("system_prompt_block", session_id=session_id)
            if isinstance(r, str) and r.strip()
        ]
        return "\n".join(parts)

    def reset(self) -> None:
        """测试用：清空全部登记。"""
        with self._lock:
            self._hooks = {e: {} for e in HOOK_EVENTS}


# ---------------------------------------------------------------- 全局单例
_GLOBAL: Optional[MemoryHooks] = None
_GLOBAL_LOCK = threading.Lock()


def get_memory_hooks() -> MemoryHooks:
    """全局注册表单例（进程内共享）。"""
    global _GLOBAL
    if _GLOBAL is None:
        with _GLOBAL_LOCK:
            if _GLOBAL is None:
                _GLOBAL = MemoryHooks()
    return _GLOBAL


# ---------------------------------------------------------------- 默认接线
def install_default_wiring(hooks: Optional[MemoryHooks] = None,
                           card_store: Any = None) -> List[str]:
    """把内置联动装上钩子（幂等：重复安装先清旧名）。

    当前内置（F-01 范围）：
      - on_memory_write/default_index_card：记忆写入事件 → 索引卡联动。
        payload 约定 {record: {session_id, turns | content}}：
          - record 带 turns（[{role, content}]）→ 直接 build_card
          - 只带 content（单条事实写入）→ 包装成单 turn 建卡
        card_store 缺省时懒加载全局 IndexCardStore（:memory:，测试可注入）。

    注意：钩子总开关（NEKO_MEMORY_HOOKS）默认关闭，本接线装上也不生效，
    打开开关才真正联动——"默认关闭不改变现行为"。
    """
    h = hooks or get_memory_hooks()

    def _on_memory_write(record: Optional[Dict[str, Any]] = None, **_: Any) -> Optional[int]:
        from .index_cards.store import IndexCardStore, heuristic_summary

        nonlocal card_store
        if card_store is None:
            card_store = IndexCardStore(":memory:")
        rec = record or {}
        session_id = str(rec.get("session_id") or "adhoc")
        turns = rec.get("turns")
        if not turns:
            content = str(rec.get("content") or "").strip()
            if not content:
                return None
            turns = [{"role": "user", "content": content}]
        try:
            return int(card_store.build_card(session_id, list(turns),
                                             summarizer=heuristic_summary))
        except Exception as exc:  # noqa: BLE001 — 联动失败不影响写入主路径
            logger.warning("[memory-hooks] on_memory_write 索引卡联动失败: %s", exc)
            return None

    # 幂等：先卸同名旧接线再装（重复 install 不叠加触发）
    h.unregister("on_memory_write", "default_index_card")
    h.register("on_memory_write", _on_memory_write, name="default_index_card")
    return ["on_memory_write/default_index_card"]


__all__ = [
    "HOOK_EVENTS",
    "MemoryHooks",
    "get_memory_hooks",
    "hooks_enabled",
    "install_default_wiring",
]
