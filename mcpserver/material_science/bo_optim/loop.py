"""BO 闭环：初始点 → 批量推荐 → 实测回填 → 更新代理；支持失败实验纳入。

多目标（映射 3）一期用标量化 scalarize（加权 + 方向），二期 Pareto/EHVI 留扩展点。
失败实验（映射 1）以 FAILED_OBJECTIVE 占位目标进训练集，采集函数叠加失败邻域惩罚。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from .acquisition import recommend as _acq_recommend
from .params import ParameterSpace, lignin_hydrothermal_space
from .surrogate import make_surrogate

# 失败实验的目标占位值：给"域内最差值"级别的低分，让代理模型学会避开失败区域（映射 1）。
FAILED_OBJECTIVE = -1e18


def scalarize(metrics: Dict[str, Any], objectives: Sequence[Dict[str, Any]]) -> float:
    """多目标标量化：返回"越大越好"的加权分数。

    objectives 元素: {"name", "direction" ∈ {max, min, target}, "weight", "low", "high"}。
    - max:  (v - low) / span
    - min:  (high - v) / span
    - target: 落在 [low, high] 得 1，越界按距离线性衰减。
    缺测指标（value 为 None）不参与，不臆造。
    """
    total = 0.0
    for obj in objectives:
        name = obj["name"]
        direction = obj["direction"]
        weight = float(obj.get("weight", 1.0))
        lo = float(obj["low"])
        hi = float(obj["high"])
        span = (hi - lo) if hi > lo else 1.0
        v = metrics.get(name) if metrics is not None else None
        if v is None:
            continue
        v = float(v)
        if direction == "max":
            norm = (v - lo) / span
        elif direction == "min":
            norm = (hi - v) / span
        elif direction == "target":
            if lo <= v <= hi:
                norm = 1.0
            elif v < lo:
                norm = 1.0 - (lo - v) / span
            else:
                norm = 1.0 - (v - hi) / span
        else:
            raise ValueError(f"未知 direction: {direction!r}（可选 max / min / target）")
        total += weight * float(np.clip(norm, -10.0, 10.0))
    return float(total)


def lignin_objectives() -> List[Dict[str, Any]]:
    """木质素 NPs 水热合成的多目标定义（方向/权重/归一化区间为设计假设，待真机）。"""
    return [
        {"name": "yield", "direction": "max", "weight": 1.0, "low": 0.0, "high": 0.5},
        {"name": "pdi", "direction": "min", "weight": 1.0, "low": 0.0, "high": 1.0},
        {"name": "size_nm", "direction": "target", "weight": 0.8, "low": 100.0, "high": 300.0},
    ]


class BOLoop:
    """BO 闭环状态机。

    用法:
        loop = BOLoop(lignin_hydrothermal_space())
        initial = loop.init(n=4)                    # 返回 n 个初始粗扫配方（待测）
        ... 实测 initial 每个配方 ...
        loop.record(initial[0], {"yield":0.31, "pdi":0.26, "size_nm":210})
        loop.record(bad_point, failed=True)         # 失败实验也纳入
        loop.update()                               # 用全量历史（含失败）重拟合代理
        batch = loop.recommend_batch(k=3)           # 下一批配方（可导出 CSV）
    """

    def __init__(
        self,
        space: ParameterSpace,
        surrogate=None,
        strategy: str = "ei",
        objectives: Sequence[Dict[str, Any]] | None = None,
        n_candidates: int = 256,
        seed: int = 0,
        failure_penalty: float = 0.0,
    ) -> None:
        self.space = space
        self.strategy = strategy
        self.objectives = list(objectives) if objectives is not None else lignin_objectives()
        self.n_candidates = n_candidates
        self.rng = np.random.default_rng(seed)
        self.failure_penalty = failure_penalty
        self.surrogate = surrogate if surrogate is not None else make_surrogate("rf")

        self.X: List[np.ndarray] = []                 # 已观测编码向量
        self.y: List[float] = []                      # 标量化目标（失败为 FAILED_OBJECTIVE）
        self.failed: List[bool] = []                  # 失败标记
        self.points: List[Dict[str, Any]] = []        # 已观测原始配方
        self.metrics: List[Dict[str, Any] | None] = []  # 原始指标（失败为 None）
        self.pending: List[Dict[str, Any]] = []       # 待测配方（init 产出、未回填）
        self._surrogate_fitted = False

    # ---- 状态 ----
    def n_observations(self) -> int:
        return len(self.X)

    def y_best(self) -> float | None:
        ok = [v for v, f in zip(self.y, self.failed) if not f]
        return float(max(ok)) if ok else None

    def surrogate_is_ready(self) -> bool:
        """有 ≥2 个有效（非失败）观测时，代理模型才有可学的信号。"""
        return sum(1 for f in self.failed if not f) >= 2

    # ---- 初始点 ----
    def init(
        self,
        n: int | None = None,
        warm_start: Sequence[Dict[str, Any]] | None = None,
    ) -> List[Dict[str, Any]]:
        """采样 n 个初始粗扫配方（写入 pending，等待实测回填），并返回它们。

        warm_start: 历史记录预热（映射 5）。每条为 {"recipe": {...}, "metrics": {...}}
        或 {"recipe": {...}, "failed": True}，直接进训练集。
        """
        if warm_start:
            for rec in warm_start:
                recipe = rec.get("recipe", rec)
                self.record(
                    recipe,
                    rec.get("metrics"),
                    failed=bool(rec.get("failed", False)),
                    objective=rec.get("objective"),
                )
        n = n if n is not None else 0
        new_points: List[Dict[str, Any]] = []
        if n > 0:
            new_points = [self.space.sample(1, self.rng)[0] for _ in range(n)]
            self.pending.extend(new_points)
        return [dict(p) for p in new_points]

    def pending_recipes(self) -> List[Dict[str, Any]]:
        return [dict(p) for p in self.pending]

    def _drop_pending(self, point: Dict[str, Any]) -> None:
        """把已回填的点从待测队列移除，避免与已观测点重复。"""
        if not self.pending:
            return
        enc = self.space.encode(point)
        self.pending = [
            p for p in self.pending
            if not np.allclose(self.space.encode(p), enc, atol=1e-9)
        ]

    @staticmethod
    def _recipe_key(space: ParameterSpace, p: Dict[str, Any]):
        parts = [(n, round(float(p[n]), 8)) for n in space.continuous_names]
        parts += [(n, p[n]) for n in space.categorical_names]
        return tuple(parts)

    # ---- 推荐 ----
    def recommend(self, k: int = 1, strategy: str | None = None) -> List[Dict[str, Any]]:
        """用采集函数选出 k 个下一实验点（配方 dict 列表，不重复）。"""
        strategy = strategy or self.strategy
        # 候选集 = 随机采样 + 已观测/待测点（保留已探区域）
        cand_points = self.space.sample(self.n_candidates, self.rng)
        known = self.points + self.pending
        if known:
            cand_points = known + cand_points
        cand_X = np.asarray([self.space.encode(p) for p in cand_points])

        failed_X = (
            np.asarray([self.X[i] for i, f in enumerate(self.failed) if f], dtype=float)
            if any(self.failed)
            else None
        )

        # 数据不足或模型未就绪 → 随机；否则先确保代理已拟合
        if not self.surrogate_is_ready():
            strategy = "random"
        elif not self._surrogate_fitted:
            self.update()

        _, scores = _acq_recommend(
            self.surrogate,
            cand_X,
            strategy,
            y_best=self.y_best(),
            rng=self.rng,
            failed_points=failed_X,
            failure_penalty=self.failure_penalty,
        )

        k = min(int(k), len(scores))
        order = np.argsort(scores)[::-1]
        picked: List[Dict[str, Any]] = []
        seen = set()
        for i in order:
            if len(picked) >= k:
                break
            recipe = self.space.decode(cand_X[i])
            key = self._recipe_key(self.space, recipe)
            if key in seen:
                continue
            seen.add(key)
            picked.append(recipe)
        return picked

    def recommend_batch(self, k: int = 1) -> List[Dict[str, Any]]:
        """批量推荐 k 个下一实验点（与 xtalyst 衔接：可导出为下一批配方表 CSV）。"""
        return self.recommend(k=k)

    # ---- 回填 ----
    def record(
        self,
        point: Dict[str, Any],
        metrics: Dict[str, Any] | None = None,
        *,
        failed: bool = False,
        objective: float | None = None,
    ) -> None:
        """回填一次实测。

        - 成功：metrics 给原始指标，内部用 scalarize 转目标；也可直接给 objective。
        - 失败：failed=True（或 metrics 缺失），目标置 FAILED_OBJECTIVE，仍进训练集（映射 1）。
        """
        self.space.validate(point)
        self._drop_pending(point)
        self.points.append(dict(point))
        self.X.append(self.space.encode(point))
        if failed or (metrics is None and objective is None):
            self.failed.append(True)
            self.y.append(FAILED_OBJECTIVE)
            self.metrics.append(None)
        else:
            self.failed.append(False)
            val = objective if objective is not None else scalarize(metrics or {}, self.objectives)
            self.y.append(float(val))
            self.metrics.append(dict(metrics) if metrics is not None else None)
        self._surrogate_fitted = False  # 数据变化，代理需重拟合

    # ---- 更新 ----
    def update(self) -> None:
        """用全量历史（含失败点）重拟合代理模型。"""
        if len(self.X) == 0:
            return
        X = np.asarray(self.X, dtype=float)
        y = np.asarray(self.y, dtype=float)
        self.surrogate.fit(X, y)
        self._surrogate_fitted = True

    # ---- 导出 ----
    def export_recipes(self, points: Sequence[Dict[str, Any]] | None = None) -> List[Dict[str, Any]]:
        """把配方列表导出为可写 CSV 的 dict 列表（键 = 参数名）。"""
        pts = points if points is not None else self.points
        return [dict(p) for p in pts]
