"""数据库备份 —— `VACUUM INTO` 一致性快照 + 按天轮转（卷192 黄档 Y2 处置）。

背景：
    卷192 数据库层勘察结论「Y2：无任何备份路径」——13+ 个 SQLite 库裸跑，
    `db_migrations` 只管 schema 版本、不管数据可恢复性。本模块补上这一层。

方案：
    `VACUUM INTO '<target>'`（SQLite ≥3.27）——**只读源库**（不改写、不阻塞读），
    产出一个已整理（无碎片、无 WAL 残留）的一致性快照文件。
    按天命名 → `prune_old` 轮转保留最近 N 天。

落点：
    `<data_dir>/db_backups/<库名>/<库名>-YYYY-MM-DD.db`（`LUMO_DB_BACKUP_DIR` 可覆盖）。
    库清单默认取 `apiserver.db_migrations.registry.databases()`（单一真源，含新增库自动覆盖）。

铁律：
    - 源库不存在 → 跳过并记录（**不创建空库**）；
    - 当天备份已存在 → 跳过（幂等，不覆盖）；
    - 失败不抛（返回结构化 status/error，供调度方继续处理其它库）。

用法：
    python -m apiserver.db_backup                 # 备份全部登记库
    python -m apiserver.db_backup --keep-days 14  # 自定义保留天数
    python -m apiserver.db_backup --only papers   # 只备份指定库
"""
from __future__ import annotations

import argparse
import datetime as _dt
import sqlite3
from pathlib import Path
from typing import Any, Iterable
from apiserver.config import settings

DEFAULT_KEEP_DAYS = 7
_FILENAME_SUFFIX = ".db"


def default_backup_root() -> Path:
    """备份根目录：env 优先，否则 `<data_dir>/db_backups`。"""
    import os

    env = settings.db_backup_dir()
    if env:
        return Path(env)
    try:
        from system.config import get_data_dir

        return Path(get_data_dir()) / "db_backups"
    except Exception:  # noqa: BLE001 - 配置链不可用时退回 HOME（与 registry 同款降级）
        return Path.home() / ".lumo" / "db_backups"


def _target_for(src: Path, backup_root: Path, day: str) -> Path:
    return Path(backup_root) / src.stem / f"{src.stem}-{day}{_FILENAME_SUFFIX}"


def backup_one(db_path: str | Path, backup_root: str | Path, *,
               today: _dt.date | None = None,
               keep_days: int = DEFAULT_KEEP_DAYS) -> dict[str, Any]:
    """备份单个库。返回结构化结果（**不抛异常**）。

    status 取值：``created`` / ``skipped_exists`` / ``skipped_missing`` / ``failed``
    """
    src = Path(db_path)
    root = Path(backup_root)
    day = (today or _dt.date.today()).isoformat()
    target = _target_for(src, root, day)

    if not src.exists():
        return {"name": src.stem, "status": "skipped_missing", "source": str(src)}
    if target.exists():
        return {"name": src.stem, "status": "skipped_exists", "path": str(target)}

    target.parent.mkdir(parents=True, exist_ok=True)
    # SQLite 的 VACUUM INTO 不接受参数绑定 → 手工转义单引号（SQLite 字符串字面量规则）
    safe = str(target).replace("'", "''")
    try:
        with sqlite3.connect(str(src)) as conn:
            conn.execute(f"VACUUM INTO '{safe}'")
    except Exception as exc:  # noqa: BLE001 - 备份失败不能拖垮其它库
        return {"name": src.stem, "status": "failed",
                "error": f"{type(exc).__name__}: {exc}", "path": str(target)}

    pruned = prune_old(target.parent, keep_days=keep_days, today=today)
    return {"name": src.stem, "status": "created", "path": str(target),
            "bytes": target.stat().st_size if target.exists() else 0,
            "pruned": [str(p) for p in pruned]}


def prune_old(out_dir: str | Path, *, keep_days: int,
              today: _dt.date | None = None) -> list[Path]:
    """删除超出保留窗口的备份文件。

    **只动本模块命名模式**（`<stem>-YYYY-MM-DD.db`）的文件——目录里其它文件一律不碰。
    """
    d = Path(out_dir)
    if keep_days < 0 or not d.is_dir():
        return []
    cutoff = (today or _dt.date.today()) - _dt.timedelta(days=keep_days)
    removed: list[Path] = []
    for f in sorted(d.glob(f"*-[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]{_FILENAME_SUFFIX}")):
        stamp = f.name[len(f.name) - len("YYYY-MM-DD.db"):-len(_FILENAME_SUFFIX)]
        try:
            day = _dt.date.fromisoformat(stamp)
        except ValueError:
            continue          # 解析不了的不动（宁可不删）
        if day < cutoff:
            try:
                f.unlink()
                removed.append(f)
            except OSError:
                continue
    return removed


def backup_all(db_paths: Iterable[tuple[str, str | Path]] | None = None,
               backup_root: str | Path | None = None, *,
               keep_days: int = DEFAULT_KEEP_DAYS,
               today: _dt.date | None = None,
               only: str | None = None) -> dict[str, Any]:
    """备份一组库（默认取 registry 登记清单）。返回汇总 dict（含逐库明细）。"""
    if db_paths is None:
        from apiserver.db_migrations.registry import databases

        db_paths = databases()
    root = Path(backup_root) if backup_root is not None else default_backup_root()

    results: list[dict[str, Any]] = []
    for name, path in db_paths:
        if only and name != only:
            continue
        r = backup_one(path, root, today=today, keep_days=keep_days)
        r.setdefault("name", name)
        results.append(r)

    created = [r for r in results if r["status"] == "created"]
    return {
        "backup_root": str(root),
        "day": (today or _dt.date.today()).isoformat(),
        "keep_days": keep_days,
        "total": len(results),
        "created": len(created),
        "skipped": len([r for r in results if r["status"].startswith("skipped")]),
        "failed": len([r for r in results if r["status"] == "failed"]),
        "results": results,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="SQLite 库备份（VACUUM INTO 按天轮转）")
    ap.add_argument("--keep-days", type=int, default=DEFAULT_KEEP_DAYS,
                    help=f"保留天数（默认 {DEFAULT_KEEP_DAYS}）")
    ap.add_argument("--dir", default=None, help="备份根目录（默认 data_dir/db_backups）")
    ap.add_argument("--only", default=None, help="只备份指定逻辑名（如 papers）")
    args = ap.parse_args(argv)

    summary = backup_all(backup_root=args.dir, keep_days=args.keep_days, only=args.only)
    print(f"[db_backup] {summary['day']} → {summary['backup_root']}")
    for r in summary["results"]:
        line = f"  {r['name']:<18} {r['status']}"
        if r.get("bytes"):
            line += f"  {r['bytes']} B"
        if r.get("error"):
            line += f"  !! {r['error']}"
        print(line)
    print(f"[db_backup] created={summary['created']} skipped={summary['skipped']} "
          f"failed={summary['failed']} / total={summary['total']}")
    return 1 if summary["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
