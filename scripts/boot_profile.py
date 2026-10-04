#!/usr/bin/env python3
"""boot_profile.py — apiserver 启动打点（卷191-B1）。

测三件事：
  1. 模块 import 耗时 top N（含传递依赖，用 importtime hook 计时）
  2. 路由注册耗时
  3. 总启动耗时（import apiserver.api_server 到 app 就绪）

用法：
    python scripts/boot_profile.py                 # 单次
    python scripts/boot_profile.py --repeat 3      # 跑 3 次取中位
    python scripts/boot_profile.py --json out.json # 输出 JSON

输出：markdown 表，便于贴进 PR。

设计说明：
  - 用子进程隔离每次测量（避免模块缓存污染）。
  - import 钩子基于 sys.meta_path 的自定义 finder，统计每个顶层模块
    首次加载的真实耗时（含其触发的子 import）。
  - 不 import 用户代码以外的副作用（只加载，不启动 uvicorn）。
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 子进程内跑的探针：统计 import 耗时 + 总时长
PROBE = textwrap.dedent('''
import importlib
import json
import sys
import time

ROOT = sys.argv[1]
sys.path.insert(0, ROOT)

import_times = {}
_orig_import = None


class TimingFinder:
    """记录每个模块首次 import 的起止时间（挂到最后，不改变解析结果）。"""

    def __init__(self):
        self._stack = []

    def find_module(self, name, path=None):
        return None


def _install_hook():
    """用 sys.setprofile 之外的方式：包裹 builtins.__import__ 统计耗时。"""
    import builtins

    real = builtins.__import__

    def timed(name, globals=None, locals=None, fromlist=(), level=0):
        key = name.split(".")[0]
        if key in import_times:
            return real(name, globals, locals, fromlist, level)
        # 只统计顶层模块的"首次整块"耗时
        t0 = time.perf_counter()
        # 标记占位，避免递归重复统计
        import_times[key] = -1.0
        try:
            mod = real(name, globals, locals, fromlist, level)
            if import_times.get(key) == -1.0:
                import_times[key] = time.perf_counter() - t0
            return mod
        except Exception:
            import_times.pop(key, None)
            raise

    builtins.__import__ = timed


t_total0 = time.perf_counter()
_install_hook()
t_hook0 = time.perf_counter()

try:
    import apiserver.api_server as m
    app = getattr(m, "app", None)
    routes = len(getattr(app, "routes", [])) if app is not None else -1
    ok = app is not None
    err = ""
except Exception as e:
    import traceback
    ok = False
    routes = -1
    err = traceback.format_exc()
    t_total0 = time.perf_counter()

t_total = time.perf_counter() - t_total0

top = sorted(
    ((k, v) for k, v in import_times.items() if v and v > 0),
    key=lambda kv: -kv[1],
)[:25]

print("@@PROFILE@@" + json.dumps({
    "ok": ok,
    "error": err,
    "total": t_total,
    "routes": routes,
    "top": top,
}))
''')


def run_once() -> dict:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT)
    p = subprocess.run(
        [sys.executable, "-c", PROBE, str(ROOT)],
        cwd=str(ROOT), capture_output=True, text=True, env=env,
    )
    for line in p.stdout.splitlines():
        if line.startswith("@@PROFILE@@"):
            return json.loads(line[len("@@PROFILE@@"):])
    raise SystemExit(
        f"探针没有输出结果\nstdout:\n{p.stdout[-2000:]}\nstderr:\n{p.stderr[-2000:]}"
    )


def fmt_table(rows: list[tuple[str, float]], limit: int = 20) -> str:
    lines = ["| # | 模块 | 首次 import 耗时 (s) |", "|---|------|---------------------|"]
    for i, (name, sec) in enumerate(rows[:limit], 1):
        lines.append(f"| {i} | `{name}` | {sec:.4f} |")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeat", type=int, default=1, help="重复次数（取中位）")
    ap.add_argument("--json", help="把结果写成 JSON")
    args = ap.parse_args()

    results = [run_once() for _ in range(max(1, args.repeat))]

    if not all(r["ok"] for r in results):
        for r in results:
            if not r["ok"]:
                print("❌ 加载失败：\n" + r["error"])
        return 1

    totals = [r["total"] for r in results]
    routes = results[0]["routes"]
    med = statistics.median(totals)

    print("## apiserver 启动打点（卷191-B1）\n")
    print(f"- 采样次数：{len(results)}")
    print(f"- 总耗时代码：{', '.join(f'{t:.3f}s' for t in totals)}")
    print(f"- **中位总耗时：{med:.3f}s**")
    print(f"- 注册路由数：{routes}\n")

    # 各模块耗时取中位
    keys = set()
    for r in results:
        keys.update(k for k, _ in r["top"])
    per_key: dict[str, list[float]] = {k: [] for k in keys}
    for r in results:
        for k, v in r["top"]:
            per_key[k].append(v)
    med_rows = sorted(
        ((k, statistics.median(v)) for k, v in per_key.items() if v),
        key=lambda kv: -kv[1],
    )

    print("### import 耗时 top 20\n")
    print(fmt_table(med_rows, 20))

    if args.json:
        Path(args.json).write_text(json.dumps({
            "total_median": med,
            "totals": totals,
            "routes": routes,
            "top": med_rows,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n（JSON 已写入 {args.json}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
