"""候选算法（工单246）。

一个候选 = 编辑面上的一组取值 + 它的**出处**（谁提的）+ 它的**评测记录**（约束门/打分）。
把"出处"记下来是刻意的：SeisEvo 的搜索是 LLM 多智能体驱动的，
本单的默认路径是**确定性规则**、LLM 是可选旁路 —— 两者产出的候选必须能区分，
否则无法审计"这个算法到底是谁想出来的"。
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Candidate:
    """编辑面上的一个候选参数组。"""

    params: dict
    provenance: str = "rules"           # rules / llm / seed / manual
    label: str = ""                     # 人类可读来源（如 "grid[3]" / "perturb(prom=15)"）
    generation: int = 0                 # 第几轮演化产出（0 = 初始）
    rejected: bool = False              # 是否被约束门否决
    reject_stage: str = ""              # A / B
    violations: list[dict] = field(default_factory=list)
    score: dict | None = None           # scorer.ScoreResult.as_dict()
    wall_s: float = 0.0

    @property
    def key(self) -> tuple:
        """用于去重的规范化键（dict 不可哈希 ⇒ 转元组）。"""
        return tuple(sorted((k, v) for k, v in self.params.items()))

    def as_dict(self) -> dict:
        return {
            "params": dict(self.params),
            "provenance": self.provenance,
            "label": self.label,
            "generation": self.generation,
            "rejected": self.rejected,
            "reject_stage": self.reject_stage,
            "violations": self.violations,
            "score": self.score,
        }

    def __str__(self) -> str:  # pragma: no cover - 仅调试用
        state = "REJECT" if self.rejected else (f"{self.score['mean_db']:+.2f}dB"
                                                if self.score else "unscored")
        return f"<{self.provenance}:{self.label} {self.params} {state}>"
