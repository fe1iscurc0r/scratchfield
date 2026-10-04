"""memory_snapshot — NEKO 记忆层「快照 / 回滚」旁路（N-02）。

借鉴 nocturne_memory 的「导出 → 快照 → 恢复点列表 → 回滚前强制备份 → 精确还原」
机制（勘察报告 docs/nocturne-记忆可视化-勘察报告.md，N-01），降维成纯标准库旁路，
不引 nocturne 代码，不动 NEKO `memory/` 主流程任何文件。

定位：调试记忆漂移的辅助工具——把某个记忆目录（每角色 `facts.json / persona.json /
recent.json / time_indexed.db / settings.json ...`）的现状导出成一份自包含 JSON 快照，
列出现有快照与恢复点，需要时从快照还原（还原前强制备份当前态）。

旁路零侵入约束：
  - 只读/只写记忆目录文件本身，不 import、不修改 `memory/` 任何模块；
  - 纯 Python 标准库（json / shutil / hashlib / pathlib / argparse / datetime）；
  - 快照落在独立 `snapshot_dir`，不污染被快照的源目录。

License: Apache-2.0（机制借鉴 nocturne_memory；实现独立重写，无代码复制）。
"""
from __future__ import annotations

from .snap import snapshot, list_snapshots
from .rollback import SnapshotError, restore

__all__ = [
    "snapshot",
    "list_snapshots",
    "restore",
    "SnapshotError",
]
