"""
W62-01 BO 自驾驶材料实验旁路
====================================
把 biopred 的「规则表推荐器」替换为「代理模型 + 采集函数」的贝叶斯优化闭环。

核心组件
--------
- ParameterSpace   : 参数空间（含连续/离散/约束），支持木质素 NPs 合成参数
- RFSurrogate      : 随机森林代理模型 (sklearn)，支持失败实验纳入训练
- AcquisitionFunc  : EI / UCB 采集函数（含失败惩罚项）
- BOLoop           : 闭环状态机：init / record / update / recommend

示例场景（mock 数据，标「待真机标定」）
------------------------------------------
木质素 NPs 合成收率寻优：
  连续变量: T(°C), t(min), C(wt%)
  离散变量: 溶剂(water/ethanol/acid), pH(acidic/neutral/alkaline)
  目标:    char_yield (%)

参考文献：docs/bo-自驾驶材料实验-设计.md
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import LabelEncoder

# ---------------------------------------------------------------------------
# 1. 参数空间
# ---------------------------------------------------------------------------

class ParameterSpace:
    """
    统一参数空间：支持连续变量 + 离散变量 + 线性约束。
    本实现用混合向量编码（continuous 直接归一化，discrete 用 label encoding）。
    """

    def __init__(
        self,
        continuous_bounds: Dict[str, Tuple[float, float]],
        discrete_choices: Dict[str, List[Any]],
        constraints: List[Tuple[List[str], str, float]] | None = None,
    ):
        """
        Parameters
        ----------
        continuous_bounds : {name: (lo, hi)}  连续变量上下界
        discrete_choices  : {name: [val0, val1, ...]}  离散变量可选值
        constraints       : [(param_names, '>', threshold), ...]  线性约束（暂未激活）
        """
        self.cont_names = list(continuous_bounds.keys())
        self.disc_names = list(discrete_choices.keys())
        self.cont_bounds = {k: continuous_bounds[k] for k in self.cont_names}
        self.disc_choices = {k: discrete_choices[k] for k in self.disc_names}
        self.constraints = constraints or []

        # 为每个离散变量建编码器
        self._encoders: Dict[str, LabelEncoder] = {}
        for name, choices in self.disc_choices.items():
            enc = LabelEncoder()
            enc.fit(choices)
            self._encoders[name] = enc

        self.n_continuous = len(self.cont_names)
        self.n_discrete   = len(self.disc_names)
        self.n_total      = self.n_continuous + self.n_discrete

    # ------------------------------------------------------------------ //
    def encode(self, params: Dict[str, Any]) -> np.ndarray:
        """单组参数 → 归一化数值向量。"""
        vec = np.zeros(self.n_total)
        # 连续变量：归一化到 [0, 1]
        for i, name in enumerate(self.cont_names):
            lo, hi = self.cont_bounds[name]
            vec[i] = (params[name] - lo) / (hi - lo + 1e-12)
        # 离散变量：label encoding 映射到 [0, 1]
        for j, name in enumerate(self.disc_names):
            enc = self._encoders[name]
            idx = enc.transform([params[name]])[0]
            vec[self.n_continuous + j] = idx / (len(enc.classes_) - 1 + 1e-12)
        return vec

    def decode(self, vec: np.ndarray) -> Dict[str, Any]:
        """数值向量 → 原始参数字典。"""
        params = {}
        for i, name in enumerate(self.cont_names):
            lo, hi = self.cont_bounds[name]
            params[name] = float(np.clip(vec[i] * (hi - lo) + lo, lo, hi))
        for j, name in enumerate(self.disc_names):
            enc = self._encoders[name]
            n_classes = len(enc.classes_)
            idx = int(np.clip(round(vec[self.n_continuous + j] * (n_classes - 1)),
                              0, n_classes - 1))
            params[name] = enc.inverse_transform([idx])[0]
        return params

    def sample_random(self, n: int, seed: int | None = None) -> np.ndarray:
        """拉丁超立方抽样（LHS）产生 n 组参数。"""
        rng = np.random.default_rng(seed)
        # 连续部分：LHS
        U = rng.uniform(size=(n, self.n_continuous))
        # 打散每列
        P = rng.permutation(n)
        cont = np.zeros((n, self.n_continuous))
        for i in range(self.n_continuous):
            cont[:, i] = (P + U[:, i]) / n
        # 离散部分：均匀随机
        disc = np.zeros((n, self.n_discrete))
        for j, name in enumerate(self.disc_names):
            choices = self.disc_choices[name]
            disc[:, j] = rng.integers(0, len(choices), size=n) / (len(choices) - 1 + 1e-12)
        return np.hstack([cont, disc])

    def sample_grid(self) -> np.ndarray:
        """粗网格枚举（用于对比 BO 采样效率）。"""
        # 只对连续变量做 5 档网格，离散变量取所有值
        n_cont = self.n_continuous
        n_disc = self.n_discrete
        n_levels = 5
        # 连续网格
        cont_mesh = np.meshgrid(*[np.linspace(0, 1, n_levels) for _ in range(n_cont)], indexing='ij')
        cont_grid = np.stack([m.ravel() for m in cont_mesh], axis=1)
        # 离散全展开
        disc_combos = np.array(
            [[j / (len(self.disc_choices[name]) - 1 + 1e-12)
              for name in self.disc_names]
             for j in range(len(list(self.disc_choices.values())[0]))],
        )
        # 笛卡尔积
        rows = []
        for c in cont_grid:
            for d in disc_combos:
                rows.append(np.concatenate([c, d]))
        return np.array(rows)

    def __repr__(self) -> str:
        return (f"ParameterSpace(n_cont={self.n_continuous}, n_disc={self.n_discrete}, "
                f"cont={self.cont_names}, disc={self.disc_names})")


# ---------------------------------------------------------------------------
# 2. 随机森林代理模型（支持失败实验）
# ---------------------------------------------------------------------------

class RFSurrogate:
    """
    基于 sklearn RandomForestRegressor 的代理模型。

    特性
    ----
    - 失败实验 (y=None) 的标签用 FAIL_TOKEN 编码并在训练时排除，
      但记录 failed mask 使其参与不确定性估计
    - predict 返回 (mean, std)，std 来自各棵树预测的标准差
    """

    FAIL_TOKEN: float = -999.0  # 失败实验的代理标签

    def __init__(self, n_estimators: int = 100, seed: int = 42, **rf_kwargs):
        self.n_estimators = n_estimators
        self.seed = seed
        self.rf_kwargs = rf_kwargs
        self._model: RandomForestRegressor | None = None
        self._X: np.ndarray | None = None   # 历史输入（不含失败）
        self._y: np.ndarray | None = None   # 历史输出（不含失败）
        self._failed_X: List[np.ndarray] = []   # 失败实验输入

    def fit(self, X: np.ndarray, y: np.ndarray, failed_mask: np.ndarray):
        """
        Parameters
        ----------
        X           : (N, D) 历史参数向量
        y           : (N,)  实测指标（含 None → 失败）
        failed_mask : (N,)  bool，True 表示失败实验
        """
        self._X = X
        # 失败实验单独存储
        self._failed_X = X[failed_mask].tolist() if failed_mask.any() else []
        # 训练只用成功实验
        X_ok = X[~failed_mask]
        y_ok = y[~failed_mask]
        if len(y_ok) < 2:
            self._model = None
            return self

        model = RandomForestRegressor(
            n_estimators=self.n_estimators,
            random_state=self.seed,
            **self.rf_kwargs,
        )
        model.fit(X_ok, y_ok)
        self._model = model
        return self

    def predict(self, X_cand: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """
        Parameters
        ----------
        X_cand : (M, D) 候选点

        Returns
        -------
        (mu, sigma)  预测均值与标准差
        """
        if self._model is None:
            # 没有训练数据：返回均匀预测
            return np.full(len(X_cand), 0.5), np.full(len(X_cand), 1.0)

        preds = np.array([tree.predict(X_cand) for tree in self._model.estimators_])
        mu    = preds.mean(axis=0)
        sigma = preds.std(axis=0)

        # 失败实验点的 sigma 人为放大（回避区域）
        for i, fx in enumerate(X_cand):
            if any(np.allclose(fx, f) for f in self._failed_X):
                sigma[i] *= 3.0   # 惩罚：提高不确定性

        return mu, sigma

    @property
    def n_train(self) -> int:
        return 0 if self._X is None else len(self._X)


# ---------------------------------------------------------------------------
# 3. 采集函数（含失败惩罚项）
# ---------------------------------------------------------------------------

class AcquisitionFunc:
    """
    支持 EI / UCB，含失败惩罚项。

    失败惩罚机制
    -------------
    候选点 x 若在历史上被标记为失败，采集值乘以 PENALTY_FACTOR (< 1)；
    penalty_strength 控制惩罚强度。
    """

    EI: str = "ei"
    UCB: str = "ucb"

    def __init__(
        self,
        mode: str = EI,
        xi: float = 0.01,        # EI 的提升阈值
        beta: float = 2.0,       # UCB 的探索系数
        penalty_strength: float = 0.25,  # 失败惩罚系数
        failure_history: List[np.ndarray] | None = None,
    ):
        if mode not in (self.EI, self.UCB):
            raise ValueError(f"Unknown acquisition mode: {mode}")
        self.mode = mode
        self.xi = xi
        self.beta = beta
        self.penalty_strength = penalty_strength
        self.failure_history: List[np.ndarray] = failure_history or []

    def _penalty(self, x: np.ndarray) -> float:
        """若 x 与某失败点足够近，应用惩罚系数。"""
        for f in self.failure_history:
            if np.linalg.norm(x - f) < 0.05:   # 阈值 0.05（归一化空间）
                return self.penalty_strength
        return 1.0

    def ei(self, mu: np.ndarray, sigma: np.ndarray, y_best: float) -> np.ndarray:
        """Expected Improvement (已知 sigma，无 GP 故用采样近似)。"""
        # 用蒙特卡洛近似 EI
        J = 32   # 采样次数
        eps = 1e-9
        improvement = np.zeros(len(mu))
        for _ in range(J):
            y_samp = mu + sigma * np.random.randn(len(mu))
            imp = np.maximum(y_samp - y_best - self.xi, 0.0)
            improvement += imp
        improvement /= J

        # sigma → 0 时退化为确定性改进
        with np.errstate(divide='ignore', invalid='ignore'):
            ei_vals = improvement * np.where(sigma > eps, 1.0, 0.0)
        return ei_vals

    def ucb(self, mu: np.ndarray, sigma: np.ndarray, y_best: float) -> np.ndarray:
        """Upper Confidence Bound。"""
        return mu + self.beta * sigma

    def evaluate(
        self,
        X_cand: np.ndarray,
        mu: np.ndarray,
        sigma: np.ndarray,
        y_best: float,
    ) -> np.ndarray:
        """
        在候选集上计算采集值（已含失败惩罚）。

        Returns
        -------
        acq : (M,)  采集函数值，越大约束越优先探索
        """
        if self.mode == self.EI:
            raw = self.ei(mu, sigma, y_best)
        else:
            raw = self.ucb(mu, sigma, y_best)

        # 逐点失败惩罚
        penalties = np.array([self._penalty(x) for x in X_cand])
        return raw * penalties

    def best_of(self, X_cand: np.ndarray, mu: np.ndarray,
                sigma: np.ndarray, y_best: float) -> Tuple[int, np.ndarray]:
        """返回采集值最大的候选点索引。"""
        acq = self.evaluate(X_cand, mu, sigma, y_best)
        idx = int(np.argmax(acq))
        return idx, X_cand[idx]

    def add_failure(self, x: np.ndarray):
        """记录一个失败实验点。"""
        self.failure_history.append(x.copy())


# ---------------------------------------------------------------------------
# 4. BO 闭环状态机
# ---------------------------------------------------------------------------

class BOLoop:
    """
    贝叶斯优化主循环。

    使用方法
    --------
    loop = BOLoop(space, surrogate_factory, acq_mode='ei')
    loop.init(n_init=4)                       # LHS 初始点
    while not loop.converged():
        x_next = loop.recommend()            # 采集函数选点
        y      = synthesize_and_measure(x_next)  # 真实实验
        loop.record(x_next, y)
        loop.update()
    """

    def __init__(
        self,
        space: ParameterSpace,
        surrogate_factory,        # 可调用，返回 RFSurrogate 实例
        acq_mode: str = AcquisitionFunc.EI,
        acq_xi: float = 0.01,
        acq_beta: float = 2.0,
        penalty_strength: float = 0.25,
        max_rounds: int = 30,
        y_threshold: float = 0.95,
        seed: int = 42,
    ):
        self.space      = space
        self.sur_factory = surrogate_factory
        self.acq_mode   = acq_mode
        self.acq_xi     = acq_xi
        self.acq_beta   = acq_beta
        self.penalty_strength = penalty_strength
        self.max_rounds  = max_rounds
        self.y_threshold = y_threshold
        self.seed        = seed
        self.rng         = np.random.default_rng(seed)

        self.X_history: List[np.ndarray] = []
        self.y_history: List[float | None] = []
        self.failed_mask: List[bool] = []
        self.surrogate: RFSurrogate | None = None
        self.acquisition: AcquisitionFunc | None = None
        self.round: int = 0
        self.y_best: float = -np.inf

    # ------------------------------------------------------------------ //
    def init(self, n_init: int = 4):
        """用 LHS 产生 n_init 个初始点并记录。"""
        X_init = self.space.sample_random(n_init, seed=self.seed)
        for i in range(n_init):
            self.X_history.append(X_init[i])
            self.y_history.append(None)    # 待实测填充
            self.failed_mask.append(False)
        self._build_surrogate_and_acq()
        # 假设初始点全成功（mock）
        for i in range(n_init):
            self.y_history[i] = self._mock_y(X_init[i])
        self._update_best()

    def _mock_y(self, x: np.ndarray) -> float:
        """
        Mock 木质素 NPs 收率函数（3 峰高斯混合 + 噪声）。
        真实物理：T↑ 收率先升后降；t↑ 产率趋于饱和；
        C↑ 初期线性后期抑制；酸性环境利于脱聚。
        标「待真机标定」。
        """
        # 解析归一化向量 → 物理值
        T   = x[0] * 220.0 + 80.0    # °C → [80, 300]
        t   = x[1] * 120.0 + 10.0   # min → [10, 130]
        C   = x[2] * 0.12 + 0.01     # wt% → [0.01, 0.13]
        pH_i = int(round(x[3]))     # 0=acidic, 1=neutral, 2=alkaline
        solv_i = int(round(x[4]))    # 0=water, 1=ethanol, 2=acid

        # 主效应
        base = 0.10 + 0.55 * np.exp(-((T - 170) ** 2) / 8000)   # 高斯峰 T≈170°C
        base *= (1 + 0.30 * t / 130) / 1.3                       # t 线性提升
        base *= (1 - 0.60 * C / 0.13)                            # C 抑制
        if pH_i == 0:
            base *= 1.30                                          # 酸性最优
        elif pH_i == 2:
            base *= 0.70                                          # 碱性抑制
        if solv_i == 0:
            base *= 1.10                                          # 水溶剂基准
        elif solv_i == 2:
            base *= 1.20                                          # 酸性溶剂最佳

        # 噪声
        noise = self.rng.normal(0, 0.025)
        y = np.clip(base + noise, 0.0, 1.0)
        return float(y)

    def _build_surrogate_and_acq(self):
        self.surrogate = self.sur_factory()
        self.acquisition = AcquisitionFunc(
            mode=self.acq_mode,
            xi=self.acq_xi,
            beta=self.acq_beta,
            penalty_strength=self.penalty_strength,
        )

    def record(self, x: np.ndarray, y: float | None, failed: bool = False):
        """记录一次实验结果。"""
        self.X_history.append(x.copy())
        self.y_history.append(y)
        self.failed_mask.append(failed)
        if failed:
            self.acquisition.add_failure(x)

    def update(self):
        """用全量历史（含失败）重拟合代理模型。"""
        self.round += 1
        X_arr = np.array(self.X_history)
        y_arr = np.array(self.y_history, dtype=float)
        fail_arr = np.array(self.failed_mask)

        # 失败实验标签替换为 FAIL_TOKEN（训练时排除，但影响 uncertainty）
        y_arr[fail_arr] = RFSurrogate.FAIL_TOKEN
        self.surrogate.fit(X_arr, y_arr, fail_arr)
        self._update_best()

    def _update_best(self):
        """更新当前最优 y。"""
        ok = [(y, x) for y, x, f in zip(self.y_history, self.X_history, self.failed_mask)
              if y is not None and not f]
        if ok:
            self.y_best = max(y for y, _ in ok)

    def recommend(self, candidate_pool: np.ndarray | None = None) -> np.ndarray:
        """
        采集函数推荐下一个实验点。
        若 candidate_pool 未提供，用 LHS 生成 200 个候选点。
        """
        if candidate_pool is None:
            candidate_pool = self.space.sample_random(200, seed=self.seed + self.round)

        mu, sigma = self.surrogate.predict(candidate_pool)
        idx, x_next = self.acquisition.best_of(
            candidate_pool, mu, sigma, self.y_best
        )
        return x_next

    def recommend_batch(self, k: int, candidate_pool: np.ndarray | None = None) -> List[np.ndarray]:
        """推荐 k 个点（贪心，逐点更新 surrogate）。"""
        batch = []
        X_copy = list(self.X_history)
        y_copy = list(self.y_history)
        f_copy = list(self.failed_mask)
        acq_copy = AcquisitionFunc(
            mode=self.acq_mode,
            xi=self.acq_xi,
            beta=self.acq_beta,
            penalty_strength=self.penalty_strength,
            failure_history=list(self.acquisition.failure_history),
        )

        for _ in range(k):
            if candidate_pool is None:
                pool = self.space.sample_random(200, seed=self.seed + self.round + len(batch))
            else:
                pool = candidate_pool

            mu, sigma = self.surrogate.predict(pool)
            idx, x_n = acq_copy.best_of(pool, mu, sigma, self.y_best)
            batch.append(x_n)
            # 暂存（不写入主历史）
            X_copy.append(x_n)
            y_copy.append(None)
            f_copy.append(False)
            # 临时更新用于下一步
            X_arr = np.array(X_copy)
            y_arr = np.array(y_copy, dtype=float)
            f_arr = np.array(f_copy)
            y_arr[f_arr] = RFSurrogate.FAIL_TOKEN
            self.surrogate.fit(X_arr, y_arr, f_arr)
            # 记录失败惩罚
            acq_copy.add_failure(x_n)

        return batch

    def converged(self) -> bool:
        """简单收敛判据：达到阈值 y_threshold 或超过最大轮次。"""
        if self.round >= self.max_rounds:
            return True
        ok_vals = [y for y, f in zip(self.y_history, self.failed_mask)
                   if y is not None and not f]
        if ok_vals and max(ok_vals) >= self.y_threshold:
            return True
        # 连续 5 轮 y_best 未提升
        recent = self._recent_improve_count()
        if recent >= 5:
            return True
        return False

    def _recent_improve_count(self) -> int:
        ok = [(y, i) for i, (y, f) in enumerate(zip(self.y_history, self.failed_mask))
              if y is not None and not f]
        if len(ok) < 2:
            return 0
        best_so_far = -np.inf
        count = 0
        for y, _ in reversed(ok):
            if y > best_so_far:
                best_so_far = y
                count += 1
            else:
                break
        return count

    @property
    def n_total_rounds(self) -> int:
        return self.round

    def summary(self) -> Dict[str, Any]:
        ok = [(y, x) for y, x, f in zip(self.y_history, self.X_history, self.failed_mask)
              if y is not None and not f]
        return {
            "round": self.round,
            "y_best": self.y_best,
            "n_total": len(self.X_history),
            "n_failed": sum(self.failed_mask),
            "n_success": len(ok),
            "top_params": self.space.decode(ok[-1][1]) if ok else None,
        }


# ---------------------------------------------------------------------------
# 5. 便捷工厂：木质素 NPs 参数空间
# ---------------------------------------------------------------------------

def lignin_hydrothermal_space() -> ParameterSpace:
    """
    木质素 NPs 水热合成参数空间（示例，mock 数据，待真机标定）。

    连续变量
    --------
    - T(°C)   : 80–300
    - t(min)  : 10–130
    - C(wt%)  : 0.01–0.13

    离散变量
    --------
    - 溶剂    : water / ethanol / acidic
    - pH      : acidic / neutral / alkaline
    """
    return ParameterSpace(
        continuous_bounds={
            "T": (80.0, 300.0),
            "t": (10.0, 130.0),
            "C": (0.01, 0.13),
        },
        discrete_choices={
            "solvent": ["water", "ethanol", "acidic"],
            "pH":      ["acidic", "neutral", "alkaline"],
        },
    )


def default_surrogate_factory() -> RFSurrogate:
    return RFSurrogate(n_estimators=50, seed=42, max_depth=8)


# ---------------------------------------------------------------------------
# 6. 完整 BO 运行示例（可直接 python bo_materials_loop.py 跑）
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 60)
    print("BO 自驾驶材料实验旁路 — 木质素 NPs 合成收率寻优")
    print("  [mock 数据 · 标「待真机标定」]")
    print("=" * 60)

    space = lignin_hydrothermal_space()
    print(f"\n参数空间: {space}")

    loop = BOLoop(
        space=space,
        surrogate_factory=default_surrogate_factory,
        acq_mode=AcquisitionFunc.EI,
        acq_xi=0.01,
        penalty_strength=0.25,
        max_rounds=20,
        y_threshold=0.90,
        seed=42,
    )

    loop.init(n_init=4)
    print(f"\n初始 {4} 点已完成，y_best={loop.y_best:.4f}")

    n_bo_rounds = 0
    while not loop.converged():
        x_next = loop.recommend()
        y = loop._mock_y(x_next)
        # 模拟 15% 失败率（待真机标定）
        failed = (np.random.rand() < 0.15)
        loop.record(x_next, y if not failed else None, failed=failed)
        loop.update()
        n_bo_rounds += 1
        ok = [(yi, xi) for yi, xi, fi in
              zip(loop.y_history, loop.X_history, loop.failed_mask)
              if yi is not None and not fi]
        print(f"  Round {n_bo_rounds:2d} | y={y:.4f} | "
              f"{'FAILED' if failed else 'OK':6s} | "
              f"y_best={loop.y_best:.4f} | top={space.decode(ok[-1][1]) if ok else 'N/A'}")

    print(f"\n收敛完成: {n_bo_rounds} 轮 | y_best={loop.y_best:.4f}")

    # 与全网格对比
    grid = space.sample_grid()
    print(f"\n全网格枚举 {len(grid)} 点（对比用）")
    grid_y = [loop._mock_y(x) for x in grid]
    grid_best = max(grid_y)
    print(f"  全网格最优 y={grid_best:.4f}")
    print(f"  BO 轮次 {n_bo_rounds} < 全网格 {len(grid)}: {n_bo_rounds < len(grid)}")
    print("\n[待真机标定] 以上为 mock 数据，真实实验需替换 _mock_y()")
