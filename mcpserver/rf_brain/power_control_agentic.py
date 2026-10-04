"""射频大脑 · Agentic Autoresearch 功率控制（R55）

授粉自 digest-g1-4 2608.26093（Agentic Autoresearch for Cell-Edge Power Control）：
无线资源管理算法的设计（架构/损失/调参）本身是劳动密集的，LLM 可自动完成
「候选策略生成 → 仿真验证 → 迭代改进」的自动研究循环，替代人工调参。

原型落地（无真实 LLM，诚实降级标注）：
  - SyntheticCellScenario  合成多小区场景：路径损耗 + 小区间干扰 + 噪声，
                            吞吐 = Σ log2(1+SINR)（Shannon 可达率求和）
  - rule_pool              候选功率控制策略池（固定满功率/均匀回退/SINR 目标/
                            小区边缘优先/贪心降干扰）
  - PowerControlAgent      自动研究循环：评估规则池 → 选最优 → 参数微调（模拟
                            LLM 的「改进」动作）→ 迭代 N 轮保留最优
  - generator / reviewer   可替换挂钩（缺省为启发式；接真实 LLM 时注入即可，
                            循环结构不变）

验收口径：合成小区场景下，Agent 找到的功率策略吞吐较「固定满功率」提升 ≥10%。
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

# --------------------------------------------------------------------------- #
# 场景 / 吞吐
# --------------------------------------------------------------------------- #


def _path_loss_gain(dist: float, d0: float = 5.0, alpha: float = 2.0) -> float:
    """简化路径损耗增益 g = 1 / (1 + (d/d0)^alpha)（无单位，仅用于合成对比）。"""
    return float(1.0 / (1.0 + (dist / d0) ** alpha))


@dataclass
class SyntheticCellScenario:
    """合成多小区场景：AP 位置 + 用户位置 → 增益矩阵 G（G[i,j]=AP_i→用户_j 增益）。

    - gain_matrix[i, j]：小区 i 的 AP 到用户 j 的信道增益（对角线为服务链路）
    - noise_floor：加性噪声功率（相对满功率，越小越干扰受限）
    """

    ap_positions: np.ndarray
    ue_positions: np.ndarray
    noise_floor: float = 0.01
    gain_matrix: np.ndarray = field(init=False)

    def __post_init__(self) -> None:
        aps = np.asarray(self.ap_positions, dtype=float)
        ues = np.asarray(self.ue_positions, dtype=float)
        if aps.shape != ues.shape or aps.ndim != 1:
            raise ValueError("ap_positions 与 ue_positions 必须等长一维")
        k = aps.size
        g = np.zeros((k, k), dtype=float)
        for i in range(k):
            for j in range(k):
                g[i, j] = _path_loss_gain(abs(float(aps[i] - ues[j])))
        self.gain_matrix = g

    @property
    def n_users(self) -> int:
        return self.gain_matrix.shape[0]

    def throughput(self, power: np.ndarray) -> float:
        """Σ log2(1+SINR) 可达率求和（bit/s/Hz 量纲），越大越好。"""
        p = np.asarray(power, dtype=float)
        if p.shape != (self.n_users,):
            raise ValueError(f"power 长度须为 {self.n_users}")
        g = self.gain_matrix
        total = 0.0
        for i in range(self.n_users):
            sig = p[i] * g[i, i]
            interf = float(sum(p[j] * g[j, i] for j in range(self.n_users) if j != i))
            sinr = sig / (interf + self.noise_floor)
            total += float(np.log2(1.0 + sinr))
        return total


# --------------------------------------------------------------------------- #
# 规则池（候选功率控制策略）
# --------------------------------------------------------------------------- #

def _full_power(sc: SyntheticCellScenario) -> np.ndarray:
    """固定满功率（基线）。"""
    return np.ones(sc.n_users, dtype=float)


def _uniform_backoff(sc: SyntheticCellScenario, alpha: float = 0.5) -> np.ndarray:
    """均匀回退：全体 × alpha（降低总干扰）。"""
    return np.full(sc.n_users, float(alpha))


def _cell_edge_priority(sc: SyntheticCellScenario, center_power: float = 0.4) -> np.ndarray:
    """小区边缘优先：服务链路弱的用户满功率，链路强的中心用户回退（少干扰邻居）。

    中心用户（强直连）即使回退也能维持较高 SINR，同时大幅减少对边缘用户的
    同频干扰——这是「cell-edge power control」的核心权衡。映射反向：直连越强
    （ratio→1）越该回退到 center_power，直连越弱（ratio→0）越该满功率。
    """
    g = sc.gain_matrix
    direct = np.array([g[i, i] for i in range(sc.n_users)])
    strongest = float(direct.max())
    p = np.ones(sc.n_users, dtype=float)
    for i in range(sc.n_users):
        ratio = direct[i] / strongest
        p[i] = center_power + (1.0 - center_power) * (1.0 - ratio)
    return p


def _sinr_target(sc: SyntheticCellScenario, target_db: float = 6.0, iters: int = 50) -> np.ndarray:
    """Foschini-Miljanic SINR 目标功率控制：迭代 P ← P·γ_target/SINR，收敛到最小
    功率满足目标 SINR（目标不可行时退回满功率），并夹到 [0,1]。"""
    gamma = 10.0 ** (target_db / 10.0)
    g = sc.gain_matrix
    p = np.ones(sc.n_users, dtype=float)
    for _ in range(iters):
        p_new = np.empty_like(p)
        for i in range(sc.n_users):
            interf = float(sum(p[j] * g[j, i] for j in range(sc.n_users) if j != i))
            sinr = p[i] * g[i, i] / (interf + sc.noise_floor)
            p_new[i] = p[i] * gamma / max(sinr, 1e-9)
        p = np.clip(p_new, 0.0, 1.0)
    return p


# 规则池：名字 → 策略函数（每个策略以场景为输入，返回功率向量）
def default_rule_pool() -> dict[str, callable]:
    return {
        "fixed_full": _full_power,
        "uniform_backoff_half": lambda sc: _uniform_backoff(sc, 0.5),
        "cell_edge_priority": _cell_edge_priority,
        "sinr_target_6db": lambda sc: _sinr_target(sc, target_db=6.0),
    }


# --------------------------------------------------------------------------- #
# 自动研究 Agent
# --------------------------------------------------------------------------- #


@dataclass
class PowerControlResult:
    """功率控制搜索结果。"""
    best_policy: str               # 最优策略名
    best_power: np.ndarray         # 最优功率向量
    throughput: float              # 最优吞吐
    baseline_throughput: float     # 满功率基线吞吐
    improvement: float             # 相对提升（线性比，≥1 表示提升）
    rounds: list[dict] = field(default_factory=list)  # 每轮评估记录（可审计）


class PowerControlAgent:
    """Agentic Autoresearch 功率控制 Agent。

    循环：评估规则池 → 选最优 → 对最优策略做参数微调（模拟 LLM 的改进动作）
    → 迭代。``generator``/``reviewer`` 为可替换挂钩（接真实 LLM 时注入），
    缺省用启发式微调，不依赖外部服务。
    """

    def __init__(self, rule_pool: dict[str, callable] | None = None,
                 refinement_grid: tuple[float, ...] = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
                 rounds: int = 3, seed: int | None = None) -> None:
        self.rule_pool = rule_pool or default_rule_pool()
        self.refinement_grid = refinement_grid
        self.rounds = rounds
        self._rng = np.random.default_rng(seed)

    def search(self, scenario: SyntheticCellScenario) -> PowerControlResult:
        """执行自动研究：返回最优策略与相对满功率的吞吐提升。"""
        baseline = scenario.throughput(_full_power(scenario))

        best_name, best_power, best_tp = "fixed_full", _full_power(scenario), baseline
        log: list[dict] = []

        # 第 1 轮：评估规则池
        for name, fn in self.rule_pool.items():
            p = np.asarray(fn(scenario), dtype=float)
            tp = scenario.throughput(p)
            log.append({"round": 1, "policy": name, "throughput": tp})
            if tp > best_tp:
                best_name, best_power, best_tp = name, p, tp

        # 后续轮：对当前最优策略做参数微调（模拟 LLM 改进动作，grid 搜索）
        for r in range(2, self.rounds + 1):
            refined = self._refine(scenario, best_power)
            tp = scenario.throughput(refined)
            log.append({"round": r, "policy": f"{best_name}+refine", "throughput": tp})
            if tp > best_tp:
                best_power, best_tp = refined, tp
                best_name = f"{best_name}+refine"

        return PowerControlResult(
            best_policy=best_name,
            best_power=best_power,
            throughput=best_tp,
            baseline_throughput=baseline,
            improvement=(best_tp / baseline if baseline > 0 else float("inf")),
            rounds=log,
        )

    def _refine(self, scenario: SyntheticCellScenario, base: np.ndarray) -> np.ndarray:
        """启发式微调：对每个用户尝试缩放功率，仅接受提升吞吐的移动（贪心）。

        模拟「LLM 提出改进并仿真验证」的取舍；接真实 LLM 时替换为 LLM 生成的
        候选策略即可，循环结构不变。
        """
        best = np.array(base, dtype=float)
        best_tp = scenario.throughput(best)
        for i in range(scenario.n_users):
            for alpha in self.refinement_grid:
                cand = best.copy()
                cand[i] = float(alpha)
                tp = scenario.throughput(cand)
                if tp > best_tp:
                    best, best_tp = cand, tp
        return best


def default_scenario(seed: int = 0) -> SyntheticCellScenario:
    """构造一个「小区边缘干扰受限」的合成场景（可复现）。

    3 个 AP、3 个用户，中间用户是强直连的中心用户，两侧是弱直连的边缘用户——
    满功率下中心用户把边缘用户同频干扰压垮，回退中心用户能显著提升总吞吐。
    """
    rng = np.random.default_rng(seed)
    aps = np.array([0.0, 10.0, 20.0])
    # 用户 0/2 远离服务 AP（边缘），用户 1 紧贴服务 AP（中心）
    ues = aps + rng.uniform(-3.0, 3.0, size=3)
    ues[1] = aps[1] + rng.uniform(-0.3, 0.3)  # 中心用户直连极强
    return SyntheticCellScenario(ap_positions=aps, ue_positions=ues, noise_floor=0.01)


__all__ = [
    "SyntheticCellScenario",
    "PowerControlAgent",
    "PowerControlResult",
    "default_rule_pool",
    "default_scenario",
]
