"""工单209 任务一 · 巨石体检测量脚本（AST 静态测量，只读）。

产出：每个目标文件的
  - LOC / 顶层函数数 / 顶层类数
  - 最长函数（名 + 行数）与 Top5
  - **import 出度**（全仓有多少个 .py 文件 import 它）
  - 反向：它自己 import 了多少个仓内模块（耦合广度）

用法：cd "D:/my git/scratchpad" && .venv/Scripts/python.exe tools/monolith_metrics.py [--json]
"""
from __future__ import annotations

import ast
import json
import os
import re
import sys
from pathlib import Path

TARGETS = [
    "system/config.py",
    "coupled/omnilimb-face/omnilimb_face/runtime.py",
    "build.py",
    "agentserver/openclaw/openclaw_client.py",
    "agentserver/openclaw/instance_manager.py",
    "agentserver/openclaw/embedded_runtime.py",
    "apiserver/travel_service.py",
    "apiserver/routes/chat.py",
]

SKIP_DIRS = {"__pycache__", ".venv", "node_modules", "NEKO", "frontend", ".git", "dist", "build"}


def iter_repo_py() -> list[Path]:
    out = []
    for dirpath, dirnames, filenames in os.walk("."):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in filenames:
            if fn.endswith(".py"):
                out.append(Path(dirpath) / fn)
    return out


def module_names(path: str) -> list[str]:
    """一个文件可能被 import 的写法（点分模块名）。"""
    p = Path(path)
    if p.name == "__init__.py":
        base = ".".join(p.parent.parts)
    else:
        base = ".".join(p.with_suffix("").parts)
    names = {base}
    # 顶层包名（供 `from system import config` 这类）
    if len(p.parts) > 1:
        names.add(".".join(p.with_suffix("").parts[:-1]))
    names.add(p.stem)
    return sorted(names)


def measure(path: str) -> dict:
    src = Path(path).read_text(encoding="utf-8", errors="replace")
    loc = src.count("\n") + 1
    info = {"path": path, "loc": loc, "funcs": 0, "classes": 0, "longest": [],
            "parse_ok": True, "internal_imports": 0}
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        info["parse_ok"] = False
        info["error"] = str(e)[:80]
        return info
    spans = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            info["funcs"] += 1
            spans.append((node.name, (node.end_lineno or node.lineno) - node.lineno + 1))
        elif isinstance(node, ast.ClassDef):
            info["classes"] += 1
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    info["funcs"] += 1
                    spans.append((f"{node.name}.{sub.name}",
                                  (sub.end_lineno or sub.lineno) - sub.lineno + 1))
    spans.sort(key=lambda x: -x[1])
    info["longest"] = spans[:5]
    # 自身 import 了多少仓内模块
    internal = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            if not node.module.startswith(("__future__",)) and "." in node.module:
                internal += 1
        elif isinstance(node, ast.Import):
            internal += len(node.names)
    info["internal_imports"] = internal
    return info


def import_out_degree(path: str, all_py: list[Path]) -> tuple[int, list[str]]:
    """全仓有多少文件 import 它。"""
    names = module_names(path)
    hits: list[str] = []
    pats = []
    for n in names:
        if not n or n == Path(path).stem and len(names) > 1:
            continue
        pats.append(re.compile(rf"^\s*(from\s+{re.escape(n)}\s+import|import\s+{re.escape(n)}\b)",
                               re.M))
    me = Path(path)
    for f in all_py:
        if f == me:
            continue
        try:
            t = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if any(p.search(t) for p in pats):
            hits.append(str(f).replace(os.sep, "/").lstrip("./"))
    return len(hits), sorted(hits)


def main() -> int:
    all_py = iter_repo_py()
    print(f"扫描仓内 .py（不含 NEKO/frontend/venv）: {len(all_py)} 个\n")
    rows = []
    for t in TARGETS:
        if not Path(t).exists():
            print(f"[缺失] {t}")
            continue
        m = measure(t)
        deg, who = import_out_degree(t, all_py)
        m["import_degree"] = deg
        m["importers"] = who
        rows.append(m)
    for m in sorted(rows, key=lambda r: -r["import_degree"]):
        print("=" * 78)
        print(f"{m['path']}  LOC={m['loc']}  函数={m['funcs']}  类={m['classes']}  "
              f"**被 {m['import_degree']} 个文件 import**")
        print(f"  最长函数 Top5: " + ", ".join(f"{n}({L}行)" for n, L in m["longest"]))
        print(f"  被谁 import（前 12）: {m['importers'][:12]}")
    if "--json" in sys.argv:
        out = Path("C:/Users/ASUS/AppData/Local/Temp/w222/monolith_metrics.json")
        out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nJSON → {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
