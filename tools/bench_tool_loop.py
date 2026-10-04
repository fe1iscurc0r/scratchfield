"""bench_tool_loop.py — 拆分前后纯函数基准（卷190-A2 验收：耗时差 ≤5%）。

从指定 revision 取**拆分前**的 `agentic_tool_loop.py`，与当前薄壳（拆分包）跑同一批
纯函数、同一批输入，比较总耗时。

为什么只测纯函数：解析/口径类函数无 IO、无副作用，重复调用稳定可比；
带网络/会话的执行器差异会被环境噪声淹没，不适合做 ≤5% 判据。

用法：
    .venv/Scripts/python.exe tools/bench_tool_loop.py                 # 默认 base=HEAD~N 自动找
    .venv/Scripts/python.exe tools/bench_tool_loop.py --rev <sha> --n 3000
"""
from __future__ import annotations

import argparse
import importlib
import importlib.util
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REL = "apiserver/agentic_tool_loop.py"

SAMPLE_TEXT = """先规划一下。
<|tool_calls_section_begin|>
<|tool_call_begin|>functions.mcp_alpha_search<|tool_call_argument_begin|>{"query": "perovskite stability", "top_k": 5}<|tool_call_end|>
<|tool_call_begin|>functions.local_file_read<|tool_call_argument_begin|>{"path": "docs/a.md"}<|tool_call_end|>
<|tool_calls_section_end|>
```json
{"tool_name": "web_fetch", "arguments": {"url": "https://example.com/x", "mode": "markdown"}}
```
{"status": "error", "message": "timeout while connecting"}
"""

SAMPLE_JSON = '{"a": 1, "b": {"c": "d"}}  前置说明 {"e": [1,2,3]} 尾注'

FUNCS = [
    ("parse_tool_calls_from_text", (SAMPLE_TEXT,)),
    ("_extract_json_objects", (SAMPLE_JSON,)),
    ("_effective_status", ({"status": "error", "message": "boom"},)),
    ("_retryable_failure", ({"status": "error", "message": "connection timeout"},)),
]


def _load_from_rev(rev: str):
    out = subprocess.run(["git", "show", f"{rev}:{REL}"], cwd=ROOT,
                         capture_output=True, text=True)
    if out.returncode != 0:
        raise SystemExit(f"✗ 无法读取 {rev}:{REL}: {out.stderr.strip()}")
    tmp = Path(tempfile.mkdtemp()) / "bench_old_tool_loop.py"
    tmp.write_text(out.stdout, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("_bench_old_tool_loop", tmp)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_bench_old_tool_loop"] = mod
    spec.loader.exec_module(mod)
    return mod


def _best_rev() -> str:
    """找最近的、仍是巨石形态的版本（本文件行数 >2000）。"""
    log = subprocess.run(["git", "log", "--format=%H", "-n", "20", "--", REL],
                         cwd=ROOT, capture_output=True, text=True).stdout.split()
    for sha in log:
        blob = subprocess.run(["git", "show", f"{sha}:{REL}"], cwd=ROOT,
                              capture_output=True, text=True).stdout
        if len(blob.splitlines()) > 2000:
            return sha
    return "HEAD"


def _run(mod, n: int) -> tuple[float, dict]:
    """跑 n 轮全部基准函数；返回 (总耗时秒, {函数: 首次结果摘要})。"""
    sigs = {}
    t0 = time.perf_counter()
    for _ in range(n):
        for name, args in FUNCS:
            fn = getattr(mod, name, None)
            if fn is None:
                continue
            try:
                r = fn(*args)
            except Exception as e:  # 参数形态差异不应让基准崩
                r = f"<{type(e).__name__}>"
            sigs.setdefault(name, repr(r)[:60])
    return time.perf_counter() - t0, sigs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rev", default=None, help="拆分前 revision（默认自动探测）")
    ap.add_argument("--n", type=int, default=2000, help="每个函数重复轮数")
    ap.add_argument("--rounds", type=int, default=3, help="取最好成绩的轮数")
    args = ap.parse_args()

    rev = args.rev or _best_rev()
    old = _load_from_rev(rev)
    new = importlib.import_module("apiserver.agentic_tool_loop")

    # 预热（避免首次 import/JIT/缓存差异）
    _run(old, 50)
    _run(new, 50)

    old_best = min(_run(old, args.n)[0] for _ in range(args.rounds))
    new_best = min(_run(new, args.n)[0] for _ in range(args.rounds))
    ratio = new_best / old_best if old_best else float("inf")

    print(f"基准 revision : {rev[:10]}  (n={args.n} × {args.rounds} 轮取最好)")
    print(f"拆分前耗时    : {old_best * 1000:.1f} ms")
    print(f"拆分后耗时    : {new_best * 1000:.1f} ms")
    print(f"比值          : {ratio * 100:.2f}%  （阈值 ≤105%）")

    _, sig_old = _run(old, 1)
    _, sig_new = _run(new, 1)
    diff = {k: (sig_old.get(k), sig_new.get(k))
            for k in sig_old if sig_old.get(k) != sig_new.get(k)}
    if diff:
        print("\n⚠️ 输出不一致（拆分改变了行为）：")
        for k, (a, b) in diff.items():
            print(f"   {k}\n     old={a}\n     new={b}")
        return 1
    print("✓ 输出逐函数一致；耗时差在阈值内" if ratio <= 1.05 else "✗ 耗时差超阈值")
    return 0 if ratio <= 1.05 else 1


if __name__ == "__main__":
    sys.exit(main())
