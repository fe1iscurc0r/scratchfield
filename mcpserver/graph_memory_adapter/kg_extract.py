"""文本 → 知识图谱 实体/关系抽取管线（卷142）。

设计借鉴 rahulnyk/knowledge_graph（MIT · 4060★）的 `helpers/prompts.py` 与
`helpers/df_helpers.py`：概念抽取（固定类别词表 + importance）→ 关系抽取
（Thought 1/2/3 脚手架 → node_1/node_2/edge）→ 归一化（小写 + 去重合并）。
只借 prompt 设计与管线思路，不复制其 Notebook 代码。

与卷139 的分工：
  * 卷139 `engine.py`  = **存储与查询层**（三表 + 递归 CTE）
  * 本模块            = **抽取层**，产出直接喂 `GraphMemory.ingest_entities()`

LLM 通过**可注入的 callable** 提供（`llm(system_prompt, user_prompt) -> str`），
因此单元测试完全离线、零 API key；线上用 `get_default_llm()` 走仓内 LLM 栈。
"""
from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable

PROMPTS_DIR = Path(__file__).with_name("prompts")

# 概念类别白名单（与 prompts/kg-extract-concept.md 一致，抽取结果按此校验）
ALLOWED_CATEGORIES = {
    "event", "concept", "place", "object", "document",
    "organisation", "condition", "misc",
}

# 模糊归一的相似度阈值（仅对 ASCII 名启用；中文靠精确归一，避免误合并）
FUZZY_THRESHOLD = 0.90

LLM = Callable[[str, str], str]


class ExtractError(Exception):
    """抽取管线的显式失败。"""


# ---------------------------------------------------------------- prompt 读取

def load_prompt(name: str) -> dict:
    """从 prompts/*.md 读出 system prompt 与 user 模板。

    文档里 system prompt 放在第一个 ``` 代码块内（见两个 md 的约定）。
    """
    path = PROMPTS_DIR / name
    if not path.exists():
        raise ExtractError(f"prompt 文件不存在: {path}")
    text = path.read_text(encoding="utf-8")
    blocks = re.findall(r"```(?:json)?\n(.*?)```", text, re.S)
    if not blocks:
        raise ExtractError(f"prompt 文件里找不到代码块: {path}")
    system = blocks[0].strip()
    return {"system": system, "path": str(path)}


def _extract_json_array(raw: str) -> list:
    """从模型输出里抠出 JSON 数组（容忍 ``` 围栏与前后废话）。"""
    if not raw:
        raise ExtractError("模型返回空")
    s = raw.strip()
    # 去 markdown 围栏
    fence = re.search(r"```(?:json)?\s*(.*?)```", s, re.S)
    if fence:
        s = fence.group(1).strip()
    # 直接解析
    try:
        data = json.loads(s)
    except json.JSONDecodeError:
        # 退一步：取第一个 [ ... ] 区间
        m = re.search(r"\[.*\]", s, re.S)
        if not m:
            raise ExtractError(f"输出里没有 JSON 数组: {raw[:160]}")
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError as e:
            raise ExtractError(f"JSON 解析失败: {e} | 原文: {raw[:160]}") from e
    if not isinstance(data, list):
        raise ExtractError(f"期望数组，得到 {type(data).__name__}")
    return data


# ---------------------------------------------------------------- 抽取

def extract_concepts(text: str, llm: LLM) -> list[dict]:
    """文本 → 概念列表 [{entity, importance, category, aliases}]。

    类别不在白名单的项归入 misc（不丢弃，避免信息损失）。
    """
    if not str(text or "").strip():
        return []
    prompt = load_prompt("kg-extract-concept.md")
    raw = llm(prompt["system"], f"context: ```{text}```\n\noutput:\n")
    out: list[dict] = []
    for item in _extract_json_array(raw):
        if not isinstance(item, dict):
            continue
        name = str(item.get("entity", "")).strip()
        if not name:
            continue
        cat = str(item.get("category", "")).strip().lower()
        if cat not in ALLOWED_CATEGORIES:
            cat = "misc"
        try:
            imp = int(item.get("importance", 3))
        except (TypeError, ValueError):
            imp = 3
        aliases = item.get("aliases") or []
        if isinstance(aliases, str):
            aliases = [a for a in aliases.split(",") if a.strip()]
        out.append({
            "entity": name,
            "importance": max(1, min(imp, 5)),
            "category": cat,
            "aliases": [str(a).strip() for a in aliases if str(a).strip()],
        })
    return out


def extract_relations(text: str, entities: list[str], llm: LLM) -> list[dict]:
    """文本 + 已知实体 → 关系边 [{node_1, node_2, edge}]。

    端点不在 entities 里的边会被丢弃（上游同款约束：边端点必须来自节点清单）。
    """
    if not str(text or "").strip() or not entities:
        return []
    prompt = load_prompt("kg-extract-relation.md")
    ent_block = " / ".join(entities)
    raw = llm(prompt["system"], f"context: ```{text}```\n\n已知实体清单（边端点必须来自这里）：\n{ent_block}\n\noutput:\n")
    known = {e.strip().lower() for e in entities}
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for item in _extract_json_array(raw):
        if not isinstance(item, dict):
            continue
        a = str(item.get("node_1", "")).strip()
        b = str(item.get("node_2", "")).strip()
        edge = str(item.get("edge", "")).strip()
        if not (a and b and edge):
            continue
        if a.lower() not in known or b.lower() not in known:
            continue  # 端点必须来自实体清单
        key = tuple(sorted((a.lower(), b.lower())))
        if key in seen:
            continue  # 同一对节点只留一条最强边
        seen.add(key)
        out.append({"node_1": a, "node_2": b, "edge": edge})
    return out


def extract_triples(text: str, llm: LLM) -> dict:
    """一步到位：文本 → 可直接喂 `GraphMemory.ingest_entities()` 的结构。

    返回 {"nodes": [...], "edges": [...], "aliases": [...], "source_doc": ""}
    """
    concepts = extract_concepts(text, llm)
    names = [c["entity"] for c in concepts]
    relations = extract_relations(text, names, llm)

    nodes = [{"name": c["entity"], "type": c["category"].upper(),
              "description": f"importance={c['importance']}"} for c in concepts]
    edges = [{"source": r["node_1"], "predicate": r["edge"], "target": r["node_2"]}
             for r in relations]
    aliases = [{"entity": c["entity"], "alias": a}
               for c in concepts for a in c["aliases"]]
    return {"nodes": nodes, "edges": edges, "aliases": aliases}


# ---------------------------------------------------------------- 归一化

def normalise_key(name: str) -> str:
    """归一键：小写 + 去空白 + 去常见标点（与卷139 的 normalise 同源思路）。"""
    s = str(name or "").strip().lower()
    s = re.sub(r"[\s\u3000]+", "", s)
    s = re.sub(r"[（）()\[\]【】:：,，.。\-_/]+", "", s)
    return s


def build_alias_map(names: list[str], fuzzy: bool = True,
                    threshold: float = FUZZY_THRESHOLD) -> dict[str, str]:
    """构造 别名→规范名 映射。

    策略（借鉴上游"同名实体合并"）：
      1. 归一键完全相同的合并（"Lignin NPs" 与 "lignin  nps"）
      2. ASCII 名之间再做模糊匹配（SequenceMatcher ≥ threshold），
         例："ops manager" 与 "opsmanager" / "Ops Managers"
      3. 中文只做精确归一（模糊匹配对中文误合并风险高，不做）
    规范名取该组里**最长**的原名（信息最全的那个）。
    """
    groups: dict[str, list[str]] = {}
    for n in names:
        k = normalise_key(n)
        if k:
            groups.setdefault(k, []).append(str(n).strip())

    canonical: dict[str, str] = {}
    keys = list(groups)
    merged: dict[str, str] = {}  # key → 代表 key

    if fuzzy:
        ascii_keys = [k for k in keys if k.isascii()]
        for i, k1 in enumerate(ascii_keys):
            if k1 in merged:
                continue
            for k2 in ascii_keys[i + 1:]:
                if k2 in merged:
                    continue
                if SequenceMatcher(None, k1, k2).ratio() >= threshold:
                    merged[k2] = k1

    for k, variants in groups.items():
        rep = merged.get(k, k)
        bucket = canonical.setdefault(rep, [])
        bucket.extend(variants)

    out: dict[str, str] = {}
    for rep_key, variants in canonical.items():
        # 规范名：最长原名；并列取字典序最小，保证确定性
        best = sorted(set(variants), key=lambda s: (-len(s), s))[0]
        for v in variants:
            out[v] = best
        out.setdefault(best, best)
    return out


def apply_alias_map(nodes: list[dict], edges: list[dict],
                    alias_map: dict[str, str]) -> tuple[list[dict], list[dict]]:
    """按别名映射把节点名/边端点统一到规范名，并去掉自环。"""
    def canon(n: str) -> str:
        return alias_map.get(str(n).strip(), str(n).strip())

    merged: dict[str, dict] = {}
    for n in nodes:
        name = canon(n.get("name", ""))
        if not name:
            continue
        cur = merged.get(name)
        if cur is None:
            merged[name] = {**n, "name": name}
        else:
            # 描述保留信息更全的那条
            if len(str(n.get("description", ""))) > len(str(cur.get("description", ""))):
                cur["description"] = n.get("description", "")

    new_edges: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for e in edges:
        a, b = canon(e.get("source", "")), canon(e.get("target", ""))
        pred = str(e.get("predicate", "")).strip()
        if not (a and b and pred) or a == b:
            continue
        key = (a, b, pred)
        if key in seen:
            continue
        seen.add(key)
        new_edges.append({"source": a, "predicate": pred, "target": b})
    return list(merged.values()), new_edges


# ---------------------------------------------------------------- 默认 LLM

def get_default_llm() -> LLM:
    """仓内 LLM 栈的适配器（惰性导入；无可用栈时报错而非静默降级）。"""
    try:
        from apiserver.llm_service import get_llm_service  # type: ignore

        service = get_llm_service()
    except Exception as e:  # pragma: no cover - 取决于运行环境
        raise ExtractError(f"仓内 LLM 栈不可用（请显式注入 llm 参数）: {e}") from e

    def _call(system: str, user: str) -> str:
        # llm_service 的同步单轮接口（不同版本命名不一，做兼容探测）
        for meth in ("chat_sync", "complete", "chat"):
            fn = getattr(service, meth, None)
            if callable(fn):
                return str(fn(system=system, user=user))
        raise ExtractError("llm_service 上没有可用的同步单轮接口")

    return _call
