"""自维护机制 — 遗忘调度 + 相似合并 + 快照联动（cron 触发，不内置常驻线程）。

设计依据 POLLINATION-2026-08-28-round9（par 15-min heartbeat + retention sweep +
consolidation）：让 typed 记忆层自管理，避免长期运行膨胀。

策略要点：
- retention_sweep：pinned 永不删；低信任（source_rank ≥ min_source_rank）且超龄的先删；
  type=note 比 decision/insight 优先清理（旧 note 超龄可清，决策/洞察保留）。
- consolidate：只合并 note（同 tags 短条目 → 一条，被吸收 id 列表保留在 relations），
  不删 decision/insight/handoff。
- snapshot：sweep/consolidate 执行前自动导出 JSON 快照（回滚保护），
  同构实现 NEKO/N.E.K.O/main_logic/memory_snapshot/ 的旁路接口（该目录源未落库）。
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

from mcpserver.memory_maas.entities import TypedMemoryStore

_REPO_ROOT = Path(__file__).resolve().parents[2]  # scratchpad/
_DEFAULT_DATA_DIR = _REPO_ROOT / "memory_maas_data"


# ---------------------------------------------------------------- 数据目录

def resolve_data_dir(data_dir: str | Path | None = None) -> Path:
    if data_dir:
        return Path(data_dir)
    return Path(os.environ.get("MEMORY_MAAS_DATA_DIR") or _DEFAULT_DATA_DIR)


def _open_store(data_dir: str | Path | None = None) -> TypedMemoryStore:
    return TypedMemoryStore(resolve_data_dir(data_dir) / "entities.db")


# ---------------------------------------------------------------- 快照旁路

def snapshot(store: TypedMemoryStore,
             snapshots_dir: str | Path | None = None) -> dict[str, Any]:
    """导出 typed 实体 + 关系为 JSON 快照（回滚保护点）。"""
    snap_dir = Path(snapshots_dir) if snapshots_dir \
        else (store.db_path.parent / "snapshots")
    snap_dir.mkdir(parents=True, exist_ok=True)
    entities = store.list_entities()
    relations = store.all_relations()
    ts = time.time()
    path = snap_dir / f"snapshot-{int(ts * 1000)}.json"
    data = {"created_at": ts, "entities": entities, "relations": relations}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return {"ok": True, "snapshot_path": str(path), "created_at": ts,
            "entities": len(entities), "relations": len(relations)}


def list_snapshots(snapshots_dir: str | Path) -> list[dict[str, Any]]:
    d = Path(snapshots_dir)
    if not d.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for p in sorted(d.glob("snapshot-*.json")):
        out.append({"path": str(p), "created_at": p.stat().st_mtime})
    return out


def restore_snapshot(store: TypedMemoryStore,
                     snapshot_path: str | Path) -> dict[str, Any]:
    """从 JSON 快照回滚（清空后按快照重放，保留原 id / source_rank / 关系）。"""
    data = json.loads(Path(snapshot_path).read_text(encoding="utf-8"))
    store.clear()
    for e in data.get("entities", []):
        store.add(e["content"], type=e["type"], tags=e.get("tags", []),
                  pinned=bool(e.get("pinned")),
                  source_rank=int(e.get("source_rank", 0)),
                  isolation=bool(e.get("isolation")),
                  entity_id=e["id"], created_at=float(e.get("created_at")))
    for r in data.get("relations", []):
        store.add_relation(r["from_id"], r["to_id"],
                           rel_type=r.get("rel_type", "related"))
    return {"ok": True, "entities": store.count(),
            "restored_from": str(snapshot_path)}


# ---------------------------------------------------------------- 遗忘调度

def retention_sweep(store: TypedMemoryStore, *, now: float | None = None,
                    max_age_days: float = 30.0, min_source_rank: int = 2,
                    limit: int | None = None,
                    snapshots_dir: str | Path | None = None,
                    dry_run: bool = False) -> dict[str, Any]:
    """按策略清理低价值 / 过期记忆（pinned 永不删；note 优先于 decision/insight）。"""
    snap = None
    if not dry_run:
        snap = snapshot(store, snapshots_dir)  # sweep 前自动快照（回滚保护）
    now = now if now is not None else time.time()
    max_age = max_age_days * 86400.0
    candidates: list[tuple[int, float, dict[str, Any]]] = []
    for e in store.list_entities():
        if e["pinned"]:
            continue  # 标星永不删
        age = now - e["created_at"]
        untrusted_old = e["source_rank"] >= min_source_rank and age > max_age
        old_note = e["type"] == "note" and age > max_age
        if untrusted_old:
            candidates.append((0, -age, e))   # 低价值 + 超龄：最高优先级
        elif old_note:
            candidates.append((1, -age, e))   # 旧 note 次之
        # decision/insight/handoff（可信）保留
    candidates.sort(key=lambda t: (t[0], t[1]))
    if limit is not None:
        candidates = candidates[:max(0, int(limit))]
    swept: list[str] = []
    for _, _, e in candidates:
        if dry_run or store.delete(e["id"]):
            swept.append(e["id"])
    return {"ok": True, "swept": swept, "candidates": len(candidates),
            "kept": store.count(), "dry_run": bool(dry_run), "snapshot": snap}


# ---------------------------------------------------------------- 相似合并

def consolidate(store: TypedMemoryStore, *, min_group: int = 2,
                max_content_len: int = 120,
                template_mode: str = "default",
                snapshots_dir: str | Path | None = None,
                dry_run: bool = False) -> dict[str, Any]:
    """合并同 tags 的短 note（只合并 note，不删 decision/insight/handoff）。

    03-03 压缩块 XML 模板：组成员全部可解析为压缩块时，按模板渲染结构化合并块
    （title/fact/narrative/concept/checkpoint 聚合，比自由文本更可解析）；
    任一成员是自由文本（解析降级）时保持旧行为整段拼接，不丢内容。
    template_mode：default | compact（TEMPLATE_MODES 角色卡预设，可切换）。
    """
    from mcpserver.memory_maas.xml_template import get_template, merge_contents
    cfg = get_template(template_mode)  # 未知模式 fail-fast 抛 ValueError
    snap = None
    if not dry_run:
        snap = snapshot(store, snapshots_dir)  # consolidate 前自动快照
    notes = [e for e in store.list_entities()
             if e["type"] == "note" and len(e["content"]) <= max_content_len]
    groups: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for e in notes:
        groups.setdefault(tuple(sorted(e["tags"])), []).append(e)
    merged_groups: list[dict[str, Any]] = []
    xml_merges = 0
    for _, members in groups.items():
        if len(members) < min_group:
            continue
        members.sort(key=lambda e: -len(e["content"]))
        base = members[0]
        absorbed = members[1:]
        if not dry_run:
            merged = merge_contents([e["content"] for e in members], cfg)
            store.update(base["id"], content=merged["content"])
            xml_merges += int(merged["used_xml"])
            for e in absorbed:
                # 被吸收 id 列表保留在 relations（rel_type=consolidated_from）
                store.add_relation(base["id"], e["id"],
                                   rel_type="consolidated_from")
                store.delete(e["id"])
        merged_groups.append({"base_id": base["id"],
                              "absorbed": [e["id"] for e in absorbed]})
    return {"ok": True, "merged_groups": len(merged_groups),
            "xml_template_mode": template_mode,
            "xml_merges": xml_merges,
            "groups": merged_groups, "dry_run": bool(dry_run), "snapshot": snap}


# ---------------------------------------------------------------- 调度入口（cron）

def sweep_once(data_dir: str | Path | None = None, **kw: Any) -> dict[str, Any]:
    """外部 cron 触发：开库 → 自动快照 → sweep → 关库。"""
    store = _open_store(data_dir)
    try:
        kw.setdefault("snapshots_dir", store.db_path.parent / "snapshots")
        return retention_sweep(store, **kw)
    finally:
        store.close()


def consolidate_once(data_dir: str | Path | None = None,
                     **kw: Any) -> dict[str, Any]:
    store = _open_store(data_dir)
    try:
        kw.setdefault("snapshots_dir", store.db_path.parent / "snapshots")
        return consolidate(store, **kw)
    finally:
        store.close()


def maintenance_status(data_dir: str | Path | None = None) -> dict[str, Any]:
    store = _open_store(data_dir)
    try:
        snap_dir = store.db_path.parent / "snapshots"
        snaps = list_snapshots(snap_dir)
        return {"ok": True, "data_dir": str(store.db_path.parent),
                "entities": store.count(),
                "pinned": len(store.list_entities(pinned=True)),
                "snapshots": len(snaps),
                "last_snapshot": snaps[-1]["path"] if snaps else None}
    finally:
        store.close()
