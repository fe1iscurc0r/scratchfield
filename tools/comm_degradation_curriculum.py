"""UC-PSRO 通信退化课程 · 最小原型（A22 · NEKO 多 Agent 协作鲁棒性）。

依据 docs/uc-psro-通信退化课程-方案.md：
- 任务：发送方在丢包信道（丢包率 p）上把消息交付给接收方，收齐 ≥1 份即成功
- 策略：发送方选择冗余档位 r（发 r 份），成功概率 1 - p^r，代价 = 通信成本
- 无课程基线：在 p=0（理想信道）下训练 → 学到「单发即止」，50% 丢包时崩
- 通信退化课程：p 从 0% 渐进升至 50% → 学到「冗余重传」，50% 丢包时仍稳
- 验收（SPEC A22）：丢包 50% 时课程策略任务成功率较无课程基线提升 ≥20%

纯标准库，epsilon-greedy 表格 Q 学习做最小演示；NEKO 真实落地换 PPO/PSRO。

运行：
  python tools/comm_degradation_curriculum.py
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

R_MAX = 4  # 最大冗余档位
COST_PER_COPY = 0.10  # 每份副本的成本惩罚


@dataclass
class Channel:
    """丢包信道：每份副本独立以 drop_prob 丢失。"""

    drop_prob: float

    def send(self, copies: int, rng: random.Random) -> bool:
        """发 copies 份，任一份到达即成功。成功概率 1 - p^copies。"""
        for _ in range(copies):
            if rng.random() >= self.drop_prob:
                return True
        return False


@dataclass
class RedundancyAgent:
    """在冗余档位 {1..R_MAX} 上做 epsilon-greedy Q 学习。"""

    q: dict[int, float] = field(default_factory=dict)
    epsilon: float = 0.1
    lr: float = 0.1

    def __post_init__(self):
        if not self.q:
            self.q = {r: 0.0 for r in range(1, R_MAX + 1)}

    def choose(self, rng: random.Random) -> int:
        if rng.random() < self.epsilon:
            return rng.randint(1, R_MAX)
        return max(self.q, key=self.q.get)

    def update(self, r: int, reward: float) -> None:
        self.q[r] += self.lr * (reward - self.q[r])

    def greedy(self) -> int:
        return max(self.q, key=self.q.get)


def _reward(success: bool, copies: int) -> float:
    return (1.0 if success else 0.0) - COST_PER_COPY * copies


def train(agent: RedundancyAgent, p: float, steps: int, seed: int | None = None) -> None:
    """固定丢包率 p 下训练 steps 步。"""
    rng = random.Random(seed)
    ch = Channel(p)
    for _ in range(steps):
        r = agent.choose(rng)
        ok = ch.send(r, rng)
        agent.update(r, _reward(ok, r))


def curriculum_train(agent: RedundancyAgent, steps_per_stage: int = 2000, seed: int | None = 0) -> None:
    """通信退化课程：丢包率 0%→50% 渐进（6 阶段）。"""
    ramp = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5]
    for i, p in enumerate(ramp):
        train(agent, p, steps_per_stage, seed=(seed + i) if seed is not None else None)


def evaluate(agent: RedundancyAgent, p: float, trials: int = 10000, seed: int | None = 42) -> float:
    """在丢包率 p 下用贪心策略评估任务成功率。"""
    rng = random.Random(seed)
    ch = Channel(p)
    r = agent.greedy()
    ok = sum(1 for _ in range(trials) if ch.send(r, rng))
    return ok / trials


def main() -> int:
    # 无课程基线：只在 p=0 训练
    baseline = RedundancyAgent()
    train(baseline, 0.0, steps=6000, seed=0)
    # 通信退化课程：0%→50% 渐进
    curriculum = RedundancyAgent()
    curriculum_train(curriculum, seed=0)

    p_eval = 0.5
    base_sr = evaluate(baseline, p_eval)
    cur_sr = evaluate(curriculum, p_eval)
    gain = cur_sr - base_sr

    print(f"[无课程] 冗余档位={baseline.greedy()} @50%丢包 成功率={base_sr:.3f}")
    print(f"[课程]   冗余档位={curriculum.greedy()} @50%丢包 成功率={cur_sr:.3f}")
    print(f"[提升]   {gain:+.3f}（验收要求 ≥+0.20）")
    return 0 if gain >= 0.20 else 1


if __name__ == "__main__":
    raise SystemExit(main())
