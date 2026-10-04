"""A45 · Drift Recovery Graph 漂移恢复图原型（来源 2608.14109）

论文核心：状态机恢复图 + 小语言模型专精化节点，在 AppWorld 上做出正确恢复决策。

原型（mock，显式标注）：
  - 恢复图：错误签名 → {恢复动作: 成功概率}（状态机边的量化）
  - 小语言模型 mock：关键词→首选动作决策表（替代微调小模型，即"专精化节点"）
  - mock 环境：随机触发错误签名的 episode，策略选动作，按图中概率判定恢复成功
评估：决策表策略恢复率 > 随机策略。

运行：python -m mcpserver.agent_lab.prototypes.drift_recovery_graph
"""
from __future__ import annotations

import numpy as np

# 恢复图：错误签名 → {动作: 恢复成功概率}（即状态机转移边的标注）
RECOVERY_GRAPH: dict[str, dict[str, float]] = {
    "auth_expired": {"renew_token": 0.90, "relogin": 0.70, "retry": 0.20},
    "missing_field": {"patch_field": 0.85, "retry": 0.30, "abort": 0.00},
    "rate_limited": {"backoff_wait": 0.90, "retry": 0.40, "relogin": 0.10},
    "not_found": {"switch_api": 0.80, "retry": 0.20, "abort": 0.00},
}

# 小语言模型 mock：错误签名关键词 → 首选恢复动作（专精化节点决策表）
SLM_TABLE = {
    "auth_expired": "renew_token",
    "missing_field": "patch_field",
    "rate_limited": "backoff_wait",
    "not_found": "switch_api",
}


def slm_decide(signature: str) -> str:
    """小语言模型节点：把错误文本映射到恢复动作；未知签名回退 retry"""
    for key, action in SLM_TABLE.items():
        if key in signature:
            return action
    return "retry"


def random_decide(signature: str, rng: np.random.Generator) -> str:
    """随机策略基线：在该签名的动作集里均匀随机选"""
    actions = list(RECOVERY_GRAPH.get(signature, {"retry": 1.0}))
    return str(rng.choice(actions))


def run_episodes(policy, n_episodes: int = 400, seed: int = 3) -> float:
    """跑 n 个漂移-恢复 episode，返回恢复成功率"""
    rng = np.random.default_rng(seed)
    sigs = list(RECOVERY_GRAPH)
    recovered = 0
    for _ in range(n_episodes):
        sig = sigs[int(rng.integers(len(sigs)))]
        action = policy(sig, rng)
        prob = RECOVERY_GRAPH[sig].get(action, 0.0)
        if rng.random() < prob:
            recovered += 1
    return recovered / n_episodes


def evaluate(seed: int = 3, n_episodes: int = 400) -> dict:
    """对比小语言模型决策表与随机策略的恢复率（同一批 episode 种子）"""
    slm_rate = run_episodes(lambda s, r: slm_decide(s), n_episodes, seed)
    rand_rate = run_episodes(lambda s, r: random_decide(s, r), n_episodes, seed)
    return dict(slm_recovery=slm_rate, random_recovery=rand_rate,
                better=slm_rate > rand_rate)


if __name__ == "__main__":
    r = evaluate()
    print(f"漂移恢复图：小模型决策表恢复率 {r['slm_recovery']:.3f}"
          f" > 随机策略 {r['random_recovery']:.3f}")
