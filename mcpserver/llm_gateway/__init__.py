"""LLM 网关适配层（工单 228）。

当前含 anthropic SDK 1.x 兼容层（:mod:`anthropic_compat`）。

定位：**旁路验证** —— 不替换任何现有调用点，只为 v5.2.9 是否整体切换提供可跑的 PoC
（见工单 228 任务三的硬约束「不替换现有调用点，只验证兼容层跑通」）。
"""
from __future__ import annotations

from . import anthropic_compat

__all__ = ["anthropic_compat"]
