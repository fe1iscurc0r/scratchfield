"""VICT+VISTA SDR 感知 Agent 决策闭环（A30 · rf_brain/IC-705）。

依据 round3 digest-g1a-2026-08-31.md 授粉点 3：
- VICT（2608.28128）：把验证器内部**原子结构**暴露给训练时信用分配，用依赖
  证明边回溯动作，无需额外 rollout；
- VISTA（2608.28306）：用 outcome 验证过的 rollout 反向适配 teacher 分布，
  仅在错误位置做修正。

对 SDR 感知 Agent 的迁移：构建「信号检测 → 下一步动作」决策闭环。决策是
**复合动作**（解调模式 + 频段），验证器返回**结构化子判决**（mode_ok /
band_ok / demod_ok），VICT 把信用按「特征 × 子判决」逐条追溯（而非单一布尔），
VISTA 用失败样本只修正出错的子决策。

原型（纯 stdlib，确定性）：
  - 合成信号：(带宽档 bw, 频偏档 off) → 真值 (调制模式, 频段)
  - agent：查 teacher 规则表 → 输出复合动作 (mode, band)
  - 验证器：结构化判决（模式对否 / 频段对否 / 解调成功）
  - VICT 信用：按 (特征, 子判决) 累加成功/失败，可视化含子判决分解
  - VISTA：失败样本反向修正对应子决策规则

验收（SPEC A30）：合成场景决策正确率 ≥75%，含信用分配可视化。

运行：
  python tools/sdr_perception_agent.py
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

MODES = ["FM", "AM", "SSB", "PSK"]
BANDS = ["low", "high"]


def true_mode(bw: int, off: int) -> str:
    """可学的真值规则：调制模式 = (bw + off) % 4。"""
    return MODES[(bw + off) % 4]


def true_band(off: int) -> str:
    """频段真值：off ∈ [0,2) 低段，[2,4) 高段。"""
    return "high" if off >= 2 else "low"


@dataclass
class SDRPerceptionAgent:
    """感知 Agent：teacher 规则表（模式/频段）+ VICT 结构化信用账本。"""

    bw_bins: int = 2
    off_bins: int = 4
    rules_mode: dict[tuple[int, int], str] = field(default_factory=dict)
    rules_band: dict[tuple[int, int], str] = field(default_factory=dict)
    credit: dict[tuple[int, int, str], list[int]] = field(default_factory=dict)  # (bw,off,subcheck)->[成功,总]

    def __post_init__(self):
        # 初始 teacher：模式与频段规则都故意部分错误（制造可学习空间）
        for bw in range(self.bw_bins):
            for off in range(self.off_bins):
                self.rules_mode[(bw, off)] = MODES[(bw + off + (1 if off % 2 else 0)) % 4]
                self.rules_band[(bw, off)] = ("high" if off % 2 == 0 else "low")

    def decide(self, bw: int, off: int) -> tuple[str, str]:
        """信号检测 → 复合动作 (解调模式, 频段)。"""
        return (self.rules_mode[(bw, off)], self.rules_band[(bw, off)])

    def verify(self, bw: int, off: int, mode: str, band: str) -> dict:
        """验证器：暴露内部原子结构（模式/频段两个子判决）。"""
        m_ok = mode == true_mode(bw, off)
        b_ok = band == true_band(off)
        return {"mode_ok": m_ok, "band_ok": b_ok, "demod_ok": m_ok and b_ok}

    def update_credit(self, bw: int, off: int, subcheck: str, ok: bool) -> None:
        """VICT 信用追溯：按 (特征, 子判决) 记账。"""
        rec = self.credit.setdefault((bw, off, subcheck), [0, 0])
        rec[1] += 1
        if ok:
            rec[0] += 1

    def teacher_correct_mode(self, bw: int, off: int, true_m: str) -> None:
        self.rules_mode[(bw, off)] = true_m

    def teacher_correct_band(self, bw: int, off: int, true_b: str) -> None:
        self.rules_band[(bw, off)] = true_b

    def visualize_credit(self) -> str:
        """信用分配可视化：按子判决分组展示。"""
        lines = ["子判决  特征(bw,off)  成功/总  可信度"]
        for subcheck in ("mode", "band"):
            for (bw, off, sc), (s, t) in sorted(self.credit.items()):
                if sc == subcheck:
                    lines.append(f"{sc:<6}  ({bw},{off})        {s}/{t}    {s / t:.2f}")
        return "\n".join(lines)


def run_training(agent: SDRPerceptionAgent, samples: list[tuple[int, int]], seed: int = 0) -> None:
    """决策-验证-信用-修正闭环。"""
    rng = random.Random(seed)
    for (bw, off) in samples:
        mode, band = agent.decide(bw, off)
        v = agent.verify(bw, off, mode, band)
        agent.update_credit(bw, off, "mode", v["mode_ok"])
        agent.update_credit(bw, off, "band", v["band_ok"])
        if not v["mode_ok"]:
            agent.teacher_correct_mode(bw, off, true_mode(bw, off))  # VISTA：只修出错子决策
        if not v["band_ok"]:
            agent.teacher_correct_band(bw, off, true_band(off))


def evaluate(agent: SDRPerceptionAgent, samples: list[tuple[int, int]]) -> float:
    """复合决策正确率（模式与频段都对才算对）。"""
    if not samples:
        return 1.0
    ok = sum(1 for (bw, off) in samples
             if agent.decide(bw, off) == (true_mode(bw, off), true_band(off)))
    return ok / len(samples)


def make_samples(bw_bins: int, off_bins: int, seed: int = 0) -> list[tuple[int, int]]:
    rng = random.Random(seed)
    all_feats = [(bw, off) for bw in range(bw_bins) for off in range(off_bins)]
    return [rng.choice(all_feats) for _ in range(200)]


def main() -> int:
    agent = SDRPerceptionAgent()
    train = make_samples(agent.bw_bins, agent.off_bins, seed=0)
    test = make_samples(agent.bw_bins, agent.off_bins, seed=1)

    before = evaluate(agent, test)
    run_training(agent, train, seed=2)
    after = evaluate(agent, test)

    print(f"[决策正确率] 训练前 {before:.2f} → 训练后 {after:.2f}（验收要求 ≥0.75）")
    print(agent.visualize_credit())
    return 0 if after >= 0.75 else 1


if __name__ == "__main__":
    raise SystemExit(main())
