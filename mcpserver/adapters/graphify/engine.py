"""graphify 知识图谱引擎 — 离线生成 + 向量检索 + 引用溯源。

设计约束（对齐 W-03 工单）：
- 零第三方依赖：纯标准库（ast/json/re/math/pathlib/collections），
  pytest 与 MCP 注册不因缺 graphifyy/Claude Code 而挂。
- 图谱生成管线：Python 源码走 ast（函数/类/调用/导入，确定性），
  Markdown 走标题层级 + 文内链接，纯文本只建文件节点。
  上游 CLI（pip install graphifyy，需 Claude Code）支持 PDF/图片/多模态，
  本引擎不重复造那部分——上游产出的 graph.json 可 graphify_import 直接查。
- 存储：graph.json 单文件，schema 对齐上游 worked/mixed-corpus/graph.json：
    nodes: {id, label, file_type, source_file, source_location, community}
    links: {relation, confidence(EXTRACTED|INFERRED), source_file,
            source_location, weight, source, target}
- 查询 API：TF-IDF 稀疏向量余弦（"向量检索"路）+ 关键词包含路，
  两路排名 RRF 融合（k=60），返回 matches/relations/citations，
  每条命中携带 citation 字段（grep 可断言 '"citation"'）。
"""
from __future__ import annotations

import ast
import json
import math
import re
from collections import Counter, deque
from pathlib import Path
from typing import Any

EXTRACTED = "EXTRACTED"
INFERRED = "INFERRED"

# 生成管线跳过的目录（graphify-out 是自家输出，绝不能反吞进图谱）
SKIP_DIRS = {"graphify-out", "__pycache__", ".git", ".venv", "node_modules",
             ".mypy_cache", ".pytest_cache", "cache", "build", "dist"}
CODE_EXTS = {".py"}
DOC_EXTS = {".md", ".markdown", ".txt"}
MAX_FILES = 2000          # 单次生成上限，防误扫巨型目录
MAX_TOKENS_PER_DOC = 512  # TF-IDF 每节点截断，防超长文件拖垮索引

_STOPWORDS = {
    "the", "a", "an", "of", "in", "on", "to", "and", "or", "is", "are",
    "for", "with", "how", "what", "why", "does", "do", "这个", "那个",
    "什么", "怎么", "如何", "哪些", "哪里", "为什么", "请", "一下",
}

_CAMEL_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")
_WORD_RE = re.compile(r"[A-Za-z0-9_\u4e00-\u9fff]+")


def tokenize(text: str) -> list[str]:
    """分词：camelCase/snake_case 二次拆分 → 小写 → 去停用词。"""
    tokens: list[str] = []
    for raw in _WORD_RE.findall(text or ""):
        for part in raw.split("_"):
            if not part:
                continue
            for leaf in _CAMEL_RE.split(part):
                leaf = leaf.lower().strip("_")
                if len(leaf) >= 2 and leaf not in _STOPWORDS:
                    tokens.append(leaf)
    return tokens


class GraphifyError(RuntimeError):
    """图谱不可用 / 查询失败统一异常（fail-fast，不静默空返回）。"""


# =====================================================================
# 1. 图谱生成管线（离线，确定性）
# =====================================================================
class CorpusExtractor:
    """代码/文献目录 → graph.json（上游 schema）。

    与上游 CLI 的分工：上游（graphifyy + Claude Code）吃 PDF/图片/多模态概念，
    需 API key；本提取器纯本地确定性 AST，覆盖 .py/.md/.txt，
    community 用"文件级"兜底分配（上游为 Leiden 社区检测）。
    """

    def __init__(self) -> None:
        self.nodes: list[dict[str, Any]] = []
        self.links: list[dict[str, Any]] = []
        self._used_ids: set[str] = set()
        self._func_index: dict[str, str] = {}  # 全局函数名 → node_id（跨文件调用解析）
        self._pending_calls: list[tuple[str, list[str]]] = []  # (caller_id, callee_names)
        self._import_index: dict[str, str] = {}  # 模块名/stem → file node_id
        self._pending_imports: list[tuple[str, str]] = []  # (importer_id, module)
        self._community = 0

    # ---- 公共 ID/节点工具 ----
    def _uniq_id(self, base: str) -> str:
        """生成不冲突的节点 id（上游惯例：file=stem，函数=stem_name）。"""
        cand, n = base, 1
        while cand in self._used_ids:
            n += 1
            cand = f"{base}_{n}"
        self._used_ids.add(cand)
        return cand

    def _add_node(self, *, base_id: str, label: str, file_type: str,
                  source_file: str, source_location: str) -> str:
        node_id = self._uniq_id(base_id)
        self.nodes.append({
            "label": label[:120],
            "file_type": file_type,
            "source_file": source_file,
            "source_location": source_location,
            "id": node_id,
            "community": self._community,
        })
        return node_id

    def _add_link(self, *, source: str, target: str, relation: str,
                  confidence: str, source_file: str, source_location: str,
                  weight: float = 1.0) -> None:
        if source == target:
            return
        self.links.append({
            "relation": relation,
            "confidence": confidence,
            "source_file": source_file,
            "source_location": source_location,
            "weight": weight,
            "source": source,
            "target": target,
        })

    # ---- 入口 ----
    def extract(self, root: Path) -> dict[str, Any]:
        root = root.resolve()
        if not root.is_dir():
            raise GraphifyError(f"待建图谱的目录不存在或不是目录: {root}")
        files = [p for p in sorted(root.rglob("*"))
                 if p.is_file() and not (SKIP_DIRS & set(p.parts))
                 and p.suffix.lower() in (CODE_EXTS | DOC_EXTS)]
        if not files:
            raise GraphifyError(f"目录内没有可解析的 .py/.md/.txt 文件: {root}")
        if len(files) > MAX_FILES:
            files = files[:MAX_FILES]

        for path in files:
            rel = path.relative_to(root).as_posix()
            self._community += 1
            if path.suffix.lower() in CODE_EXTS:
                self._extract_py(path, rel)
            else:
                self._extract_doc(path, rel)

        # 第二遍：跨文件调用/导入解析（依赖全量 _func_index/_import_index）
        for caller_id, callees in self._pending_calls:
            for name in callees:
                callee_id = self._func_index.get(name)
                if callee_id and callee_id != caller_id:
                    self._add_link(source=caller_id, target=callee_id,
                                   relation="calls", confidence=INFERRED,
                                   source_file="", source_location="L?",
                                   weight=0.6)
        for importer_id, module in self._pending_imports:
            target_id = self._import_index.get(module)
            if target_id and target_id != importer_id:
                self._add_link(source=importer_id, target=target_id,
                               relation="imports", confidence=EXTRACTED,
                               source_file="", source_location="L?", weight=0.8)

        # 去重（同一对节点同关系只留一条，权重取最大）
        seen: dict[tuple[str, str, str], dict[str, Any]] = {}
        for link in self.links:
            key = (link["source"], link["target"], link["relation"])
            if key not in seen or link["weight"] > seen[key]["weight"]:
                seen[key] = link
        self.links = list(seen.values())
        return {
            "directed": False,
            "multigraph": False,
            "graph": {},
            "nodes": self.nodes,
            "links": self.links,
        }

    # ---- Python：AST ----
    def _extract_py(self, path: Path, rel: str) -> None:
        stem = re.sub(r"[^0-9A-Za-z_]", "_", path.stem) or "module"
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError as e:
            # 解析失败仍保留文件节点（标注 unparseable），不让单文件炸整库
            file_id = self._add_node(base_id=stem, label=path.name,
                                     file_type="code", source_file=rel,
                                     source_location=f"L{e.lineno or 1}")
            return
        file_id = self._add_node(base_id=stem, label=path.name,
                                 file_type="code", source_file=rel,
                                 source_location="L1")
        self._import_index.setdefault(stem, file_id)

        def walk_body(body: list[ast.stmt], owner_id: str, prefix: str,
                      class_stack: tuple[str, ...] = ()) -> None:
            for stmt in body:
                if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    node_id = self._add_node(
                        base_id=f"{stem}_{stmt.name}", label=f"{stmt.name}()",
                        file_type="code", source_file=rel,
                        source_location=f"L{stmt.lineno}")
                    self._add_link(source=owner_id, target=node_id,
                                   relation="contains", confidence=EXTRACTED,
                                   source_file=rel,
                                   source_location=f"L{stmt.lineno}")
                    # 类方法挂全局函数索引时带类前缀优先，避免同名遮蔽
                    qualname = ".".join(class_stack + (stmt.name,))
                    self._func_index.setdefault(stmt.name, node_id)
                    self._func_index.setdefault(qualname, node_id)
                    self._pending_calls.append((node_id, self._collect_calls(stmt)))
                    walk_body(stmt.body, node_id, prefix)
                elif isinstance(stmt, ast.ClassDef):
                    node_id = self._add_node(
                        base_id=f"{stem}_{stmt.name}",
                        label=f"class {stmt.name}", file_type="code",
                        source_file=rel, source_location=f"L{stmt.lineno}")
                    self._add_link(source=owner_id, target=node_id,
                                   relation="contains", confidence=EXTRACTED,
                                   source_file=rel,
                                   source_location=f"L{stmt.lineno}")
                    walk_body(stmt.body, node_id, prefix, class_stack + (stmt.name,))
                elif isinstance(stmt, (ast.Import, ast.ImportFrom)):
                    mod = getattr(stmt, "module", None) or ""
                    names = [mod] if mod else []
                    for alias in stmt.names:
                        names.append(alias.name)
                        names.append(alias.name.split(".")[-1])
                    for name in names:
                        if name:
                            self._pending_imports.append((file_id, name))

        walk_body(tree.body, file_id, stem)

    @staticmethod
    def _collect_calls(func: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
        """收集函数体内所有 Call 的可解析名（Name 优先，Attribute 取末段）。"""
        names: list[str] = []
        for node in ast.walk(func):
            if isinstance(node, ast.Call):
                f = node.func
                if isinstance(f, ast.Name):
                    names.append(f.id)
                elif isinstance(f, ast.Attribute):
                    names.append(f.attr)
        return names

    # ---- Markdown / 纯文本 ----
    def _extract_doc(self, path: Path, rel: str) -> None:
        stem = re.sub(r"[^0-9A-Za-z_]", "_", path.stem) or "doc"
        text = path.read_text(encoding="utf-8", errors="replace")
        file_id = self._add_node(base_id=stem, label=path.name,
                                 file_type="doc", source_file=rel,
                                 source_location="L1")
        heading_re = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$", re.MULTILINE)
        link_re = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
        for idx, match in enumerate(heading_re.finditer(text), start=1):
            lineno = text[:match.start()].count("\n") + 1
            title = match.group(2).strip()
            node_id = self._add_node(base_id=f"{stem}_h{idx}",
                                     label=f"{match.group(1)} {title}",
                                     file_type="doc", source_file=rel,
                                     source_location=f"L{lineno}")
            self._add_link(source=file_id, target=node_id, relation="contains",
                           confidence=EXTRACTED, source_file=rel,
                           source_location=f"L{lineno}")
        # 文内 markdown 链接 → 同库其他文档的 mentions 边
        for target_rel in {m for m in link_re.findall(text)
                           if m.endswith((".md", ".markdown", ".txt"))}:
            target_stem = re.sub(r"[^0-9A-Za-z_]", "_",
                                 Path(target_rel).stem) or "doc"
            self._pending_imports.append((file_id, target_stem))


# =====================================================================
# 2. 查询 API：TF-IDF 向量检索 + 关键词 + RRF 融合 + 引用溯源
# =====================================================================
class GraphifyGraph:
    """加载 graph.json（本引擎或上游 CLI 产出，schema 容错）并回答查询。"""

    def __init__(self, data: dict[str, Any], source_path: str | None = None) -> None:
        nodes = data.get("nodes") or []
        raw_links = (data.get("links") or data.get("edges") or [])
        if not nodes:
            raise GraphifyError("graph.json 缺少 nodes（空图谱无法查询）")
        self.source_path = source_path
        self.node_by_id: dict[str, dict[str, Any]] = {}
        for n in nodes:
            nid = str(n.get("id") or n.get("node_id") or n.get("label") or "")
            if not nid:
                continue
            self.node_by_id[nid] = {
                "id": nid,
                "label": str(n.get("label") or nid),
                "file_type": str(n.get("file_type") or n.get("type") or "unknown"),
                "source_file": str(n.get("source_file") or n.get("file") or ""),
                "source_location": str(n.get("source_location")
                                       or n.get("location") or "L?"),
                "community": n.get("community"),
            }
        self.links: list[dict[str, Any]] = []
        for e in raw_links:
            src = str(e.get("source") or e.get("_src") or "")
            tgt = str(e.get("target") or e.get("_tgt") or "")
            if src == tgt or src not in self.node_by_id \
                    or tgt not in self.node_by_id:
                continue  # 自环/悬空端点不进邻接表
            self.links.append({
                "source": src, "target": tgt,
                "relation": str(e.get("relation") or e.get("type")
                                or "related"),
                "confidence": str(e.get("confidence") or EXTRACTED),
                "source_file": str(e.get("source_file") or ""),
                "source_location": str(e.get("source_location") or "L?"),
                "weight": float(e.get("weight") or 1.0),
            })
        self._build_index()

    # ---- 索引 ----
    def _node_text(self, nid: str) -> str:
        n = self.node_by_id[nid]
        parts = [n["label"], n["label"],  # label 权重 ×2
                 n["source_file"].rsplit("/", 1)[-1].rsplit(".", 1)[0]]
        return " ".join(parts)

    def _build_index(self) -> None:
        self.adj: dict[str, list[tuple[str, dict[str, Any]]]] = {
            nid: [] for nid in self.node_by_id}
        for e in self.links:
            self.adj[e["source"]].append((e["target"], e))
            self.adj[e["target"]].append((e["source"], e))
        # TF-IDF（稀疏向量）：df = 出现该词的节点数
        self.doc_tf: dict[str, Counter] = {}
        df: Counter = Counter()
        for nid in self.node_by_id:
            tf = Counter(tokenize(self._node_text(nid))[:MAX_TOKENS_PER_DOC])
            self.doc_tf[nid] = tf
            for term in tf:
                df[term] += 1
        n_docs = max(len(self.doc_tf), 1)
        self.idf: dict[str, float] = {
            t: math.log((n_docs + 1) / (d + 1)) + 1.0 for t, d in df.items()}
        # 模长缓存，供余弦分母
        self.doc_norm: dict[str, float] = {
            nid: math.sqrt(sum((tf[t] * self.idf.get(t, 0.0)) ** 2
                               for t in tf))
            for nid, tf in self.doc_tf.items()}

    def _vector_rank(self, query: str) -> list[tuple[str, float]]:
        """TF-IDF 余弦相似度排名（向量检索路）。"""
        q_tf = Counter(tokenize(query))
        if not q_tf:
            return []
        q_vec = {t: c * self.idf.get(t, 0.0) for t, c in q_tf.items()}
        q_norm = math.sqrt(sum(v * v for v in q_vec.values())) or 1.0
        scores: list[tuple[str, float]] = []
        for nid, tf in self.doc_tf.items():
            dot = sum(q_vec.get(t, 0.0) * c * self.idf.get(t, 0.0)
                      for t, c in tf.items() if t in q_vec)
            if dot > 0:
                denom = self.doc_norm.get(nid) or 1.0
                scores.append((nid, dot / (q_norm * denom)))
        scores.sort(key=lambda x: (-x[1], x[0]))
        return scores

    def _keyword_rank(self, query: str) -> list[tuple[str, float]]:
        """关键词包含排名（标签/文件名子串命中，带度数微加成）。"""
        terms = [t for t in tokenize(query) if len(t) >= 2]
        if not terms:
            return []
        scores: list[tuple[str, float]] = []
        for nid, n in self.node_by_id.items():
            hay = f"{n['label']} {n['source_file']}".lower()
            hit = sum(1 for t in terms if t in hay)
            if hit:
                scores.append((nid, hit / len(terms)
                               + 0.01 * min(len(self.adj.get(nid, [])), 50)))
        scores.sort(key=lambda x: (-x[1], x[0]))
        return scores

    @staticmethod
    def rrf_fuse(*rank_lists: list[tuple[str, float]], k: int = 60,
                 limit: int = 8) -> list[tuple[str, float]]:
        """多路排名 RRF 融合（k=60 对齐仓内 hybrid_search 惯例）。"""
        fused: dict[str, float] = {}
        for ranking in rank_lists:
            for rank, (nid, _) in enumerate(ranking, start=1):
                fused[nid] = fused.get(nid, 0.0) + 1.0 / (k + rank)
        out = sorted(fused.items(), key=lambda x: (-x[1], x[0]))[:limit]
        return out

    # ---- 引用构造（验收：grep 断言 citation 字段） ----
    def citation_of(self, nid: str, link: dict[str, Any] | None = None) -> dict[str, Any]:
        n = self.node_by_id[nid]
        loc = link["source_location"] if (link and link.get("source_location")
                                          and link["source_location"] != "L?") \
            else n["source_location"]
        src = (link.get("source_file") if link and link.get("source_file")
               else "") or n["source_file"]
        ref = f"{src}:{loc}" if src else loc
        return {
            "citation": ref,
            "source_file": src,
            "source_location": loc,
            "label": n["label"],
            "file_type": n["file_type"],
        }

    # ---- 对外查询 ----
    def query(self, question: str, top_k: int = 8) -> dict[str, Any]:
        if not (question or "").strip():
            raise GraphifyError("graphify_query: question 不能为空")
        top_k = max(1, min(int(top_k or 8), 32))
        vector_rank = self._vector_rank(question)
        keyword_rank = self._keyword_rank(question)
        if not vector_rank and not keyword_rank:
            raise GraphifyError(
                f"图谱中没有任何节点与问题相关：{question!r}（节点数={len(self.node_by_id)}）")
        fused = self.rrf_fuse(vector_rank, keyword_rank, limit=top_k)
        matched_ids = [nid for nid, _ in fused]

        matches, answer_lines = [], []
        for nid, score in fused:
            n = self.node_by_id[nid]
            cit = self.citation_of(nid)
            matches.append({
                "id": nid, "label": n["label"], "score": round(score, 6),
                "community": n["community"],
                "citation": cit,
            })
            answer_lines.append(
                f"- {n['label']}（{n['file_type']}，{cit['citation']}）")

        # 关系面：命中节点两两之间 + 各自最重要的一条邻边
        matched_set = set(matched_ids)
        relations: list[dict[str, Any]] = []
        seen_rel: set[tuple[str, str, str]] = set()

        def _push_link(e: dict[str, Any]) -> None:
            key = (e["source"], e["target"], e["relation"])
            if key in seen_rel:
                return
            seen_rel.add(key)
            relations.append({
                "source": e["source"], "target": e["target"],
                "relation": e["relation"], "confidence": e["confidence"],
                "weight": e["weight"],
                "citation": self.citation_of(e["target"], e),
            })

        for e in self.links:
            if e["source"] in matched_set and e["target"] in matched_set:
                _push_link(e)
        for nid in matched_ids:  # 每命中节点补一条最强邻边，展示图上下文
            best = max(self.adj.get(nid, []),
                       key=lambda pair: pair[1]["weight"], default=None)
            if best:
                _push_link(best[1])
            if len(relations) >= 24:
                break

        answer = (
            f"问题「{question}」在图谱中命中 {len(matches)} 个节点"
            f"（向量检索 + 关键词 RRF 融合）：\n" + "\n".join(answer_lines))
        if relations:
            rel_lines = [
                f"- {self.node_by_id[r['source']]['label']}"
                f" --{r['relation']}({r['confidence']})-->"
                f" {self.node_by_id[r['target']]['label']}"
                for r in relations[:8]
            ]
            answer += "\n相关关系：\n" + "\n".join(rel_lines)
        return {
            "ok": True,
            "question": question,
            "answer": answer,
            "matches": matches,
            "relations": relations,
            "citations": [m["citation"]["citation"] for m in matches],
            "stats": {
                "nodes": len(self.node_by_id),
                "links": len(self.links),
                "vector_hits": len(vector_rank),
                "keyword_hits": len(keyword_rank),
            },
        }

    def shortest_path(self, a: str, b: str) -> dict[str, Any]:
        for nid in (a, b):
            if nid not in self.node_by_id:
                raise GraphifyError(
                    f"节点不存在: {nid}（可用 graphify_explain 查任意节点详情）")
        prev: dict[str, tuple[str, dict[str, Any]] | None] = {a: None}
        queue: deque[str] = deque([a])
        while queue:
            cur = queue.popleft()
            if cur == b:
                break
            for nxt, e in self.adj.get(cur, []):
                if nxt not in prev:
                    prev[nxt] = (cur, e)
                    queue.append(nxt)
        if b not in prev:
            return {"ok": False, "from": a, "to": b,
                    "message": f"两节点间无通路: {a} ↔ {b}"}
        path: list[str] = []
        hop: str | None = b
        while hop is not None:
            path.append(hop)
            entry = prev[hop]
            hop = entry[0] if entry else None
        path.reverse()
        steps = []
        for u, v in zip(path, path[1:]):
            e = prev[v][1]
            steps.append({
                "from": u, "to": v,
                "relation": e["relation"], "confidence": e["confidence"],
                "citation": self.citation_of(v, e),
            })
        return {"ok": True, "from": a, "to": b,
                "path": [self.node_by_id[n]["label"] for n in path],
                "path_ids": path, "steps": steps}

    def explain(self, nid: str) -> dict[str, Any]:
        if nid not in self.node_by_id:
            # 容错：按 label 精确/前缀匹配补一次（用户常拿 label 当 id）
            candidates = [k for k, n in self.node_by_id.items()
                          if n["label"] == nid or k.startswith(nid)]
            if len(candidates) != 1:
                raise GraphifyError(f"节点不存在或歧义: {nid}（候选 {candidates[:5]}）")
            nid = candidates[0]
        n = self.node_by_id[nid]
        in_out = self.adj.get(nid, [])
        edges = [{
            "direction": "out" if e["source"] == nid else "in",
            "peer": e["target"] if e["source"] == nid else e["source"],
            "peer_label": self.node_by_id[
                e["target"] if e["source"] == nid else e["source"]]["label"],
            "relation": e["relation"], "confidence": e["confidence"],
            "weight": e["weight"],
            "citation": self.citation_of(
                e["target"] if e["source"] == nid else e["source"], e),
        } for _, e in in_out]
        return {
            "ok": True,
            "node": {**n, "citation": self.citation_of(nid)},
            "degree": len(edges),
            "edges": edges,
            "stats": {"nodes": len(self.node_by_id),
                      "links": len(self.links)},
        }

    @classmethod
    def load(cls, path: str | Path) -> "GraphifyGraph":
        p = Path(path)
        if not p.is_file():
            raise GraphifyError(f"graph.json 不存在: {p}（先 graphify_build 或"
                                f" graphify_import）")
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise GraphifyError(f"graph.json 解析失败: {p}: {e}") from e
        return cls(data, source_path=str(p))


def extract_corpus(root: str | Path, out_dir: str | Path | None = None) -> dict[str, Any]:
    """生成管线入口：目录 → <root>/graphify-out/graph.json，返回状态摘要。"""
    root = Path(root).resolve()
    extractor = CorpusExtractor()
    graph = extractor.extract(root)
    out_dir = Path(out_dir) if out_dir else (root / "graphify-out")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "graph.json"
    out_path.write_text(json.dumps(graph, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    return {
        "ok": True,
        "graph_json": str(out_path),
        "nodes": len(graph["nodes"]),
        "links": len(graph["links"]),
        "engine": "builtin-ast",
        "files_scanned": extractor._community,
    }
