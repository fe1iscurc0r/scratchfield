"""snap — 记忆目录现状导出为自包含 JSON 快照 + 恢复点列表。

机制借鉴 nocturne_memory 的 ChangesetStore（写时快照 + 恢复点列表），但降维成
纯标准库旁路：把一个记忆目录（每角色 facts.json / persona.json / recent.json /
time_indexed.db / settings.json ...）的当前文件内容 + sha256 一起序列化成一份
JSON 快照，落在独立 `snapshot_dir`。文本文件按 utf-8 存，二进制（如 SQLite .db）
按 base64 存；每份快照都是可独立恢复的自包含恢复点。

License: Apache-2.0（机制同源 nocturne_memory；实现独立）。
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 快照 schema 版本：restore 校验时用来拒绝未知格式
SNAPSHOT_SCHEMA = "memory_snapshot/1"

# 快照文件名前缀：list 只认这个前缀，避免扫到无关 JSON
_SNAPSHOT_PREFIX = "snapshot-"
_SNAPSHOT_SUFFIX = ".json"

# 文本文件按 utf-8 内联存储；二进制（SQLite/其它）按 base64 内联存储
_BINARY_SUFFIXES = frozenset({".db", ".sqlite", ".sqlite3", ".bin", ".dat", ".wal", ".shm"})
# utf-8 解码上限保护：超过此字节数不尝试内联为文本（走 base64）
_MAX_TEXT_BYTES = 16 * 1024 * 1024


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _now_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _encode_file(raw: bytes, rel_path: str) -> Dict[str, Any]:
    """把单个文件字节序列化为快照条目 {sha256, size, encoding, content}。"""
    entry: Dict[str, Any] = {
        "sha256": _sha256_hex(raw),
        "size": len(raw),
    }
    suffix = Path(rel_path).suffix.lower()
    is_binary = suffix in _BINARY_SUFFIXES or len(raw) > _MAX_TEXT_BYTES
    if is_binary:
        entry["encoding"] = "base64"
        entry["content"] = base64.b64encode(raw).decode("ascii")
    else:
        try:
            entry["encoding"] = "utf-8"
            entry["content"] = raw.decode("utf-8")
        except UnicodeDecodeError:
            # 后缀判断漏网但实际非 utf-8：退回 base64，保证自包含无损
            entry["encoding"] = "base64"
            entry["content"] = base64.b64encode(raw).decode("ascii")
    return entry


def _iter_files(source_dir: Path, snapshot_dir: Optional[Path]) -> List[Path]:
    """递归列出要快照的常规文件（跳过 snapshot_dir 自身，避免自嵌套）。"""
    out: List[Path] = []
    snapshot_dir_resolved = snapshot_dir.resolve() if snapshot_dir else None
    for path in sorted(source_dir.rglob("*")):
        if not path.is_file():
            continue
        if snapshot_dir_resolved is not None:
            try:
                if path.resolve().is_relative_to(snapshot_dir_resolved):
                    continue
            except (OSError, ValueError):
                pass
        out.append(path)
    return out


def snapshot(
    source_dir: str | Path,
    snapshot_dir: str | Path,
    label: Optional[str] = None,
    note: Optional[str] = None,
) -> Dict[str, Any]:
    """导出 ``source_dir`` 现状为一份 JSON 快照，返回快照元数据。

    - ``label`` 非空时作为恢复点标记（人类可读的名字），
      写入快照的 ``restore_point``/``label`` 字段。
    - 快照文件落盘到 ``snapshot_dir/snapshot-<id>.json``，不写入 source_dir。
    """
    source_dir = Path(source_dir)
    snapshot_dir = Path(snapshot_dir)
    if not source_dir.is_dir():
        raise NotADirectoryError(f"源目录不存在: {source_dir}")
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    snapshot_id = _now_id()
    created_at = _now_iso()
    files: Dict[str, Dict[str, Any]] = {}
    for path in _iter_files(source_dir, snapshot_dir):
        rel = path.relative_to(source_dir).as_posix()
        try:
            raw = path.read_bytes()
        except OSError as exc:  # 单文件读取失败不阻断整份快照，但记录告警
            logger.warning("[memory-snapshot] 跳过不可读文件 %s: %s", rel, exc)
            continue
        files[rel] = _encode_file(raw, rel)

    doc: Dict[str, Any] = {
        "schema": SNAPSHOT_SCHEMA,
        "id": snapshot_id,
        "created_at": created_at,
        "label": label or None,
        "restore_point": bool(label),
        "note": note or None,
        "source_dir": str(source_dir),
        "file_count": len(files),
        "files": files,
    }
    out_path = snapshot_dir / f"{_SNAPSHOT_PREFIX}{snapshot_id}{_SNAPSHOT_SUFFIX}"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
    logger.info("[memory-snapshot] 快照已创建 %s（%d 文件）", out_path, len(files))
    return {
        "id": snapshot_id,
        "path": str(out_path),
        "created_at": created_at,
        "label": label,
        "restore_point": bool(label),
        "file_count": len(files),
        "source_dir": str(source_dir),
    }


def _read_meta(path: Path) -> Optional[Dict[str, Any]]:
    """只读快照文件的元数据头（不把 files 内容全量载入内存）。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("[memory-snapshot] 跳过损坏快照 %s: %s", path, exc)
        return None
    if not isinstance(doc, dict):
        return None
    return {
        "id": doc.get("id"),
        "path": str(path),
        "created_at": doc.get("created_at"),
        "label": doc.get("label"),
        "restore_point": bool(doc.get("restore_point")),
        "file_count": doc.get("file_count"),
        "source_dir": doc.get("source_dir"),
    }


def list_snapshots(snapshot_dir: str | Path) -> List[Dict[str, Any]]:
    """列出快照目录里的全部快照元数据（按创建时间倒序）。"""
    snapshot_dir = Path(snapshot_dir)
    if not snapshot_dir.is_dir():
        return []
    metas: List[Dict[str, Any]] = []
    for path in snapshot_dir.glob(f"{_SNAPSHOT_PREFIX}*{_SNAPSHOT_SUFFIX}"):
        if not path.is_file():
            continue
        meta = _read_meta(path)
        if meta is not None:
            metas.append(meta)
    metas.sort(key=lambda m: m.get("created_at") or "", reverse=True)
    return metas


__all__ = ["snapshot", "list_snapshots", "SNAPSHOT_SCHEMA"]
