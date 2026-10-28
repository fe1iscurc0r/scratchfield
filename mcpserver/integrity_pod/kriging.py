"""二期预留：克里金（GP）插值的 POD 面。

一期不实现——克里金需要 `scikit-learn` 的 GaussianProcess 或 `openturns`（GPL-3.0，
本仓不引入）。保留模块与签名，避免二期改 `__init__` 导出。
"""
from __future__ import annotations

from typing import Any


def kriging_pod_surface(samples: Any, *, length_scale: float = 1.0) -> Any:
    """二期：由稀疏样本插值出 POD 面（多尺寸 × 多参数）。

    Raises:
        NotImplementedError: 一期不实现；二期走 sklearn 的 GaussianProcessRegressor，
            不引入 openturns（GPL-3.0）。
    """
    del samples, length_scale
    raise NotImplementedError(
        "一期只提供解析式 POD；克里金 POD 面留二期（sklearn GaussianProcessRegressor，"
        "不引入 openturns/otpod —— 许可证不兼容）"
    )
