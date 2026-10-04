"""PTZ 审计日志（卷130 W130-04 §2）——JSONL，含 ts/source/命令/结果。

工单要求「对齐卷124 surface_telemetry 消费者」。这里刻意**不新造 schema**：
字段名沿用 `apiserver/event_bus/tool_gate.py` 的审计记录（`phase` / `ts` / `tool`），
再补上机械操控特有的 `source`（serial/lora/sim）与 `result`，
这样同一个消费端（surface_telemetry）能同时吃两边的条目。

三条纪律：

1. **审计失败绝不阻断操控回路**——写不进去只告警，机械命令该发还发。
   审计是「事后可查」，不是「事前许可」；把可观测性做成单点故障是反模式。
2. **落盘在专用目录**（`<user_data>/audit/ptz_calls.ndjson`），与 tool_gate 的
   `tool_calls.ndjson` 并列而不混同一个文件——两种记录的字段集合不同，
   混在一起会让消费端要靠猜字段来分流。
3. **参数不落敏感值**——复用 telemetry 的脱敏规则（失败退化为截断）。
"""
from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

AUDIT_FILENAME = "ptz_calls.ndjson"

#: 结果归类（消费端按这三档做统计，不用去解析 reply 文本）
RESULT_OK = "ok"
RESULT_ERROR = "error"
RESULT_BLOCKED = "blocked"      # 被确认门/Scope/熔断/锁机拦下（没发出去）


def default_audit_path() -> Path:
    """`<user_data>/audit/ptz_calls.ndjson`；user_data 取不到时退到当前目录。"""
    try:
        from system.config import get_data_dir  # noqa: PLC0415

        return Path(get_data_dir()) / "audit" / AUDIT_FILENAME
    except Exception:  # noqa: BLE001
        return Path.cwd() / ".ptz_audit" / AUDIT_FILENAME


def _sanitize(args: Any, *, max_chars: int = 400) -> Any:
    """参数脱敏 + 截断（同 tool_gate 的做法，尽量复用 telemetry 规则）。"""
    cleaned = args
    try:
        from apiserver.telemetry import _sanitize_value  # noqa: PLC0415

        cleaned = _sanitize_value(args)
    except Exception:  # noqa: BLE001
        pass
    text = json.dumps(cleaned, ensure_ascii=False, default=str)
    return json.loads(text) if len(text) <= max_chars else text[:max_chars] + "…<truncated>"


class PTZAuditLog:
    """追加式审计（线程安全；写入失败只告警）。"""

    def __init__(self, path: Any | None = None, *, enabled: bool = True):
        self.enabled = bool(enabled)
        self.path = Path(path) if path else default_audit_path()
        self._lock = threading.Lock()
        #: 进程内留存最近若干条（测试与 ptz_config 展示用，不依赖磁盘）
        self.recent: List[Dict[str, Any]] = []
        self.written = 0
        self.write_failures = 0

    # ---- 写 ----

    def record(self, *, cmd: str, source: str = "", result: str = RESULT_OK,
               ok: bool | None = None, detail: str = "", tool: str = "",
               error: str = "", args: Any = None, phase: str = "command",
               extra: Dict[str, Any] | None = None) -> Dict[str, Any]:
        """记一条。`ts` 用 wall clock（审计要能和人读的时间对上）；
        内部还附 `ts_mono` 便于算间隔（monotonic 才是算时长的正确基准）。"""
        entry: Dict[str, Any] = {
            "phase": str(phase),
            "ts": round(time.time(), 3),
            "ts_mono": round(time.monotonic(), 3),
            "tool": str(tool or ""),
            "cmd": str(cmd or ""),
            "source": str(source or ""),
            "result": str(result),
            "ok": bool(ok) if ok is not None else (result == RESULT_OK),
        }
        if detail:
            entry["detail"] = str(detail)
        if error:
            entry["error"] = str(error)
        if args is not None:
            entry["args"] = _sanitize(args)
        if extra:
            entry.update(extra)

        with self._lock:
            self.recent.append(entry)
            if len(self.recent) > 200:
                del self.recent[:-200]
        self._flush(entry)
        return entry

    def _flush(self, entry: Dict[str, Any]) -> None:
        if not self.enabled:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
            self.written += 1
        except (OSError, ValueError) as exc:
            # ValueError 也要接：非法路径字符（如 NUL）抛的是它而不是 OSError，
            # 漏接会让审计异常穿透到操控回路——那正好违反「审计不阻断操控」。
            self.write_failures += 1
            logger.warning("[ptz_audit] 审计落盘失败（不阻断操控）: %s", exc)

    # ---- 读 ----

    def tail(self, limit: int = 50) -> List[Dict[str, Any]]:
        """内存里最近若干条（不读盘——诊断路径不该有 I/O 副作用）。"""
        with self._lock:
            return list(self.recent[-max(1, int(limit)):])

    def read_all(self) -> List[Dict[str, Any]]:
        """读整份 JSONL（坏行跳过，不因一行损坏丢掉整份日志）。"""
        if not self.path.is_file():
            return []
        out: List[Dict[str, Any]] = []
        try:
            with open(self.path, encoding="utf-8") as fh:
                for line in fh:
                    text = line.strip()
                    if not text:
                        continue
                    try:
                        out.append(json.loads(text))
                    except json.JSONDecodeError:
                        continue
        except OSError as exc:
            logger.warning("[ptz_audit] 读审计失败: %s", exc)
        return out

    def stats(self) -> Dict[str, Any]:
        """按 result 归类统计（诊断用）。"""
        entries = self.read_all() or self.tail(200)
        counts: Dict[str, int] = {}
        for item in entries:
            key = str(item.get("result") or "?")
            counts[key] = counts.get(key, 0) + 1
        return {"path": str(self.path), "enabled": self.enabled, "entries": len(entries),
                "by_result": counts, "written": self.written,
                "write_failures": self.write_failures}


__all__ = ["PTZAuditLog", "default_audit_path", "AUDIT_FILENAME",
           "RESULT_OK", "RESULT_ERROR", "RESULT_BLOCKED"]
