"""合成路线 RAG MCP 桥 — SynthRagBridge（INDIA 线，挂进 material_science）。

U-03（UNIFORM 总装线）：把 synth_rag 的路线库挂成 material_science 的 MCP 工具。
本桥只封装 store/retrieve/validator 现有接口，不重写检索/校验逻辑；
检索保持 sqlite 轻量实现，不引向量 DB。

工具（3 个）：
- search(product, reactant, condition, top_k)：按产物/反应物/条件过滤 + 相似度排序
- add(route)：入库一条路线（物理校验可选前置）
- validate(route, rules)：物理校验（产率区间/温度合理等，规则可开关）
"""
from __future__ import annotations

import logging
from typing import Any

from mcpserver.material_science.synth_rag import retrieve, validator
from mcpserver.material_science.synth_rag.store import RouteStore

logger = logging.getLogger(__name__)


class SynthRagBridge:
    """合成路线 RAG 桥（每次调用开关 RouteStore，避免长持 SQLite 文件锁）。"""

    def __init__(self, db_path: str | None = None):
        # None → store 默认库；":memory:" → 内存库（测试）
        self.db_path = db_path

    def _open_store(self) -> RouteStore:
        return RouteStore(self.db_path)

    # ---- 工具实现（封装，不重写）----

    def search(self, product: str = "", reactant: str = "",
               condition: str = "", top_k: int = 10) -> dict[str, Any]:
        """检索路线（全空过滤词时返回全量按 id）。"""
        try:
            top_k = max(1, int(top_k))
        except (TypeError, ValueError):
            top_k = 10
        store = self._open_store()
        try:
            result = retrieve.search(store, product=str(product or ""),
                                     reactant=str(reactant or ""),
                                     condition=str(condition or ""),
                                     top_k=top_k)
        finally:
            store.close()
        return {"status": "ok", **result}

    def add(self, route: dict | None = None) -> dict[str, Any]:
        """入库一条路线（route 为 dict，字段见 schema.Route）。"""
        if not isinstance(route, dict):
            return {"status": "error", "error": "route 必须是 JSON 对象"}
        store = self._open_store()
        try:
            route_id = store.add_route(route)  # 坏输入抛 ValueError/TypeError
            count = store.count()
        except (ValueError, TypeError, KeyError) as e:
            return {"status": "error", "error": str(e)}
        finally:
            store.close()
        return {"status": "ok", "route_id": route_id, "count": count}

    def validate(self, route: dict | None = None,
                 rules: dict | None = None) -> dict[str, Any]:
        """物理校验一条路线（不入库），返回 {valid, passed, issues}。"""
        if not isinstance(route, dict):
            return {"status": "error", "error": "route 必须是 JSON 对象"}
        try:
            result = validator.validate(route, rules=rules)
        except (ValueError, TypeError, KeyError) as e:
            return {"status": "error", "error": str(e)}
        return {"status": "ok", **result}


def register_synth_tools(agent) -> None:
    """往 MaterialScienceAgent 注入 synth_search / synth_add / synth_validate。"""
    bridge = SynthRagBridge()  # 默认库路径与 CLI 同源

    def _tool_search(params: dict[str, Any]) -> dict[str, Any]:
        return bridge.search(product=str(params.get("product") or ""),
                             reactant=str(params.get("reactant") or ""),
                             condition=str(params.get("condition") or ""),
                             top_k=params.get("top_k", 10))

    def _tool_add(params: dict[str, Any]) -> dict[str, Any]:
        return bridge.add(params.get("route"))

    def _tool_validate(params: dict[str, Any]) -> dict[str, Any]:
        return bridge.validate(params.get("route"), rules=params.get("rules"))

    agent.tools["synth_search"] = _tool_search
    agent.tools["synth_add"] = _tool_add
    agent.tools["synth_validate"] = _tool_validate
    logger.info("[MCP] synth_search/synth_add/synth_validate 已注入 material_science agent")


__all__ = ["SynthRagBridge", "register_synth_tools"]
