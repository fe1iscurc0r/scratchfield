"""事件溯源 surface 双层（卷124 W124-04）。

卷119 W119-02 的 `event_store` 是 **append-only 事件全量**（权威，带轮转/回放）。
本模块在它之上加一层 **surface 投影**：同一份日志服务四类消费者，各自只看到该看的部分。

```
                  ┌── surface_model      喂 LLM 的上下文子集（裁剪 + 脱敏）
event_store ──────┼── surface_transcript 人类可见对话子集（展示用）
（权威全量）       ├── surface_replay     重放（调试/恢复：原样信封）
                  └── surface_telemetry  统计（计数/延迟，只留数值字段）
```

三层约束：

1. **投影规则**：topic → 进哪些面 + 字段白名单（未列字段一律裁掉）+ 脱敏（复用
   `metric_sanitize` 的值级掩码）
2. **append 边界原子验证**：写前校验 `id/topic/source/trace_id/timestamp` 必填 + `seq`
   单调递增；非法事件**拒绝写入**并计数（不中断服务）
3. **断档检测**：`seq` 不连续即告警（模拟丢事件/写盘异常）

与 message_store（W110-05）的关系：message_store 仍是**对话消息**的权威存储；
`surface_model` 是**事件视角**的 LLM 上下文投影，两者用途不同。迁移点写在 README
（`bus.surface.use_for_llm_context` 开关默认关，打开后投影会作为补充上下文注入）。
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple

logger = logging.getLogger(__name__)

SURFACES = ("model", "transcript", "replay", "telemetry", "router")

#: 投影规则：topic 前缀/全名 → 进哪些面 + 字段白名单
#: 约定：`payload` 里的字段按白名单裁剪；信封自身字段（id/topic/source/trace_id/timestamp/seq）
#: 在 model/transcript/telemetry 面按需保留，replay 面保留全量。
_RULES: List[Dict[str, Any]] = [
    {
        "match": ("lumo.user.input.received", "lumo.asr.result"),
        "surfaces": ("model", "transcript", "replay", "telemetry"),
        "payload_fields": ("text", "session_id", "source_channel"),
    },
    {
        "match": ("lumo.speak.requested", "lumo.emotion.requested", "lumo.tts.start", "lumo.tts.end"),
        "surfaces": ("transcript", "replay", "telemetry"),
        "payload_fields": ("text", "emotion", "action", "session_id"),
    },
    {
        "match": ("lumo.tool.pre-execute", "lumo.tool.guard", "lumo.tool.post-execute"),
        "surfaces": ("model", "replay", "telemetry"),
        "payload_fields": ("tool", "session_id", "ok", "exit_code", "signal", "error",
                           "aborted", "duration", "status", "reason"),
    },
    {
        "match": ("lumo.task.", "lumo.review."),
        "surfaces": ("model", "transcript", "replay", "telemetry"),
        "payload_fields": ("task_id", "goal", "status", "summary", "step_id", "session_id"),
    },
    {
        "match": ("lumo.memory.created", "lumo.memory.archived", "lumo.memory.embed-requested"),
        "surfaces": ("replay", "telemetry"),
        "payload_fields": ("memory_id", "layer", "summary"),
    },
    {
        "match": ("lumo.skill.invoked", "lumo.router.decision"),
        "surfaces": ("telemetry", "router", "replay"),
        "payload_fields": ("skill", "score", "injected_chars", "tier", "model", "model_chosen",
                           "complexity", "cost_estimate", "session_id", "turn_id", "reasons",
                           "sensitive", "step_type", "task_type"),
    },
    {
        "match": ("lumo.scheduler.tick", "lumo.node.heartbeat", "internal/dispatch"),
        "surfaces": ("replay", "telemetry"),
        "payload_fields": ("interval", "tick_n", "topic", "mode"),
    },
]
_DEFAULT_RULE = {
    "surfaces": ("replay", "telemetry"),
    "payload_fields": (),
}

#: 信封字段：哪些面保留
_ENVELOPE_FIELDS = {
    "model": ("topic", "timestamp", "trace_id"),
    "transcript": ("topic", "timestamp", "source"),
    "replay": ("id", "topic", "mode", "source", "trace_id", "timestamp", "seq", "payload"),
    "telemetry": ("topic", "timestamp"),
    # W125-04：路由决策面（对齐 OpenSquilla observability 契约：决策可查、可统计）
    "router": ("topic", "timestamp", "trace_id"),
}

REQUIRED_FIELDS = ("id", "topic", "source", "trace_id", "timestamp")


# ---------------------------------------------------------------------------
# 投影规则
# ---------------------------------------------------------------------------


def rule_for(topic: str) -> Dict[str, Any]:
    text = str(topic or "")
    for rule in _RULES:
        for pattern in rule["match"]:
            if text == pattern or (pattern.endswith(".") and text.startswith(pattern)):
                return rule
    return _DEFAULT_RULE


def _project_payload(payload: Any, fields: Iterable[str]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {"value": payload} if payload is not None else {}
    allow = tuple(fields)
    if not allow:
        return {}
    out = {k: payload.get(k) for k in allow if k in payload}
    return _sanitize(out)


def _sanitize(value: Any) -> Any:
    """脱敏（复用 W120-04 的值级掩码；不可用时原样返回）。"""
    try:
        from apiserver.metric_sanitize import sanitize_value

        return sanitize_value(value)
    except Exception:  # noqa: BLE001
        try:
            from apiserver.telemetry import _sanitize_value

            return _sanitize_value(value)
        except Exception:  # noqa: BLE001
            return value


def project_event(event: Dict[str, Any], surface: str) -> Dict[str, Any] | None:
    """把一条事件投影到指定面；不属于该面返回 None。"""
    if surface not in SURFACES:
        raise ValueError(f"未知 surface: {surface}")
    envelope = event.get("envelope") if isinstance(event.get("envelope"), dict) else event
    topic = str(envelope.get("topic") or "")
    rule = rule_for(topic)
    if surface not in rule["surfaces"]:
        return None
    projected: Dict[str, Any] = {}
    for key in _ENVELOPE_FIELDS[surface]:
        if key == "payload":
            projected["payload"] = envelope.get("payload")
        elif key in envelope:
            projected[key] = envelope.get(key)
    if surface != "replay":
        projected["payload"] = _project_payload(envelope.get("payload"), rule["payload_fields"])
        projected["surface"] = surface
    return projected


def project(events: Iterable[Dict[str, Any]], surface: str, *, limit: int = 200) -> List[Dict[str, Any]]:
    """批量投影（保序，取最近的 `limit` 条）。"""
    if surface not in SURFACES:
        raise ValueError(f"未知 surface: {surface}")
    out: List[Dict[str, Any]] = []
    for event in list(events)[-max(1, limit):]:
        item = project_event(event, surface)
        if item is not None:
            out.append(item)
    return out


# ---------------------------------------------------------------------------
# append 边界原子验证 + 断档检测
# ---------------------------------------------------------------------------


class SurfaceStore:
    """surface 运行时：验证 → 入 event_store；并维护投影所需的最近事件窗口。"""

    def __init__(self, store: Any = None, *, window: int = 500) -> None:
        self._store = store
        self._lock = threading.Lock()
        self._recent: List[Dict[str, Any]] = []
        self._window = max(50, int(window))
        self._last_seq: Dict[str, int] = {}
        self.accepted = 0
        self.rejected = 0
        self.gaps = 0
        self.last_reject_reason = ""

    # ---- 验证 ----

    def validate(self, event: Dict[str, Any]) -> Tuple[bool, str]:
        """schema 必填 + seq 单调。返回 (ok, reason)。"""
        if not isinstance(event, dict):
            return False, "not_a_dict"
        for field in REQUIRED_FIELDS:
            if not event.get(field) and event.get(field) != 0:
                return False, f"missing_{field}"
        source = str(event.get("source") or "")
        seq = event.get("seq")
        if seq is not None:
            try:
                seq_num = int(seq)
            except (TypeError, ValueError):
                return False, "bad_seq"
            last = self._last_seq.get(source)
            if last is not None and seq_num <= last:
                return False, f"seq_not_monotonic({seq_num}<={last})"
        return True, ""

    def ingest(self, event: Dict[str, Any]) -> bool:
        """验证通过才入 store；非法事件拒绝并计数（不中断服务）。"""
        ok, reason = self.validate(event)
        if not ok:
            with self._lock:
                self.rejected += 1
                self.last_reject_reason = reason
            logger.warning("[surface] 拒绝非法事件（%s）：%s", reason, str(event)[:160])
            return False
        source = str(event.get("source") or "")
        seq = event.get("seq")
        with self._lock:
            if seq is None:
                # 顺序号由 surface 统一分配（同一 source 内单调），断档才好检测
                event["seq"] = self._last_seq.get(source, 0) + 1
                seq = event["seq"]
            last = self._last_seq.get(source)
            if last is not None and int(seq) > last + 1:
                self.gaps += 1
                logger.warning("[surface] 顺序号断档：source=%s 从 %s 跳到 %s", source, last, seq)
            self._last_seq[source] = int(seq)
            self.accepted += 1
            self._recent.append(event)
            if len(self._recent) > self._window:
                self._recent = self._recent[-self._window:]
        if self._store is not None:
            try:
                self._store.append(event)
            except Exception as e:  # noqa: BLE001 - 落盘失败不影响业务
                logger.debug("[surface] event_store 写入失败: %s", e)
        return True

    # ---- 消费面 ----

    def events(self, *, session_id: str = "", limit: int = 200) -> List[Dict[str, Any]]:
        with self._lock:
            items = list(self._recent)
        if session_id:
            items = [
                e for e in items
                if str((e.get("payload") or {}).get("session_id") or "") == str(session_id)
            ]
        return items[-max(1, limit):]

    def surface(self, name: str, *, session_id: str = "", limit: int = 200) -> List[Dict[str, Any]]:
        return project(self.events(session_id=session_id, limit=limit), name, limit=limit)

    def model_messages(self, *, session_id: str = "", limit: int = 40) -> List[Dict[str, Any]]:
        """把 model 面投影还原成 LLM 可读的补充上下文块（不替代 message_store）。"""
        items = self.surface("model", session_id=session_id, limit=limit)
        if not items:
            return []
        return [{"role": "system", "content": _format_model_context(items)}]

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "accepted": self.accepted,
                "rejected": self.rejected,
                "gaps": self.gaps,
                "window": len(self._recent),
                "last_reject_reason": self.last_reject_reason,
                "sources": dict(self._last_seq),
            }


def _format_model_context(items: List[Dict[str, Any]]) -> str:
    lines = ["〔事件面（surface_model）〕"]
    for item in items[-20:]:
        payload = item.get("payload") or {}
        bits = "，".join(f"{k}={payload[k]}" for k in list(payload)[:5])
        lines.append(f"- {item.get('topic')}：{bits}")
    return "\n".join(lines)


_store: SurfaceStore | None = None
_store_lock = threading.Lock()


def get_surface_store() -> SurfaceStore:
    """进程内单例（与 tool_gate / confirm_gate 同风格）。"""
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = SurfaceStore()
    return _store


def bind_event_store(store: Any) -> SurfaceStore:
    """把 event_store 绑到 surface（api_server 启动时调）。"""
    global _store
    surface = get_surface_store()
    surface._store = store
    return surface


def reset_surface_store_for_tests(surface: SurfaceStore | None = None) -> None:
    global _store
    with _store_lock:
        _store = surface


def surface_stats() -> Dict[str, Any]:
    return {"surfaces": list(SURFACES), "store": get_surface_store().stats()}


def dump_surface(name: str, *, session_id: str = "", limit: int = 50) -> Dict[str, Any]:
    """调试端点用：取某个面的投影。"""
    if name not in SURFACES:
        return {"error": "unknown_surface", "surfaces": list(SURFACES)}
    items = get_surface_store().surface(name, session_id=session_id, limit=limit)
    return {"surface": name, "count": len(items), "items": items}


__all__ = [
    "SURFACES", "SurfaceStore", "bind_event_store", "dump_surface", "get_surface_store",
    "project", "project_event", "reset_surface_store_for_tests", "rule_for", "surface_stats",
    "REQUIRED_FIELDS",
]
