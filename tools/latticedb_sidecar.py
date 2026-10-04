"""W69-03 融合 · latticedb 记忆 sidecar 适配器（MIT）

把 latticedb（嵌入式单文件图数据库：图遍历 + HNSW 向量 + BM25 全文三合一）融合成
NEKO 记忆 sidecar。有 latticedb 时用真实后端；无 latticedb 时用内存 mock 降级
（诚实标注 degraded=True），对外暴露同一套「三合一查询」接口。

纯 numpy/stdlib（mock 路径），真实后端经 `import latticedb` 接入。
"""
from __future__ import annotations

import numpy as np

try:  # 真实后端（可选依赖）
    import latticedb as _ldb  # type: ignore
    HAS_LATTICEDB = True
except ImportError:  # mock 降级
    _ldb = None
    HAS_LATTICEDB = False

__all__ = ["HAS_LATTICEDB", "LatticeSidecar"]


def _cos(a: np.ndarray, b: np.ndarray) -> float:
    return float(a @ b / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


class LatticeSidecar:
    """记忆 sidecar：图 + 向量 + 全文三合一。"""

    def __init__(self, path: str = ":memory:") -> None:
        self.degraded = not HAS_LATTICEDB
        if HAS_LATTICEDB:
            self._db = _ldb.open(path)  # 真实后端（单文件 / 内存）
        else:
            self._nodes: dict[str, str] = {}       # node_id -> text
            self._vecs: dict[str, np.ndarray] = {}  # node_id -> embedding
            self._edges: dict[str, list[tuple[str, str]]] = {}  # src -> [(rel, dst)]

    # ---------- 写入 ----------

    def add_node(self, node_id: str, text: str, embedding: np.ndarray) -> None:
        if self.degraded:
            self._nodes[node_id] = text
            self._vecs[node_id] = np.asarray(embedding, dtype=float)
        else:
            self._db.add_node(node_id, text=text, embedding=embedding)

    def add_edge(self, src: str, rel: str, dst: str) -> None:
        if self.degraded:
            self._edges.setdefault(src, []).append((rel, dst))
        else:
            self._db.add_edge(src, rel, dst)

    # ---------- 三合一查询 ----------

    def query(self, qvec: np.ndarray, qtext: str, top_k: int = 5) -> list[tuple[str, float]]:
        """图 + 向量 + 全文三合一：返回 (node_id, 综合得分) 降序。"""
        if self.degraded:
            return self._mock_query(qvec, qtext, top_k)
        # 真实 latticedb 走 Cypher（图遍历 + <=> 向量 + @@ 全文）
        rows = self._db.query(qvec=qvec, text=qtext, limit=top_k)
        return [(r["id"], float(r["score"])) for r in rows]

    def _mock_query(self, qvec: np.ndarray, qtext: str, top_k: int) -> list[tuple[str, float]]:
        qvec = np.asarray(qvec, dtype=float)
        # ① 全文命中
        text_hits = [n for n, t in self._nodes.items() if qtext.lower() in t.lower()]
        # ② 向量近邻得分
        scored: dict[str, float] = {}
        for n in text_hits:
            scored[n] = _cos(self._vecs[n], qvec)
        # ③ 图邻接扩展：命中节点的邻居按 0.5× 折扣补入
        for n in list(scored):
            for rel, dst in self._edges.get(n, []):
                if dst in self._nodes and dst not in scored:
                    scored[dst] = 0.5 * scored[n]
        ranked = sorted(scored.items(), key=lambda kv: -kv[1])
        return ranked[:top_k]
