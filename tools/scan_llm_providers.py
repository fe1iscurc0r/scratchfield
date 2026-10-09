"""工单210 任务一/三 · LLM provider 硬编码扫描器（AST 分类，stdlib only，只读）。

对每个命中给出：文件 / 行号 / 命中文本 / 类型 / 所在函数 / 是否字符串字面量 / 是否经 system.config。

类型判定（按优先级）：
  comment      行内 # 注释
  url          含 http(s):// 或 bigmodel.cn
  model_name   形如 glm-4 / glm-4-plus / glm-4v（大小写不敏感）
  import       import zhipuai / from zhipuai import
  key          api_key / secret 相关
  other        其余

用法：
  .venv/Scripts/python.exe tools/scan_llm_providers.py                 # 扫仓库（排除第三方）
  .venv/Scripts/python.exe tools/scan_llm_providers.py --root NEKO/N.E.K.O --json out.json
"""
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
from pathlib import Path

PATTERN = re.compile(r"open\.bigmodel\.cn|bigmodel|zhipu|glm[-_]|\bGLM\b", re.I)
MODEL_NAME = re.compile(r"\bglm[\-_][0-9a-z\-\.]+", re.I)
URL = re.compile(r"https?://|bigmodel\.cn", re.I)
KEY = re.compile(r"api[_-]?key|secret|token", re.I)

# 第三方 / 生成物目录（扫到但单列，不计入"自家代码"）
VENDOR_DIRS = {"mod/sources", "vendor", "github_haul", "frontend/backend-dist",
               "frontend/release", "node_modules", ".venv", "__pycache__", "dist", "build"}
DEFAULT_SKIP = {"NEKO", "frontend", ".venv", "node_modules", "__pycache__", ".git", "dist", "build"}


def classify(line: str, matched: str) -> str:
    stripped = line.lstrip()
    if stripped.startswith("#"):
        return "comment"
    if URL.search(matched):
        return "url"
    if MODEL_NAME.search(matched):
        return "model_name"
    if re.search(r"(^|\s)(import|from)\s+\w*zhipu", line):
        return "import"
    if KEY.search(line):
        return "key"
    return "other"


def enclosing_func(tree: ast.AST, lineno: int) -> str:
    best = "<module>"
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.lineno <= lineno <= (node.end_lineno or node.lineno):
                best = getattr(node, "name", best)
    return best


def is_string_literal(src_lines: list[str], lineno: int) -> bool:
    ln = src_lines[lineno - 1]
    return bool(re.search(r"['\"].*?'|['\"].*", ln))


def scan_file(p: Path) -> list[dict]:
    try:
        src = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    lines = src.splitlines()
    try:
        tree = ast.parse(src)
    except SyntaxError:
        tree = None
    uses_config = bool(re.search(r"^\s*from\s+system[\.\s]|^\s*import\s+system", src, re.M))
    rows = []
    for i, ln in enumerate(lines, 1):
        for m in PATTERN.finditer(ln):
            rows.append({
                "file": str(p).replace(os.sep, "/"),
                "line": i,
                "text": m.group(0),
                "snippet": ln.strip()[:110],
                "kind": classify(ln, m.group(0)),
                "func": enclosing_func(tree, i) if tree else "?",
                "in_string": is_string_literal(lines, i),
                "uses_config": uses_config,
            })
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--json")
    ap.add_argument("--include-vendor", action="store_true")
    args = ap.parse_args()

    root = Path(args.root)
    rows: list[dict] = []
    for dirpath, dirnames, filenames in os.walk(root):
        rel = Path(dirpath).as_posix()
        parts = set(Path(dirpath).parts)
        if args.include_vendor:
            dirnames[:] = [d for d in dirnames if d not in {"__pycache__", ".venv", ".git"}]
        else:
            skip = DEFAULT_SKIP if root == Path(".") else {"__pycache__", ".venv", ".git"}
            dirnames[:] = [d for d in dirnames if d not in skip]
            if any(v in rel for v in VENDOR_DIRS):
                dirnames[:] = []
                continue
        for fn in filenames:
            if fn.endswith(".py"):
                rows.extend(scan_file(Path(dirpath) / fn))

    own = [r for r in rows if not any(v in r["file"] for v in VENDOR_DIRS)
           and "tools/scan_llm_providers.py" not in r["file"]]
    print(f"扫描 root={root} → 命中 {len(rows)} 处（自家代码 {len(own)} 处）\n")
    by_file: dict[str, list[dict]] = {}
    for r in own:
        by_file.setdefault(r["file"], []).append(r)
    print(f"{'文件':<52}{'处':>3}  类型分布")
    for f, rs in sorted(by_file.items(), key=lambda x: -len(x[1])):
        kinds = {}
        for r in rs:
            kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
        print(f"{f:<52}{len(rs):>3}  {kinds}")
    print("\n=== 逐条（自家代码）===")
    for r in own:
        print(f"  {r['file']}:{r['line']:<5} [{r['kind']:<10}] {r['func']:<28} cfg={'Y' if r['uses_config'] else 'N'}")
        print(f"        {r['snippet']}")
    if args.json:
        Path(args.json).write_text(json.dumps(own, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nJSON → {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
