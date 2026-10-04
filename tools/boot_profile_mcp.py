"""boot_profile_mcp.py — mcp 注册冷启动打点（卷189-A1 前后对比数据）。

测三段：
  ① import mcpserver.mcp_registry（模块加载）
  ② auto_register_mcp()（扫描 manifest + 创建 agent 实例）
  ③ 汇总：manifest 数 / 实例化数 / 冷启动总耗时

用法：
    .venv/Scripts/python.exe tools/boot_profile_mcp.py            # 单次
    .venv/Scripts/python.exe tools/boot_profile_mcp.py --repeat 3  # 取中位
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def one_run() -> dict:
    """一次冷启动（本进程内）。repeat>1 时由 main 用子进程隔离调用。"""
    t0 = time.perf_counter()
    import importlib
    reg = importlib.import_module("mcpserver.mcp_registry")
    t_import = time.perf_counter() - t0

    t1 = time.perf_counter()
    try:
        names = reg.auto_register_mcp()
    except Exception as e:  # 依赖缺失等不应让打点崩
        names = []
        print(f"[warn] auto_register_mcp 异常: {e}", file=sys.stderr)
    t_reg = time.perf_counter() - t1

    n_inst = len(getattr(reg, "MCP_REGISTRY", {}))
    n_manifest = len(getattr(reg, "MANIFEST_CACHE", {}))
    n_cold = len(getattr(reg, "_COLD_TABLE", {}))
    return {
        "import_s": round(t_import, 4),
        "register_s": round(t_reg, 4),
        "total_s": round(t_import + t_reg, 4),
        "services_registered": len(names),
        "instances": n_inst,
        "manifests": n_manifest,
        "cold_table": n_cold,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeat", type=int, default=1,
                    help="重复次数（取中位；>1 时逐次起子进程隔离，避免幂等短路）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--subprocess", action="store_true", help="内部用：单次运行输出 JSON")
    args = ap.parse_args()

    if args.subprocess:
        print(json.dumps(one_run(), ensure_ascii=False))
        return 0

    if args.repeat > 1:
        import subprocess
        runs = []
        for _ in range(args.repeat):
            out = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "--subprocess"],
                capture_output=True, text=True, cwd=str(ROOT),
            )
            line = (out.stdout or "").strip().splitlines()
            if not line:
                print(f"[warn] 子进程无输出: {(out.stderr or '')[:200]}", file=sys.stderr)
                continue
            runs.append(json.loads(line[-1]))
    else:
        runs = [one_run()]
    if args.json:
        print(json.dumps(runs, ensure_ascii=False, indent=2))
        return 0
    for k in ("import_s", "register_s", "total_s"):
        vals = [r[k] for r in runs]
        print(f"{k:12s} median={statistics.median(vals):.4f}s  all={vals}")
    print(f"instances   = {runs[-1]['instances']}")
    print(f"manifests   = {runs[-1]['manifests']}")
    print(f"cold_table  = {runs[-1]['cold_table']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
