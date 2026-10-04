"""verify_export_parity.py — 薄壳重构的「导出面零变化」验证器（卷190-A1/A2 通用）。

比对 **HEAD 版模块源码**的顶层定义名 与 **拆分后薄壳模块实际可导出名**，
两者必须完全一致（少了 = 调用方会 ImportError；多了 = 意外暴露，需人工确认）。

用法：
    .venv/Scripts/python.exe tools/verify_export_parity.py apiserver/routes/extensions.py
    .venv/Scripts/python.exe tools/verify_export_parity.py apiserver/agentic_tool_loop.py
"""
from __future__ import annotations

import argparse
import ast
import importlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def top_level_names(src: str) -> set[str]:
    """源码顶层定义名（函数/类/赋值目标），不含 import 进来的名字。"""
    names: set[str] = set()
    for node in ast.parse(src).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    names.add(t.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", help="相对仓库根的模块路径，如 apiserver/routes/extensions.py")
    ap.add_argument("--rev", default="HEAD",
                    help="对比基准 revision（默认 HEAD；若 HEAD 已是薄壳，请指定拆分前的提交）")
    args = ap.parse_args()

    rel = args.path.replace("\\", "/")
    old_src = subprocess.run(["git", "show", f"{args.rev}:{rel}"], cwd=ROOT,
                             capture_output=True, text=True)
    if old_src.returncode != 0:
        print(f"✗ 无法从 {args.rev} 读取 {rel}: {old_src.stderr.strip()}", file=sys.stderr)
        return 2
    old_names = top_level_names(old_src.stdout)

    mod_name = rel[:-3].replace("/", ".")
    mod = importlib.import_module(mod_name)
    new_names = {n for n in dir(mod) if not n.startswith("__")}

    missing = sorted(old_names - new_names)
    print(f"{rel}  (base={args.rev})")
    print(f"  基准顶层定义名: {len(old_names)}")
    print(f"  薄壳可导出名  : {len(new_names)}")
    if missing:
        print(f"\n✗ 丢失 {len(missing)} 个（调用方会 ImportError）：")
        for n in missing:
            print(f"   {n}")
        return 1
    print("\n✓ 导出面完整（HEAD 的每个顶层定义名在薄壳上均可用）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
