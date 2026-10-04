# -*- coding: utf-8 -*-
"""
W62-02 ELN 报告监督 pytest（验收：≥4 用例，断言「用 ELN 字段训练的模型
能预测 char_yield 且误差有界」）。

运行：cd /home/ubuntu/scratchpad && python -m pytest tools/test_eln_report_supervision.py -v
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
from eln_report_supervision import (
    DifferentiableLossCompiler,
    ELNRegressor,
    load_eln_data,
)

# ---------------------------------------------------------------------------
# 共享测试数据（60 行真实 CSV）
# ---------------------------------------------------------------------------

def _data():
    """返回 (X, y) 测试 fixture。"""
    X, y, fields = load_eln_data()
    return X, y


# ---------------------------------------------------------------------------
# 用例 1：CSV 加载与字段完整性
# ---------------------------------------------------------------------------

def test_csv_loads_60_rows():
    """CSV 成功加载，且包含 lignin/temp/char_yield 三字段。"""
    X, y, fields = load_eln_data()
    assert len(fields) == 2, f"字段应为 2，实际: {fields}"
    assert X.shape == (60, 2), f"X shape 应为 (60,2)，实际: {X.shape}"
    assert y.shape == (60,), f"y shape 应为 (60,)，实际: {y.shape}"
    assert fields == ["lignin", "temp"]


def test_csv_lignin_and_temp_ranges():
    """lignin ∈ [0.10, 0.50]、temp ∈ [4.09, 7.88]，与数据统计一致。"""
    X, y, _ = load_eln_data()
    assert X[:, 0].min() > 0.09, "lignin 最小值异常"
    assert X[:, 0].max() < 0.51, "lignin 最大值异常"
    assert X[:, 1].min() > 4.0, "temp 最小值异常"
    assert X[:, 1].max() < 8.0, "temp 最大值异常"


# ---------------------------------------------------------------------------
# 用例 2：回归模型 in-sample 误差有界
# ---------------------------------------------------------------------------

def test_model_in_sample_mae_bounded():
    """ELN 字段训练的 OLS 模型 in-sample MAE ≤ 1.5（真实 CSV 有界）。"""
    X, y = _data()
    model = ELNRegressor().fit(X, y)
    m = model.in_sample_metrics(X, y)
    assert m["mae"] <= 1.5, f"MAE {m['mae']:.3f} 超出有界阈值 1.5"
    assert m["r2"] > 0.5, f"R² {m['r2']:.3f} 过低，模型无效"


def test_model_in_sample_rmse_bounded():
    """in-sample RMSE ≤ 2.0。"""
    X, y = _data()
    model = ELNRegressor().fit(X, y)
    m = model.in_sample_metrics(X, y)
    assert m["rmse"] <= 2.0, f"RMSE {m['rmse']:.3f} 超出有界阈值 2.0"


# ---------------------------------------------------------------------------
# 用例 3：交叉验证误差有界（泛化质量）
# ---------------------------------------------------------------------------

def test_model_5fold_cv_mae_bounded():
    """5-fold CV MAE ≤ 3.0，验证模型有泛化能力（numpy 手写，无 sklearn）。"""
    X, y = _data()
    n = len(y)
    indices = np.arange(n)
    rng = np.random.default_rng(42)
    rng.shuffle(indices)
    folds = np.array_split(indices, 5)
    mae_list = []
    for val_idx in folds:
        tr_mask = np.ones(n, dtype=bool)
        tr_mask[val_idx] = False
        tr_idx = indices[tr_mask]
        model = ELNRegressor().fit(X[tr_idx], y[tr_idx])
        yp = model.predict(X[val_idx])
        mae_list.append(float(np.mean(np.abs(yp - y[val_idx]))))

    cv_mae = np.mean(mae_list)
    assert cv_mae <= 3.0, f"5-fold CV MAE {cv_mae:.3f} 超出有界阈值 3.0"


# ---------------------------------------------------------------------------
# 用例 4：字段级损失编译骨架——lignin 约束路径存在且非负
# ---------------------------------------------------------------------------

def test_lignin_loss_path_exists():
    """DifferentiableLossCompiler 对 lignin 字段返回非负损失。"""
    X, y = _data()
    model = ELNRegressor().fit(X, y)
    compiler = DifferentiableLossCompiler(model)
    compiler.add_constraint(
        "lignin", "monotonic_dec",
        weight=1.0,
        description="lignin 升高不利于产炭",
    )
    loss = compiler.compute_loss(X, y)
    assert loss >= 0.0, f"损失应为非负，实际: {loss}"


def test_compile_report_adds_constraint():
    """compile_report 从一句话提取出约束建议。"""
    X, y = _data()
    model = ELNRegressor().fit(X, y)
    compiler = DifferentiableLossCompiler(model)
    result = compiler.compile_report(
        "lignin 升高不利于产炭，建议降低木质素含量以提高炭产率。", X, y
    )
    assert "lignin" in result["constraints_registered"][0]
    assert result["total_loss"] >= 0.0
