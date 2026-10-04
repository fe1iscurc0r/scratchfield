"""graph_memory MCP 桥 — GraphMemoryBridge（agent-manifest.json entryPoint）。

接入方式与 hamlog_adapter / pdf2md_adapter 同构（manifest 型，
scan_and_register_mcp_agents 自动注册，mcp_manager.unified_call 分发）。

工具（5 个）：
- graph_memory_remember(entity, relation, target, ...)：记一条三元组（幂等）
- graph_memory_recall(query, hops, top_k)：多跳检索，返回三元组 + 实体注释
- graph_memory_hook(context, hops, top_k)：格式化为可注入的上下文文本
- graph_memory_export(query, hops, top_k)：导出子图（nodes + links，可视化用）
- graph_memory_stats()：图谱规模（实体/关系/别名）

fail-fast：空操作数 / 非法 hops 一律返回 {"status":"error", ...}，不静默空返回。
"""
from __future__ import annotations

import json
import logging
from typing import Any

from mcpserver.graph_memory_adapter.engine import GraphMemory, get_graph_memory

logger = logging.getLogger(__name__)


class GraphMemoryError(Exception):
    """图谱操作的显式失败。"""


class GraphMemoryBridge:
    """MCP 桥：把 GraphMemory 引擎包成可调用工具面。"""

    def __init__(self, db_path: str | None = None):
        self._db_path = db_path
        self._memory: GraphMemory | None = None

    # ---- 惰性取引擎（首次调用才开门，避免 import 期副作用）----
    @property
    def memory(self) -> GraphMemory:
        if self._memory is None:
            self._memory = get_graph_memory(self._db_path)
        return self._memory

    # -------------------------------------------------- 工具

    def graph_memory_remember(self, entity: str = "", relation: str = "",
                              target: str = "", entity_type: str = "",
                              target_type: str = "", description: str = "",
                              target_description: str = "", source_doc: str = "",
                              aliases: Any = None, **_: Any) -> dict:
        """记一条 (entity --[relation]--> target)。重复写幂等。"""
        if not (str(entity).strip() and str(relation).strip() and str(target).strip()):
            return {"status": "error", "error": "empty_operand",
                    "detail": "entity / relation / target 三者必填"}
        if isinstance(aliases, str):
            aliases = [a for a in aliases.split(",") if a.strip()]
        result = self.memory.remember(
            entity=str(entity).strip(), relation=str(relation).strip(),
            target=str(target).strip(), entity_type=entity_type,
            target_type=target_type, description=description,
            target_description=target_description, source_doc=source_doc,
            aliases=aliases)
        if not result.get("ok"):
            return {"status": "error", **result}
        return {"status": "ok", **result}

    def graph_memory_recall(self, query: str = "", hops: int = 3,
                            top_k: int = 8, **_: Any) -> dict:
        """多跳检索：从提问出发走 hops 跳，返回相关事实。"""
        if not str(query).strip():
            return {"status": "error", "error": "empty_query",
                    "detail": "query 必填"}
        hops, top_k = self._clamp(hops, top_k)
        facts = self.memory.recall(str(query), hops=hops, top_k=top_k)
        return {"status": "ok", **facts.to_dict(), "text": facts.as_text()}

    def graph_memory_hook(self, context: str = "", hops: int = 3,
                          top_k: int = 8, **_: Any) -> dict:
        """返回可直接注入对话的上下文文本（无匹配时空串）。"""
        hops, top_k = self._clamp(hops, top_k)
        text = self.memory.hook_prompt(str(context), hops=hops, top_k=top_k)
        return {"status": "ok", "injected": bool(text), "text": text}

    def graph_memory_export(self, query: str = "", hops: int = 3,
                            top_k: int = 8, **_: Any) -> dict:
        """导出子图（前端可视化）。"""
        if not str(query).strip():
            return {"status": "error", "error": "empty_query"}
        hops, top_k = self._clamp(hops, top_k)
        return {"status": "ok", **self.memory.export_subgraph(str(query), hops, top_k)}

    def graph_memory_stats(self, **_: Any) -> dict:
        """图谱规模。"""
        return {"status": "ok", **self.memory.stats()}

    async def handle_handoff(self, tool_call: dict[str, Any]) -> str:
        """类方法入口（总线契约）：按 tool 名分发到本类工具方法。

        注册表运行时按 instance.handle_handoff 调用（Format A: {module, class}），
        task 格式 {"tool": ..., "params": {...}}；工具方法均带 **_ 兜底，
        未知参数键不崩。返回 JSON 字符串。
        """
        tool = str(tool_call.get("tool") or tool_call.get("tool_name") or "").strip()
        params = tool_call.get("params")
        if not isinstance(params, dict):
            params = {}
        dispatcher: dict[str, Any] = {
            "graph_memory_remember": self.graph_memory_remember,
            "graph_memory_recall": self.graph_memory_recall,
            "graph_memory_hook": self.graph_memory_hook,
            "graph_memory_export": self.graph_memory_export,
            "graph_memory_stats": self.graph_memory_stats,
        }
        handler = dispatcher.get(tool)
        if handler is None:
            result: dict[str, Any] = {
                "status": "error",
                "error": f"unknown_tool: {tool}",
                "available": sorted(dispatcher),
            }
        else:
            result = handler(**params)
        return json.dumps(result, ensure_ascii=False, default=str)

    # -------------------------------------------------- 内部

    @staticmethod
    def _clamp(hops: Any, top_k: Any) -> tuple[int, int]:
        """钳位：hops 1–5，top_k 1–50（防一次拉爆上下文）。"""
        try:
            h = int(hops)
        except (TypeError, ValueError):
            h = 3
        try:
            k = int(top_k)
        except (TypeError, ValueError):
            k = 8
        return max(1, min(h, 5)), max(1, min(k, 50))
