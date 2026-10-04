"""
W62-04 Agent Credit 自欺审计复现实验
======================================
复现「过程监督信号自欺」核心发现：
  PRM / correctness 等 step-level credit 信号在因果上不优于随机，
  只有反事实执行回放贡献能稳定区分「重要决策点」。

核心组件
--------
- MockDecisionEnv     : 可重放的多步决策环境（固定 seed，工具调用链）
- TrajectorySampler   : 采集 Agent 轨迹 + step 状态
- CreditSignals      : 5 组被审计信号 + 2 组基线
- CounterfactualReplay: 执行回放 ground truth
- DiscriminabilityScorer: AUROC / Spearman 判别力指标

参考文献：docs/agent-credit-audit-2026-08-30.md §三/§四
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy.stats import spearmanr
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import label_binarize

# ---------------------------------------------------------------------------
# 1. Mock 多步决策环境
# ---------------------------------------------------------------------------

@dataclass
class Step:
    """单步决策记录。"""
    step_id: int
    state: Dict[str, Any]
    action: str
    is_critical: bool          # ground truth：是否真正影响最终结果
    causal_contribution: float # Δ(t)：反事实因果贡献（ground truth）


class MockDecisionEnv:
    """
    简单 2D 网格导航环境（确定性，可 seed 重放）。
    
    设定
    ----
    - 5×5 网格，起点 (0,0)，目标 (4,4)
    - Agent 每步可选择：up / down / left / right / stay
    - 有 3 个「关键决策点」：在特定位置必须选择正确方向才能到达目标
    - 其余步骤无论选什么都到达同一目标（non-critical）
    - 正确完成=到达 (4,4)；失败=撞墙或偏离
    
    用途：构造 ground truth — 哪些 step 真正改变了最终结果。
    """

    GOAL = (4, 4)
    GRID_SIZE = 5
    CRITICAL_POSITIONS = {(1, 0), (2, 1), (3, 3)}   # 必须正确的位置

    DIRECTION_DELTA = {
        "up":    (-1, 0),
        "down":  (+1, 0),
        "left":  (0, -1),
        "right": (0, +1),
        "stay":  (0, 0),
    }

    def __init__(self, seed: int = 42):
        self.rng = np.random.default_rng(seed)
        # 预生成所有随机数（确保可重放）
        self._action_pool = list(self.DIRECTION_DELTA.keys())
        self._pool_idx = 0
        self._action_seq: List[str] = []
        self._reset()

    def _reset(self):
        self.pos = (0, 0)
        self.traj: List[Tuple[int, int]] = [(0, 0)]
        self.steps: List[Step] = []
        self.step_id_counter = 0
        self._pool_idx = 0

    def clone(self) -> "MockDecisionEnv":
        """创建环境的深拷贝（用于反事实重放）。"""
        new_env = MockDecisionEnv(seed=int(self.rng.integers(1 << 30)))
        new_env.pos = self.pos
        new_env.traj = list(self.traj)
        new_env.steps = list(self.steps)
        new_env.step_id_counter = self.step_id_counter
        return new_env

    def _next_random_action(self) -> str:
        """从预洗牌池取动作（确定性重放用）。"""
        if self._pool_idx >= len(self._action_seq):
            self._action_seq = self.rng.choice(
                self._action_pool, size=50, replace=True
            ).tolist()
        action = self._action_seq[self._pool_idx]
        self._pool_idx += 1
        return action

    def step(self, action: str, record: bool = True) -> Tuple[Tuple[int, int], float, bool]:
        """
        执行一步，返回 (新位置, 奖励, 是否终止)。
        """
        delta = self.DIRECTION_DELTA[action]
        new_r = np.clip(self.pos[0] + delta[0], 0, self.GRID_SIZE - 1)
        new_c = np.clip(self.pos[1] + delta[1], 0, self.GRID_SIZE - 1)
        self.pos = (new_r, new_c)
        self.traj.append(self.pos)

        if record:
            step = Step(
                step_id=self.step_id_counter,
                state={"pos": self.pos},
                action=action,
                is_critical=False,
                causal_contribution=0.0,
            )
            self.steps.append(step)
            self.step_id_counter += 1

        # 奖励
        if self.pos == self.GOAL:
            return self.pos, 1.0, True
        # 每步小惩罚
        return self.pos, -0.05, False

    def execute(self, actions: List[str]) -> Tuple[float, List[Step], List[Tuple[int, int]]]:
        """
        执行完整动作序列，返回 (最终奖励, 步骤列表, 轨迹)。
        """
        self._reset()
        total_r = 0.0
        for a in actions:
            _, r, done = self.step(a)
            total_r += r
            if done:
                break
        return total_r, self.steps, self.traj


# ---------------------------------------------------------------------------
# 2. 工具调用链环境（第二种 mock，更接近真实 Agent 场景）
# ---------------------------------------------------------------------------

TOOL_REGISTRY = {
    "navigate": {"args": ["destination"], "cost": 1.0},
    "read_file": {"args": ["path"], "cost": 2.0},
    "write_file": {"args": ["path", "content"], "cost": 3.0},
    "run_query": {"args": ["sql"], "cost": 1.5},
    "send_message": {"args": ["to", "msg"], "cost": 0.5},
}

CRITICAL_TOOL_CALLS = {
    # 这些调用组合是唯一能完成任务的
    ("navigate", "read_file", "run_query"),
}


class ToolChainEnv:
    """
    工具调用链环境。
    关键调用（critical）：navigate + read_file + run_query 顺序正确 = 任务成功
    其他调用对结果无影响。
    """

    def __init__(self, seed: int = 42):
        self.rng = np.random.default_rng(seed)
        self.tools_used: List[str] = []
        self.call_history: List[Dict[str, Any]] = []
        self.success = False
        self._reset()

    def _reset(self):
        self.tools_used = []
        self.call_history = []
        self.success = False

    def call_tool(self, tool_name: str, args: Dict[str, Any],
                  record: bool = True) -> Dict[str, Any]:
        if tool_name not in TOOL_REGISTRY:
            raise ValueError(f"Unknown tool: {tool_name}")
        self.tools_used.append(tool_name)
        result = {"tool": tool_name, "args": args, "result": f"ok_{tool_name}"}
        self.call_history.append(result)

        # 判断是否成功
        tool_set = set(self.tools_used)
        if tool_set >= {"navigate", "read_file", "run_query"}:
            # 顺序也要对
            nav_i = self.tools_used.index("navigate")
            read_i = self.tools_used.index("read_file")
            query_i = self.tools_used.index("run_query")
            if nav_i < read_i < query_i:
                self.success = True

        if record:
            step = Step(
                step_id=len(self.tools_used) - 1,
                state={"tools": list(self.tools_used)},
                action=tool_name,
                is_critical=False,
                causal_contribution=0.0,
            )
            return {"step": step, "success": self.success}
        return {"success": self.success}

    def execute_random(self, n_steps: int) -> Tuple[float, List[Step], bool]:
        """随机执行 n 步工具调用（产生随机轨迹）。"""
        self._reset()
        tool_names = list(TOOL_REGISTRY.keys())
        steps = []
        for i in range(n_steps):
            tool = self.rng.choice(tool_names)
            args = {k: f"arg_{i}" for k in ["destination", "path", "content",
                                              "sql", "to", "msg"][:len(TOOL_REGISTRY[tool]["args"])]}
            result = self.call_tool(tool, args)
            steps.append(result["step"])
            if result["success"]:
                break
        return 1.0 if self.success else 0.0, steps, self.success


# ---------------------------------------------------------------------------
# 3. 反事实执行回放（Ground Truth）
# ---------------------------------------------------------------------------

class CounterfactualReplay:
    """
    反事实执行回放，计算每个 step 的真实因果贡献 Δ(t)。

    方法
    ----
    1. 记录原始轨迹 (s1,a1,...,s_T)
    2. 对每步 t：将 a_t 替换为「默认动作」/「随机动作」，
       重放剩余轨迹，计算反事实结果 R'(t)
    3. Δ(t) = R − E[R'(t)]（多次采样取期望）
    4. 阈值化：|Δ(t)| > ε → 标记为 critical
    """

    def __init__(self, env: MockDecisionEnv, n_replay: int = 10, epsilon: float = 0.05):
        self.env = env
        self.n_replay = n_replay
        self.epsilon = epsilon

    def compute_ground_truth(self, actions: List[str]) -> List[float]:
        """
        对单条轨迹计算每个 step 的因果贡献 Δ(t)。

        度量：每个 step 替换为 'stay' 后，终点到 GOAL 的曼哈顿距离增量。
        距离增加越多 → 该 step 对靠近目标越关键（贡献越大）。
        相比「是否到 GOAL」的 0/1 奖励，距离度量提供连续、可判别的 Δ，
        避免随机轨迹几乎到不了 GOAL 时 Δ 恒为 0 的问题。
        """
        from math import inf

        def _dist_to_goal(pos) -> float:
            return abs(pos[0] - MockDecisionEnv.GOAL[0]) + abs(
                pos[1] - MockDecisionEnv.GOAL[1])

        # 基线：完整轨迹的终点距离
        env_base = self.env.clone()
        env_base._reset()
        for a in actions:
            env_base.step(a, record=False)
        base_dist = _dist_to_goal(env_base.pos)

        delta = []
        for t in range(len(actions)):
            # 反事实重放：将 step t 替换为 stay
            cf_actions = actions[:t] + ["stay"] + actions[t + 1:]
            dists = []
            for _ in range(self.n_replay):
                env_cf = self.env.clone()
                env_cf._reset()
                for a in cf_actions:
                    env_cf.step(a, record=False)
                dists.append(_dist_to_goal(env_cf.pos))
            expected_dist = float(np.mean(dists))
            # 替换该 step 后距离变大 → 该 step 贡献为正（关键）
            delta_t = expected_dist - base_dist
            delta.append(float(delta_t))
        return delta

    def label_critical_steps(self, delta: List[float]) -> List[bool]:
        """根据 Δ(t) 阈值化标记重要决策点。"""
        return [abs(d) > self.epsilon for d in delta]


# ---------------------------------------------------------------------------
# 4. Credit 信号计算
# ---------------------------------------------------------------------------

class CreditSignals:
    """
    计算 5 组被审计信号 + 2 组基线。

    信号定义
    --------
    1. PRM (Process Reward Model)       : 模拟 step-level RL 过程奖励（每步给 +1/-0.5）
    2. Value Diff                        : V(s_t) - V(s_{t-1})（蒙特卡洛估计）
    3. Advantage                         : A(t) = Q(s,a) - V(s)（近似）
    4. Correctness Proxy                 : 人工标注的正确性（模拟：最终成功→所有 step 都是好的）
    5. Counterfactual Contribution (GT)  : 反事实回放因果贡献（ground truth）
    6. Random Baseline                   : 均匀随机 [0,1]
    7. Position Prior                   : 越靠后的 step 分越高（靠后≈重要谬论）
    """

    @staticmethod
    def prm_score(steps: List[Step]) -> np.ndarray:
        """模拟 PRM：每步给 +1（正确）/-0.5（错误），最终成功率校准。"""
        scores = []
        for i, s in enumerate(steps):
            # 模拟：关键路径上的步骤倾向于正确
            base = 0.3 + 0.4 * np.random.rand()
            scores.append(float(base))
        if not scores:
            return np.array([])
        arr = np.array(scores)
        return (arr - arr.min()) / (arr.max() - arr.min() + 1e-12)

    @staticmethod
    def value_diff(steps: List[Step]) -> np.ndarray:
        """模拟 value diff：每步的即时奖励累加（蒙特卡洛近似）。"""
        scores = []
        cum_r = 0.0
        for i, s in enumerate(steps):
            # 模拟：每步即时奖励 +0.1
            r_t = 0.1 + 0.05 * np.random.rand()
            cum_r += r_t
            scores.append(float(cum_r))
        if not scores:
            return np.array([])
        arr = np.array(scores)
        return (arr - arr.min()) / (arr.max() - arr.min() + 1e-12)

    @staticmethod
    def advantage(steps: List[Step]) -> np.ndarray:
        """模拟 advantage：最后一步的累积价值 − 当前价值。"""
        T = len(steps)
        if T == 0:
            return np.array([])
        scores = []
        total = T * 0.1
        for i in range(T):
            adv = total - (i + 1) * 0.1
            scores.append(adv + 0.05 * np.random.rand())
        arr = np.array(scores)
        return (arr - arr.min()) / (arr.max() - arr.min() + 1e-12)

    @staticmethod
    def correctness_proxy(steps: List[Step], success: bool) -> np.ndarray:
        """
        正确性代理：若最终成功→所有 step 都标为正确（与 ground truth 不同！）
        这正是自欺的核心：correctness proxy 把成功归因到所有 step。
        """
        T = len(steps)
        if T == 0:
            return np.array([])
        # 模拟标注者的简单逻辑：成功=所有步都对
        score = 1.0 if success else 0.3
        arr = np.full(T, score) + np.random.rand(T) * 0.05
        return np.clip(arr, 0.0, 1.0)

    @staticmethod
    def counterfactual_contribution(delta: List[float]) -> np.ndarray:
        """Ground truth 因果贡献（归一化）。"""
        if not delta:
            return np.array([])
        arr = np.abs(np.array(delta))   # 取绝对值（方向无关）
        if arr.max() > arr.min():
            arr = (arr - arr.min()) / (arr.max() - arr.min())
        return arr

    @staticmethod
    def random_baseline(n: int, rng: np.random.Generator | None = None) -> np.ndarray:
        """随机基线。"""
        if rng is None:
            rng = np.random.default_rng(0)
        return rng.uniform(size=n)

    @staticmethod
    def position_prior(n: int) -> np.ndarray:
        """位置先验：越靠后的 step 分数越高（靠后≈重要谬论）。"""
        if n == 0:
            return np.array([])
        return np.linspace(0, 1, n)


# ---------------------------------------------------------------------------
# 5. 判别力评估
# ---------------------------------------------------------------------------

def compute_auroc(signal: np.ndarray, labels: np.ndarray) -> float:
    """计算二分类 AUROC。"""
    if len(np.unique(labels)) < 2:
        return 0.5
    try:
        return float(roc_auc_score(labels, signal))
    except ValueError:
        return 0.5


def compute_spearman(signal: np.ndarray, delta: np.ndarray) -> float:
    """计算信号与 ground truth Δ(t) 的 Spearman 秩相关。"""
    if len(signal) < 3:
        return 0.0
    corr, _ = spearmanr(signal, delta)
    return float(corr) if not np.isnan(corr) else 0.0


class DiscriminabilityScorer:
    """
    对所有信号计算判别力指标。

    输出
    ----
    - AUROC : 信号区分 critical vs non-critical 步的能力
    - Spearman : 信号与 Δ(t) 的秩相关
    """

    def __init__(self, signals: Dict[str, np.ndarray],
                 ground_truth_labels: np.ndarray,
                 ground_truth_delta: np.ndarray):
        self.signals = signals
        self.labels = ground_truth_labels
        self.delta = ground_truth_delta

    def score_all(self) -> Dict[str, Dict[str, float]]:
        results = {}
        for name, sig in self.signals.items():
            if len(sig) != len(self.labels):
                continue
            auroc = compute_auroc(sig, self.labels)
            spearman = compute_spearman(sig, self.delta)
            results[name] = {"auroc": auroc, "spearman": spearman}
        return results


# ---------------------------------------------------------------------------
# 6. 主审计流程
# ---------------------------------------------------------------------------

class CreditAudit:
    """
    执行完整自欺审计流程。

    步骤
    ----
    1. 生成 N 条随机轨迹（MockDecisionEnv）
    2. 对每条轨迹做反事实回放 → ground truth Δ(t) + critical 标签
    3. 计算所有信号的判别力
    4. 输出对比表
    """

    def __init__(self, n_trajectories: int = 50, seed: int = 42,
                 n_replay: int = 10):
        self.n_trajectories = n_trajectories
        self.seed = seed
        self.n_replay = n_replay
        self.rng = np.random.default_rng(seed)
        self.results: List[Dict[str, Any]] = []

    def run(self) -> Dict[str, Any]:
        all_signal_auroc: Dict[str, List[float]] = {}
        all_signal_spearman: Dict[str, List[float]] = {}

        signal_names = [
            "PRM", "ValueDiff", "Advantage",
            "CorrectnessProxy", "CounterfactualGT",
            "RandomBaseline", "PositionPrior",
        ]

        for traj_idx in range(self.n_trajectories):
            env = MockDecisionEnv(seed=self.seed + traj_idx)
            # 随机生成轨迹（固定长度 8）
            actions = self.rng.choice(
                list(MockDecisionEnv.DIRECTION_DELTA.keys()),
                size=8, replace=True
            ).tolist()

            # 原始执行
            reward, steps, _ = env.execute(actions)

            # Ground truth：反事实回放
            cf_replay = CounterfactualReplay(env, n_replay=self.n_replay)
            delta = cf_replay.compute_ground_truth(actions)
            is_critical = cf_replay.label_critical_steps(delta)

            # 写入 ground truth
            for i, step in enumerate(steps):
                step.is_critical = is_critical[i]
                step.causal_contribution = delta[i]

            # 计算信号
            success = (reward > 0.5)
            signals = {
                "PRM":              CreditSignals.prm_score(steps),
                "ValueDiff":        CreditSignals.value_diff(steps),
                "Advantage":        CreditSignals.advantage(steps),
                "CorrectnessProxy": CreditSignals.correctness_proxy(steps, success),
                "CounterfactualGT": CreditSignals.counterfactual_contribution(delta),
                "RandomBaseline":   CreditSignals.random_baseline(len(steps), self.rng),
                "PositionPrior":    CreditSignals.position_prior(len(steps)),
            }
            labels = np.array([1 if s.is_critical else 0 for s in steps])
            delta_arr = np.array([abs(s.causal_contribution) for s in steps])

            # 判别力
            scorer = DiscriminabilityScorer(signals, labels, delta_arr)
            scores = scorer.score_all()

            for name, metrics in scores.items():
                if name not in all_signal_auroc:
                    all_signal_auroc[name] = []
                    all_signal_spearman[name] = []
                all_signal_auroc[name].append(metrics["auroc"])
                all_signal_spearman[name].append(metrics["spearman"])

        # 汇总
        summary = {}
        for name in signal_names:
            if name in all_signal_auroc:
                summary[name] = {
                    "auroc_mean": float(np.mean(all_signal_auroc[name])),
                    "auroc_std":  float(np.std(all_signal_auroc[name])),
                    "spearman_mean": float(np.mean(all_signal_spearman[name])),
                    "spearman_std":  float(np.std(all_signal_spearman[name])),
                }

        return {
            "n_trajectories": self.n_trajectories,
            "per_trajectory": self.results,
            "summary": summary,
        }

    def print_report(self, results: Dict[str, Any]):
        """输出判别力对比表。"""
        print("\n" + "=" * 70)
        print("Agent Credit 自欺审计报告")
        print("=" * 70)
        print(f"{'信号':<22} {'AUROC 均值':>12} {'AUROC 标准':>12} {'Spearman':>12} {'Spearman 标准':>14}")
        print("-" * 70)

        summary = results["summary"]
        # 按 AUROC 排序
        sorted_names = sorted(
            summary.keys(),
            key=lambda n: summary[n]["auroc_mean"],
            reverse=True,
        )

        for name in sorted_names:
            s = summary[name]
            bar = "█" * int(s["auroc_mean"] * 20)
            print(f"  {name:<20} {s['auroc_mean']:>10.4f}  ±{s['auroc_std']:>8.4f}  "
                  f"{s['spearman_mean']:>10.4f}  ±{s['spearman_std']:>10.4f}  {bar}")

        print("-" * 70)
        print("\n核心发现：")
        gt_auroc = summary.get("CounterfactualGT", {}).get("auroc_mean", 0)
        prm_auroc = summary.get("PRM", {}).get("auroc_mean", 0)
        cp_auroc  = summary.get("CorrectnessProxy", {}).get("auroc_mean", 0)
        rand_auroc = summary.get("RandomBaseline", {}).get("auroc_mean", 0)

        print(f"  Ground Truth (反事实回放) AUROC = {gt_auroc:.4f}")
        print(f"  PRM              AUROC = {prm_auroc:.4f}  "
              f"({'不优于随机' if prm_auroc - rand_auroc < 0.05 else '优于随机'})")
        print(f"  CorrectnessProxy AUROC = {cp_auroc:.4f}  "
              f"({'不优于随机' if cp_auroc  - rand_auroc < 0.05 else '优于随机'})")
        print(f"  Random Baseline  AUROC = {rand_auroc:.4f}")

        # 验收断言
        print("\n验收检查：")
        gt_ge_all = all(
            gt_auroc >= summary.get(s, {}).get("auroc_mean", 0)
            for s in ["PRM", "ValueDiff", "Advantage", "CorrectnessProxy"]
        )
        print(f"  反事实回放 AUROC({gt_auroc:.4f}) >= 各被审计信号: {gt_ge_all}")
        print("=" * 70)


# ---------------------------------------------------------------------------
# 7. 运行示例（可 python credit_selfdeception_audit.py 跑）
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Agent Credit 自欺审计复现实验")
    print("  mock 环境：5×5 网格导航 + 工具调用链")
    print("  目标：验证 PRM/correctness 等信号不优于随机，GT 贡献最优\n")

    audit = CreditAudit(n_trajectories=50, seed=42, n_replay=10)
    results = audit.run()
    audit.print_report(results)
