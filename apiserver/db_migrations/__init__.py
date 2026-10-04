"""db_migrations — 轻量 schema 版本机制（卷192-C 档2）。

模块布局（刻意保持"纯 stdlib、可脱离 apiserver 包单独加载"）：
- ``runner.py``            迁移执行器（版本表 / 幂等 / 并发防双跑 / fail-fast / 回滚检测）
- ``001_initial_baseline.py`` 基线（版本 1，只登记不建表）
- ``registry.py``          需要登记 schema_version 的库清单

对外入口：
    from apiserver.db_migrations import apply_all, apply, Migration

启动接入：``apiserver/api_server.py`` lifespan 中调用 ``apply_all()``。
"""

from __future__ import annotations

__all__ = ["apply", "apply_all", "Migration", "MigrationError", "ApplyResult",
           "current_version"]


def __getattr__(name: str):
    """延迟绑定（避免 import apiserver.db_migrations 时拉起 apiserver/__init__ 重链）。"""
    if name in __all__:
        from . import runner
        return getattr(runner, name)
    raise AttributeError(name)
