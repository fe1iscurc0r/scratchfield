"""GraphRAG 向量索引（SPEC-02 Phase 2 任务 2.2：bge-small-zh 接图谱节点）。

- 复用 rag.embedding_engine.EmbeddingEngine（bge-small-zh-v1.5 单例），
  不另起模型实例；模型不可用时 encode 返回 None → 索引标记降级，
  查询侧退回词元重合打分（能跑通，分数字段如实标 fallback）。
- 向量与节点 id 落盘：vectors.npz + node_ids.json（随 graph.json 同目录）。
"""
from __future__ import annotations

import json
from typing import Any

import numpy as np

from .store import GraphStore

_MAX_TEXT_CHARS = 400  # 每节嵌入文本截断长度（标题 + 正文头部，够表达主题）


def _embed_texts(texts: list[str]) -> np.ndarray | None:
    """走端侧嵌入（卷125 W125-03：本地优先 + LRU 缓存 + 云端回退）；失败返回 None。

    与直接调 `rag.embedding_engine` 的区别：多一层缓存（同样文本不重复计算）与
    本地不可用时的云端回退路径（不会因为本地模型缺文件就整条检索挂掉）。
    """
    if not texts:
        return None
    try:
        from apiserver.local_embedder import embed

        vectors = embed(texts)
        if vectors:
            return np.asarray(vectors, dtype="float32")
    except Exception:  # noqa: BLE001 - 回退到原始引擎
        pass
    try:
        from rag.embedding_engine import get_embedding_engine
        return get_embedding_engine().encode(texts)
    except Exception:
        return None


def build_index(store: GraphStore) -> dict[str, Any]:
    """为全部 section 节点建向量索引（doc 节点不入索引，经 contains 边导航）。"""
    sec_nodes = [n for n in store.nodes.values() if n["type"] == "section"]
    ids = [n["id"] for n in sec_nodes]
    texts = [f"{n['label']}。{n['text'][:_MAX_TEXT_CHARS]}" for n in sec_nodes]

    vectors = _embed_texts(texts) if texts else None
    payload = {"node_ids": ids, "backend": "bge-small-zh-v1.5" if vectors is not None else "token_fallback"}
    (store.dir / "node_ids.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    if vectors is not None:
        np.savez_compressed(store.dir / "vectors.npz", vectors=vectors)
    elif (store.dir / "vectors.npz").exists():
        (store.dir / "vectors.npz").unlink()  # 避免旧向量与新节点 id 错位
    return {"success": True, "indexed": len(ids), "backend": payload["backend"],
            "dim": int(vectors.shape[1]) if vectors is not None else 0}


class VectorIndex:
    """加载态索引：cosine top-k；无向量文件时走词元重合打分。"""

    def __init__(self, store: GraphStore):
        self.store = store
        self.node_ids: list[str] = []
        self.backend = "none"
        self._matrix: np.ndarray | None = None
        ids_path = store.dir / "node_ids.json"
        vec_path = store.dir / "vectors.npz"
        if ids_path.exists():
            payload = json.loads(ids_path.read_text(encoding="utf-8"))
            self.node_ids = payload["node_ids"]
            self.backend = payload.get("backend", "none")
        if vec_path.exists():
            self._matrix = np.load(vec_path)["vectors"]

    def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        from .importer import extract_tokens  # 延迟导入避免循环

        if self._matrix is not None and self.node_ids:
            qv = _embed_texts([query])
            if qv is not None and qv.shape[1] == self._matrix.shape[1]:
                # 矩阵已行归一（引擎侧 normalize），点积即 cosine
                scores = self._matrix @ qv[0]
                order = np.argsort(scores)[::-1][:top_k]
                return [{"node_id": self.node_ids[i], "score": float(scores[i]),
                         "backend": "bge-small-zh-v1.5"} for i in order]
        # 降级：词元重合（Jaccard 变体）
        qt = extract_tokens(query)
        if not qt or not self.node_ids:
            return []
        scored = []
        for nid in self.node_ids:
            node = self.store.nodes.get(nid)
            if not node:
                continue
            nt = extract_tokens(node["label"] + " " + node["text"][:_MAX_TEXT_CHARS])
            inter = len(qt & nt)
            if inter:
                scored.append((inter / len(qt | nt), nid))
        scored.sort(reverse=True)
        return [{"node_id": nid, "score": round(s, 4), "backend": "token_fallback"}
                for s, nid in scored[:top_k]]
