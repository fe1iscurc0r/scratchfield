"""registry.py — 需要 schema_version 登记的库清单（卷192-C）。

按"路径来源可靠度"分三组注册：

A. data_dir 下（apiserver/mcpserver 启动链会打开的）—— **默认登记**
B. 仓库内固定路径（graph_memory / sentinel_rf / memory_maas_data）—— **默认登记**
C. 相对 CWD 的库（`papers.db` / `carbonization.db`）—— **不登记**：路径随工作目录漂移，
   本身就是勘察发现的风险项（见 docs/db-audit-2026-10.md 黄档），先记录不接管。

纯 stdlib；`get_data_dir` 延迟 import（不在 import 期触发 system.config 重链）。
"""
from __future__ import annotations

from pathlib import Path


def _data_dir() -> Path:
    try:
        from system.config import get_data_dir
        return Path(get_data_dir())
    except Exception:
        return Path.home() / ".lumo"


def _repo_root() -> Path:
    """仓库根（apiserver/db_migrations/registry.py → 上三级）。"""
    return Path(__file__).resolve().parents[2]


def databases() -> list[tuple[str, Path]]:
    """(逻辑名, 库路径) 列表。延迟求值，导入本模块不触碰文件系统。"""
    d = _data_dir()
    r = _repo_root()
    return [
        # A. data_dir 下
        ("message_store", d / "message_store.db"),   # 亦承载 tasks（task_store 同库）
        ("papers", d / "papers" / "papers.db"),
        ("sync", d / "sync" / "sync.db"),
        ("rag_material", d / "rag" / "materialscience.db"),
        ("synth_rag", d / "synth_rag" / "routes.db"),
        ("tool_calls", d / "tool_calls.db"),         # 卷189-B 新增
        ("knowledge_store", d / "knowledge_store.db"),
        # B. 仓库内固定路径
        ("graph_memory", r / "knowledge-base" / "graph_memory" / "graph_memory.db"),
        ("sentinel_rf", r / "sentinel_rf.db"),
        ("maas_cards", r / "memory_maas_data" / "cards.db"),
        ("maas_entities", r / "memory_maas_data" / "entities.db"),
        ("maas_hs", r / "memory_maas_data" / "hs.db"),
        ("maas_lineage", r / "memory_maas_data" / "lineage.db"),
    ]


# 注意：不在此处求值（避免 import 期触发 system.config 重链）——
# 调用方一律用 databases()。
__all__ = ["databases"]
