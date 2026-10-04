"""Shared pytest + Hypothesis configuration for the omnilimb-face test suite.

Registers and loads a Hypothesis settings profile so every property-based test
runs at least 100 random examples, as mandated by the design's Testing
Strategy. The active profile is selected by the ``HYPOTHESIS_PROFILE``
environment variable (default ``vtuber``); set ``HYPOTHESIS_PROFILE=ci`` for a
heavier run in CI.
"""

from __future__ import annotations

import os

try:
    from hypothesis import settings
except ModuleNotFoundError:  # pragma: no cover - 依赖缺失时优雅降级
    # omnilimb-face 是自带 pyproject 的独立子项目，其属性测试依赖 hypothesis
    # （声明于 coupled/omnilimb-face/pyproject.toml 的 dev extras）。若根测试
    # 环境未安装 hypothesis，跳过本目录全部测试，而不是在收集期报
    # ModuleNotFoundError 中断整个仓库的 pytest 树。
    collect_ignore_glob = ["test_*.py"]
    settings = None
else:
    pass

if settings is not None:
    # Minimum example count required for every property-based test (>= 100).
    DEFAULT_MAX_EXAMPLES = 100
    CI_MAX_EXAMPLES = 250

    # `deadline=None` disables Hypothesis' per-example timing deadline. The
    # property tests added by later tasks exercise pure logic, but some run a
    # non-trivial amount of work per example; disabling the deadline keeps the
    # suite from flaking on slow machines without weakening the properties.
    settings.register_profile(
        "vtuber",
        max_examples=DEFAULT_MAX_EXAMPLES,
        deadline=None,
    )
    settings.register_profile(
        "ci",
        max_examples=CI_MAX_EXAMPLES,
        deadline=None,
    )

    settings.load_profile(os.getenv("HYPOTHESIS_PROFILE", "vtuber"))
