"""graphify MCP 桥 — GraphifyBridge（agent-manifest.json entryPoint）。

接入方式与 hamlog_adapter 同构（manifest 型，scan_and_register_mcp_agents
自动注册，mcp_manager.unified_call 走 handle_handoff 分发）。

工具（6 个）：
- graphify_build(path): 代码/文献目录 → <path>/graphify-out/graph.json
  （内置确定性 AST 管线；上游 graphifyy CLI 的产出可 graphify_import）
- graphify_import(graph_json): 导入上游 CLI/其他机器产出的 graph.json
- graphify_query(question, top_k): 向量检索+关键词 RRF 融合，
  返回 matches/relations/citations（每条带 citation 字段）
- graphify_path(a, b): 两节点最短通路（每跳带边解释）
- graphify_explain(node): 节点详情 + 全部邻边（含置信标签）
- graphify_status(): 图谱状态（活跃路径/规模/引擎/上游 CLI 可用性）

fail-fast 原则：目录不存在 / 图谱未建 / 节点缺失一律 GraphifyError →
{"status": "error", ...}，绝不静默空返回。
"""
from __future__ import annotations

import json
import logging
import os
import shutil
from pathlib import Path
from typing import Any

from mcpserver.adapters.graphify.engine import (
    EXTRACTED,
    GraphifyError,
    GraphifyGraph,
    extract_corpus,
)

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_GRAPH_ENV = "GRAPHIFY_GRAPH_JSON"


class GraphifyBridge:
    """graphify 知识图谱 MCP 服务实例。"""

    def __init__(self) -> None:
        self._graph: GraphifyGraph | None = None
        self._graph_path: str | None = None
        self._engine: str | None = None

    # ---- 图谱定位 ----
    def _active_graph(self, candidate: str | None = None) -> GraphifyGraph:
        """取活跃图谱：显式路径 > 上次加载 > 环境变量 > 仓库默认输出位。"""
        if candidate:
            self._graph = GraphifyGraph.load(candidate)
            self._graph_path = self._graph.source_path
            self._engine = self._engine or "imported"
            return self._graph
        if self._graph is not None:
            return self._graph
        env_path = os.environ.get(_DEFAULT_GRAPH_ENV, "").strip()
        if env_path:
            self._graph = GraphifyGraph.load(env_path)
            self._graph_path = self._graph.source_path
            self._engine = "env"
            return self._graph
        default = _REPO_ROOT / "graphify-out" / "graph.json"
        if default.is_file():
            self._graph = GraphifyGraph.load(default)
            self._graph_path = self._graph.source_path
            self._engine = "repo-default"
            return self._graph
        raise GraphifyError(
            "尚未加载知识图谱：先 graphify_build(path) 生成，或 "
            f"graphify_import(graph_json) 导入上游产出（或设 {_DEFAULT_GRAPH_ENV}）")

    @staticmethod
    def _upstream_cli_available() -> bool:
        """上游 graphifyy CLI 是否在 PATH（仅作能力提示，不阻塞内置管线）。"""
        return shutil.which("graphify") is not None

    # ---- 工具实现 ----
    def tool_build(self, path: str) -> dict[str, Any]:
        result = extract_corpus(path)
        # 建完即挂载为活跃图谱，后续 query/path/explain 直接可查
        self._graph = GraphifyGraph.load(result["graph_json"])
        self._graph_path = result["graph_json"]
        self._engine = "builtin-ast"
        result["upstream_cli"] = self._upstream_cli_available()
        result["note"] = (
            "内置确定性管线覆盖 .py/.md/.txt；PDF/图片/多模态概念需上游 "
            "graphifyy CLI + Claude Code（pip install graphifyy，产出可 "
            "graphify_import 回本引擎查询）")
        return result

    def tool_import(self, graph_json: str) -> dict[str, Any]:
        g = self._active_graph(graph_json)
        self._engine = "imported"
        return {
            "ok": True,
            "graph_json": g.source_path,
            "nodes": len(g.node_by_id),
            "links": len(g.links),
            "engine": self._engine,
        }

    def tool_query(self, question: str, top_k: int = 8) -> dict[str, Any]:
        g = self._active_graph()
        result = g.query(question, top_k=top_k)
        result["graph_json"] = g.source_path
        result["engine"] = self._engine
        return result

    def tool_path(self, a: str, b: str) -> dict[str, Any]:
        g = self._active_graph()
        result = g.shortest_path(a, b)
        result["graph_json"] = g.source_path
        return result

    def tool_explain(self, node: str) -> dict[str, Any]:
        g = self._active_graph()
        result = g.explain(node)
        result["graph_json"] = g.source_path
        return result

    def tool_status(self) -> dict[str, Any]:
        loaded = self._graph is not None
        return {
            "ok": True,
            "loaded": loaded,
            "graph_json": self._graph_path,
            "engine": self._engine,
            "nodes": len(self._graph.node_by_id) if loaded else 0,
            "links": len(self._graph.links) if loaded else 0,
            "upstream_cli": self._upstream_cli_available(),
            "upstream_repo": "https://github.com/Graphify-Labs/graphify",
            "upstream_license": "Apache-2.0",
            "env_graph": os.environ.get(_DEFAULT_GRAPH_ENV, ""),
        }

    # ---- MCP 分发 ----
    async def handle_handoff(self, tool_call: dict[str, Any]) -> str:
        """unified_call 入口：按 tool_name 分发，参数从 tool_call 平铺取。"""
        tool_name = str(tool_call.get("tool_name") or "").strip()
        params = {k: v for k, v in tool_call.items()
                  if k not in ("service_name", "tool_name", "message",
                               "session_id", "callback_url")}
        try:
            if tool_name == "graphify_build":
                result = self.tool_build(str(params.get("path", "")))
            elif tool_name == "graphify_import":
                result = self.tool_import(str(params.get("graph_json", "")))
            elif tool_name == "graphify_query":
                result = self.tool_query(
                    str(params.get("question") or ""),
                    top_k=int(params.get("top_k", 8) or 8))
            elif tool_name == "graphify_path":
                result = self.tool_path(str(params.get("a", "")),
                                        str(params.get("b", "")))
            elif tool_name == "graphify_explain":
                result = self.tool_explain(str(params.get("node", "")))
            elif tool_name == "graphify_status":
                result = self.tool_status()
            else:
                raise GraphifyError(
                    f"graphify 不支持的工具: {tool_name!r}（可用: build/import/"
                    "query/path/explain/status，前缀 graphify_）")
        except GraphifyError as e:
            logger.warning("[graphify] %s 失败: %s", tool_name or "(no-tool)", e)
            return json.dumps({"status": "error", "service": "graphify",
                               "tool": tool_name, "error": str(e)},
                              ensure_ascii=False)
        except Exception as e:  # 兜底：不让单次调用炸掉整个 MCP 服务
            logger.exception("[graphify] %s 未预期异常", tool_name)
            return json.dumps({"status": "error", "service": "graphify",
                               "tool": tool_name,
                               "error": f"未预期异常: {e}"},
                              ensure_ascii=False)
        return json.dumps({"status": "ok", "service": "graphify",
                           "tool": tool_name, "result": result},
                          ensure_ascii=False)


# 供测试/其他模块直接引用的置信常量
assert EXTRACTED == "EXTRACTED"
