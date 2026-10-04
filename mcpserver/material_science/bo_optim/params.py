"""BO 参数空间定义：连续 / 离散 / 约束，内置木质素水热合成示例。

设计要点：
- continuous: 连续参数 {name: (low, high)}，编码时标准化到 [0, 1]。
- categorical: 离散参数 {name: [choices, ...]}，编码时 one-hot。
- constraints: 硬约束列表 [{"name": ..., "min": ..., "max": ...}]，在 validate 时检查。
- 范围与约束均为设计假设（继承 ALPHA 线 §六），非实测，落地前逐项"待真机"。
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np


class ParameterSpace:
    """混合变量（连续 + 离散）参数空间。

    编码约定（encode 输出的向量维度 dim = len(continuous) + Σ len(choices)）：
      [0..n_c)             连续参数，标准化到 [0, 1]
      [n_c..dim)           离散参数，逐组 one-hot
    """

    def __init__(
        self,
        continuous: Dict[str, Tuple[float, float]] | None = None,
        categorical: Dict[str, Sequence[str]] | None = None,
        constraints: List[Dict[str, Any]] | None = None,
    ) -> None:
        self.continuous: Dict[str, Tuple[float, float]] = dict(continuous or {})
        # 保证离散选项有序，编码/解码稳定
        self.categorical: Dict[str, List[str]] = {
            k: list(v) for k, v in (categorical or {}).items()
        }
        self.constraints: List[Dict[str, Any]] = list(constraints or [])

    # ---- 结构 ----
    @property
    def continuous_names(self) -> List[str]:
        return list(self.continuous.keys())

    @property
    def categorical_names(self) -> List[str]:
        return list(self.categorical.keys())

    @property
    def dim(self) -> int:
        n_cat = sum(len(v) for v in self.categorical.values())
        return len(self.continuous) + n_cat

    def _cat_slices(self) -> Dict[str, Tuple[int, int]]:
        """每个离散参数在编码向量中的 one-hot 切片 [start, end)。"""
        slices: Dict[str, Tuple[int, int]] = {}
        offset = len(self.continuous)
        for name, choices in self.categorical.items():
            slices[name] = (offset, offset + len(choices))
            offset += len(choices)
        return slices

    # ---- 编码 / 解码 ----
    def encode(self, point: Dict[str, Any]) -> np.ndarray:
        """把配方 dict 编码为浮点向量（连续标准化 + 离散 one-hot）。"""
        vec: List[float] = []
        for name, (lo, hi) in self.continuous.items():
            if name not in point:
                raise ValueError(f"缺连续参数: {name}")
            v = float(point[name])
            if hi == lo:
                raise ValueError(f"连续参数 {name} 区间为空 (low==high)")
            vec.append((v - lo) / (hi - lo))
        slices = self._cat_slices()
        for name, choices in self.categorical.items():
            if name not in point:
                raise ValueError(f"缺离散参数: {name}")
            if point[name] not in choices:
                raise ValueError(f"离散参数 {name} 取值 {point[name]!r} 不在 {choices!r}")
            start, end = slices[name]
            one_hot = [0.0] * (end - start)
            one_hot[choices.index(point[name])] = 1.0
            vec.extend(one_hot)
        return np.asarray(vec, dtype=float)

    def decode(self, vec: Sequence[float]) -> Dict[str, Any]:
        """把浮点向量解码回配方 dict（离散取 one-hot 最大者）。"""
        vec = list(vec)
        if len(vec) != self.dim:
            raise ValueError(f"向量维度 {len(vec)} != 空间维度 {self.dim}")
        point: Dict[str, Any] = {}
        n_c = len(self.continuous)
        for i, (name, (lo, hi)) in enumerate(self.continuous.items()):
            point[name] = lo + vec[i] * (hi - lo)
        slices = self._cat_slices()
        for name, choices in self.categorical.items():
            start, end = slices[name]
            block = vec[start:end]
            point[name] = choices[int(np.argmax(block))]
        return point

    # ---- 校验 ----
    def validate(self, point: Dict[str, Any]) -> None:
        """校验配方是否在空间与约束内；不合法抛 ValueError。"""
        for name, (lo, hi) in self.continuous.items():
            if name not in point:
                raise ValueError(f"缺连续参数: {name}")
            v = float(point[name])
            if not (lo <= v <= hi):
                raise ValueError(f"连续参数 {name}={v} 越界 [{lo}, {hi}]")
        for name, choices in self.categorical.items():
            if name not in point:
                raise ValueError(f"缺离散参数: {name}")
            if point[name] not in choices:
                raise ValueError(f"离散参数 {name} 取值 {point[name]!r} 不在 {choices!r}")
        for c in self.constraints:
            name = c.get("name")
            lo = c.get("min")
            hi = c.get("max")
            if name not in point:
                continue
            v = float(point[name])
            if lo is not None and v < lo:
                raise ValueError(f"约束违反: {name}={v} < {lo}")
            if hi is not None and v > hi:
                raise ValueError(f"约束违反: {name}={v} > {hi}")

    # ---- 采样 ----
    def sample(self, n: int, rng: np.random.Generator | None = None) -> List[Dict[str, Any]]:
        """在空间内随机采 n 个合法配方（用于采集函数的候选集）。"""
        rng = rng or np.random.default_rng(0)
        points: List[Dict[str, Any]] = []
        for _ in range(n):
            p: Dict[str, Any] = {}
            for name, (lo, hi) in self.continuous.items():
                p[name] = float(rng.uniform(lo, hi))
            for name, choices in self.categorical.items():
                p[name] = str(rng.choice(choices))
            points.append(p)
        return points

    def grid(self, n_per_cont: int = 5) -> List[Dict[str, Any]]:
        """连续参数均匀切分 × 离散全枚举，生成结构化候选点（用于确定性候选集）。"""
        grids = [np.linspace(lo, hi, n_per_cont) for (lo, hi) in self.continuous.values()]
        import itertools

        points: List[Dict[str, Any]] = []
        cont_names = self.continuous_names
        cat_names = self.categorical_names
        cat_choices = [self.categorical[n] for n in cat_names]
        for cont_vals in itertools.product(*grids):
            for cat_vals in itertools.product(*cat_choices):
                p = dict(zip(cont_names, (float(v) for v in cont_vals)))
                p.update(dict(zip(cat_names, cat_vals)))
                points.append(p)
        return points


def lignin_hydrothermal_space() -> ParameterSpace:
    """内置示例：木质素 NPs 水热合成参数空间（范围/约束为设计假设，待真机）。"""
    continuous = {
        "T": (140.0, 220.0),   # 水热温度 °C
        "t": (2.0, 24.0),      # 保温时间 h
        "C": (1.0, 20.0),      # 木质素浓度 mg/mL
        "R": (1.0, 10.0),      # 前驱体/交联剂质量比
    }
    categorical = {
        "S": ["纯水", "乙醇-水"],          # 溶剂体系
        "pH": ["酸性", "中性", "碱性"],      # pH 档
        "L": ["碱木质素", "酶解木质素", "其他"],  # 木质素来源
    }
    constraints = [
        {"name": "T", "max": 220.0},   # 设备温度上限
        {"name": "C", "max": 18.0},    # 原料批次溶解度上限（假设，待真机）
    ]
    return ParameterSpace(continuous=continuous, categorical=categorical, constraints=constraints)
