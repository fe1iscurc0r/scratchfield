"""skill 语义重叠检测（纯 stdlib · TF-IDF + cosine 基线，无 LLM/无 sklearn）。

授粉来源：NVIDIA/SkillEvaluator（Apache-2.0 ★399）的「语义重叠检测」设计思想，
独立实现。目的：给 skill_gate 质量门补一层「语义重叠」——新 skill 与已有 skill
语义高度重叠时，产出「可能重复 / 建议合并」告警，避免技能库重复膨胀。

实现纪律（授粉）：
- 纯 Python 标准库（math/re），不引新依赖；不调用 LLM API，保证离线可跑。
- 只做「检测 + 告警建议」，不修改/覆盖 skill_gate 现有核心（对接由调用方决定）。
- 中文 + 英文混合文本：ASCII 词 token + CJK 单字 + CJK 相邻双字组，兼顾词粒度。
"""
from __future__ import annotations

import math
import re

_ASCII_WORD = re.compile(r"[a-z0-9_]+")
_CJK = re.compile(r"[\u4e00-\u9fff]")


def tokenize(text: str) -> list[str]:
    """文本 → token 列表（小写 ASCII 词 + CJK 单字 + CJK 双字组）。"""
    text = (text or "").lower()
    tokens = _ASCII_WORD.findall(text)
    cjk = _CJK.findall(text)
    tokens.extend(cjk)
    tokens.extend(cjk[i] + cjk[i + 1] for i in range(len(cjk) - 1))
    return tokens


def _build_vocab_idf(docs: list[list[str]]) -> tuple[dict[str, int], list[float]]:
    """语料 → 词表（term→下标）+ 平滑 IDF 向量。"""
    df: dict[str, int] = {}
    for doc in docs:
        for term in set(doc):
            df[term] = df.get(term, 0) + 1
    n = len(docs)
    terms = sorted(df)
    vocab = {term: i for i, term in enumerate(terms)}
    # 平滑 IDF：log((N+1)/(df+1)) + 1，避免除零且对高频词温和
    idf = [math.log((n + 1) / (df[term] + 1)) + 1.0 for term in terms]
    return vocab, idf


def _tfidf(tokens: list[str], vocab: dict[str, int], idf: list[float]) -> list[float]:
    """token 列表 → TF-IDF 向量（子线性 TF：1 + log(tf)）。"""
    vec = [0.0] * len(vocab)
    tf: dict[str, int] = {}
    for t in tokens:
        tf[t] = tf.get(t, 0) + 1
    for term, count in tf.items():
        idx = vocab.get(term)
        if idx is not None:
            vec[idx] = (1.0 + math.log(count)) * idf[idx]
    return vec


def _cosine(a: list[float], b: list[float]) -> float:
    """余弦相似度；任一向量为零向量时返回 0（诚实：无信息不硬凑相似）。"""
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


def detect_overlap(
    new_skill_text: str,
    existing_skills: list[dict],
    top_k: int = 3,
    threshold: float = 0.5,
) -> list[dict]:
    """检测新 skill 与已有 skills 的语义重叠。

    参数
    ----
    new_skill_text : 新 skill 的 SKILL.md 文本（正文 + 触发条件均可）
    existing_skills : 已有 skills 索引，每项为 dict，需含 ``name`` 与 ``text``
        （或 ``body``）两个键，如 ``{"name": "send-email", "text": "..."}``
    top_k : 返回最相似的 top_k 个
    threshold : 相似度 ≥ 该阈值时 ``suggest_merge`` 置 True（建议合并/标注）

    返回
    ----
    list[dict]：按相似度降序，每项 ``{"name", "score", "suggest_merge"}``。
    """
    if not existing_skills:
        return []
    docs = [new_skill_text] + [s.get("text", s.get("body", "")) or "" for s in existing_skills]
    tokenized = [tokenize(d) for d in docs]
    vocab, idf = _build_vocab_idf(tokenized)
    new_vec = _tfidf(tokenized[0], vocab, idf)

    results: list[dict] = []
    for i, skill in enumerate(existing_skills):
        vec = _tfidf(tokenized[i + 1], vocab, idf)
        score = _cosine(new_vec, vec)
        results.append({
            "name": skill.get("name", f"skill_{i}"),
            "score": round(score, 4),
            "suggest_merge": score >= threshold,
        })
    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:top_k]
