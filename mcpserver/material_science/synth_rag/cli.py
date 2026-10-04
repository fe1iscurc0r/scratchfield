"""合成路线旁路 CLI（I-02）：add / search / validate / seed 子命令。

用法示例：
  python -m mcpserver.material_science.synth_rag.cli seed
  python -m mcpserver.material_science.synth_rag.cli search --product 木质素
  python -m mcpserver.material_science.synth_rag.cli validate --all
  python -m mcpserver.material_science.synth_rag.cli add --json '{"name":"...","product":"..."}'

纯标准库 argparse + sqlite3，不依赖外部包；库路径由 store.default_db_path() 决定。
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from . import example_data, retrieve, validator
from .store import RouteStore, default_db_path


def _store(args: argparse.Namespace) -> RouteStore:
    return RouteStore(args.db or default_db_path())


def cmd_seed(args: argparse.Namespace) -> int:
    store = _store(args)
    try:
        n = example_data.seed_examples(store)
        print(f"已内置示例路线 {n} 条（库共 {store.count()} 条）")
        return 0
    finally:
        store.close()


def cmd_add(args: argparse.Namespace) -> int:
    store = _store(args)
    try:
        if args.json:
            payload = json.loads(args.json)
        elif args.file:
            payload = json.loads(open(args.file, encoding="utf-8").read())
        else:
            print("错误：add 需要 --json 或 --file", file=sys.stderr)
            return 2
        route_id = store.add_route(payload)
        print(f"已入库路线 id={route_id}：{payload.get('name', '')}")
        return 0
    except (ValueError, json.JSONDecodeError, OSError) as e:
        print(f"入库失败：{e}", file=sys.stderr)
        return 1
    finally:
        store.close()


def cmd_search(args: argparse.Namespace) -> int:
    store = _store(args)
    try:
        res = retrieve.search(
            store, product=args.product or "", reactant=args.reactant or "",
            condition=args.condition or "", top_k=args.top_k)
        if not res["success"]:
            print(f"检索失败：{res.get('error')}", file=sys.stderr)
            return 1
        if not res["results"]:
            print("无命中路线")
            return 0
        for r in res["results"]:
            matched = ",".join(r["matched_on"]) or "全量"
            print(f"[{r['route_id']}] {r['name']} → {r['product']} "
                  f"(score={r['score']}, 命中={matched})")
        return 0
    finally:
        store.close()


def cmd_validate(args: argparse.Namespace) -> int:
    store = _store(args)
    try:
        if args.all:
            routes = store.list_routes()
        elif args.route_id is not None:
            r = store.get_route(args.route_id)
            routes = [r] if r else []
            if not r:
                print(f"路线 id={args.route_id} 不存在", file=sys.stderr)
                return 1
        else:
            print("错误：validate 需要 --all 或 --route-id", file=sys.stderr)
            return 2
        for route in routes:
            res = validator.validate(route)
            status = "✓ 通过" if res["valid"] else "✗ 拒绝"
            print(f"[{route.id}] {route.name}：{status}")
            for it in res["issues"]:
                print(f"    - [{it['severity']}] {it['rule']}: {it['message']}")
        return 0
    finally:
        store.close()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="synth_rag", description="材料合成路线 RAG 旁路（PIRAG SSKB 范式落地）")
    sub = p.add_subparsers(dest="command", required=True)

    # 共享父解析器：--db 挂在每个子命令后（subcommand 后接参数，符合 CLI 惯例）
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument("--db", default=None,
                        help="SQLite 库路径（默认 %APPDATA%/Lumo/synth_rag/routes.db）")

    sp_seed = sub.add_parser("seed", parents=[parent], help="内置示例路线入库")
    sp_seed.set_defaults(func=cmd_seed)

    sp_add = sub.add_parser("add", parents=[parent], help="入库一条路线（JSON）")
    sp_add.add_argument("--json", default=None, help="内联 JSON 字符串")
    sp_add.add_argument("--file", default=None, help="JSON 文件路径")
    sp_add.set_defaults(func=cmd_add)

    sp_search = sub.add_parser("search", parents=[parent], help="按产物/反应物/条件检索")
    sp_search.add_argument("--product", default=None)
    sp_search.add_argument("--reactant", default=None)
    sp_search.add_argument("--condition", default=None)
    sp_search.add_argument("--top-k", type=int, default=10)
    sp_search.set_defaults(func=cmd_search)

    sp_val = sub.add_parser("validate", parents=[parent], help="物理校验路线")
    sp_val.add_argument("--all", action="store_true")
    sp_val.add_argument("--route-id", type=int, default=None)
    sp_val.set_defaults(func=cmd_validate)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
