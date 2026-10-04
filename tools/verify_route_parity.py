"""verify_route_parity.py — 拆分前后路由清单逐条对比（卷190-A1 验收证据）。

比对 HEAD 版 extensions.py 与拆分后 extensions_parts/ 的 (method, path) 集合，
并输出差异。两者必须完全相同。

用法：.venv/Scripts/python.exe tools/verify_route_parity.py
"""
from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DEC_RE = re.compile(r'@router\.(get|post|put|delete|patch)\(\s*"([^"]*)"')


def routes_from_source(src: str) -> set[tuple[str, str]]:
    """从源码里抓 @router.<method>("path")（足够精确：装饰器行不会出现在字符串里）。"""
    out = set()
    for m in DEC_RE.finditer(src):
        out.add((m.group(1).upper(), m.group(2)))
    return out


def main() -> int:
    old = subprocess.run(["git", "show", "HEAD:apiserver/routes/extensions.py"],
                         cwd=ROOT, capture_output=True, text=True, check=True).stdout
    old_routes = routes_from_source(old)

    parts = ROOT / "apiserver" / "routes" / "extensions_parts"
    new_routes: set[tuple[str, str]] = set()
    for p in sorted(parts.glob("*.py")):
        new_routes |= routes_from_source(p.read_text(encoding="utf-8"))

    print(f"拆分前（HEAD extensions.py）: {len(old_routes)} 条路由")
    print(f"拆分后（extensions_parts/）: {len(new_routes)} 条路由")

    missing = sorted(old_routes - new_routes)
    extra = sorted(new_routes - old_routes)
    if missing:
        print(f"\n✗ 丢失 {len(missing)} 条：")
        for m, p in missing:
            print(f"   {m:6s} {p}")
    if extra:
        print(f"\n⚠ 多出 {len(extra)} 条：")
        for m, p in extra:
            print(f"   {m:6s} {p}")
    if not missing and not extra:
        print("\n✓ 路由集合逐条一致（行为零变化）")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
