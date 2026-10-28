"""全局敏感性（Sobol 指数）· 一期占位。"""
from __future__ import annotations

from typing import Any

_PHASE2_NOTE = (
    "一期不实现 Sobol 分解：它需要可分离的参数模型与大量采样，当前只有解析式 POD；"
    "二期接入 otpod/openturns 时一并实现（许可证问题需先解决）。"
)


def sobol_indices(model: Any, n_samples: int = 1024) -> dict:
    """一期按工单返回空 dict（**不假装算过**）。

    返回值里只有说明字段，调用方可用 `if not result` 判断「未实现」。
    """
    del model
    if n_samples <= 0:
        raise ValueError("n_samples 必须为正")
    return {}
