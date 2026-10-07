"""tests/ 全局收集配置 / Global collection config for the test suite.

按模块存在性做收集级跳过（skip collection when an optional dependency is
absent）。规则：被引用的模块在当前分支不存在时，测试文件整体不收集，
而不是在 import 阶段炸掉整个收集流程。
"""
from __future__ import annotations

import importlib.util

# (测试文件名, 依赖模块) — 依赖缺失时跳过收集
# antenna_rotator: w130 云台服务引用的固件侧 Python 包，随 w129 硬件分支
# 交付；主线未合入（2026-09-22 登记，见 tests/test_ptz_lora.py 头注）。
_OPTIONAL_MODULE_TESTS: list[tuple[str, str]] = [
    ("test_ptz_lora.py", "mcpserver.antenna_rotator"),
    ("test_ptz_service.py", "mcpserver.antenna_rotator"),
    ("test_ptz_scheduler.py", "mcpserver.antenna_rotator"),
    ("test_ptz_safety.py", "mcpserver.antenna_rotator"),
    # 卷173 分层落地时补登记：scipy 为 try/except 降级依赖（pyproject 未声明，
    # 见 2026-09-29 依赖审计），干净 venv 下缺失属预期——跳过收集不拦全量。
    ("test_raman_utils.py", "scipy"),
]

collect_ignore = [
    test_file
    for test_file, module_name in _OPTIONAL_MODULE_TESTS
    if importlib.util.find_spec(module_name) is None
]
