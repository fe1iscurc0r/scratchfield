#!/usr/bin/env python3
"""扫描各模块 tests/ 目录，列出「无任何测试分层 marker」的测试文件清单。

卷173 配套辅助工具——**只列清单，不自动打标**（冒烟位需人工挑选：
import + 主入口签名级的测试才算 smoke，机器选会选进慢测试）。

用法：
    python scripts/mark_smoke.py                 # 全仓扫描
    python scripts/mark_smoke.py mcpserver       # 只扫指定顶层目录

分层语义见 pyproject.toml [tool.pytest.ini_options] markers：
    smoke ⊂ core ⊂ full；未标注文件默认按 full 对待。
stdlib only。
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCAN_TOPS = sys.argv[1:] or ["tests", "mcpserver", "agentserver", "summer_memory",
                             "apiserver", "thinking", "ui", "voice", "domains", "scripts"]
EXCLUDE_PARTS = {"NEKO", "vendor", "node_modules", ".venv", "build", "dist", "archive",
                 "__pycache__", "frontend", "HamLog", "site-packages"}


def has_layer_marker(path: Path) -> bool:
    try:
        src = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return True  # 读不了的不报
    return bool(re.search(r"^pytestmark\b.*pytest\.mark\.(smoke|core|full)", src, re.M))


def is_marker_line_clean(path: Path) -> tuple[bool, str]:
    """额外检查：标注块是否引入了语法问题（ast 可解析 = 干净）。"""
    try:
        ast.parse(path.read_text(encoding="utf-8"))
        return True, ""
    except SyntaxError as e:
        return False, f"SyntaxError line {e.lineno}"


def main() -> int:
    unmarked: list[Path] = []
    broken: list[tuple[Path, str]] = []
    total = 0
    for top in SCAN_TOPS:
        base = REPO_ROOT / top
        if base.is_file():
            files = [base]
        elif base.is_dir():
            files = sorted(base.rglob("test_*.py"))
        else:
            continue
        for f in files:
            if any(part in f.parts for part in EXCLUDE_PARTS):
                continue
            total += 1
            ok, why = is_marker_line_clean(f)
            if not ok:
                broken.append((f, why))
                continue
            if not has_layer_marker(f):
                unmarked.append(f)

    print(f"扫描 {total} 个测试文件：未标注 {len(unmarked)}，语法异常 {len(broken)}")
    if broken:
        print("\n== 语法异常（需人工修） ==")
        for f, why in broken:
            print(f"  {f.relative_to(REPO_ROOT)}  {why}")
    if unmarked:
        print("\n== 未标注（默认按 full 对待） ==")
        for f in unmarked:
            print(f"  {f.relative_to(REPO_ROOT)}")
    # 冒烟挑选建议：文件名含 import/smoke/registry/policy 等签名级关键词的排前面
    if unmarked:
        import argparse

        print("\n提示：冒烟位请人工挑选（import + 主入口签名级），不是所有未标注文件都适合。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
