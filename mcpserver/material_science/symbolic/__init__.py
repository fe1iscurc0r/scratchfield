"""mcpserver/material_science/symbolic — 符号回归旁路（Y-02）。

与 biopred.py 黑箱主流程正交：独立拟合显式表达式，供"黑箱预测 + 符号表达式对照"。
纯 Python + numpy，无 gplearn/pysr 重依赖。工具选型见
docs/material-symbolic-regression-勘察报告.md（Y-01）。

硬约束：不修改 biopred.py 主流程。
"""
from __future__ import annotations

from .expr import Expression, evaluate
from .fit import FitResult, fit, self_test

# 与 mcpserver/academic/ 的 MODEL_INTERFACE 同构的元数据（旁路，不并入 academic 注册表）
MODEL_INTERFACE = {
    "name": "symbolic",
    "package": "material_science/symbolic（本仓旁路，纯 numpy 遗传编程）",
    "vendor_repo": "https://github.com/fe1iscurc0r/scratchpad",
    "pip": None,
    "license": "MIT（本仓自研；方法论参考 gplearn BSD-3）",
    "fusion_level": "MCP（material_science 旁路，非 academic 注册表）",
    "description": "显式符号回归：X/y → 显式表达式（可写进论文）+ 编码策略评估对比",
    "entrypoints": [
        {
            "command": "symbolic_fit",
            "params": {"X": "[n,d] 特征矩阵", "y": "[n] 目标向量",
                       "feature_names": "可选，变量名"},
            "returns": "FitResult(expression/rmse/r2/generations)",
        },
        {
            "command": "symbolic_apply",
            "params": {"expr": "表达式文本或 JSON 路径", "values": "变量取值 dict"},
            "returns": "预测值（标量或数组）",
        },
    ],
    "runtime_deps": ["numpy（fit 必需；Expression 标量求值可退 math）"],
    "degradation": "无 numpy 时 Expression 标量求值走 math；fit 需 numpy",
    "verified": "2026-08-28 合成数据自测（fit.self_test + pytest）",
}

__all__ = ["Expression", "evaluate", "fit", "FitResult", "self_test",
           "MODEL_INTERFACE"]
