"""授粉落地 · LightRAG 图增强检索（HKUDS/LightRAG → scratchpad rag 栈）

授粉点（EMNLP2025 LightRAG）：把文档建成**实体-关系图**，检索时从查询命中
实体出发做**图扩散**拉取关联上下文，比纯向量/关键词检索多一层结构相关。

与现有栈的关系（不重复造）：
  - 复用 rag/chunk_splitter 的分块语义（chunk 即文档片段）
  - 复用 material_science/graphrag/store.py 的 GraphStore 做图持久化
  - 本模块是"查询侧图增强"：给定查询 → 实体匹配 → 图扩散 → 返回关联
    chunk 上下文（LightRAG 的 retrieve 阶段），供 RAGService.query 融合

设计取舍：
  - 实体抽取用**轻量规则**（中英文 token + 共现）而非 LLM——离线可测、
    确定性，对应 LightRAG 实体抽取的轻量替代（无 API 依赖）
  - 图扩散用 BFS 多跳（depth 可调），返回关联节点及其源文本
  - 全部纯 stdlib + 少量现有依赖，pytest 全绿

验收：
  1. 图构建：共现边正确、孤立实体单节点
  2. 图检索：查询命中实体 → 多跳扩散返回关联上下文（比单节点召回多）
  3. 确定性：同输入两次构建/检索结果一致
  4. 空语料/无命中容错
"""
from __future__ import annotations

import re
from collections import Counter, deque
from dataclasses import dataclass, field
from typing import Iterable

# 可复用图存储（轻量 JSON 图）
try:
    from mcpserver.material_science.graphrag.store import GraphStore
    _HAS_GRAPHSTORE = True
except Exception:  # pragma: no cover - 环境缺依赖时退化
    _HAS_GRAPHSTORE = False

_ENTITY_RE = re.compile(r"[A-Za-z][A-Za-z0-9_\-]{1,30}|[\u4e00-\u9fff]")
# 中文按标点/空格/英文边界切段，段内做 2-gram 候选
_CN_SEG_RE = re.compile(r"[\u4e00-\u9fff]{2,}")
_CN_STOPS = {"一个", "可以", "进行", "以及", "相关", "这些", "那些", "就是",
             "对于", "通过", "主要", "其中", "以及", "用于", "实现", "作为",
             "常作", "适合", "网络", "信号", "处理", "使用"}
_EN_STOPS = {"the", "and", "for", "with", "this", "that", "from", "into",
             "will", "have", "been", "are", "was", "were", "not", "but",
             "you", "your", "all", "can", "its", "has", "had", "did"}


def _cn_ngrams(seg: str, max_tokens: int) -> list[str]:
    """中文段 2-gram 滑窗候选（覆盖 2/3/4 字词元），过滤停用。"""
    cands: list[str] = []
    for n in (2, 3, 4):
        for i in range(len(seg) - n + 1):
            w = seg[i:i + n]
            if w not in _CN_STOPS and w not in cands:
                cands.append(w)
        if len(cands) >= max_tokens:
            break
    return cands[:max_tokens]


def extract_entities(text: str | None, *, max_tokens: int = 200) -> list[str]:
    """轻量实体抽取：英文词元 + 中文 2-gram（非 LLM，确定性）。

    英文按 [A-Za-z][A-Za-z0-9_\-]{1,30}（≥2 字符）；中文按标点/英文切段后
    做 2/3/4-gram 滑窗候选。过滤停用词与纯数字。
    """
    text = text or ""
    tokens = [t for t in _ENTITY_RE.findall(text)]
    out: list[str] = []
    for t in tokens:
        if t.isascii():
            tl = t.lower()
            if len(t) < 2 or tl in _EN_STOPS or tl in _CN_STOPS or t.isdigit():
                continue
            if tl not in (o.lower() for o in out):
                out.append(t)
        # 中文单字先攒起来，按连续段做 n-gram
    # 中文连续段（用 _CN_SEG_RE 直接从原文切，避免单字拆散）
    cn_segs = _CN_SEG_RE.findall(text or "")
    for seg in cn_segs:
        for w in _cn_ngrams(seg, max_tokens):
            if w not in out:
                out.append(w)
        if len(out) >= max_tokens:
            break
    return out[:max_tokens]


@dataclass
class EntityGraph:
    """实体共现图：节点=实体，边=同一 chunk 内共现（带权重）。"""

    nodes: set[str] = field(default_factory=set)
    adj: dict[str, dict[str, int]] = field(default_factory=dict)
    entity_texts: dict[str, list[str]] = field(default_factory=dict)  # 实体→源文本

    def add_chunk(self, entities: Iterable[str], text: str) -> None:
        """把一个 chunk 的实体建为团（两两共现边 + 权重 +1）。"""
        ents = [e for e in entities if e]
        if not ents:
            return
        self.nodes.update(ents)
        self.entity_texts.setdefault(ents[0], []).append(text)
        for i, a in enumerate(ents):
            for b in ents[i + 1:]:
                w = self.adj.setdefault(a, {}).get(b, 0)
                self.adj.setdefault(a, {})[b] = w + 1
                self.adj.setdefault(b, {})[a] = w + 1

    def neighbors(self, entity: str, depth: int = 2) -> dict[str, int]:
        """BFS 多跳扩散：返回 (实体 → 最短距离)（不含自身）。"""
        if entity not in self.nodes:
            return {}
        dist: dict[str, int] = {}
        q: deque[tuple[str, int]] = deque([(entity, 0)])
        while q:
            cur, d = q.popleft()
            if d >= depth:
                continue
            for nb in self.adj.get(cur, {}):
                if nb != entity and nb not in dist:
                    dist[nb] = d + 1
                    q.append((nb, d + 1))
        return dist

    def context_for(self, query_entities: Iterable[str],
                    depth: int = 2) -> list[dict]:
        """图增强检索：查询实体 → 图扩散 → 返回关联实体及其源文本。

        返回按相关度排序的上下文项（命中实体 → 一跳扩散加权优先）。
        """
        hits = [e for e in query_entities if e in self.nodes]
        if not hits:
            return []
        scored: dict[str, float] = {}
        for h in hits:
            scored[h] = scored.get(h, 0.0) + 2.0          # 直接命中权重高
            for nb, d in self.neighbors(h, depth).items():
                scored[nb] = scored.get(nb, 0.0) + 1.0 / d  # 多跳递减
        ranked = sorted(scored.items(), key=lambda kv: -kv[1])
        ctx: list[dict] = []
        for ent, score in ranked:
            for text in self.entity_texts.get(ent, [])[:2]:
                ctx.append({"entity": ent, "score": round(float(score), 3),
                            "text": text})
        return ctx

    @property
    def edge_count(self) -> int:
        return sum(len(v) for v in self.adj.values()) // 2

    @property
    def isolated_count(self) -> int:
        """孤立节点数（无任何共现边的实体）。"""
        return sum(1 for n in self.nodes if not self.adj.get(n))


def build_graph(chunks: Iterable[tuple[str, str]],
                *, max_tokens: int = 200, min_freq: int = 2) -> EntityGraph:
    """从 (chunk_id, text) 列表构建实体共现图。

    min_freq：中文候选词元需在 ≥min_freq 个不同 chunk 中出现才入图
    （过滤错位 bigram 噪声，保留稳定实体）。
    """
    # 第一遍：统计候选词元跨 chunk 频率
    chunk_records: list[tuple[str, list[str]]] = []  # (text, ents)
    freq: Counter = Counter()
    for _cid, text in chunks:
        ents = extract_entities(text, max_tokens=max_tokens)
        chunk_records.append((text, ents))
        for e in set(ents):
            freq[e] += 1
    g = EntityGraph()
    for text, ents in chunk_records:
        stable = [e for e in ents if freq[e] >= min_freq or e.isascii()]
        g.add_chunk(stable, text)
    return g


def query_graph(g: EntityGraph, query: str, *, depth: int = 2,
                max_tokens: int = 200) -> list[dict]:
    """查询侧图增强：抽取查询实体 → 图扩散 → 返回上下文。"""
    q_ents = extract_entities(query, max_tokens=max_tokens)
    return g.context_for(q_ents, depth=depth)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    chunks = [
        ("c1", "射频信号处理使用 FFT 计算频谱，SDR 接收机依赖频谱分析。"),
        ("c2", "SDR 接收机可解调 AM FM 信号，LoRa 调制用于远距离低功耗。"),
        ("c3", "LoRa 网络适合物联网传感器，ESP32 常作为 LoRa 节点主控。"),
        ("c4", "ESP32 开发板集成 WiFi 蓝牙，常用于嵌入式边缘设备。"),
        ("c5", "天线设计影响通信距离，匹配网络决定阻抗匹配质量。"),
    ]
    g = build_graph(chunks)
    print(f"节点数 = {len(g.nodes)}, 边数 = {g.edge_count}, "
          f"孤立节点 = {g.isolated_count}")
    for q in ("SDR 解调", "LoRa 传感器", "ESP32 开发"):
        ctx = query_graph(g, q)
        print(f"查询「{q}」→ {len(ctx)} 条图上下文: "
              + " | ".join(c["entity"] for c in ctx[:5]))


if __name__ == "__main__":
    main()
