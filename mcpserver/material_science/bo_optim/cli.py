"""BO 寻优 CLI：init / recommend / record 子命令。

闭环用法（与 xtalyst 衔接，推荐点可导出 CSV 作为下一批合成配方表）:
    python -m mcpserver.material_science.bo_optim.cli init       --n 4 --state bo.json
    python -m mcpserver.material_science.bo_optim.cli record     --state bo.json --recipe '{...}' --metrics '{...}'
    python -m mcpserver.material_science.bo_optim.cli recommend  --state bo.json --n 3 --out next_batch.csv

状态文件为 JSON（space=内置"lignin"），真实实验数据留真机，本 CLI 以合成数据验收。
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from .loop import BOLoop
from .params import ParameterSpace, lignin_hydrothermal_space

_SPACE_KIND = "lignin"


def _build_space() -> ParameterSpace:
    return lignin_hydrothermal_space()


def _build_loop(strategy: str = "ei") -> BOLoop:
    return BOLoop(_build_space(), strategy=strategy)


def _state_dict(loop: BOLoop) -> Dict[str, Any]:
    return {
        "space": _SPACE_KIND,
        "strategy": loop.strategy,
        "points": [dict(p) for p in loop.points],
        "metrics": [dict(m) if m else None for m in loop.metrics],
        "failed": [bool(f) for f in loop.failed],
        "y": [float(v) for v in loop.y],
        "pending": [dict(p) for p in loop.pending],
    }


def _load(path: str) -> BOLoop:
    state = json.loads(Path(path).read_text(encoding="utf-8"))
    loop = _build_loop(state.get("strategy", "ei"))
    loop.points = [dict(p) for p in state.get("points", [])]
    loop.metrics = [dict(m) if m else None for m in state.get("metrics", [])]
    loop.failed = [bool(f) for f in state.get("failed", [])]
    loop.y = [float(v) for v in state.get("y", [])]
    loop.pending = [dict(p) for p in state.get("pending", [])]
    loop.X = [loop.space.encode(p) for p in loop.points]
    return loop


def _save(loop: BOLoop, path: str) -> None:
    Path(path).write_text(
        json.dumps(_state_dict(loop), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _recipes_to_csv(recipes: List[Dict[str, Any]], space: ParameterSpace, path: str) -> None:
    """把推荐配方导出为 CSV（下一批合成配方表，衔接 xtalyst 湿环节）。"""
    fields = space.continuous_names + space.categorical_names
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in recipes:
            w.writerow({k: r.get(k) for k in fields})


def _parse_json_arg(raw: str | None, what: str) -> Dict[str, Any]:
    if not raw:
        return {}
    p = Path(raw)
    if p.exists():
        raw = p.read_text(encoding="utf-8")
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as e:
        raise SystemExit(f"{what} 不是合法 JSON: {e}") from e
    if not isinstance(obj, dict):
        raise SystemExit(f"{what} 必须是 JSON 对象")
    return obj


def cmd_init(args) -> int:
    loop = _build_loop(args.strategy)
    initial = loop.init(n=args.n)
    _save(loop, args.state)
    print(json.dumps({"initial": initial, "n": len(initial), "state": args.state},
                     ensure_ascii=False, indent=2))
    return 0


def cmd_recommend(args) -> int:
    loop = _load(args.state)
    recipes = loop.recommend_batch(k=args.n)
    if args.out:
        _recipes_to_csv(recipes, loop.space, args.out)
    print(json.dumps({"recommended": recipes, "n": len(recipes)}, ensure_ascii=False, indent=2))
    return 0


def cmd_record(args) -> int:
    loop = _load(args.state)
    recipe = _parse_json_arg(args.recipe, "--recipe")
    metrics = _parse_json_arg(args.metrics, "--metrics") if args.metrics else None
    if not recipe:
        print("错误：--recipe 为空", file=sys.stderr)
        return 2
    try:
        loop.record(recipe, metrics, failed=args.failed)
    except ValueError as e:
        print(f"错误：配方非法 - {e}", file=sys.stderr)
        return 2
    loop.update()
    out = args.out or args.state
    _save(loop, out)
    print(json.dumps({"recorded": recipe, "failed": bool(args.failed),
                      "n_observations": loop.n_observations(), "state": out},
                     ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="bo_optim",
        description="贝叶斯优化寻优旁路（init / recommend / record）",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("init", help="采样初始粗扫点并保存状态")
    sp.add_argument("--n", type=int, default=4, help="初始点数（默认 4）")
    sp.add_argument("--state", required=True, help="状态文件 JSON 路径")
    sp.add_argument("--strategy", default="ei", help="采集策略 ei/ucb/random")
    sp.set_defaults(func=cmd_init)

    sp = sub.add_parser("recommend", help="推荐下一批实验点（可导出 CSV）")
    sp.add_argument("--state", required=True, help="状态文件 JSON 路径")
    sp.add_argument("--n", type=int, default=1, help="推荐点数（默认 1）")
    sp.add_argument("--out", default=None, help="可选：导出配方 CSV 路径")
    sp.set_defaults(func=cmd_recommend)

    sp = sub.add_parser("record", help="回填一次实测（含失败实验）")
    sp.add_argument("--state", required=True, help="状态文件 JSON 路径")
    sp.add_argument("--recipe", required=True, help="配方 JSON（字符串或文件路径）")
    sp.add_argument("--metrics", default=None, help="指标 JSON（字符串或文件路径）")
    sp.add_argument("--failed", action="store_true", help="标记为失败实验")
    sp.add_argument("--out", default=None, help="可选：写出状态到新路径")
    sp.set_defaults(func=cmd_record)
    return p


def main(argv: List[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
