"""演化主循环（工单246）。

把 SeisEvo 的四条机制串起来：

```
初始（经典算法参数）
   │
   ├─► ① 受限编辑面提案（proposers：默认确定性 rules / 可选 LLM 旁路）
   │
   ├─► ② 约束门（constraints：违反 ⇒ **直接否决**，不进打分）
   │        A 段参数级（O(1)）→ B 段检测级（1 次 FFT，**不跑陷波**）
   │
   ├─► ③ 执行打分（scorer：真跑 rf_brain 的既有实现，读数=对干净参考的 S/N 提升 dB）
   │
   └─► ④ 选择（主键=各场景均值，次键=最差场景）──► 下一轮
                                          └─► 收敛后输出**白盒算法**（codegen）
```

刻意保留的两件事
----------------
- **全轨迹**（`history`）：每个候选的出处/是否被否/否决码/读数都留着 —— 演化过程要可审计，
  不能被压缩成"最后那个参数组"。
- **省下的算力**（`gate_stats.saved_notch_ops`）：约束门在便宜阶段挡掉灾难候选，
  这件事有**可核对**的量化（同时 `wall_s` 是真实墙钟）。
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field

from .candidate import Candidate
from .constraints import gate
from .editspace import EditSpace, spaces
from .proposers import make_proposer
from .scorer import DEFAULT_SCENARIOS, Scenario, baseline_report, score


@dataclass
class EvolveConfig:
    """一次演化运行的配置。"""

    space: str = "rfi_mitigation"
    generations: int = 4
    batch: int = 6
    proposal: str = "rules"              # rules（默认）/ llm（可选旁路）
    seed: int = 20261016
    signal_band_hz: float = 100_000.0
    max_notches: int = 12
    max_notch_band_fraction: float = 0.5
    time_budget_s: float = 180.0

    def describe(self) -> dict:
        return asdict(self)


@dataclass
class EvolveResult:
    """一次演化运行的结果（含全轨迹与统计）。"""

    config: dict
    space: dict
    baseline: dict
    best: dict
    history: list[dict] = field(default_factory=list)
    gate_stats: dict = field(default_factory=dict)
    proposal_mode: str = "rules"
    notes: list[str] = field(default_factory=list)
    wall_s: float = 0.0

    def as_dict(self) -> dict:
        return {
            "config": self.config, "space": self.space, "baseline": self.baseline,
            "best": self.best, "history": self.history, "gate_stats": self.gate_stats,
            "proposal_mode": self.proposal_mode, "notes": self.notes,
            "wall_s": round(self.wall_s, 4),
        }


def get_space(name: str) -> EditSpace:
    sp = spaces().get(name)
    if sp is None:
        raise KeyError(f"未登记的编辑面 {name!r}（可用：{sorted(spaces())}）")
    return sp


def evolve(config: EvolveConfig | None = None,
           scenarios: tuple[Scenario, ...] = DEFAULT_SCENARIOS) -> EvolveResult:
    """跑一次演化。默认配置下**完全离线且确定性**（rules 提案器 + 固定 seed）。"""
    cfg = config or EvolveConfig()
    space = get_space(cfg.space)
    # ⚠️ kwargs 按模式给：`make_proposer` 会**严格校验**（给错参数就报错，不静默丢弃），
    #    而 `LLMProposer` 不接受 seed（它不采样）。
    proposer = make_proposer(space, cfg.proposal,
                             **({"seed": cfg.seed} if cfg.proposal == "rules" else {}))

    built = {sc.name: sc.build() for sc in scenarios}      # 场景只造一次（确定性 & 省时）
    t0 = time.perf_counter()

    base_scores = score(space.defaults(), scenarios, built=built)
    baseline = {"params": space.defaults(), "score": base_scores.as_dict()}

    stats = {"proposed": 0, "rejected_stage_A": 0, "rejected_stage_B": 0,
             "scored": 0, "saved_notch_ops": 0}
    history: list[dict] = []
    seen: set[tuple] = set()

    seed_cand = Candidate(params=space.defaults(), provenance="seed",
                          label="classical-default", generation=0,
                          score=base_scores.as_dict(), wall_s=base_scores.wall_s)
    best = seed_cand
    history.append(seed_cand.as_dict())
    seen.add(seed_cand.key)

    notes: list[str] = []
    if cfg.proposal == "llm":
        ok, reason = proposer.available()          # type: ignore[attr-defined]
        notes.append(f"LLM 提案器可用性：{reason}")
        if not ok:
            notes.append("已按『不静默降级』原则回退到 rules —— 见 proposal_mode 字段")
            cfg = EvolveConfig(**{**cfg.describe(), "proposal": "rules"})
            proposer = make_proposer(space, "rules", seed=cfg.seed)   # 回退后 seed 才有意义

    for gen in range(1, cfg.generations + 1):
        if time.perf_counter() - t0 > cfg.time_budget_s:
            notes.append(f"第 {gen} 代前触发时间预算 {cfg.time_budget_s}s，提前收敛")
            break
        # ⚠️ 第一代传 best=None ⇒ 走**网格扫描**（系统性覆盖编辑面）；
        #    否则首代就会带着 seed 的分数去扰动，文档里写的「先铺网格再扰动」根本不生效
        #    （实测踩过：搜索从一开始就只在种子附近打转）。
        parsed = proposer.propose(generation=gen, best=(None if gen == 1 else best),
                                  n=cfg.batch)
        notes.append(f"gen{gen}: {parsed.note}")
        for cand in parsed.candidates:
            if cand.key in seen:
                continue
            seen.add(cand.key)
            stats["proposed"] += 1

            g = gate(cand.params, built[scenarios[0].name][1], scenarios[0].sample_rate_hz,
                     signal_band_hz=cfg.signal_band_hz, max_notches=cfg.max_notches,
                     max_notch_band_fraction=cfg.max_notch_band_fraction)
            stats["saved_notch_ops"] += g.saved_notch_ops
            if not g.passed:
                cand.rejected = True
                cand.reject_stage = g.stage
                cand.violations = [v.as_dict() for v in g.violations]
                stats["rejected_stage_A" if g.stage == "A" else "rejected_stage_B"] += 1
                history.append(cand.as_dict())
                continue

            sr = score(cand.params, scenarios, built=built)
            cand.score = sr.as_dict()
            cand.wall_s = sr.wall_s
            stats["scored"] += 1
            history.append(cand.as_dict())
            if sr.fitness > (best.score["mean_db"], best.score["min_db"]):
                best = cand

    stats["generated"] = cfg.generations
    stats["unique_candidates"] = len(seen)
    stats["reject_rate"] = round(
        (stats["rejected_stage_A"] + stats["rejected_stage_B"]) / max(1, stats["proposed"]), 4)
    return EvolveResult(
        config=cfg.describe(), space=space.describe(), baseline=baseline,
        best=best.as_dict(), history=history, gate_stats=stats,
        proposal_mode=cfg.proposal, notes=notes, wall_s=time.perf_counter() - t0,
    )


def baseline(scenarios: tuple[Scenario, ...] = DEFAULT_SCENARIOS) -> dict:
    """只跑基线（不开搜索）—— 用于人工核对"演化到底带来了多少"。"""
    return baseline_report(scenarios)
