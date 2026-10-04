"""W119-04：跨总线桥 —— Lumo InProcessBus ↔ mcpserver workflow ↔ NEKO plugin bus。

系统里现有五个总线（Lumo InProcessBus / NEKO plugin bus / NEKO ZMQ agent_event_bus /
lifecycle_bus / mcpserver workflow event_bus）各自为政。本模块先桥通三条主线中的两条：
**Lumo ↔ mcpserver workflow**（同进程，直接 import）与 **Lumo ↔ NEKO plugin bus**
（本地适配层 + 传输抽象；NEKO 上游零改动）。

统一信封：沿用 W119-02 的 `{id, topic, mode, source, trace_id, timestamp, payload}`
（workflow 侧 Event 字段 name 不同但语义对齐：event_type↔topic、source、trace_id、payload）。

防环去重：桥接产生的记录都带 `id` 与 `source`（`lumo-bridge` / `workflow-bridge`），
双向各自维护有界 seen-id 集合；收到 source 属于自己的记录直接丢弃 —— 杜绝
Lumo → workflow → Lumo 或 Lumo → NEKO → Lumo 的镜像回环。

映射表见 `docs/跨总线桥映射-2026-09-17.md`。
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from collections import OrderedDict
from typing import Any, Callable, Dict, List, Optional, Protocol

from .bus import EventBus
from .disposable import Disposable
from .topics import Topics

logger = logging.getLogger(__name__)

SOURCE_LUMO = "lumo-bridge"
SOURCE_WORKFLOW = "workflow-bridge"

# 有界去重窗口（按 id），防回环同时避免内存无界增长
_SEEN_LIMIT = 2000


class _SeenIds:
    """有界 FIFO 去重集合（id → 首次见到的时间）。"""

    def __init__(self, limit: int = _SEEN_LIMIT) -> None:
        self._items: "OrderedDict[str, float]" = OrderedDict()
        self._limit = max(16, int(limit))
        self._lock = threading.Lock()

    def seen(self, key: str) -> bool:
        """标记并判断：已见过返回 True。"""
        if not key:
            return False
        with self._lock:
            if key in self._items:
                return True
            self._items[key] = time.time()
            while len(self._items) > self._limit:
                self._items.popitem(last=False)
            return False


# ---------------------------------------------------------------------------
# 桥 A：Lumo ↔ mcpserver workflow（同进程）
# ---------------------------------------------------------------------------

#: workflow event_type → Lumo topic（提升方向；topic 名字见 Topics 的 TASK_*/REVIEW_*）
WORKFLOW_TO_LUMO: Dict[str, str] = {
    "task_created": Topics.TASK_CREATED,
    "task_assigned": Topics.TASK_ASSIGNED,
    "task_claimed": Topics.TASK_CLAIMED,
    "task_blocked": Topics.TASK_BLOCKED,
    "task_done": Topics.TASK_DONE,
    "review_requested": Topics.REVIEW_REQUESTED,
    "review_approved": Topics.REVIEW_APPROVED,
}

#: Lumo topic → workflow event_type（自动转发方向；默认空 = 只允许显式转发，避免臆造语义）
LUMO_TO_WORKFLOW: Dict[str, str] = {}


class WorkflowBusBridge:
    """Lumo InProcessBus ↔ workflow EventBus 的同进程双向桥。"""

    def __init__(
        self,
        lumo_bus: EventBus,
        workflow_bus: Any,
        *,
        auto_forward: Dict[str, str] | None = None,
    ) -> None:
        self.lumo_bus = lumo_bus
        self.workflow_bus = workflow_bus
        self.auto_forward = dict(auto_forward if auto_forward is not None else LUMO_TO_WORKFLOW)
        self.forwarded_to_lumo = 0
        self.forwarded_to_workflow = 0
        self.skipped_loops = 0
        self._seen = _SeenIds()
        self._disposers: List[Callable[[], None]] = []

    # ---- 提升：workflow → Lumo ----

    def _on_workflow_event(self, event: Any) -> None:
        try:
            event_type = str(getattr(event, "event_type", "") or (event.get("event_type") if isinstance(event, dict) else ""))
            topic = WORKFLOW_TO_LUMO.get(event_type)
            if not topic:
                return
            event_id = str(getattr(event, "id", "") or (event.get("id") if isinstance(event, dict) else ""))
            source = str(getattr(event, "source", "") or "")
            # 防环：source==SOURCE_LUMO 表示这条是桥自己刚发进 workflow 的（回环回声），不再提升；
            # 同 id 第二次进入同样丢弃。
            if source == SOURCE_LUMO or self._seen.seen(f"wf:{event_id}"):
                self.skipped_loops += 1
                return
            payload = getattr(event, "payload", None) or (event.get("payload") if isinstance(event, dict) else {}) or {}
            trace_id = str(getattr(event, "trace_id", "") or "")
            self.lumo_bus.emit(
                topic,
                {
                    "id": event_id,
                    "source": SOURCE_WORKFLOW,
                    "trace_id": trace_id,
                    "workflow_event_type": event_type,
                    "payload": payload,
                },
            )
            self.forwarded_to_lumo += 1
        except Exception:  # noqa: BLE001 - 桥不得影响发布方
            logger.warning("[bridge] workflow→Lumo 提升失败", exc_info=True)

    # ---- 显式转发：Lumo → workflow ----

    def publish_to_workflow(
        self, event_type: str, payload: Dict[str, Any] | None = None, *, trace_id: str | None = None
    ) -> Any:
        """把一条事件显式发布进 workflow 总线（自带防环标记）。"""
        if self.workflow_bus is None:
            return None
        event = self.workflow_bus.publish(
            str(event_type), SOURCE_LUMO, payload=dict(payload or {}), trace_id=trace_id
        )
        self.forwarded_to_workflow += 1
        return event

    def _on_lumo_event(self, event: Any, topic: str = "") -> None:
        """自动转发（仅映射表里登记的 topic；默认空表）。

        注：总线 handler 只拿到 event，topic 由订阅时用闭包注入（见 attach）。
        """
        try:
            event_type = self.auto_forward.get(str(topic))
            if not event_type:
                return
            # 防环：source==SOURCE_WORKFLOW 表示这条是刚从 workflow 提升上来的，不再回桥
            if isinstance(event, dict) and str(event.get("source") or "") == SOURCE_WORKFLOW:
                self.skipped_loops += 1
                return
            event_id = str(event.get("id") if isinstance(event, dict) else "")
            if self._seen.seen(f"lumo:{event_id}"):
                self.skipped_loops += 1
                return
            self.publish_to_workflow(
                event_type,
                event.get("payload") if isinstance(event, dict) else {},
                trace_id=str(event.get("trace_id") or "") or None,
            )
        except Exception:  # noqa: BLE001
            logger.warning("[bridge] Lumo→workflow 转发失败", exc_info=True)

    # ---- 生命周期 ----

    def attach(self) -> None:
        """订阅两侧总线（幂等）。"""
        if self._disposers:
            return
        try:
            from mcpserver.workflow.event_bus import ALL_EVENT_TYPES
        except Exception:  # noqa: BLE001 - mcpserver 不可用时只做单向
            ALL_EVENT_TYPES = tuple(WORKFLOW_TO_LUMO.keys())
        if self.workflow_bus is not None and hasattr(self.workflow_bus, "subscribe"):
            for event_type in ALL_EVENT_TYPES:
                unsubscribe = self.workflow_bus.subscribe(event_type, self._on_workflow_event)
                if callable(unsubscribe):
                    self._disposers.append(unsubscribe)
        for topic in self.auto_forward:
            _topic = str(topic)  # 闭包捕获：总线 handler 只收到 event，topic 需在此注入

            def _handler(event: Any, _t: str = _topic) -> None:
                self._on_lumo_event(event, _t)

            self._disposers.append(self.lumo_bus.on(topic, _handler))
        logger.info(
            "[bridge] workflow 桥已挂载（workflow→Lumo %d 类；Lumo→workflow 自动转发 %d 类）",
            len(ALL_EVENT_TYPES),
            len(self.auto_forward),
        )

    def detach(self) -> None:
        while self._disposers:
            dispose = self._disposers.pop()
            try:
                dispose()
            except Exception:  # noqa: BLE001
                continue

    def stats(self) -> Dict[str, Any]:
        return {
            "forwarded_to_lumo": self.forwarded_to_lumo,
            "forwarded_to_workflow": self.forwarded_to_workflow,
            "skipped_loops": self.skipped_loops,
        }


# ---------------------------------------------------------------------------
# 桥 B：Lumo ↔ NEKO plugin bus（传输抽象；NEKO 上游零改动）
# ---------------------------------------------------------------------------


class NekoBusTransport(Protocol):
    """NEKO 侧总线传输契约（实现方：NEKO 侧插件桩 / 本地注入通道 / HTTP 代理）。"""

    def available(self) -> bool: ...

    def publish(self, record: Dict[str, Any]) -> bool: ...

    def subscribe(self, handler: Callable[[Dict[str, Any]], None]) -> Callable[[], None]: ...


#: Lumo topic → NEKO 侧记录类型（命令方向：Lumo 请求 NEKO 做事）
LUMO_TO_NEKO: Dict[str, str] = {
    Topics.SPEAK_REQUESTED: "LUMO_SPEAK_REQUESTED",
    Topics.EMOTION_REQUESTED: "LUMO_EMOTION_REQUESTED",
}

#: NEKO 侧记录类型 → Lumo topic（事件方向：NEKO 汇报状态）
NEKO_TO_LUMO: Dict[str, str] = {
    "NEKO_TTS_START": Topics.TTS_START,
    "NEKO_TTS_END": Topics.TTS_END,
    "NEKO_ASR_RESULT": Topics.ASR_RESULT,
    "NEKO_USER_INPUT": Topics.USER_INPUT_RECEIVED,
}

COMMAND_SOURCE = "lumo"


class NekoHttpTransport:
    """Lumo → NEKO 的真实传输：复用 NEKO 既有注入路由（`/api/lumo/speak|emotion`）。

    - 鉴权：`LUMO_PROXY_TOKEN`（fusion 启动时注入两侧环境，与 NEKO 的 require_proxy_token 同源）
    - 发送在**后台线程**做（有界队列）：总线 emit 是同步调用，不能让它等 HTTP 往返；
      队列满则丢弃并计数，不阻塞、不抛。
    - 反向（NEKO → Lumo）不需要本 transport：NEKO 侧 `main_logic/lumo_event_sender.py` 已在推
      `POST /api/lumo/event`，由 `apiserver/routes/lumo_event.py` 直接 emit 到 Lumo 总线。
    """

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        *,
        timeout: float = 10.0,
        queue_max: int = 200,
    ) -> None:
        import os

        self.base_url = (
            base_url or os.environ.get("NEKO_MAIN_BASE_URL") or "http://127.0.0.1:48911"
        ).rstrip("/")
        self.token = (token if token is not None else os.environ.get("LUMO_PROXY_TOKEN", "")).strip()
        self.timeout = float(timeout)
        self._queue: "queue.Queue[Dict[str, Any]]" = queue.Queue(maxsize=max(10, int(queue_max)))
        self._lock = threading.Lock()
        self.sent = 0
        self.failed = 0
        self.dropped = 0
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._last_error = ""

    # ---- 契约 ----

    def available(self) -> bool:
        return bool(self.token)

    def publish(self, record: Dict[str, Any]) -> bool:
        if not self.available():
            self._last_error = "LUMO_PROXY_TOKEN 未设置"
            return False
        try:
            self._queue.put_nowait(record)
        except Exception:  # noqa: BLE001 - queue.Full
            with self._lock:
                self.dropped += 1
            return False
        self._ensure_thread()
        return True

    def subscribe(self, handler: Callable[[Dict[str, Any]], None]) -> Callable[[], None]:
        """NEKO→Lumo 方向不走本 transport（见类 docstring），返回空退订函数。"""
        return lambda: None

    # ---- 发送线程 ----

    def _ensure_thread(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                self._stop.clear()
                self._thread = threading.Thread(
                    target=self._sender_loop, name="neko-http-transport", daemon=True
                )
                self._thread.start()

    def _sender_loop(self) -> None:
        import httpx

        with httpx.Client(timeout=self.timeout, trust_env=False) as client:
            while not self._stop.is_set() or not self._queue.empty():
                try:
                    record = self._queue.get(timeout=0.5)
                except Exception:  # noqa: BLE001 - queue.Empty
                    continue
                try:
                    path, body = self._build_request(record)
                    if path is None:
                        continue
                    resp = client.post(
                        f"{self.base_url}{path}",
                        json=body,
                        headers={"Authorization": f"Bearer {self.token}"},
                    )
                    if resp.status_code >= 400:
                        with self._lock:
                            self.failed += 1
                            self._last_error = f"HTTP {resp.status_code}: {resp.text[:120]}"
                        logger.warning("[bridge] NEKO 注入失败 %s → %s", path, resp.status_code)
                    else:
                        with self._lock:
                            self.sent += 1
                except Exception as e:  # noqa: BLE001
                    with self._lock:
                        self.failed += 1
                        self._last_error = f"{type(e).__name__}: {e}"
                    logger.warning("[bridge] NEKO 注入异常: %s", e)

    def _build_request(self, record: Dict[str, Any]) -> tuple[str | None, Dict[str, Any]]:
        """把桥记录映射成 NEKO 注入路由的 (path, body)。"""
        record_type = str(record.get("type") or "")
        payload = record.get("payload") or {}
        character = str(payload.get("character") or payload.get("lanlan_name") or "")
        if not character:
            try:
                from system.character_bundle import resolve_neko_active_character

                character = resolve_neko_active_character() or ""
            except Exception:  # noqa: BLE001
                character = ""
        if record_type == "LUMO_SPEAK_REQUESTED":
            text = str(payload.get("text") or payload.get("content") or "").strip()
            if not text or not character:
                return None, {}
            body: Dict[str, Any] = {"lanlan_name": character, "text": text}
            if payload.get("emotion"):
                body["emotion"] = str(payload["emotion"])
                body["emotion_confidence"] = float(payload.get("emotion_confidence") or 0.5)
            return "/api/lumo/speak", body
        if record_type == "LUMO_EMOTION_REQUESTED":
            emotion = str(payload.get("emotion") or "").strip()
            if not emotion or not character:
                return None, {}
            return "/api/lumo/emotion", {"lanlan_name": character, "emotion": emotion}
        return None, {}

    def close(self, timeout: float = 2.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "base_url": self.base_url,
                "token_present": bool(self.token),
                "sent": self.sent,
                "failed": self.failed,
                "dropped": self.dropped,
                "queued": self._queue.qsize(),
                "last_error": self._last_error,
            }


class NekoStubTransport:
    """内存桩传输（测试 / 未接 NEKO 时的占位）。

    真实部署时应由 NEKO 侧用户插件实现同一契约（NEKO 上游零改动，桥只走插件通道）。
    """

    def __init__(self) -> None:
        self.published: List[Dict[str, Any]] = []
        self._handlers: List[Callable[[Dict[str, Any]], None]] = []

    def available(self) -> bool:
        return True

    def publish(self, record: Dict[str, Any]) -> bool:
        self.published.append(record)
        return True

    def subscribe(self, handler: Callable[[Dict[str, Any]], None]) -> Callable[[], None]:
        self._handlers.append(handler)

        def unsubscribe() -> None:
            if handler in self._handlers:
                self._handlers.remove(handler)

        return unsubscribe

    def inject(self, record: Dict[str, Any]) -> None:
        """测试用：模拟 NEKO 侧推来一条记录。"""
        for handler in list(self._handlers):
            handler(record)


class LumoNekoBridge:
    """Lumo ↔ NEKO plugin bus 桥（命令出、事件入 + 防环去重）。"""

    def __init__(self, lumo_bus: EventBus, transport: NekoBusTransport) -> None:
        self.lumo_bus = lumo_bus
        self.transport = transport
        self.forwarded_to_neko = 0
        self.forwarded_to_lumo = 0
        self.skipped_loops = 0
        self._seen = _SeenIds()
        self._disposers: List[Callable[[], None]] = []

    # ---- 命令方向：Lumo → NEKO ----

    def _on_lumo_command(self, event: Any, topic: str = "") -> None:
        try:
            record_type = LUMO_TO_NEKO.get(str(topic))
            if not record_type:
                return
            event_id = str(event.get("id") if isinstance(event, dict) else "")
            if self._seen.seen(f"lumo:{event_id}"):
                self.skipped_loops += 1
                return
            record = {
                "id": event_id,
                "type": record_type,
                "source": COMMAND_SOURCE,
                "trace_id": str(event.get("trace_id") or "") or None,
                "timestamp": time.time(),
                "payload": event.get("payload") if isinstance(event, dict) else {},
            }
            if self.transport.publish(record):
                self.forwarded_to_neko += 1
        except Exception:  # noqa: BLE001
            logger.warning("[bridge] Lumo→NEKO 命令转发失败", exc_info=True)

    # ---- 事件方向：NEKO → Lumo ----

    def _on_neko_record(self, record: Dict[str, Any]) -> None:
        try:
            record_type = str(record.get("type") or "")
            topic = NEKO_TO_LUMO.get(record_type)
            if not topic:
                return
            record_id = str(record.get("id") or "")
            if self._seen.seen(f"neko:{record_id}"):
                self.skipped_loops += 1
                return
            self.lumo_bus.emit(
                topic,
                {
                    "id": record_id,
                    "source": "neko",
                    "trace_id": record.get("trace_id"),
                    "neko_type": record_type,
                    "payload": record.get("payload") or {},
                },
            )
            self.forwarded_to_lumo += 1
        except Exception:  # noqa: BLE001
            logger.warning("[bridge] NEKO→Lumo 事件提升失败", exc_info=True)

    # ---- 生命周期 ----

    def attach(self) -> None:
        if self._disposers:
            return
        for topic in LUMO_TO_NEKO:
            _topic = str(topic)

            def _handler(event: Any, _t: str = _topic) -> None:
                self._on_lumo_command(event, _t)

            self._disposers.append(self.lumo_bus.on(topic, _handler))
        unsubscribe = self.transport.subscribe(self._on_neko_record)
        if callable(unsubscribe):
            self._disposers.append(unsubscribe)
        logger.info(
            "[bridge] NEKO 桥已挂载（命令 %d 类；事件 %d 类；transport=%s）",
            len(LUMO_TO_NEKO),
            len(NEKO_TO_LUMO),
            type(self.transport).__name__,
        )

    def detach(self) -> None:
        while self._disposers:
            dispose = self._disposers.pop()
            try:
                dispose()
            except Exception:  # noqa: BLE001
                continue

    def stats(self) -> Dict[str, Any]:
        return {
            "forwarded_to_neko": self.forwarded_to_neko,
            "forwarded_to_lumo": self.forwarded_to_lumo,
            "skipped_loops": self.skipped_loops,
            "transport": type(self.transport).__name__,
            "transport_available": bool(self.transport.available()),
        }


# ---------------------------------------------------------------------------
# 进程级装配
# ---------------------------------------------------------------------------

_bridges: Dict[str, Any] = {}
_bridge_lock = threading.Lock()


def get_workflow_bridge() -> WorkflowBusBridge | None:
    return _bridges.get("workflow")


def get_neko_bridge() -> LumoNekoBridge | None:
    return _bridges.get("neko")


def setup_bridges(
    lumo_bus: EventBus,
    *,
    workflow_bus: Any = None,
    neko_transport: NekoBusTransport | None = None,
) -> Dict[str, Any]:
    """装配并挂载两侧桥（可只给其中一侧）。"""
    with _bridge_lock:
        if workflow_bus is not None and "workflow" not in _bridges:
            bridge = WorkflowBusBridge(lumo_bus, workflow_bus)
            bridge.attach()
            _bridges["workflow"] = bridge
        if neko_transport is not None and "neko" not in _bridges:
            neko = LumoNekoBridge(lumo_bus, neko_transport)
            neko.attach()
            _bridges["neko"] = neko
        return dict(_bridges)


def reset_bridges_for_tests() -> None:
    with _bridge_lock:
        for bridge in _bridges.values():
            try:
                bridge.detach()
            except Exception:  # noqa: BLE001
                continue
        _bridges.clear()


def bridge_stats() -> Dict[str, Any]:
    stats: Dict[str, Any] = {}
    for name, bridge in _bridges.items():
        try:
            stats[name] = bridge.stats()
        except Exception:  # noqa: BLE001
            stats[name] = {"error": "stats unavailable"}
    return stats
