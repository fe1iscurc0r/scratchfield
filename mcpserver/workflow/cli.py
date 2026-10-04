"""workflow-board CLI — 工单板命令行。

用法：
  workflow-board create <id> [--title ...] [--desc ...] [--deps a,b] [--parent p] [--assignee x]
  workflow-board list [--status s] [--assignee a]
  workflow-board assign <id> <assignee>
  workflow-board claim <id> [--scope s] [--owner o] [--ttl n]
  workflow-board status <id> [--set to] [--reason code]
  workflow-board done <id>          # 完成（审查门开启时进 in_review）
  workflow-board blocked <id> --reason code
  workflow-board approve <id> --reviewer name [--conclusion text]
  workflow-board reject <id> --reviewer name [--conclusion text]
  workflow-board release <id> [--scope s] [--owner o]
  workflow-board heartbeat <id> [--scope s] [--owner o]

默认数据库文件：./workflow.db（可用 --db 或 WORKFLOW_DB 覆盖）。
"""

from __future__ import annotations

import argparse
import os
import sys

from mcpserver.workflow import claim as claim_mod
from mcpserver.workflow import review_gate
from mcpserver.workflow.board import Board
from mcpserver.workflow.task import Task


def _open_board(args: argparse.Namespace) -> Board:
    db = args.db or os.environ.get("WORKFLOW_DB") or "workflow.db"
    return Board(db_path=db)


def _print_task(t: Task) -> None:
    deps = ",".join(t.deps) if t.deps else "-"
    assignee = t.assignee or "-"
    reason = t.reason_code or "-"
    review = ""
    if t.review:
        r = t.review
        review = f" | review={r.get('reviewer')}:{r.get('approved')}"
    print(f"{t.id}\t{t.status}\t{t.title}\tdeps={deps}\tassignee={assignee}"
          f"\treason={reason}{review}")


def cmd_create(args: argparse.Namespace, board: Board) -> int:
    deps = [d.strip() for d in (args.deps or "").split(",") if d.strip()]
    task = Task(id=args.id, title=args.title or "", desc=args.desc or "",
                deps=deps, parent=args.parent, assignee=args.assignee)
    board.create(task)
    print(f"created {task.id}")
    return 0


def cmd_list(args: argparse.Namespace, board: Board) -> int:
    tasks = board.list(status=args.status, assignee=args.assignee)
    if not tasks:
        print("(空板)")
        return 0
    for t in tasks:
        _print_task(t)
    return 0


def cmd_assign(args: argparse.Namespace, board: Board) -> int:
    board.assign(args.id, args.assignee)
    print(f"assigned {args.id} -> {args.assignee}")
    return 0


def cmd_claim(args: argparse.Namespace, board: Board) -> int:
    won = claim_mod.claim(board, args.id, args.scope, args.owner,
                          ttl_seconds=args.ttl)
    print(f"claim {'won' if won else 'lost (no-op)'} {args.id} "
          f"scope={args.scope} owner={args.owner}")
    return 0 if won else 1


def cmd_status(args: argparse.Namespace, board: Board) -> int:
    task = board.get(args.id)
    if task is None:
        print(f"task not found: {args.id}")
        return 1
    if args.set:
        board.set_status(args.id, args.set, reason_code=args.reason)
        task = board.get(args.id)
    _print_task(task)
    return 0


def cmd_done(args: argparse.Namespace, board: Board) -> int:
    task = board.complete(args.id)
    print(f"{args.id} -> {task.status}")
    return 0


def cmd_blocked(args: argparse.Namespace, board: Board) -> int:
    if not args.reason:
        print("blocked 需要 --reason code（可等/不可等分类）", file=sys.stderr)
        return 1
    task = board.block(args.id, args.reason)
    print(f"{args.id} -> {task.status} reason={task.reason_code}")
    return 0


def cmd_approve(args: argparse.Namespace, board: Board) -> int:
    task = review_gate.approve(board, args.id, args.reviewer,
                               conclusion=args.conclusion or "")
    print(f"{args.id} -> {task.status} (approved by {args.reviewer})")
    return 0


def cmd_reject(args: argparse.Namespace, board: Board) -> int:
    task = review_gate.reject(board, args.id, args.reviewer,
                              conclusion=args.conclusion or "")
    print(f"{args.id} -> {task.status} (rejected by {args.reviewer})")
    return 0


def cmd_release(args: argparse.Namespace, board: Board) -> int:
    ok = claim_mod.release(board, args.id, args.scope, owner=args.owner)
    print(f"release {args.id} scope={args.scope} -> {ok}")
    return 0 if ok else 1


def cmd_heartbeat(args: argparse.Namespace, board: Board) -> int:
    ok = claim_mod.heartbeat(board, args.id, args.scope, args.owner,
                             ttl_seconds=args.ttl)
    print(f"heartbeat {args.id} scope={args.scope} owner={args.owner} -> {ok}")
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="workflow-board",
                                     description="多智能体工单板 CLI")
    parser.add_argument("--db", default=None, help="SQLite 数据库路径（默认 workflow.db）")

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--db", default=None, help="SQLite 数据库路径（默认 workflow.db）")

    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("create", help="创建工单", parents=[common])
    p.add_argument("id")
    p.add_argument("--title", default="")
    p.add_argument("--desc", default="")
    p.add_argument("--deps", default="", help="逗号分隔依赖 id")
    p.add_argument("--parent", default=None)
    p.add_argument("--assignee", default=None)
    p.set_defaults(func=cmd_create)

    p = sub.add_parser("list", help="列出工单", parents=[common])
    p.add_argument("--status", default=None)
    p.add_argument("--assignee", default=None)
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("assign", help="指派负责人", parents=[common])
    p.add_argument("id")
    p.add_argument("assignee")
    p.set_defaults(func=cmd_assign)

    p = sub.add_parser("claim", help="认领（单赢家）", parents=[common])
    p.add_argument("id")
    p.add_argument("--scope", default="default")
    p.add_argument("--owner", default="agent")
    p.add_argument("--ttl", type=float, default=60.0)
    p.set_defaults(func=cmd_claim)

    p = sub.add_parser("status", help="查看/设置状态", parents=[common])
    p.add_argument("id")
    p.add_argument("--set", default=None, help="迁移到目标状态")
    p.add_argument("--reason", default=None)
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("done", help="完成（审查门开启时进 in_review）", parents=[common])
    p.add_argument("id")
    p.set_defaults(func=cmd_done)

    p = sub.add_parser("blocked", help="阻塞（必带 reason code）", parents=[common])
    p.add_argument("id")
    p.add_argument("--reason", required=True)
    p.set_defaults(func=cmd_blocked)

    p = sub.add_parser("approve", help="人审通过 → done", parents=[common])
    p.add_argument("id")
    p.add_argument("--reviewer", required=True)
    p.add_argument("--conclusion", default="")
    p.set_defaults(func=cmd_approve)

    p = sub.add_parser("reject", help="人审退回 → in_progress", parents=[common])
    p.add_argument("id")
    p.add_argument("--reviewer", required=True)
    p.add_argument("--conclusion", default="")
    p.set_defaults(func=cmd_reject)

    p = sub.add_parser("release", help="释放租约", parents=[common])
    p.add_argument("id")
    p.add_argument("--scope", default="default")
    p.add_argument("--owner", default=None)
    p.set_defaults(func=cmd_release)

    p = sub.add_parser("heartbeat", help="续租", parents=[common])
    p.add_argument("id")
    p.add_argument("--scope", default="default")
    p.add_argument("--owner", default="agent")
    p.add_argument("--ttl", type=float, default=60.0)
    p.set_defaults(func=cmd_heartbeat)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    board = _open_board(args)
    try:
        return args.func(args, board)
    except (KeyError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        board.close()


if __name__ == "__main__":
    raise SystemExit(main())
