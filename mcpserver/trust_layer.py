"""认知免疫层（盲区 ②-1）—— 入库代码/文档自动信任评分。

目标：对进入系统的代码/文档/依赖按来源历史、签名、改动血统打信任分；
低信任对象自动进入隔离区（quarantine），不直接进主流程/注册表。

设计：
- 纯 stdlib，无外部依赖。
- 评分表落盘 JSON（trust_scores.json），可回溯。
- 隔离区：低信任对象标记 quarantine=true，调用方应跳过注册/执行。
- 评分维度：
  * source_history  来源历史（已知可信源 +1，未知源 +0，黑名单 -2）
  * signature       签名/哈希校验（有签名 +1，无 0）
  * lineage         改动血统（来自可信分支 +1，混入未知提交 -1）
  * review          人工/自动化 review 标记（reviewed +1）
- 阈值：>=2 信任，1 观望，<=0 低信任（自动隔离）。
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# 已知可信源（按前缀匹配，不区分大小写）
TRUSTED_SOURCES: tuple[str, ...] = (
    "github.com/fe1iscurc0r",
    "github.com/Project-N-E-K-O",
    "pypi.org",
    "registry.npmjs.org",
)

# 黑名单源（前缀匹配）
BLACKLIST_SOURCES: tuple[str, ...] = (
    "github.com/unknown-malware",
    "evil.example",
)

# 评分阈值
TRUST_THRESHOLD_HIGH: int = 2    # >= 2 信任
TRUST_THRESHOLD_LOW: int = 1     # <= 0 低信任（隔离）；1 观望

# 默认评分表落盘路径（可用环境变量覆盖，便于测试）
_DEFAULT_STORE = os.environ.get("TRUST_SCORE_STORE", "")


def _default_store_path() -> Path:
    if _DEFAULT_STORE:
        return Path(_DEFAULT_STORE)
    return Path(__file__).resolve().parent / "trust_scores.json"


@dataclass
class TrustAssessment:
    """单对象的信任评估结果。"""

    name: str
    score: int = 0
    reasons: list[str] = field(default_factory=list)
    quarantined: bool = False
    reviewed: bool = False
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "score": self.score,
            "reasons": self.reasons,
            "quarantined": self.quarantined,
            "reviewed": self.reviewed,
            "timestamp": self.timestamp,
        }


def score_source(source: str) -> tuple[int, str]:
    """按来源历史评分。"""
    src = (source or "").lower()
    if not src:
        return 0, "unknown source"
    for bad in BLACKLIST_SOURCES:
        if src.startswith(bad.lower()):
            return -2, f"blacklist source: {source}"
    for good in TRUSTED_SOURCES:
        if src.startswith(good.lower()):
            return 1, f"trusted source: {good}"
    return 0, f"unverified source: {source}"


class TrustScorer:
    """信任评分器：评分 + 落盘 + 隔离判定。"""

    def __init__(self, store_path: Path | None = None) -> None:
        self._store_path = store_path or _default_store_path()
        self._assessments: dict[str, TrustAssessment] = {}
        self._load()

    def _load(self) -> None:
        try:
            if self._store_path.exists():
                data = json.loads(self._store_path.read_text(encoding="utf-8"))
                for name, d in data.items():
                    self._assessments[name] = TrustAssessment(
                        name=name,
                        score=int(d.get("score", 0)),
                        reasons=list(d.get("reasons", [])),
                        quarantined=bool(d.get("quarantined", False)),
                        reviewed=bool(d.get("reviewed", False)),
                        timestamp=float(d.get("timestamp", 0)),
                    )
        except Exception:
            # 表损坏不致命：重建空表
            self._assessments = {}

    def save(self) -> None:
        """评分表落盘（幂等，可追溯）。"""
        data = {name: a.to_dict() for name, a in self._assessments.items()}
        tmp = self._store_path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self._store_path)

    def assess(self, name: str, source: str = "",
               signature: bool = False, lineage: str = "",
               reviewed: bool = False, force: bool = False) -> TrustAssessment:
        """评估对象信任分；force=True 时忽略已缓存重新打分。"""
        cached = self._assessments.get(name)
        if cached and not force:
            return cached

        score = 0
        reasons: list[str] = []

        src_score, src_reason = score_source(source)
        score += src_score
        reasons.append(f"source({src_score}): {src_reason}")

        if signature:
            score += 1
            reasons.append("signature(+1): signed/checksum verified")
        else:
            reasons.append("signature(0): no signature/checksum")

        if lineage:
            low = lineage.lower()
            if "trusted" in low or "main" in low or "verified" in low:
                score += 1
                reasons.append(f"lineage(+1): {lineage}")
            elif "unknown" in low or "merge" in low or "third-party" in low:
                score -= 1
                reasons.append(f"lineage(-1): {lineage}")
            else:
                reasons.append(f"lineage(0): {lineage}")
        else:
            reasons.append("lineage(0): no lineage info")

        if reviewed:
            score += 1
            reasons.append("review(+1): human/auto reviewed")
        else:
            reasons.append("review(0): unreviewed")

        quarantined = score <= TRUST_THRESHOLD_LOW
        assessment = TrustAssessment(
            name=name,
            score=score,
            reasons=reasons,
            quarantined=quarantined,
            reviewed=reviewed,
        )
        self._assessments[name] = assessment
        self.save()
        return assessment

    def get(self, name: str) -> TrustAssessment | None:
        return self._assessments.get(name)

    def is_quarantined(self, name: str) -> bool:
        a = self._assessments.get(name)
        return bool(a and a.quarantined)

    def quarantine_list(self) -> list[dict[str, Any]]:
        return [a.to_dict() for a in self._assessments.values() if a.quarantined]

    def all(self) -> dict[str, Any]:
        return {n: a.to_dict() for n, a in self._assessments.items()}


# 单例
_scorer: TrustScorer | None = None


def get_trust_scorer() -> TrustScorer:
    global _scorer
    if _scorer is None:
        _scorer = TrustScorer()
    return _scorer
