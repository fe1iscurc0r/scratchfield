"""bridge.py — sentinel_intel MCP 桥（SPEC-09 K-01）。

结构照 mcpserver/memory_maas/ 范式（agent-manifest.json entryPoint →
Bridge 类 → handle_handoff 分发）。3 命令：
- intel_ingest(entities, edges)：幂等入库（边端点可引用 {etype,value} 或 id）
- intel_query(value, etype?)：先 alias 归并再查画像（实体+出边+时间线）
- intel_timeline(etype, value)：实体活动时间线

fail-fast：白名单违规/端点缺失 → {"status":"error"}，不静默空返回。
"""
from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

from mcpserver.sentinel_intel.graph import IntelGraph, IntelGraphError
from mcpserver.sentinel_intel.schema import entity_id

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_DB_ENV = "SENTINEL_INTEL_DB"

_GRAPH: IntelGraph | None = None
_GRAPH_LOCK = threading.Lock()


def get_graph(db_path: str | None = None,
              fresh: bool = False) -> IntelGraph:
    """进程内单例（测试 fresh=True 换独立实例时先 close 旧的；单写者纪律 RLock）。"""
    global _GRAPH
    with _GRAPH_LOCK:
        if fresh and _GRAPH is not None:
            _GRAPH.close()
            _GRAPH = None
        if _GRAPH is None:
            path = db_path or os.environ.get(_DEFAULT_DB_ENV,
                                             str(_REPO_ROOT / "sentinel_intel.db"))
            _GRAPH = IntelGraph(path)
        return _GRAPH


def reset_graph() -> None:
    """测试收尾：close 并清空单例。"""
    global _GRAPH
    with _GRAPH_LOCK:
        if _GRAPH is not None:
            _GRAPH.close()
        _GRAPH = None


class IntelBridge:
    """威胁情报实体图 MCP 服务实例。"""

    async def handle_handoff(self, tool_call: dict[str, Any]) -> str:
        tool_name = str(tool_call.get("tool_name") or "").strip()
        params = {k: v for k, v in tool_call.items()
                  if k not in ("service_name", "tool_name", "message",
                               "session_id", "callback_url")}
        try:
            result = self._dispatch(tool_name, params)
        except IntelGraphError as e:
            logger.warning("[sentinel_intel] %s 失败: %s", tool_name, e)
            return json.dumps({"status": "error", "service": "sentinel_intel",
                               "tool": tool_name, "error": str(e)},
                              ensure_ascii=False)
        except Exception as e:
            logger.exception("[sentinel_intel] %s 未预期异常", tool_name)
            return json.dumps({"status": "error", "service": "sentinel_intel",
                               "tool": tool_name, "error": f"未预期异常: {e}"},
                              ensure_ascii=False)
        return json.dumps({"status": "ok", "service": "sentinel_intel",
                           "tool": tool_name, "result": result},
                          ensure_ascii=False)

    # ------------------------------------------------------------ 分发
    def _dispatch(self, tool_name: str, p: dict[str, Any]) -> dict[str, Any]:
        graph = get_graph()
        if tool_name == "intel_ingest":
            return self._ingest(graph, p)
        if tool_name == "intel_query":
            etype = p.get("etype") or self._guess_etype(graph, p["value"])
            profile = self._query_profile(graph, etype, p["value"])
            if profile is None:
                raise IntelGraphError(
                    f"实体不存在: {etype}/{p['value']}（先 intel_ingest）")
            return profile
        if tool_name == "intel_timeline":
            return {"ok": True,
                    "timeline": graph.get_entity_timeline(p["etype"], p["value"])}
        raise IntelGraphError(
            f"sentinel_intel 不支持的工具: {tool_name!r}（可用: intel_ingest/"
            "intel_query/intel_timeline）")

    # ------------------------------------------------------------ 工具实现
    @staticmethod
    def _resolve_ref(graph: IntelGraph, ref: Any) -> str:
        """边端点引用：str=已建实体 id；dict={etype,value} 现场幂等建。"""
        if isinstance(ref, str):
            if not graph.conn.execute(
                    "SELECT 1 FROM intel_entity WHERE id=?", (ref,)).fetchone():
                raise IntelGraphError(f"边端点 id 不存在: {ref}")
            return ref
        if isinstance(ref, dict) and ref.get("etype") and ref.get("value"):
            return graph.add_node(ref["etype"], ref["value"],
                                  props=ref.get("props"))
        raise IntelGraphError(f"非法端点引用: {ref!r}（用 id 字符串或 "
                              "{{etype,value}} 对象）")

    def _ingest(self, graph: IntelGraph, p: dict[str, Any]) -> dict[str, Any]:
        entities = p.get("entities") or []
        edges = p.get("edges") or []
        if not isinstance(entities, list) or not isinstance(edges, list):
            raise IntelGraphError("entities/edges 必须是数组")
        node_ids: list[str] = []
        for ent in entities:
            if not isinstance(ent, dict) or not ent.get("etype") \
                    or not ent.get("value"):
                raise IntelGraphError(f"非法实体条目: {ent!r}")
            node_ids.append(graph.add_node(
                ent["etype"], ent["value"], props=ent.get("props"),
                ts=ent.get("ts")))
        edge_ids: list[str] = []
        for ed in edges:
            if not isinstance(ed, dict):
                raise IntelGraphError(f"非法边条目: {ed!r}")
            src = self._resolve_ref(graph, ed.get("src"))
            dst = self._resolve_ref(graph, ed.get("dst"))
            edge_ids.append(graph.add_edge(
                src, dst, ed.get("rel", "uses"), props=ed.get("props"),
                ts=ed.get("ts")))
        counts = graph.conn.execute(
            "SELECT (SELECT COUNT(*) FROM intel_entity) AS e, "
            "(SELECT COUNT(*) FROM intel_edge) AS r").fetchone()
        return {"ok": True, "ingested_entities": len(node_ids),
                "ingested_edges": len(edge_ids),
                "total_entities": counts["e"], "total_edges": counts["r"]}

    def _query_profile(self, graph: IntelGraph, etype: str,
                       value: str) -> dict[str, Any] | None:
        """先 alias 归并（三级回退）再查画像。"""
        canonical_value = graph.resolver.resolve(etype, value)
        profile = graph.get_profile(etype, canonical_value)
        if profile is not None:
            profile["resolved_from"] = value
            profile["resolved_to"] = canonical_value
            # 画像附时间线摘要（canonical 成员全部时序边）
            timeline: list[dict[str, Any]] = []
            for m in profile["members"]:
                timeline.extend(graph.get_entity_timeline(m["etype"],
                                                          m["value"]))
            timeline.sort(key=lambda t: t["ts"])
            profile["timeline"] = timeline
            profile["ok"] = True
        return profile

    @staticmethod
    def _guess_etype(graph: IntelGraph, value: str) -> str:
        """intel_query 未给 etype 时按 value 唯一命中猜测（多型命中则报错）。"""
        # 按稳定 id 逐型探测（存储展示值与规范化值不同形，不能 WHERE value=?）
        etypes = [etype for etype in ("actor", "tool", "infra", "indicator")
                  if graph.conn.execute(
                      "SELECT 1 FROM intel_entity WHERE id=?",
                      (entity_id(etype, str(value or "")),)).fetchone()]
        if len(etypes) == 1:
            return etypes[0]
        if not etypes:
            return "indicator"  # 无记录时给默认型，让后续报"实体不存在"
        raise IntelGraphError(
            f"value {value!r} 命中多 etype {etypes}，请显式传 etype")
