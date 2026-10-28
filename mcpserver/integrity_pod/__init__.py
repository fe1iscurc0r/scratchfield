"""POD（检出概率）曲线 · 一期解析式（工单 262 任务 D）。

接口固定，二期换 `otpod` 时调用方无需改：

    pod_curve(a_values, hit_miss)  → PODCurve
    a90(curve)                     → float
    sobol_indices(model, n_samples)→ dict（一期返回 {}，见 sobol.py）

**不引入** `otpod`（LGPL-3.0）与 `openturns`（GPL-3.0）——许可证与本仓 MIT 系不兼容，
二期接入路径见 `mcpserver/integrity_pod/README.md`。
"""
from __future__ import annotations

from .hit_miss import PODCurve, a90, pod_curve
from .sobol import sobol_indices

__all__ = ["PODCurve", "pod_curve", "a90", "sobol_indices"]
