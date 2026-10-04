"""M33 可解释描述符库 原型测试（pytest）。

运行：python -m pytest tools/test_biomass_descriptors.py -q
验收：≥20 个可解释描述符 + 预测案例（char_yield 线性模型 R² 达阈值）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
from biomass_descriptors import (
    DESCRIPTORS,
    BiomassStructure,
    compute_descriptors,
    descriptor_names,
    fit_char_yield_model,
    make_synthetic_samples,
    symbolic_formula_selection,
)


def test_at_least_20_descriptors():
    assert len(DESCRIPTORS) >= 20, f"描述符数量不足: {len(DESCRIPTORS)}"


def test_descriptors_computable_and_finite():
    d = compute_descriptors(BiomassStructure())
    assert len(d) == len(DESCRIPTORS)
    for k, v in d.items():
        assert np.isfinite(v), f"描述符 {k} 非有限值: {v}"


def test_prediction_case_r2():
    X, y, names = make_synthetic_samples(seed=0)
    assert X.shape[1] == len(names) == len(DESCRIPTORS)
    w, b = fit_char_yield_model(X, y)
    yhat = X @ w + b
    r2 = 1 - float(np.sum((y - yhat) ** 2) / np.sum((y - y.mean()) ** 2))
    # 合成数据 char_yield 主要由 lignin_content + 温度驱动，线性模型应能较好拟合
    assert r2 >= 0.8, f"预测案例 R² 过低: {r2:.3f}"


def test_symbolic_formula_selection():
    X, y, names = make_synthetic_samples(seed=0)
    formulas = symbolic_formula_selection(X, y, names)
    # 最优可解释式 R² 高
    top_formula, top_r2 = formulas[0]
    assert top_r2 >= 0.85, f"最优符号式 R² 过低: {top_formula} {top_r2:.3f}"
    # 最优式应包含温度（过程条件）或木质素相关描述符（真值驱动因素）
    assert ("pyrolysis_temperature" in top_formula
            or "lignin" in top_formula
            or "aromatic" in top_formula
            or "methoxy" in top_formula), f"最优式未含预期驱动描述符: {top_formula}"
