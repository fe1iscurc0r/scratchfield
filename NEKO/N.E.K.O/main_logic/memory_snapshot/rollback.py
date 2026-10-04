"""rollback — 从快照还原记忆目录（只读校验 → 强制备份 → 回写）。

机制借鉴 nocturne_memory 的「通用回滚」：回滚前先只读校验快照完整性
（schema / 路径安全 / sha256 一致性），坏快照直接报错不落盘；校验通过后，
**回写前强制把当前态备份到独立备份目录**，最后按快照逐文件还原。

硬约束：纯标准库；不 import、不修改 memory/ 主流程任何模块。

License: Apache-2.0（机制同源 nocturne_memory；实现独立）。
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .snap import SNAPSHOT_SCHEMA, _SNAPSHOT_PREFIX, _SNAPSHOT_SUFFIX

logger = logging.getLogger(__name__)


class SnapshotError(Exception):
    """快照损坏或非法（schema/路径/sha256 校验失败）。"""


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _resolve_snapshot_path(snapshot_id: str, snapshot_dir: str | Path) -> Path:
    """按 id 或路径定位快照文件。"""
    snapshot_dir = Path(snapshot_dir)
    cand = snapshot_dir / f"{_SNAPSHOT_PREFIX}{snapshot_id}{_SNAPSHOT_SUFFIX}"
    if cand.is_file():
        return cand
    # 兼容直接传快照文件名或绝对路径
    alt = Path(snapshot_id)
    if alt.is_file():
        return alt
    if (snapshot_dir / snapshot_id).is_file():
        return snapshot_dir / snapshot_id
    raise SnapshotError(f"找不到快照: {snapshot_id}")


def _safe_rel_path(rel: str) -> Path:
    """把快照里的相对路径转为受控 Path，拒绝目录穿越。

    - 拒绝绝对路径、盘符、`..` 段、空路径；
    - 返回相对 Path（不含 leading 分隔符）。
    """
    if not rel or "\x00" in rel:
        raise SnapshotError(f"非法文件路径: {rel!r}")
    p = Path(rel)
    if p.is_absolute() or p.drive:
        raise SnapshotError(f"快照含绝对路径，拒绝还原: {rel!r}")
    parts = p.parts
    if not parts:
        raise SnapshotError(f"空文件路径: {rel!r}")
    for part in parts:
        if part == "..":
            raise SnapshotError(f"快照含目录穿越，拒绝还原: {rel!r}")
    return p


def _decode_content(entry: Dict[str, Any], rel: str) -> bytes:
    """把快照条目解码回原始字节。"""
    encoding = entry.get("encoding")
    content = entry.get("content")
    if not isinstance(content, str):
        raise SnapshotError(f"快照条目 {rel!r} 缺少 content")
    if encoding == "utf-8":
        return content.encode("utf-8")
    if encoding == "base64":
        try:
            return base64.b64decode(content, validate=True)
        except Exception as exc:  # noqa: BLE001 — base64 损坏统一报 SnapshotError
            raise SnapshotError(f"快照条目 {rel!r} base64 解码失败: {exc}") from exc
    raise SnapshotError(f"快照条目 {rel!r} 未知 encoding: {encoding!r}")


def _validate_snapshot(doc: Any) -> List[Tuple[str, Dict[str, Any]]]:
    """只读校验快照，返回 [(rel_path, entry), ...] 排序后的待还原条目。

    校验失败抛 SnapshotError；本函数不产生任何写操作。
    """
    if not isinstance(doc, dict):
        raise SnapshotError("快照根节点不是对象")
    if doc.get("schema") != SNAPSHOT_SCHEMA:
        raise SnapshotError(f"未知快照 schema: {doc.get('schema')!r}")
    files = doc.get("files")
    if not isinstance(files, dict):
        raise SnapshotError("快照缺少 files 字段")
    items: List[Tuple[str, Dict[str, Any]]] = []
    for rel, entry in files.items():
        if not isinstance(rel, str) or not isinstance(entry, dict):
            raise SnapshotError(f"快照条目 {rel!r} 结构非法")
        safe = _safe_rel_path(rel)
        raw = _decode_content(entry, rel)
        recorded = entry.get("sha256")
        actual = _sha256_hex(raw)
        if recorded != actual:
            raise SnapshotError(
                f"快照条目 {rel!r} sha256 不一致（期望 {recorded}，实际 {actual}）"
            )
        if entry.get("size") is not None and int(entry["size"]) != len(raw):
            raise SnapshotError(
                f"快照条目 {rel!r} size 不一致（期望 {entry['size']}，实际 {len(raw)}）"
            )
        items.append((safe.as_posix(), entry))
    items.sort(key=lambda t: t[0])
    return items


def _load_and_validate(snapshot_id: str, snapshot_dir: str | Path) -> Tuple[Path, List[Tuple[str, Dict[str, Any]]]]:
    """定位 + 读取 + 只读校验快照，返回 (快照路径, 待还原条目列表)。"""
    path = _resolve_snapshot_path(snapshot_id, snapshot_dir)
    try:
        with open(path, "r", encoding="utf-8") as f:
            doc = json.load(f)
    except json.JSONDecodeError as exc:
        raise SnapshotError(f"快照 JSON 解析失败: {exc}") from exc
    except OSError as exc:
        raise SnapshotError(f"快照读取失败: {exc}") from exc
    items = _validate_snapshot(doc)
    return path, items


def backup_current(target_dir: str | Path, backup_root: str | Path, tag: str) -> str:
    """把 ``target_dir`` 当前态强制备份到 ``backup_root/<tag>-<ts>/``。

    返回备份目录路径。备份不校验、不删原文件——只做「回滚前安全网」。
    """
    target_dir = Path(target_dir)
    backup_root = Path(backup_root)
    backup_root.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
    backup_dir = backup_root / f"{tag}-{ts}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    if target_dir.is_dir():
        for path in sorted(target_dir.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(target_dir)
            dest = backup_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
    logger.info("[memory-snapshot] 当前态已备份到 %s", backup_dir)
    return str(backup_dir)


def restore(
    snapshot_id: str,
    snapshot_dir: str | Path,
    target_dir: str | Path,
    backup_root: Optional[str | Path] = None,
) -> Dict[str, Any]:
    """从快照还原 ``target_dir``。

    流程（严格顺序）：
      1. 定位 + 只读校验快照（schema / 路径安全 / sha256 / size）——坏快照抛
         ``SnapshotError``，此时尚未产生任何写操作；
      2. 回写前强制备份当前态到 ``backup_root``（缺省 = snapshot_dir/backups）；
      3. 逐文件把快照内容写回 ``target_dir``。

    返回 {restored_files, backup_dir, snapshot_id}。
    """
    snapshot_path, items = _load_and_validate(snapshot_id, snapshot_dir)
    target_dir = Path(target_dir)
    if backup_root is None:
        backup_root = Path(snapshot_dir) / "backups"
    else:
        backup_root = Path(backup_root)

    # 2. 回滚前强制备份当前态
    backup_dir = backup_current(target_dir, backup_root, f"pre-restore-{snapshot_path.stem}")

    # 3. 逐文件回写
    restored = 0
    for rel, entry in items:
        raw = _decode_content(entry, rel)
        dest = target_dir / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(raw)
        restored += 1
    logger.info("[memory-snapshot] 已从 %s 还原 %d 个文件到 %s", snapshot_path, restored, target_dir)
    return {
        "snapshot_id": snapshot_path.stem.replace(_SNAPSHOT_PREFIX, "", 1),
        "restored_files": restored,
        "backup_dir": backup_dir,
    }


__all__ = ["SnapshotError", "restore", "backup_current"]
