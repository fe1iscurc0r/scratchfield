"""BO 寻优旁路（旁路，独立目录，不碰 biopred 主流程）。

把 Xtalyst wet-dry loop 的"规则表推荐器"升级为"代理模型 + 采集函数"的主动学习寻优：
- params.py      参数空间（连续/离散/约束）+ 木质素水热合成示例
- surrogate.py   代理模型（随机森林 / numpy 手写 GP）：fit / predict / uncertainty
- acquisition.py 采集函数（EI / UCB / 随机）：选下一个实验点
- loop.py        闭环：初始点 → 批量推荐 → 实测回填 → 更新代理（支持失败实验）
- cli.py         CLI：init / recommend / record 子命令

硬约束：纯 Python + 轻依赖（numpy 必需；sklearn 用于 RF 代理，GP 降级路径可无；pandas 仅 CSV 导出可选）。
真实实验数据留真机，本包以合成数据验收。
"""
from .acquisition import (
    expected_improvement,
    random_score,
    recommend,
    upper_confidence_bound,
)
from .loop import BOLoop, lignin_objectives, scalarize
from .params import ParameterSpace, lignin_hydrothermal_space
from .surrogate import (
    GaussianProcessSurrogate,
    RandomForestSurrogate,
    make_surrogate,
)

__all__ = [
    "ParameterSpace",
    "lignin_hydrothermal_space",
    "RandomForestSurrogate",
    "GaussianProcessSurrogate",
    "make_surrogate",
    "expected_improvement",
    "upper_confidence_bound",
    "random_score",
    "recommend",
    "BOLoop",
    "lignin_objectives",
    "scalarize",
]
