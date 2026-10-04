"""W121-03：对话流确认门 —— 写操作先给 diff，用户点头才落盘。

作为卷119 W119-03 `TOOL_PRE_EXECUTE` waterfall 的一个 handler 挂载（与审计/敏感/熔断门同链路）。

流程：
1. 模型调 `file_write` / `file_edit` → 本门拦下，用 `dry_run` 预览算出真实 diff，
   写入该会话的 `pending_confirm` 清单，返回 veto 原因「等待用户确认：<diff>」。
2. 模型拿到这个结果会转述给用户（diff 已在其上下文中）。
3. 用户回复「确认 / 继续 / 执行」（或前端按钮 → `decide(sid, "confirm")`）→ 该签名进入
   一次性放行集；模型下一轮再调同一个（签名一致）调用 → 直接放行。
4. 用户回复「拒绝 / 取消」→ 签名进入拒绝集，下一次同签名调用被 veto（「用户拒绝，请调整方案」），
   文件 mtime 不变。

状态按会话隔离，只存内存（不落盘敏感内容）；`code_space.plan_confirm=false` 时整门旁路
（直接执行，仍由审计门记录）。
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

#: 需要确认的写类工具（其他工具不拦）
WRITE_TOOLS: Set[str] = {"file_write", "file_edit"}

#: 确认/拒绝关键词（仅在该会话确有 pending 时才生效，避免误伤正常对话）
CONFIRM_KEYWORDS: Tuple[str, ...] = (
    "确认", "继续", "执行", "同意", "可以", "好的", "批准", "允许", "动手", "就这样",
    "ok", "yes", "go ahead",
)
REJECT_KEYWORDS: Tuple[str, ...] = (
    "拒绝", "取消", "驳回", "算了", "不用了", "不要改", "别改", "先别", "停下", "停止",
    "cancel", "reject", "no",
)


class ConfirmGateRuntime:
    """确认门的运行时状态（按会话的 pending / 一次性放行 / 拒绝集）。"""

    def __init__(self, cfg: Any = None, *, audit: Callable[[Dict[str, Any]], None] | None = None) -> None:
        self._cfg = cfg
        self._audit_fn = audit
        self._lock = threading.Lock()
        self._pending: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._confirmed: Dict[str, Dict[str, float]] = {}
        self._rejected: Dict[str, Set[str]] = {}
        self.pending_total = 0
        self.confirmed_total = 0
        self.rejected_total = 0

    # ---- 配置 ----

    @property
    def enabled(self) -> bool:
        cfg = self._cfg
        if cfg is None:
            try:
                from system.config import get_config

                cfg = get_config().code_space
                self._cfg = cfg
            except Exception:  # noqa: BLE001 - 配置不可用按默认开（安全侧默认）
                return True
        return bool(getattr(cfg, "plan_confirm", True))

    # ---- 审计 ----

    def _audit(self, record: Dict[str, Any]) -> None:
        payload = {"ts": time.time(), "phase": "confirm_gate", **record}
        if self._audit_fn is not None:
            try:
                self._audit_fn(payload)
                return
            except Exception:  # noqa: BLE001
                logger.debug("[confirm_gate] 审计回调失败", exc_info=True)
        try:
            from .tool_gate import get_tool_gate_runtime

            get_tool_gate_runtime().audit(payload)
        except Exception:  # noqa: BLE001 - 审计失败不影响确认流程
            logger.debug("[confirm_gate] 审计落盘失败", exc_info=True)

    # ---- 签名 ----

    @staticmethod
    def _signature(tool: str, args: Dict[str, Any]) -> str:
        """调用签名：同工具 + 同路径 + 同内容 = 同一次待确认写操作。"""
        relevant = {
            k: v
            for k, v in (args or {}).items()
            if not str(k).startswith("_") and k != "session_id"
        }
        blob = json.dumps([tool, relevant], ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]

    # ---- 预览 ----

    @staticmethod
    def _preview(tool: str, args: Dict[str, Any], session_id: str) -> Tuple[bool, str]:
        """用 code_workspace 的 dry_run 预览算真实 diff；返回 (ok, 文本)。"""
        try:
            from mcpserver.code_workspace.tools import CodeWorkspaceBridge

            bridge = CodeWorkspaceBridge()
            if tool == "file_write":
                payload = bridge.file_write(
                    path=str(args.get("path") or ""),
                    content=str(args.get("content") or ""),
                    session_id=session_id or "default",
                    dry_run=True,
                )
            elif tool == "file_edit":
                payload = bridge.file_edit(
                    path=str(args.get("path") or ""),
                    old=str(args.get("old") or ""),
                    new=str(args.get("new") or ""),
                    session_id=session_id or "default",
                    dry_run=True,
                )
            else:
                return True, ""
        except Exception as e:  # noqa: BLE001 - 预览失败就退回粗略描述
            logger.warning("[confirm_gate] diff 预览失败: %s", e)
            return True, f"（diff 预览不可用：{e}）"
        if isinstance(payload, dict) and payload.get("error"):
            return False, str(payload.get("message") or payload.get("error"))
        diff = str((payload or {}).get("diff") or "").strip()
        if not diff:
            diff = "(无内容变化)"
        if len(diff) > 2000:
            diff = diff[:2000] + "\n…<diff 截断>"
        return True, diff

    # ---- waterfall handler ----

    def gate(self, event: Dict[str, Any], nxt: Callable[[], Any]) -> Any:
        """TOOL_PRE_EXECUTE 确认门：写操作未确认即 veto（放行时调 next 继续洋葱链）。"""
        if not self.enabled:
            return nxt()
        tool = str(event.get("tool") or "")
        if tool not in WRITE_TOOLS:
            return nxt()

        session_id = str(event.get("session_id") or "default")
        args = {k: v for k, v in (event.get("args") or {}).items() if not str(k).startswith("_")}
        sig = self._signature(tool, args)

        with self._lock:
            confirmed = self._confirmed.get(session_id, {})
            if sig in confirmed:
                confirmed.pop(sig, None)
                self.confirmed_total += 1
                self._audit({"decision": "confirmed_release", "tool": tool, "session_id": session_id,
                             "signature": sig, "path": args.get("path")})
                logger.info("[confirm_gate] 已确认，放行 %s（%s）", tool, args.get("path"))
                return nxt()

            if sig in self._rejected.get(session_id, set()):
                self._rejected[session_id].discard(sig)
                self.rejected_total += 1
                self._audit({"decision": "rejected_hold", "tool": tool, "session_id": session_id,
                             "signature": sig, "path": args.get("path")})
                logger.info("[confirm_gate] 用户已拒绝，继续拦下 %s（%s）", tool, args.get("path"))
                return {
                    "veto": True,
                    "gate": "confirm",
                    "reason": (
                        f"用户拒绝了对 {args.get('path')} 的修改，请调整方案后重新说明，"
                        "不要重复提交同一改动。"
                    ),
                }

        ok, diff = self._preview(tool, args, session_id)
        if not ok:
            # 预览阶段就报错（路径越界等）：把错误原样给模型，不挂 pending
            self._audit({"decision": "preview_error", "tool": tool, "session_id": session_id,
                         "signature": sig, "reason": diff})
            return {"veto": True, "gate": "confirm", "reason": f"改动无法应用：{diff}"}

        with self._lock:
            self._pending.setdefault(session_id, {})[sig] = {
                "tool": tool,
                "path": args.get("path"),
                "signature": sig,
                "diff": diff,
                "ts": time.time(),
            }
        self.pending_total += 1
        self._audit({"decision": "pending", "tool": tool, "session_id": session_id,
                     "signature": sig, "path": args.get("path"), "diff": diff[:500]})
        logger.info("[confirm_gate] 写操作待确认：%s %s（会话 %s）", tool, args.get("path"), session_id)
        return {
            "veto": True,
            "gate": "confirm",
            "reason": (
                f"等待用户确认：{tool} → {args.get('path')}\n"
                f"```diff\n{diff}\n```\n"
                "请把这段 diff 展示给用户并询问是否执行；用户回复「确认/继续/执行」后重发同一次调用即可落盘。"
            ),
            "pending_confirm": {"session_id": session_id, "tool": tool, "path": args.get("path"),
                                "signature": sig, "diff": diff},
        }

    # ---- 用户决策 ----

    def observe_user_message(self, session_id: str, text: str) -> str | None:
        """扫描用户消息：有 pending 时识别「确认/拒绝」。返回 'confirm' / 'reject' / None。"""
        if not self.enabled or not session_id or not text:
            return None
        with self._lock:
            if not self._pending.get(session_id):
                return None
        lowered = str(text).lower()
        # 拒绝优先：用户说「不要改」时不应被 "不要" 之外的确认词抢走
        for kw in REJECT_KEYWORDS:
            if kw in lowered:
                self.decide(session_id, "reject", source="chat_keyword")
                return "reject"
        for kw in CONFIRM_KEYWORDS:
            if kw in lowered:
                self.decide(session_id, "confirm", source="chat_keyword")
                return "confirm"
        return None

    def decide(self, session_id: str, decision: str, *, source: str = "api") -> int:
        """确认/拒绝该会话全部 pending 写操作，返回受影响条数。"""
        with self._lock:
            items = self._pending.pop(session_id, {})
            if not items:
                return 0
            if decision == "confirm":
                bucket = self._confirmed.setdefault(session_id, {})
                for sig in items:
                    bucket[sig] = time.time()
            else:
                self._rejected.setdefault(session_id, set()).update(items.keys())
        self._audit({
            "decision": "confirm_all" if decision == "confirm" else "reject_all",
            "session_id": session_id,
            "source": source,
            "count": len(items),
            "items": [{"tool": it.get("tool"), "path": it.get("path"), "signature": it.get("signature")}
                      for it in items.values()],
        })
        logger.info("[confirm_gate] 会话 %s %s %d 项写操作（来源 %s）", session_id, decision, len(items), source)
        return len(items)

    # ---- 查询 ----

    def pending(self, session_id: str) -> List[Dict[str, Any]]:
        """该会话待确认清单（不含内容明文，只有工具/路径/签名/diff）。"""
        with self._lock:
            return [dict(v) for v in self._pending.get(session_id, {}).values()]

    def clear(self, session_id: str | None = None) -> None:
        with self._lock:
            if session_id is None:
                self._pending.clear()
                self._confirmed.clear()
                self._rejected.clear()
            else:
                self._pending.pop(session_id, None)
                self._confirmed.pop(session_id, None)
                self._rejected.pop(session_id, None)

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            sessions = {sid: len(items) for sid, items in self._pending.items() if items}
        return {
            "enabled": self.enabled,
            "pending_total": self.pending_total,
            "confirmed_total": self.confirmed_total,
            "rejected_total": self.rejected_total,
            "pending_sessions": sessions,
        }


_runtime: ConfirmGateRuntime | None = None
_runtime_lock = threading.Lock()


def get_confirm_gate() -> ConfirmGateRuntime:
    """进程内单例（与 tool_gate 同风格）。"""
    global _runtime
    if _runtime is None:
        with _runtime_lock:
            if _runtime is None:
                _runtime = ConfirmGateRuntime()
    return _runtime


def reset_confirm_gate_for_tests(runtime: ConfirmGateRuntime | None = None) -> None:
    global _runtime
    with _runtime_lock:
        _runtime = runtime


def register_confirm_gate(bus: Any) -> Callable[[], None]:
    """把确认门挂到 TOOL_PRE_EXECUTE（返回 disposer）。"""
    from .topics import Topics

    runtime = get_confirm_gate()
    disposer = bus.on(Topics.TOOL_PRE_EXECUTE, runtime.gate)
    logger.info("[confirm_gate] 写操作确认门已注册（enabled=%s）", runtime.enabled)
    return disposer
