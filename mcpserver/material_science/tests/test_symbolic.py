"""test_symbolic.py — 符号回归旁路验收（≥6 用例）。

运行：python -m pytest mcpserver/material_science/tests/test_symbolic.py -q
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from mcpserver.material_science.symbolic import Expression, evaluate, fit, self_test
from mcpserver.material_science.symbolic.cli import main
from mcpserver.material_science.symbolic.encode_eval import compare_encodings


def test_fit_synthetic_linear():
    """合成数据拟合：y = 3*x0 + 2 应收敛到低误差显式表达式。"""
    x0 = np.linspace(-3.0, 3.0, 40)
    y = 3.0 * x0 + 2.0
    res = fit(x0, y, population_size=200, generations=30, random_state=0)
    assert res.rmse < 0.1
    assert res.expression.variables == ["x0"]
    assert res.r2 > 0.99


def test_fit_self_test():
    """内置合成数据自测应通过。"""
    out = self_test()
    assert out["ok"] is True
    assert isinstance(out["expression"], str)


def test_expression_evaluate():
    """表达式求值（标量 + 向量）。"""
    expr = Expression("2.0*x0 + 1.0")
    assert abs(expr.evaluate({"x0": 3.0}) - 7.0) < 1e-9
    out = expr.evaluate({"x0": np.array([0.0, 1.0, 2.0])})
    np.testing.assert_allclose(out, np.array([1.0, 3.0, 5.0]))
    # 模块级 evaluate 入口
    assert abs(evaluate(expr, {"x0": 1.0}) - 3.0) < 1e-9


def test_expression_save_load(tmp_path):
    """表达式 JSON 保存/加载往返一致。"""
    expr = Expression("x0**2 - x1")
    p = tmp_path / "expr.json"
    expr.save(p)
    loaded = Expression.load(p)
    assert loaded.text == expr.text
    assert loaded.variables == ["x0", "x1"]


def test_expression_format():
    """LaTeX / 文本格式化。"""
    expr = Expression("3.0*x0 + 2.0")
    assert expr.to_text() == "3.0*x0 + 2.0"
    latex = expr.to_latex()
    assert "x0" in latex
    assert "cdot" in latex


def test_expression_bad_input():
    """坏输入：语法错误 / 不支持结构 / 缺变量 / 非法函数。"""
    with pytest.raises(ValueError):
        Expression("x0 +")                      # 语法错误
    with pytest.raises(ValueError):
        Expression("__import__('os')")          # 不支持函数调用
    with pytest.raises(ValueError):
        Expression("foo(1)")                    # 非法函数
    with pytest.raises(ValueError):
        Expression("2*x0").evaluate({})         # 缺变量值


def test_encode_eval_table():
    """编码对比表：三种编码齐全，R² 合法，图编码以最少维度达近乎完美拟合。"""
    table = compare_encodings()
    assert len(table) == 3
    by_name = {r["encoding"]: r for r in table}
    assert set(by_name) == {"指纹(哈希 256bit)", "图(拓扑描述符)", "序列(unigram+bigram)"}
    for r in table:
        assert -1e-6 <= r["r2"] <= 1 + 1e-6
        assert r["rmse"] >= 0.0
    # 图编码：维度最少（9），且近乎完美拟合（可解释、低维高效）
    graph = by_name["图(拓扑描述符)"]
    assert graph["dim"] == min(r["dim"] for r in table)
    assert graph["r2"] > 0.99
    # 指纹：哈希不可逆，维度最高
    fp = by_name["指纹(哈希 256bit)"]
    assert fp["dim"] == max(r["dim"] for r in table)


def test_cli_integration(tmp_path, capsys):
    """CLI 集成：fit 落盘 + apply 预测。"""
    csv_path = tmp_path / "data.csv"
    x0 = np.linspace(-3.0, 3.0, 40)
    y = 3.0 * x0 + 2.0
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write("x0,y\n")
        for a, b in zip(x0, y):
            f.write(f"{a},{b}\n")
    expr_path = tmp_path / "expr.json"

    rc = main(["fit", "--csv", str(csv_path), "--target", "y",
               "--output", str(expr_path), "--generations", "30"])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert json.loads(out)["ok"] is True
    assert Path(expr_path).is_file()

    rc2 = main(["apply", "--expr", str(expr_path), "--input", "x0=2.0"])
    out2 = capsys.readouterr().out
    assert rc2 == 0, out2
    pred = json.loads(out2)["predictions"][0]
    assert abs(pred - 8.0) < 1.0
