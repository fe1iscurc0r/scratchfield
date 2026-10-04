"""GraphRAG 轻量图存储（SPEC-02 Phase 2 任务 2.1 的落地载体）。

设计取舍：
- 本地 JSON 图（节点/边/社区），不依赖 Neo4j——graphify/Hermes 在云端，
  本模块是"本地可跑的闭环"，导出格式与 graphify 对齐（nodes/edges/communities），
  后续要推云端直接序列化即可。
- 只读查询 + 全量重建导入（语料是笔记库，量级小，重建比增量简单且幂等）。
- 存储默认 %APPDATA%/Lumo/graphrag/graph.json（LUMO_GRAPHRAG_DIR 可覆盖）。
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def default_graph_dir() -> Path:
    base = os.environ.get("LUMO_GRAPHRAG_DIR")
    if base:
        d = Path(base)
    else:
        d = Path(os.environ.get("APPDATA", str(Path.home()))) / "Lumo" / "graphrag"
    d.mkdir(parents=True, exist_ok=True)
    return d


class GraphStore:
    """JSON 持久化的属性图：节点带 label/type/source/text，边带 relation。"""

    def __init__(self, graph_dir: str | Path | None = None):
        self.dir = Path(graph_dir) if graph_dir else default_graph_dir()
        self.dir.mkdir(parents=True, exist_ok=True)
        self.graph_path = self.dir / "graph.json"
        self.nodes: dict[str, dict[str, Any]] = {}
        self.edges: list[dict[str, str]] = []
        self.communities: list[list[str]] = []

    # ---------- 构建 ----------

    def add_node(self, node_id: str, label: str, node_type: str,
                 source: str = "", text: str = "") -> None:
        self.nodes[node_id] = {"id": node_id, "label": label, "type": node_type,
                               "source": source, "text": text}

    def add_edge(self, src: str, dst: str, relation: str) -> None:
        if src in self.nodes and dst in self.nodes and src != dst:
            self.edges.append({"src": src, "dst": dst, "relation": relation})

    def compute_communities(self) -> int:
        """连通分量即社区（笔记图谱边稀疏，无需 Louvain）。"""
        adj: dict[str, set[str]] = {n: set() for n in self.nodes}
        for e in self.edges:
            adj[e["src"]].add(e["dst"])
            adj[e["dst"]].add(e["src"])
        seen: set[str] = set()
        comms: list[list[str]] = []
        for start in adj:
            if start in seen:
                continue
            stack, comp = [start], []
            while stack:
                cur = stack.pop()
                if cur in seen:
                    continue
                seen.add(cur)
                comp.append(cur)
                stack.extend(adj[cur] - seen)
            comms.append(sorted(comp))
        self.communities = comms
        return len(comms)

    def neighbors(self, node_id: str, relation: str | None = None) -> list[dict]:
        out = []
        for e in self.edges:
            if e["src"] == node_id and (relation is None or e["relation"] == relation):
                out.append({"node": e["dst"], "relation": e["relation"], "dir": "out"})
            elif e["dst"] == node_id and (relation is None or e["relation"] == relation):
                out.append({"node": e["src"], "relation": e["relation"], "dir": "in"})
        return out

    def community_of(self, node_id: str) -> list[str]:
        for comm in self.communities:
            if node_id in comm:
                return comm
        return [node_id] if node_id in self.nodes else []

    # ---------- 持久化 ----------

    def save(self) -> None:
        payload = {"nodes": self.nodes, "edges": self.edges,
                   "communities": self.communities}
        self.graph_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    def load(self) -> bool:
        if not self.graph_path.exists():
            return False
        payload = json.loads(self.graph_path.read_text(encoding="utf-8"))
        self.nodes = payload["nodes"]
        self.edges = payload["edges"]
        self.communities = payload.get("communities", [])
        return True

    def stats(self) -> dict[str, Any]:
        types: dict[str, int] = {}
        for n in self.nodes.values():
            types[n["type"]] = types.get(n["type"], 0) + 1
        return {"nodes": len(self.nodes), "edges": len(self.edges),
                "communities": len(self.communities), "node_types": types}
