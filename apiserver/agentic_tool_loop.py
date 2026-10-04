#!/usr/bin/env python3
"""Agentic Tool Loop —— **薄壳**（卷190-A2）。

原 2753 行实现已按域拆到同目录 ``agentic_loop_parts/``：
markers(标记与口径) / parser / planner / context / executor_openclaw /
executor_search / executor / hooks / loop(主循环与对外入口)。

**本文件保留同名 re-export，外部 import 路径与名字全部不变**（纯搬移，行为零变化：
函数体逐字节未改，仅相对 import 层级 `from .X` → `from ..X`；`logger` 通道名显式保持
为 `apiserver.agentic_tool_loop`）。
"""
from apiserver.agentic_loop_parts import *  # noqa: F401,F403

# ruff: noqa: F405  # 薄壳模式：星号聚合导入的公共名（导出面由 tools/verify_export_parity.py 钉住）
