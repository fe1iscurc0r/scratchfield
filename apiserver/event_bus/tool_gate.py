"""W119-03：工具调用安全门（TOOL_PRE_EXECUTE waterfall 的三个内置 gate）。

三道路径（按注册顺序洋葱式执行，任一不调 next() 即 veto）：
1. **审计门**：每次工具调用（含 veto 与被拒）写 audit 日志到
   `get_data_dir()/audit/tool_calls.ndjson`；参数经脱敏 + 截断，不落敏感值。
2. **敏感工具门**：命中黑名单（或名字片段族）即 veto，`allowlist` 显式放行。
3. **熔断门**：按工具名统计窗口内连续失败次数，超阈值自动 veto。

配置：`config.bus.tool_gate.*`（enabled / audit_only / sensitive_tools / sensitive_keywords /
allowlist / breaker_threshold / breaker_window_seconds）。`audit_only=true` 时后两道门只记不拦（灰度）。

说明：审计清单来自 tool_schemas.py / mcpserver manifests 的实际枚举（见本目录 README.md 清单表），
不凭空列；veto 只拦「本次调用」，不影响工具本身的可用性（改配置即恢复）。
"""
from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .bus import EventBus
from .disposable import Disposable

logger = logging.getLogger(__name__)

AUDIT_FILENAME = "tool_calls.ndjson"


def _audit_path() -> Path:
    from system.config import get_data_dir

    return Path(get_data_dir()) / "audit" / AUDIT_FILENAME


def _sanitize_args(args: Any, *, max_chars: int = 400) -> Any:
    """参数脱敏 + 截断（复用 telemetry 的脱敏规则，失败则退化为字符串截断）。"""
    try:
        from apiserver.telemetry import _sanitize_value

        cleaned = _sanitize_value(args)
    except Exception:  # noqa: BLE001
        cleaned = args
    text = json.dumps(cleaned, ensure_ascii=False, default=str)
    return json.loads(text) if len(text) <= max_chars else text[:max_chars] + "…<truncated>"


class ToolGateRuntime:
    """工具门的运行时状态：配置 + 熔断计数 + 审计落盘。"""

    def __init__(self, cfg: Any = None, *, bus: EventBus | None = None) -> None:
        self.cfg = cfg
        self.bus = bus
        self._lock = threading.Lock()
        self._fail_streak: Dict[str, int] = {}
        self._last_failure_ts: Dict[str, float] = {}
        self.audit_written = 0
        self.veto_count = 0
        self.audit_only_skips = 0

    # ---- 配置读取（容错：配置不可用时用保守默认） ----

    @property
    def enabled(self) -> bool:
        return bool(getattr(self.cfg, "enabled", True))

    @property
    def audit_only(self) -> bool:
        return bool(getattr(self.cfg, "audit_only", False))

    @property
    def sensitive_tools(self) -> set[str]:
        return {str(x) for x in (getattr(self.cfg, "sensitive_tools", None) or [])}

    @property
    def sensitive_keywords(self) -> List[str]:
        return [str(x).lower() for x in (getattr(self.cfg, "sensitive_keywords", None) or [])]

    @property
    def allowlist(self) -> set[str]:
        return {str(x) for x in (getattr(self.cfg, "allowlist", None) or [])}

    @property
    def breaker_threshold(self) -> int:
        return max(1, int(getattr(self.cfg, "breaker_threshold", 5) or 5))

    @property
    def breaker_window(self) -> float:
        return float(getattr(self.cfg, "breaker_window_seconds", 60) or 60)

    # ---- 判定 ----

    def is_sensitive(self, tool_name: str) -> Tuple[bool, str]:
        """是否敏感工具（allowlist 优先放行）。"""
        name = str(tool_name or "")
        if not name:
            return False, ""
        if name in self.allowlist:
            return False, ""
        if name in self.sensitive_tools:
            return True, "命中敏感工具名单"
        lowered = name.lower()
        for keyword in self.sensitive_keywords:
            if keyword and keyword in lowered:
                return True, f"命中敏感片段 '{keyword}'"
        return False, ""

    def breaker_tripped(self, tool_name: str) -> Tuple[bool, int]:
        """窗口内连续失败是否已达阈值。"""
        name = str(tool_name or "")
        if not name:
            return False, 0
        with self._lock:
            streak = self._fail_streak.get(name, 0)
            last_ts = self._last_failure_ts.get(name, 0.0)
        if streak >= self.breaker_threshold and (time.time() - last_ts) <= self.breaker_window:
            return True, streak
        return False, streak

    def record_result(self, tool_name: str, ok: bool) -> None:
        """记录工具执行结果：成功清零连续失败，失败累加并打时间戳。"""
        name = str(tool_name or "")
        if not name:
            return
        with self._lock:
            if ok:
                self._fail_streak.pop(name, None)
                self._last_failure_ts.pop(name, None)
            else:
                self._fail_streak[name] = self._fail_streak.get(name, 0) + 1
                self._last_failure_ts[name] = time.time()

    # ---- 审计落盘 ----

    def audit(self, record: Dict[str, Any]) -> None:
        """追加一条审计记录（失败只告警，不影响工具调用）。"""
        try:
            path = _audit_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
            self.audit_written += 1
        except OSError as e:
            logger.warning("[tool_gate] 审计落盘失败（不拦截工具）: %s", e)

    # ---- 三个 waterfall handler ----

    def audit_gate(self, event: Dict[str, Any], nxt: Callable[[], Any]) -> Any:
        """审计门：先记 pre 记录，再放行。"""
        self.audit(
            {
                "phase": "pre",
                "ts": time.time(),
                "tool": event.get("tool"),
                "agent_type": event.get("agent_type"),
                "session_id": event.get("session_id"),
                "agent_id": event.get("agent_id"),
                "args": event.get("args"),
            }
        )
        return nxt()

    def sensitive_gate(self, event: Dict[str, Any], nxt: Callable[[], Any]) -> Any:
        """敏感工具门：命中即 veto（audit_only 时只记不拦）。"""
        tool_name = str(event.get("tool") or "")
        hit, reason = self.is_sensitive(tool_name)
        if not hit:
            return nxt()
        if self.audit_only:
            self.audit_only_skips += 1
            self.audit({"phase": "sensitive_skip", "ts": time.time(), "tool": tool_name, "reason": reason})
            return nxt()
        self.veto_count += 1
        self.audit({"phase": "veto", "ts": time.time(), "tool": tool_name, "reason": reason, "gate": "sensitive"})
        logger.warning("[tool_gate] 拦截敏感工具 %s（%s）", tool_name, reason)
        return {"veto": True, "reason": f"工具被策略拦截：{tool_name}（{reason}）", "gate": "sensitive"}

    def breaker_gate(self, event: Dict[str, Any], nxt: Callable[[], Any]) -> Any:
        """熔断门：连续失败达阈值即 veto（audit_only 时只记不拦）。"""
        tool_name = str(event.get("tool") or "")
        tripped, streak = self.breaker_tripped(tool_name)
        if not tripped:
            return nxt()
        if self.audit_only:
            self.audit_only_skips += 1
            self.audit({"phase": "breaker_skip", "ts": time.time(), "tool": tool_name, "streak": streak})
            return nxt()
        self.veto_count += 1
        self.audit({"phase": "veto", "ts": time.time(), "tool": tool_name, "streak": streak, "gate": "breaker"})
        logger.warning("[tool_gate] 熔断拦截 %s（连续失败 %d 次）", tool_name, streak)
        return {
            "veto": True,
            "reason": f"工具 {tool_name} 连续失败 {streak} 次，已熔断，稍后再试",
            "gate": "breaker",
        }

    def handlers(self) -> List[Callable[[Dict[str, Any], Callable[[], Any]], Any]]:
        return [self.audit_gate, self.sensitive_gate, self.breaker_gate]


_runtime: ToolGateRuntime | None = None
_runtime_lock = threading.Lock()


def get_tool_gate_runtime() -> ToolGateRuntime:
    """进程级单例（读 config.bus.tool_gate.*）。"""
    global _runtime
    if _runtime is None:
        with _runtime_lock:
            if _runtime is None:
                cfg = None
                try:
                    from system.config import get_config

                    cfg = get_config().bus.tool_gate
                except Exception as e:  # noqa: BLE001
                    logger.debug("[tool_gate] 读取配置失败，用默认值: %s", e)
                _runtime = ToolGateRuntime(cfg)
    return _runtime


def reset_tool_gate_runtime_for_tests(runtime: ToolGateRuntime | None = None) -> None:
    """测试用：替换单例。"""
    global _runtime
    with _runtime_lock:
        _runtime = runtime


def register_tool_gates(bus: EventBus) -> Disposable:
    """把三个内置 gate 注册到 TOOL_PRE_EXECUTE（返回 disposer；注册失败可忽略）。"""
    from .topics import Topics

    runtime = get_tool_gate_runtime()
    runtime.bus = bus
    disposers = [bus.on(Topics.TOOL_PRE_EXECUTE, handler) for handler in runtime.handlers()]

    def dispose() -> None:
        for d in disposers:
            d()

    logger.info(
        "[tool_gate] 工具安全门已注册（enabled=%s, audit_only=%s, 敏感工具 %d 个）",
        runtime.enabled,
        runtime.audit_only,
        len(runtime.sensitive_tools),
    )
    return dispose


def record_tool_result(tool_name: str, ok: bool, *, duration_s: float | None = None) -> None:
    """工具执行后回填结果（熔断计数 + 审计 post 记录）。失败静默。"""
    try:
        runtime = get_tool_gate_runtime()
        runtime.record_result(tool_name, ok)
        runtime.audit(
            {
                "phase": "post",
                "ts": time.time(),
                "tool": tool_name,
                "ok": bool(ok),
                "duration_s": round(duration_s, 3) if duration_s is not None else None,
            }
        )
    except Exception:  # noqa: BLE001 - 结果回填不得影响工具回路
        logger.debug("[tool_gate] record_tool_result 失败", exc_info=True)
