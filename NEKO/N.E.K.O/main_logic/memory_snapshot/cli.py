"""cli — memory_snapshot 命令行入口（snapshot / list / restore）。

纯标准库 argparse；三个子命令：
  - snapshot  SOURCE SNAPSHOT_DIR [--label L] [--note N]
  - list      SNAPSHOT_DIR
  - restore   SNAPSHOT_ID SNAPSHOT_DIR TARGET_DIR [--backup-root DIR]

用法示例：
  python -m main_logic.memory_snapshot.cli snapshot /path/to/memory /path/to/snaps --label v1
  python -m main_logic.memory_snapshot.cli list /path/to/snaps
  python -m main_logic.memory_snapshot.cli restore 20260828_... /path/to/snaps /path/to/memory
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Optional, Sequence

from .rollback import SnapshotError, restore
from .snap import list_snapshots, snapshot


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="memory_snapshot",
        description="NEKO 记忆层快照/回滚旁路（纯标准库）",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_snap = sub.add_parser("snapshot", help="导出记忆目录现状为 JSON 快照")
    p_snap.add_argument("source", help="记忆目录（每角色目录）")
    p_snap.add_argument("snapshot_dir", help="快照落盘目录")
    p_snap.add_argument("--label", default=None, help="恢复点标记名")
    p_snap.add_argument("--note", default=None, help="备注")
    p_snap.set_defaults(func=_cmd_snapshot)

    p_list = sub.add_parser("list", help="列出快照与恢复点")
    p_list.add_argument("snapshot_dir", help="快照目录")
    p_list.set_defaults(func=_cmd_list)

    p_restore = sub.add_parser("restore", help="从快照还原（回滚前强制备份）")
    p_restore.add_argument("snapshot_id", help="快照 id / 文件名 / 路径")
    p_restore.add_argument("snapshot_dir", help="快照目录")
    p_restore.add_argument("target", help="要还原到的记忆目录")
    p_restore.add_argument("--backup-root", default=None, help="备份根目录（缺省 snapshot_dir/backups）")
    p_restore.set_defaults(func=_cmd_restore)

    return parser


def _cmd_snapshot(args: argparse.Namespace) -> int:
    meta = snapshot(args.source, args.snapshot_dir, label=args.label, note=args.note)
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    metas = list_snapshots(args.snapshot_dir)
    print(json.dumps(metas, ensure_ascii=False, indent=2))
    return 0


def _cmd_restore(args: argparse.Namespace) -> int:
    try:
        result = restore(
            args.snapshot_id,
            args.snapshot_dir,
            args.target,
            backup_root=args.backup_root,
        )
    except SnapshotError as exc:
        print(f"restore 失败: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
