"""cli.py — fit / apply / export 子命令（python -m mcpserver.material_science.symbolic.cli）。

- fit   : --csv <path> --target <col> [--output <expr.json>] → 拟合并保存表达式
- apply : --expr <path|text> --input "x0=1.5,x1=2.0" | --csv <path> → 预测
- export: --expr <path|text> --format text|latex|json → 导出表达式

输出统一为 JSON（stdout），异常时返回 {"ok": false, "error": ...} 且退出码 1。
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

from .expr import Expression
from .fit import fit


def _read_table(csv_path: str) -> tuple[list[str], list[list[float]]]:
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    if not rows:
        raise ValueError(f"CSV 为空: {csv_path}")
    cols = list(rows[0].keys())
    data = [[float(r[c]) for c in cols] for r in rows]
    return cols, data


def _cmd_fit(args) -> dict[str, Any]:
    import numpy as np
    cols, data = _read_table(args.csv)
    if args.target not in cols:
        raise ValueError(f"目标列 {args.target} 不在 {cols}")
    feats = [c for c in cols if c != args.target]
    M = np.array(data, dtype=float)
    X = M[:, [cols.index(c) for c in feats]]
    y = M[:, cols.index(args.target)]
    res = fit(X, y, feature_names=feats, generations=args.generations,
              random_state=args.random_state)
    if args.output:
        res.expression.save(args.output)
    return {"ok": True, "expression": res.expression.text,
            "rmse": round(res.rmse, 6), "r2": round(res.r2, 6),
            "feature_names": feats, "output": args.output}


def _cmd_apply(args) -> dict[str, Any]:
    expr = Expression.load(args.expr) if Path(args.expr).is_file() else Expression(args.expr)
    if args.input:
        values: dict[str, float] = {}
        for pair in args.input.split(","):
            k, _, v = pair.partition("=")
            if not k.strip() or v == "":
                raise ValueError(f"非法输入 {pair!r}，格式 key=value")
            values[k.strip()] = float(v)
        return {"ok": True, "predictions": [round(float(expr.evaluate(values)), 6)],
                "input": values}
    if args.csv:
        cols, data = _read_table(args.csv)
        out = []
        for row in data:
            values = {c: v for c, v in zip(cols, row)}
            out.append(round(float(expr.evaluate(values)), 6))
        return {"ok": True, "predictions": out}
    raise ValueError("apply 需要 --input 或 --csv")


def _cmd_export(args) -> dict[str, Any]:
    expr = Expression.load(args.expr) if Path(args.expr).is_file() else Expression(args.expr)
    fmt = args.format
    if fmt == "json":
        return expr.to_dict()
    if fmt == "latex":
        return {"expression": expr.to_latex()}
    return {"expression": expr.to_text()}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="symbolic", description="符号回归旁路 CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    pf = sub.add_parser("fit", help="拟合显式表达式")
    pf.add_argument("--csv", required=True)
    pf.add_argument("--target", required=True)
    pf.add_argument("--output", default=None)
    pf.add_argument("--generations", type=int, default=40)
    pf.add_argument("--random-state", type=int, default=0)
    pf.set_defaults(func=_cmd_fit)

    pa = sub.add_parser("apply", help="应用表达式预测")
    pa.add_argument("--expr", required=True)
    pa.add_argument("--input", default=None)
    pa.add_argument("--csv", default=None)
    pa.set_defaults(func=_cmd_apply)

    pe = sub.add_parser("export", help="导出表达式文本/LaTeX/JSON")
    pe.add_argument("--expr", required=True)
    pe.add_argument("--format", choices=["text", "latex", "json"], default="text")
    pe.set_defaults(func=_cmd_export)

    args = p.parse_args(argv)
    try:
        out = args.func(args)
        print(json.dumps(out, ensure_ascii=False))
        return 0
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
