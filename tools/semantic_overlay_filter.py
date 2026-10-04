"""S20 Semantic Overlays 提示注入防御（token 标注层 + 注入内容降权/掩码）

来源授粉点：digest-g1-3 2608.23873v1（Semantic Overlays: Mitigating Prompt Injection
with Annotated Tokens）——核心是"语言模型看到的一切都是 token"，把每个输入 token
标注来源/信任级别，来自不可信来源的指令性内容降权。

迁移到 NEKO：在提示词进入模型前加一道**标注过滤管线**——把输入按来源分段
（system / user / tool / external），信任级别判定后，只对不可信来源（tool/external）
的"指令注入模式"做掩码降权，可信来源（system/user）原样通过。

对齐：mcpserver/trust_layer.py 的来源分级（source_history / lineage）与
docs/neko-trust-memory-设计稿.md 的来源分级（user_direct / agent / file / external）。
纯 stdlib 实现，无第三方依赖。本原型为规则式标注过滤（不引 LLM）。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# 来源 → 信任级别（对齐 trust_layer / neko-trust-memory 分级）
TRUSTED_SOURCES = frozenset({"system", "user"})
UNTRUSTED_SOURCES = frozenset({"tool", "external"})

# 注入指令模式（只对不可信来源生效）
_INJECTION_PATTERNS: tuple[str, ...] = (
    r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions?",
    r"disregard\s+(all\s+)?(previous|prior|above)?\s*instructions?",
    r"(you\s+are|you're)\s+now",
    r"(your|the)\s+new\s+(instructions?|task|role)",
    r"do\s+not\s+follow",
    r"override\s+(the\s+)?system\s+prompt",
    r"reveal\s+(the\s+)?(secret|password|api\s?key|system\s+prompt)",
    r"forget\s+(everything|your\s+instructions)",
    r"instead\s*,\s*(output|respond|say|print)",
)
_INJECTION_RE = re.compile("|".join(_INJECTION_PATTERNS), re.IGNORECASE)
_MASK = "[UNTRUSTED-CONTENT]"


@dataclass
class Segment:
    """一段输入：来源 + 文本。"""

    source: str
    text: str


def trust_level(source: str) -> str:
    """来源 → 信任级别。未知来源保守按不可信处理（默认拒绝）。"""
    s = source.strip().lower()
    if s in TRUSTED_SOURCES:
        return "trusted"
    return "untrusted"


def _mask_injections(text: str) -> str:
    """把文本中的注入模式片段掩码掉。"""
    return _INJECTION_RE.sub(_MASK, text)


@dataclass
class FilterResult:
    """过滤结果。"""

    text: str                 # 过滤后的整体文本（各段拼接）
    segments: list[str]       # 过滤后各段文本
    blocked_count: int        # 被掩码的注入片段数
    blocked_snippets: list[str]  # 被掩码片段原文（审计用）


def filter_prompt(segments: list[Segment]) -> FilterResult:
    """标注过滤管线：不可信来源掩码注入，可信来源原样。"""
    out_segments: list[str] = []
    blocked_count = 0
    blocked_snippets: list[str] = []
    for seg in segments:
        if trust_level(seg.source) == "trusted":
            out_segments.append(seg.text)
            continue
        masked = _mask_injections(seg.text)
        # 记录被掩码的注入片段（原文）
        for m in _INJECTION_RE.finditer(seg.text):
            blocked_count += 1
            blocked_snippets.append(m.group(0))
        out_segments.append(masked)
    return FilterResult(
        text="".join(out_segments),
        segments=out_segments,
        blocked_count=blocked_count,
        blocked_snippets=blocked_snippets,
    )


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def attack_survival_rate(payloads: list[str]) -> float:
    """无过滤时注入攻击成功率（payload 原文存活比例），恒为 1.0，作基线。"""
    return 1.0


def attack_survival_rate_filtered(payloads: list[str]) -> float:
    """有过滤时注入攻击成功率（payload 关键短语仍存活的样本比例）。"""
    survived = 0
    for p in payloads:
        out = filter_prompt([Segment("external", p)]).text
        if _norm(p) in _norm(out):
            survived += 1
    return survived / len(payloads)


def normal_pass_rate(segments: list[Segment]) -> float:
    """可信指令通过率 = 过滤后相对原文的词级保留率。"""
    original = "".join(s.text for s in segments)
    filtered = filter_prompt(segments).text
    if not original:
        return 1.0
    orig_words = _norm(original).split()
    if not orig_words:
        return 1.0
    kept = sum(1 for w in orig_words if w in _norm(filtered))
    return kept / len(orig_words)
