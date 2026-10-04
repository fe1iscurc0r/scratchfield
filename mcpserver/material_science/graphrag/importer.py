"""GraphRAG 图谱导入（SPEC-02 Phase 2 任务 2.1）。

语料源（全量重建，幂等）：
- vault/**/*.md          用户材料科研笔记（材料库/工艺/表征/项目）
- academic/*/MODEL_INTERFACE.md  16 项目调用接口文档（Phase 1 产物）

建图规则：
- 每个 md → doc 节点；按标题（#/##/###）切段 → section 节点（存原文）
- doc -contains-> section
- section 之间共享 ≥2 个重要词元（英文词 ≥2 字母 / CJK 二元组，去停用词）
  → mentions 边（图谱路径的骨架，支撑"材料→制备方法"这类跨文档导航）
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .store import GraphStore

REPO_ROOT = Path(__file__).resolve().parents[3]

# CJK 二元组停用词（高频无实义组合）
_CJK_STOP = {
    "的是", "是一", "一个", "可以", "进行", "通过", "使用", "以及", "或者",
    "如果", "但是", "因为", "所以", "这个", "那个", "我们", "他们", "它们",
    "没有", "需要", "包括", "主要", "用于", "相关", "其中", "对于", "根据",
}
_EN_STOP = {"the", "and", "for", "with", "this", "that", "from", "are", "was",
            "not", "you", "can", "use", "using", "will", "has", "have", "its"}

_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+?)\s*$", re.MULTILINE)
_EN_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_\-]{1,}")
_CJK_RUN_RE = re.compile(r"[\u4e00-\u9fff]{2,}")


def split_sections(text: str) -> list[dict[str, str]]:
    """按标题切段：[{heading, level, text}]。无标题时整篇一段。"""
    matches = list(_HEADING_RE.finditer(text))
    if not matches:
        return [{"heading": "(全文)", "level": 0, "text": text.strip()}]
    sections = []
    if matches[0].start() > 0 and text[:matches[0].start()].strip():
        sections.append({"heading": "(前言)", "level": 0,
                         "text": text[:matches[0].start()].strip()})
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[m.end():end].strip()
        if body:
            sections.append({"heading": m.group(2), "level": len(m.group(1)),
                             "text": body})
    return sections


def extract_tokens(text: str) -> set[str]:
    """重要词元：英文词（小写，去停用词）+ CJK 二元组（去停用词）。"""
    tokens = set()
    for w in _EN_WORD_RE.findall(text):
        wl = w.lower()
        if len(wl) >= 2 and wl not in _EN_STOP:
            tokens.add(wl)
    for run in _CJK_RUN_RE.findall(text):
        for i in range(len(run) - 1):
            bg = run[i:i + 2]
            if bg not in _CJK_STOP:
                tokens.add(bg)
    return tokens


def _iter_md_files(root: Path, pattern: str) -> list[Path]:
    return sorted(p for p in root.glob(pattern) if p.is_file())


def import_corpus(store: GraphStore, vault_dir: str | Path | None = None,
                  academic_dir: str | Path | None = None,
                  min_shared_tokens: int = 2) -> dict[str, Any]:
    """全量重建图谱：清空 store → 导入两类语料 → 共现边 → 社区。"""
    vault_dir = Path(vault_dir) if vault_dir else REPO_ROOT / "vault"
    academic_dir = Path(academic_dir) if academic_dir else REPO_ROOT / "academic"

    store.nodes.clear()
    store.edges.clear()
    store.communities.clear()

    files = [(p, "vault") for p in _iter_md_files(vault_dir, "**/*.md")]
    files += [(p, "academic") for p in _iter_md_files(academic_dir, "*/MODEL_INTERFACE.md")]

    section_tokens: dict[str, set[str]] = {}
    doc_count = 0
    for path, corpus in files:
        rel = path.relative_to(path.parents[2] if corpus == "academic" else vault_dir)
        doc_id = f"doc:{corpus}:{rel.as_posix()}"
        text = path.read_text(encoding="utf-8", errors="replace")
        store.add_node(doc_id, label=path.stem, node_type="doc",
                       source=str(path), text=text[:200])
        doc_count += 1
        for i, sec in enumerate(split_sections(text)):
            sec_id = f"{doc_id}#s{i}"
            heading = sec["heading"] if sec["level"] > 0 else f"{path.stem}·{sec['heading']}"
            store.add_node(sec_id, label=heading, node_type="section",
                           source=str(path), text=sec["text"])
            store.add_edge(doc_id, sec_id, "contains")
            section_tokens[sec_id] = extract_tokens(
                (heading + " " if sec["level"] > 0 else "") + sec["text"])

    # 共现边：共享 ≥min_shared_tokens 个词元的段对（量级 <300 段，O(n²) 可接受）
    sec_ids = list(section_tokens)
    edge_count = 0
    for i in range(len(sec_ids)):
        ti = section_tokens[sec_ids[i]]
        for j in range(i + 1, len(sec_ids)):
            shared = ti & section_tokens[sec_ids[j]]
            if len(shared) >= min_shared_tokens:
                store.add_edge(sec_ids[i], sec_ids[j], "mentions")
                edge_count += 1

    n_comm = store.compute_communities()
    store.save()
    return {"success": True, "docs": doc_count,
            "nodes": len(store.nodes), "edges": len(store.edges),
            "mentions_edges": edge_count, "communities": n_comm,
            "graph_path": str(store.graph_path)}
