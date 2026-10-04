"""工单编排 MCP 桥 — WorkflowBridge（agent-manifest.json entryPoint）。

U-01（UNIFORM 总装线）：把 GOLF 线交付的工单状态机挂成 MCP 工具，
Hermes/Lumo 经 POST /schedule → unified_call 即可操作工单板。
本桥只封装 task/board/claim/event_bus 现有接口，不重写任何状态机逻辑。

工具（7 个）：
- board_create(id, title, desc, deps, parent, assignee)：创建工单
- board_claim(id, owner, scope, ttl)：单赢家认领（租约）
- board_status(id, set, reason)：查看/迁移状态
- board_list(status, assignee)：列出工单
- board_done(id)：完成（审查门开启时进 in_review）
- board_blocked(id, reason)：阻塞（必带合法 reason code）
- event_log(limit)：最近事件日志（进程内环形缓冲）

数据库：WORKFLOW_DB 环境变量或默认 workflow.db，与 CLI 同源。
"""
from __future__ import annotations

import json
import logging
import os
from collections import deque
from typing import Any

from mcpserver.workflow import claim as claim_mod
from mcpserver.workflow.board import Board
from mcpserver.workflow.event_bus import ALL_EVENT_TYPES, EventBus
from mcpserver.workflow.task import Task

logger = logging.getLogger(__name__)

_DEFAULT_DB = "workflow.db"
_MAX_EVENTS = 200  # 进程内事件环形缓冲上限


# 调度层注入的路由键（分发前必须全部剥离，避免污染具名参数）
_ROUTING_KEYS = frozenset({
    "service_name", "tool_name", "agentType", "_tool_call_id",
    "message", "callback_url", "params", "arguments",
})


def _default_db_path() -> str:
    return os.environ.get("WORKFLOW_DB") or _DEFAULT_DB


class WorkflowBridge:
    """工单编排 MCP 服务实例（每次调用开关 Board，避免长持 SQLite 文件锁）。"""

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or _default_db_path()
        # 进程内事件缓冲：board 操作产生的事件经此总线分发并留痕
        self._events: deque[dict[str, Any]] = deque(maxlen=_MAX_EVENTS)
        self._bus = EventBus(log_path=None)
        for et in ALL_EVENT_TYPES:
            self._bus.subscribe(et, self._on_event)

    def _on_event(self, event: Any) -> None:
        self._events.append({
            "event_type": event.event_type,
            "source": event.source,
            "trace_id": event.trace_id,
            "payload": event.payload,
        })

    @property
    def event_bus(self) -> EventBus:
        """进程内事件总线（W119-04 跨总线桥订阅此实例；只读暴露，不改现有语义）。"""
        return self._bus

    def _open_board(self) -> Board:
        return Board(db_path=self.db_path, event_bus=self._bus)

    # ---- 工具实现（封装，不重写）----

    def board_create(self, id: str, title: str = "", desc: str = "",
                     deps: list[str] | None = None,
                     parent: str | None = None,
                     assignee: str | None = None) -> dict[str, Any]:
        """创建工单（同 CLI create）。"""
        if not (id or "").strip():
            return {"status": "error", "error": "id 不能为空"}
        task = Task(id=id.strip(), title=title or "", desc=desc or "",
                    deps=list(deps or []), parent=parent, assignee=assignee)
        board = self._open_board()
        try:
            board.create(task)
        finally:
            board.close()
        return {"status": "ok", "task": task.to_dict()}

    def board_claim(self, id: str, owner: str = "agent",
                    scope: str = "default",
                    ttl_seconds: float = 60.0) -> dict[str, Any]:
        """单赢家认领：赢家返回 won=true 并推进 in_progress。"""
        if not (id or "").strip():
            return {"status": "error", "error": "id 不能为空"}
        board = self._open_board()
        try:
            won = claim_mod.claim(board, id, scope, owner,
                                  ttl_seconds=float(ttl_seconds))
            task = board.get(id)
        finally:
            board.close()
        return {"status": "ok", "won": won,
                "task": task.to_dict() if task else None}

    def board_status(self, id: str, set: str | None = None,
                     reason: str | None = None) -> dict[str, Any]:
        """查看工单；带 set 时经状态机校验迁移。"""
        if not (id or "").strip():
            return {"status": "error", "error": "id 不能为空"}
        board = self._open_board()
        try:
            task = board.get(id)
            if task is None:
                return {"status": "error", "error": f"工单不存在: {id}"}
            if set:
                board.set_status(id, set, reason_code=reason)
                task = board.get(id)
        finally:
            board.close()
        return {"status": "ok", "task": task.to_dict()}

    def board_list(self, status: str | None = None,
                   assignee: str | None = None) -> dict[str, Any]:
        """列出工单（可按状态/负责人过滤）。"""
        board = self._open_board()
        try:
            tasks = board.list(status=status, assignee=assignee)
        finally:
            board.close()
        return {"status": "ok", "count": len(tasks),
                "tasks": [t.to_dict() for t in tasks]}

    def board_done(self, id: str) -> dict[str, Any]:
        """完成：审查门开启时进 in_review，否则直接 done。"""
        if not (id or "").strip():
            return {"status": "error", "error": "id 不能为空"}
        board = self._open_board()
        try:
            task = board.complete(id)
        finally:
            board.close()
        return {"status": "ok", "task": task.to_dict()}

    def board_blocked(self, id: str, reason: str) -> dict[str, Any]:
        """阻塞：必带合法 reason code（可等/不可等分类）。"""
        if not (id or "").strip():
            return {"status": "error", "error": "id 不能为空"}
        if not (reason or "").strip():
            return {"status": "error",
                    "error": "blocked 必须携带 reason code"}
        board = self._open_board()
        try:
            task = board.block(id, reason)
        finally:
            board.close()
        return {"status": "ok", "task": task.to_dict()}

    def event_log(self, limit: int = 20) -> dict[str, Any]:
        """最近 N 条事件（进程内缓冲，本实例经手的全部板操作）。"""
        try:
            limit = max(1, int(limit))
        except (TypeError, ValueError):
            limit = 20
        events = list(self._events)[-limit:]
        return {"status": "ok", "count": len(events), "events": events}

    # ---- MCP 分发 ----

    async def handle_handoff(self, tool_call: dict[str, Any]) -> str:
        """MCP 标准入口：按 tool_name 分发，剥离全部调度层路由键。"""
        tool_name = str(tool_call.get("tool_name") or "").strip()
        # 兼容嵌套 params/arguments 传参（路由键一律不透传给工具）
        inner = tool_call.get("params") or tool_call.get("arguments") or {}
        if isinstance(inner, dict):
            params = {k: v for k, v in inner.items() if k not in _ROUTING_KEYS}
        else:
            params = {}
        for k, v in tool_call.items():
            if k not in _ROUTING_KEYS and k not in params:
                params[k] = v
        try:
            if tool_name == "board_create":
                result = self.board_create(
                    str(params.get("id") or ""),
                    title=str(params.get("title") or ""),
                    desc=str(params.get("desc") or ""),
                    deps=params.get("deps") or [],
                    parent=params.get("parent"),
                    assignee=params.get("assignee"))
            elif tool_name == "board_claim":
                result = self.board_claim(
                    str(params.get("id") or ""),
                    owner=str(params.get("owner") or "agent"),
                    scope=str(params.get("scope") or "default"),
                    ttl_seconds=float(params.get("ttl_seconds", 60.0) or 60.0))
            elif tool_name == "board_status":
                result = self.board_status(
                    str(params.get("id") or ""),
                    set=params.get("set"), reason=params.get("reason"))
            elif tool_name == "board_list":
                result = self.board_list(status=params.get("status"),
                                         assignee=params.get("assignee"))
            elif tool_name == "board_done":
                result = self.board_done(str(params.get("id") or ""))
            elif tool_name == "board_blocked":
                result = self.board_blocked(str(params.get("id") or ""),
                                            str(params.get("reason") or ""))
            elif tool_name == "event_log":
                result = self.event_log(params.get("limit", 20))
            else:
                raise ValueError(
                    f"workflow 不支持的工具: {tool_name!r}（可用: "
                    "board_create/board_claim/board_status/board_list/"
                    "board_done/board_blocked/event_log）")
        except Exception as e:
            logger.exception("[workflow] %s 未预期异常", tool_name)
            return json.dumps({"status": "error", "service": "workflow",
                               "tool": tool_name, "error": str(e)},
                              ensure_ascii=False)
        return json.dumps({"service": "workflow", "tool": tool_name,
                           **result}, ensure_ascii=False)
