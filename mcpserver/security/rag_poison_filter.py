"""安全 · CamoDocs RAG 投毒防御（W60-03）

来源 docs/camodocs-rag-defense-方案.md（S23 · round3 digest-g3 2608.28389）：
CamoDocs 用「伪装文档 + 分散 token 扩散嵌入」把毒触发载荷拆散到多个文档/段落，
使单文档不包含完整查询 → 绕过「查询包含检测」。防御：文档入库前扫描「分散 token」
异常（异常高的注入式 token 密度 / 语义密度与文本量不匹配），并结合作者来源分级
（外部 vs 可信库）做置信度加权。

原型（纯 stdlib）：
  - poison_score      注入式 token 命中数 + 来源惩罚
  - RagPoisonFilter   按阈值判定「投毒可疑」，来源可信可放宽阈值

验收口径：投毒文档检出率 ≥80%，正常文档误报 ≤10%。
"""
from __future__ import annotations

from dataclasses import dataclass, field

__all__ = ["RagPoisonFilter", "poison_score", "Verdict"]

# 注入式指示 token（CamoDocs 分散扩散的载荷碎片常见词）
_POISON_TOKENS = (
    "ignore", "disregard", "override", "you are", "assistant", "instruction",
    "priority", "forget", "role", "hidden", "trigger", "activate", "payload",
    "inject", "system prompt", "always obey", "must follow",
)


def poison_score(doc: str, source_trust: str = "external") -> float:
    """投毒得分 = 注入式 token 命中数 + 来源惩罚（外部源 +1，可信库 0）。"""
    text = (doc or "").lower()
    hits = sum(1 for t in _POISON_TOKENS if t in text)
    penalty = 0.0 if source_trust == "trusted" else 1.0
    return hits + penalty


@dataclass
class Verdict:
    """入库前扫描结论。"""
    suspicious: bool
    score: float
    source_trust: str


class RagPoisonFilter:
    """RAG 文档入库前的投毒过滤器（来源分级加权）。"""

    def __init__(self, threshold: float = 3.0, trusted_threshold: float | None = None) -> None:
        self.threshold = threshold
        # 可信库来源可放宽阈值（默认阈值 +1，即要求多 1 个注入 token 才判可疑）
        self.trusted_threshold = threshold + 1.0 if trusted_threshold is None else trusted_threshold

    def check(self, doc: str, source_trust: str = "external") -> Verdict:
        score = poison_score(doc, source_trust)
        thr = self.trusted_threshold if source_trust == "trusted" else self.threshold
        return Verdict(suspicious=score >= thr, score=score, source_trust=source_trust)
