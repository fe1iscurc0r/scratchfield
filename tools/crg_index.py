#!/usr/bin/env python3
"""code-review-graph 索引 CLI —— 建图 / 查询 / 影响半径 / 变更检测 / token 对比。

零新依赖（stdlib + 本仓 mcpserver.adapters.code_review.engine），可独立运行，
也供 02-03 GitHub Action 调用（CI 无 LLM、tree-sitter 全确定性解析）。

用法示例：
    python tools/crg_index.py --build apiserver                 # 建图 → crg-out/index.json
    python tools/crg_index.py --query run_agentic_loop          # 查定义 + 调用者/被调者
    python tools/crg_index.py --impact apiserver/agentic_tool_loop.py
    python tools/crg_index.py --changes --base HEAD~1           # git diff → 风险分 + 测试缺口
    python tools/crg_index.py --overview
    python tools/crg_index.py --tokens apiserver/agentic_tool_loop.py  # 全量读 vs 图查询

输出为 JSON（确定性，无时间戳），便于 grep / jq / CI 断言。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_INDEX = _REPO_ROOT / "crg-out" / "index.json"

# 建图模块延迟导入，避免 --help 时拖慢（engine 无重依赖，此处仅为干净起见）
from mcpserver.adapters.code_review.engine import (  # noqa: E402
    CodeReviewError,
    GraphIndex,
    estimate_tokens,
)


def _load_or_build(args: argparse.Namespace) -> GraphIndex:
    index_path = Path(args.index) if args.index else _DEFAULT_INDEX
    if index_path.is_file():
        return GraphIndex.load(str(index_path))
    raise CodeReviewError(
        f"索引不存在: {index_path} —— 先 python tools/crg_index.py --build <目录>")


def cmd_build(args: argparse.Namespace) -> int:
    root = args.build
    if not Path(root).is_dir():
        print(json.dumps({"status": "error", "error": f"目录不存在: {root}"},
                         ensure_ascii=False))
        return 2
    idx = GraphIndex.build(root)
    out = Path(args.index) if args.index else _DEFAULT_INDEX
    saved = idx.save(out)
    print(json.dumps({
        "status": "ok", "index_json": saved, "root": idx.root,
        "files": len(idx._module_of_file), "nodes": len(idx.nodes),
        "edges": len(idx.edges),
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_query(args: argparse.Namespace) -> int:
    idx = _load_or_build(args)
    try:
        result = idx.query(args.query, limit=args.limit)
    except CodeReviewError as e:
        print(json.dumps({"status": "error", "error": str(e)}, ensure_ascii=False))
        return 1
    print(json.dumps({"status": "ok", **result}, ensure_ascii=False, indent=2))
    return 0


def cmd_impact(args: argparse.Namespace) -> int:
    idx = _load_or_build(args)
    files = [f for f in (args.impact or "").split(",") if f.strip()] \
        if isinstance(args.impact, str) else args.impact
    try:
        result = idx.impact_radius(files, max_depth=args.depth)
    except CodeReviewError as e:
        print(json.dumps({"status": "error", "error": str(e)}, ensure_ascii=False))
        return 1
    print(json.dumps({"status": "ok", **result}, ensure_ascii=False, indent=2))
    return 0


def cmd_changes(args: argparse.Namespace) -> int:
    idx = _load_or_build(args)
    try:
        result = idx.detect_changes(base=args.base, max_depth=args.depth)
    except CodeReviewError as e:
        print(json.dumps({"status": "error", "error": str(e)}, ensure_ascii=False))
        return 1
    print(json.dumps({"status": "ok", **result}, ensure_ascii=False, indent=2))
    return 0


def cmd_overview(args: argparse.Namespace) -> int:
    idx = _load_or_build(args)
    result = idx.architecture_overview(top_k=args.top_k)
    print(json.dumps({"status": "ok", **result}, ensure_ascii=False, indent=2))
    return 0


def cmd_tokens(args: argparse.Namespace) -> int:
    """全量读 vs 图查询 token 对比（chars/4 估算口径，与上游同口径，如实标注）。"""
    idx = _load_or_build(args)
    rel = args.tokens.replace("\\", "/")
    full_path = Path(idx.root) / rel
    if not full_path.is_file():
        print(json.dumps({"status": "error", "error": f"文件不在索引 root 下: {rel}"},
                         ensure_ascii=False))
        return 1
    full_text = full_path.read_text(encoding="utf-8")
    full_tokens = estimate_tokens(full_text)
    # 该文件的顶层函数/类：逐个 query 求和作为"图查询"所需 token
    top_ids = [n["id"] for n in idx.nodes
               if n["file"] == rel and n["kind"] in ("function", "method", "class")
               and "::" not in n["qualname"]] or \
              [n["id"] for n in idx.nodes if n["file"] == rel and n["kind"] != "module"]
    per_query = []
    graph_tokens = 0
    for nid in top_ids:
        name = idx._by_id[nid]["qualname"] or idx._by_id[nid]["name"]
        r = idx.query(name, limit=1)
        t = estimate_tokens(json.dumps(r, ensure_ascii=False))
        per_query.append({"name": name, "tokens": t})
        graph_tokens += t
    result = {
        "status": "ok",
        "file": rel,
        "chars": len(full_text),
        "full_read_tokens": full_tokens,
        "graph_query_tokens": graph_tokens,
        "ratio": round(full_tokens / max(graph_tokens, 1), 1),
        "per_query": per_query,
        "token_note": "chars/4 估算口径（与上游 CHARS_PER_TOKEN 同口径），"
                      "非 tokenizer 精确计数；图查询 tokens 为该文件顶层符号逐一 query 之和",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="crg_index",
        description="code-review-graph 索引 CLI（建图/查询/影响半径/变更检测/token 对比）")
    p.add_argument("--build", metavar="DIR", help="对目录建图 → crg-out/index.json")
    p.add_argument("--query", metavar="NAME", help="按函数/类名查定义 + 调用者/被调者")
    p.add_argument("--impact", metavar="FILES", help="变更文件（逗号分隔）反向影响半径")
    p.add_argument("--changes", action="store_true", help="git diff 变更检测（风险分+测试缺口）")
    p.add_argument("--overview", action="store_true", help="架构总览")
    p.add_argument("--tokens", metavar="FILE", help="全量读 vs 图查询 token 对比")
    p.add_argument("--base", default="HEAD~1", help="git 对比基（默认 HEAD~1）")
    p.add_argument("--depth", type=int, default=2, help="BFS/执行流深度（默认 2）")
    p.add_argument("--limit", type=int, default=10, help="query 返回上限（默认 10）")
    p.add_argument("--top-k", type=int, default=10, help="overview 榜单长度（默认 10）")
    p.add_argument("--index", help="索引 JSON 路径（默认 crg-out/index.json）")
    args = p.parse_args(argv)

    try:
        if args.build:
            return cmd_build(args)
        if args.query:
            return cmd_query(args)
        if args.impact:
            return cmd_impact(args)
        if args.changes:
            return cmd_changes(args)
        if args.overview:
            return cmd_overview(args)
        if args.tokens:
            return cmd_tokens(args)
    except CodeReviewError as e:
        print(json.dumps({"status": "error", "error": str(e)}, ensure_ascii=False))
        return 1
    p.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
