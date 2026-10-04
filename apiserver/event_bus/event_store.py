"""W119-02：事件持久化 —— append-only JSONL 事件日志 + 回放。

设计要点（对齐 `mcpserver/workflow/event_bus.py` 的「事件日志即消息总线」范式）：
- **不阻塞 dispatch 主路径**：`append()` 只做一次入队（有界队列），写盘在后台守护线程完成。
- 队列满：丢弃新事件并计数（`dropped`），不阻塞、不抛。
- 写盘失败：降级为内存-only（`degraded=True`），只告警一次，不影响总线分发。
- 轮转：单文件超过 `max_bytes` 滚动为 `<stem>.<timestamp>.jsonl`，保留最近 `keep_files` 个。
- 回放：`replay(topic=, since_ts=, limit=)` 逐行读，非法 JSON 行跳过并计数（不中断）。

事件信封（本卷先行定义，卷120 W120-01 全链路 trace 复用）：
    {"id", "topic", "mode", "source", "trace_id", "timestamp", "payload"}

用途边界（README 注明）：事件历史**仅作审计 / 调试 / 回放**，不做状态重建——
状态重建仍走 lumo_state 快照（事件不承载全部状态语义）。
"""
from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from pathlib import Path
from queue import Empty, Full, Queue
from typing import Any, Dict, Iterator, List, Optional

logger = logging.getLogger(__name__)

# 单条事件的 payload 序列化上限（防止超长文本/大对象把日志撑爆）
MAX_PAYLOAD_CHARS = 2000
_MAX_PAYLOAD_DEPTH = 4


def _safe_payload(value: Any, *, depth: int = 0) -> Any:
    """把任意事件 payload 压成 JSON 安全且长度受限的结构。"""
    if depth > _MAX_PAYLOAD_DEPTH:
        return "<max-depth>"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value if len(value) <= MAX_PAYLOAD_CHARS else value[:MAX_PAYLOAD_CHARS] + "…<truncated>"
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for key, item in list(value.items())[:50]:
            out[str(key)] = _safe_payload(item, depth=depth + 1)
        return out
    if isinstance(value, (list, tuple, set)):
        return [_safe_payload(item, depth=depth + 1) for item in list(value)[:50]]
    try:
        return _safe_payload(str(value), depth=depth + 1)
    except Exception:  # noqa: BLE001
        return "<unserializable>"


def build_envelope(
    topic: str,
    mode: str,
    event: Any,
    *,
    source: str = "lumo",
    trace_id: str | None = None,
) -> Dict[str, Any]:
    """构造统一事件信封（缺 trace_id 时取当前链路，其次自动生成 uuid4 hex）。"""
    resolved_trace = trace_id
    if not resolved_trace:
        try:
            from .trace import current_trace_id

            resolved_trace = current_trace_id()
        except Exception:  # noqa: BLE001 - trace 不可用时退回自动生成
            resolved_trace = None
    return {
        "id": uuid.uuid4().hex,
        "topic": str(topic),
        "mode": str(mode),
        "source": str(source or "lumo"),
        "trace_id": str(resolved_trace) if resolved_trace else uuid.uuid4().hex,
        "timestamp": time.time(),
        "payload": _safe_payload(event),
    }


class EventStore:
    """append-only JSONL 事件日志（后台线程写盘 + 轮转 + 回放）。"""

    def __init__(
        self,
        path: Path | None = None,
        *,
        enabled: bool = True,
        buffer_lines: int = 200,
        max_bytes: int = 16 * 1024 * 1024,
        keep_files: int = 5,
        queue_max: int = 5000,
    ) -> None:
        self.enabled = bool(enabled)
        self.path = Path(path) if path is not None else self._default_path()
        self.buffer_lines = max(1, int(buffer_lines))
        self.max_bytes = max(64 * 1024, int(max_bytes))
        self.keep_files = max(1, int(keep_files))

        self._queue: Queue = Queue(maxsize=max(10, int(queue_max)))
        self._lock = threading.Lock()
        self._closed = False
        self._degraded = False
        self._warned = False
        self._written = 0
        self._dropped = 0
        self._rotations = 0
        self._bad_lines = 0
        self._thread: threading.Thread | None = None

        if self.enabled:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
            except OSError as e:
                self._degrade(f"创建事件目录失败: {e}")
            if not self._degraded:
                self._thread = threading.Thread(
                    target=self._writer_loop, name="event-store-writer", daemon=True
                )
                self._thread.start()

    # ---- 路径 ----

    @staticmethod
    def _default_path() -> Path:
        from system.config import get_data_dir

        return Path(get_data_dir()) / "event_store" / "events.jsonl"

    # ---- 写入（主路径只入队） ----

    def append(self, envelope: Dict[str, Any]) -> None:
        """入队一条事件（不阻塞、不抛）。禁用/降级时直接返回。"""
        if not self.enabled or self._closed:
            return
        try:
            self._queue.put_nowait(envelope)
        except Full:
            with self._lock:
                self._dropped += 1
            if not self._warned:
                self._warned = True
                logger.warning("[event_store] 写盘队列满，事件将被丢弃（后续同类告警静默）")

    def _writer_loop(self) -> None:
        buffer: List[str] = []
        last_flush = time.time()
        while True:
            try:
                item = self._queue.get(timeout=1.0)
            except Empty:
                item = None
            if item is not None:
                try:
                    buffer.append(json.dumps(item, ensure_ascii=False, default=str))
                except Exception as e:  # noqa: BLE001
                    logger.debug("[event_store] 序列化失败，丢弃该条: %s", e)
            should_flush = (
                len(buffer) >= self.buffer_lines
                or (buffer and (time.time() - last_flush) >= 2.0)
                or (self._closed and buffer != [])
            )
            if should_flush:
                self._flush_buffer(buffer)
                buffer = []
                last_flush = time.time()
            if self._closed and self._queue.empty() and not buffer:
                return

    def _flush_buffer(self, buffer: List[str]) -> None:
        if not buffer:
            return
        try:
            self._rotate_if_needed()
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write("\n".join(buffer) + "\n")
            with self._lock:
                self._written += len(buffer)
        except OSError as e:
            self._degrade(f"写盘失败: {e}")

    def _rotate_if_needed(self) -> None:
        try:
            if not self.path.exists() or self.path.stat().st_size < self.max_bytes:
                return
            stamp = time.strftime("%Y%m%d-%H%M%S")
            rotated = self.path.with_name(f"{self.path.stem}.{stamp}{self.path.suffix}")
            # 同一秒内可能轮转多次 → 名字冲突时递增后缀（零填充保持文件名可排序）
            seq = 1
            while rotated.exists():
                rotated = self.path.with_name(f"{self.path.stem}.{stamp}-{seq:04d}{self.path.suffix}")
                seq += 1
            self.path.rename(rotated)
            with self._lock:
                self._rotations += 1
            self._prune_old_files()
        except OSError as e:
            logger.warning("[event_store] 轮转失败（继续写当前文件）: %s", e)

    def _prune_old_files(self) -> None:
        pattern = f"{self.path.stem}.*{self.path.suffix}"
        files = sorted(self.path.parent.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in files[self.keep_files:]:
            try:
                old.unlink()
            except OSError:
                continue

    def _degrade(self, reason: str) -> None:
        """写盘不可用 → 降级为内存-only（只告警一次，不抛）。"""
        self._degraded = True
        if not self._warned:
            self._warned = True
            logger.warning("[event_store] 持久化降级为内存-only: %s", reason)

    # ---- 回放 ----

    def replay(
        self,
        topic: str | None = None,
        since_ts: float | None = None,
        limit: int | None = None,
    ) -> Iterator[Dict[str, Any]]:
        """按写入顺序回放事件；非法 JSON 行跳过并计数（不中断）。"""
        if not self.path.parent.exists():
            return
        emitted = 0
        for file_path in self._files_oldest_first():
            try:
                fh = open(file_path, encoding="utf-8", errors="replace")
            except OSError:
                continue
            with fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        item = json.loads(line)
                    except json.JSONDecodeError:
                        with self._lock:
                            self._bad_lines += 1
                        continue
                    if not isinstance(item, dict):
                        continue
                    if topic and str(item.get("topic")) != str(topic):
                        continue
                    if since_ts is not None and float(item.get("timestamp") or 0) < float(since_ts):
                        continue
                    yield item
                    emitted += 1
                    if limit is not None and emitted >= int(limit):
                        return

    def _files_oldest_first(self) -> List[Path]:
        """回放顺序：先历史轮转文件（按文件名时间戳升序），再当前文件。"""
        rotated = sorted(
            (
                p
                for p in self.path.parent.glob(f"{self.path.stem}.*{self.path.suffix}")
                if p.is_file()
            ),
            key=lambda p: p.name,
        )
        ordered = list(rotated)
        if self.path.exists():
            ordered.append(self.path)
        return ordered

    # ---- 生命周期 / 观测 ----

    def flush(self, timeout: float = 5.0) -> bool:
        """等待队列排空（测试与进程退出前用）。返回是否在超时内排空。"""
        deadline = time.time() + max(0.0, timeout)
        while time.time() < deadline:
            if self._queue.empty():
                time.sleep(0.05)
                if self._queue.empty():
                    return True
            time.sleep(0.02)
        return self._queue.empty()

    def close(self, timeout: float = 5.0) -> None:
        self.flush(timeout)
        self._closed = True
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            size = self.path.stat().st_size if self.path.exists() else 0
            return {
                "enabled": self.enabled,
                "path": str(self.path),
                "written": self._written,
                "dropped": self._dropped,
                "bad_lines": self._bad_lines,
                "rotations": self._rotations,
                "degraded": self._degraded,
                "queued": self._queue.qsize(),
                "file_bytes": size,
            }


_store: EventStore | None = None
_store_lock = threading.Lock()


def get_event_store() -> EventStore:
    """进程级单例（读 config.bus.event_store.*，默认启用）。"""
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                cfg = None
                try:
                    from system.config import get_config

                    cfg = get_config().bus.event_store
                except Exception as e:  # noqa: BLE001 - 配置不可用时用默认值
                    logger.debug("[event_store] 读取配置失败，用默认值: %s", e)
                _store = EventStore(
                    enabled=getattr(cfg, "enabled", True),
                    buffer_lines=getattr(cfg, "buffer_lines", 200),
                    max_bytes=getattr(cfg, "max_bytes", 16 * 1024 * 1024),
                    keep_files=getattr(cfg, "keep_files", 5),
                    queue_max=getattr(cfg, "queue_max", 5000),
                )
    return _store


def reset_event_store_for_tests(store: EventStore | None = None) -> None:
    """测试用：替换/清空单例。"""
    global _store
    with _store_lock:
        if _store is not None and _store is not store:
            _store.close(timeout=0.5)
        _store = store
