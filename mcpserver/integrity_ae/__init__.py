"""声发射（AE）接入 · vallenae 包装层（工单 262 任务 C）。

**只做包装，不复制上游源码**。上游 `vallen-systems/vallenae`（MIT, 54★）。
三个入口：
    read_pridb(path)                      → 参数表 DataFrame
    detect_hits(pridb, tradb, threshold)  → 超过阈值的 hit DataFrame
    cluster_events(hits, max_dt_us)       → 按时间间隔聚类的 hit 索引组

缺依赖时的行为：**调用时**抛 ``ImportError("pip install vallenae")``，
不在 import 期间崩掉整个 mcpserver（`mcpserver` 启动路径会导入本包）。
"""
from __future__ import annotations

from .detector import cluster_events, detect_hits
from .reader import read_pridb

__all__ = ["read_pridb", "detect_hits", "cluster_events"]
