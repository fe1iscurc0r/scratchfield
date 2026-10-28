#!/usr/bin/env python3
"""依赖落点审计器（工单 228 任务二 · 主版本升级预审 S1/S2 的自动化部分）。

## 干什么

给定一个库名，扫出**本仓**所有 import 落点（文件 + 行号 + 原文），外加 ``tests/``
中与该库相关的 mock/patch 点 —— 这是主版本升级预审的第一步，配套文档见
``docs/DEPENDABOT-MAJOR-UPGRADE-SOP.md``。

## 为什么不是纯 ripgrep

工单 S1 写的是 ripgrep。rg 快，但**不是所有环境都装**（CI 干净容器、Windows
开发机都可能没有）。所以这里：**优先调 rg，缺失时回退纯 Python 扫描** ——
两条路径产出同一份数据结构，测试对两者都覆盖（见 ``tests/test_deps_audit.py``）。

## 用法

    python tools/deps_audit.py pandas
    python tools/deps_audit.py anthropic --roots apiserver tests
    python tools/deps_audit.py pillow --no-write        # 只打印不落盘
    python tools/deps_audit.py numpy --no-rg            # 强制纯 Python 扫描

产物：``docs/audit/<lib>-<YYYY-MM-DD>.md`` + 同名 ``.json``（双格式，见工单要求）。
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess  # noqa: S404 - 仅用于调用 rg，参数全部由本模块构造
import sys
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_ROOTS: tuple[str, ...] = ("apiserver", "mcpserver", "tools", "tests")
DEFAULT_OUT_DIR = "docs/audit"

# 与 pyproject.toml 的 ruff exclude / pytest norecursedirs 保持一致的跳过集，
# 保证「扫描口径 == 本仓 CI 口径」，不把上游/第三方夹具算成落点。
_SKIP_DIRS = frozenset({
    "__pycache__", ".venv", "venv", "env", "node_modules", ".git",
    "NEKO", "vendor", "build", "dist", "frontend", "research", "HamLog",
})

_MOCK_TOKEN = re.compile(r"mock|patch|monkeypatch", re.IGNORECASE)

# S4 决策矩阵阈值（与 SOP 文档同源；改这里要同步改文档）
THRESHOLD_DIRECT = 5
THRESHOLD_SPLIT = 20


def _from_pattern(lib: str) -> re.Pattern[str]:
    return re.compile(rf"^\s*from\s+{re.escape(lib)}(?:\.\w+)*\s+import\b")


def _import_pattern(lib: str) -> re.Pattern[str]:
    """覆盖 ``import lib`` / ``import lib as x`` / ``import a, lib`` / ``import lib.sub``。"""
    return re.compile(rf"^\s*import\s+(?:[\w.]+,\s*)*{re.escape(lib)}(?:\.\w+)*(?:\s|,|$)")


def _rg_pattern(lib: str) -> str:
    esc = re.escape(lib)
    return (
        rf"^\s*(from\s+{esc}(\.\w+)*\s+import"
        rf"|import\s+([\w.]+,?\s+)*{esc}(\.\w+)*(\s|,|$))"
    )


def _is_skipped(path: Path) -> bool:
    return any(part in _SKIP_DIRS for part in path.parts)


def _dedupe(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, int]] = set()
    out: list[dict[str, Any]] = []
    for h in sorted(hits, key=lambda x: (x["file"], x["line"])):
        key = (h["file"], h["line"])
        if key in seen:
            continue
        seen.add(key)
        out.append(h)
    return out


def scan_imports_python(lib: str, roots: tuple[str, ...] | list[str]) -> list[dict[str, Any]]:
    """纯 Python 回退扫描（无 rg 环境、以及跨平台一致性验证用）。"""
    pat_from, pat_imp = _from_pattern(lib), _import_pattern(lib)
    hits: list[dict[str, Any]] = []
    for rel in roots:
        base = ROOT / rel
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.py")):
            if _is_skipped(path):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:  # 权限/占用等一律跳过，不让单个坏文件打断审计
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                if pat_from.match(line) or pat_imp.match(line):
                    hits.append({
                        "file": path.relative_to(ROOT).as_posix(),
                        "line": lineno,
                        "text": line.strip(),
                    })
    return hits


def scan_imports_rg(lib: str, roots: tuple[str, ...] | list[str]) -> list[dict[str, Any]] | None:
    """ripgrep 扫描；rg 不可用/异常时返回 None（交给调用方回退）。"""
    rg = shutil.which("rg")
    if not rg:
        return None
    existing = [r for r in roots if (ROOT / r).exists()]
    if not existing:
        return []
    args = [
        rg, "--line-number", "--no-heading", "--with-filename", "--no-ignore",
        "--glob", "*.py", "--glob", "!**/__pycache__/**",
        "-e", _rg_pattern(lib), *existing,
    ]
    try:
        proc = subprocess.run(  # noqa: S603 - 命令与参数均由本模块构造，无用户输入拼接
            args, cwd=ROOT, capture_output=True, text=True, timeout=120, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode not in (0, 1):  # 1 = 无命中（正常）
        return None
    hits: list[dict[str, Any]] = []
    for raw in proc.stdout.splitlines():
        parts = raw.split(":", 2)
        if len(parts) != 3:
            continue
        rel, lineno, text = parts
        if not lineno.isdigit() or _is_skipped(Path(rel)):
            continue
        hits.append({"file": rel.replace("\\", "/"), "line": int(lineno), "text": text.strip()})
    return hits


def scan_imports(
    lib: str,
    roots: tuple[str, ...] | list[str] = DEFAULT_ROOTS,
    *,
    use_rg: bool = True,
) -> tuple[list[dict[str, Any]], str]:
    """返回 ``(落点列表, 实际使用的扫描器名)``。"""
    if use_rg:
        hits = scan_imports_rg(lib, roots)
        if hits is not None:
            return _dedupe(hits), "ripgrep"
    return _dedupe(scan_imports_python(lib, roots)), "python"


def scan_mocks(lib: str, roots: tuple[str, ...] | list[str] = ("tests",)) -> list[dict[str, Any]]:
    """扫 ``tests/`` 中同时提到该库与 mock/patch 的行（升级时最容易炸的地方）。"""
    name_pat = re.compile(re.escape(lib))
    hits: list[dict[str, Any]] = []
    for rel in roots:
        base = ROOT / rel
        if not base.exists():
            continue
        for path in sorted(base.rglob("*.py")):
            if _is_skipped(path):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                if name_pat.search(line) and _MOCK_TOKEN.search(line):
                    hits.append({
                        "file": path.relative_to(ROOT).as_posix(),
                        "line": lineno,
                        "text": line.strip(),
                    })
    return _dedupe(hits)


def decide(count: int) -> str:
    """S4 决策矩阵。"""
    if count >= THRESHOLD_SPLIT:
        return "🛑 走 v5.x.0 升级路线（落点 ≥ 20）"
    if count >= THRESHOLD_DIRECT:
        return "⚠️ 拆迁移 PR / 留评论给 Trae（落点 ≥ 5）"
    return "✅ 全绿即可直合（落点 < 5）"


def render_markdown(
    lib: str,
    imports: list[dict[str, Any]],
    mocks: list[dict[str, Any]],
    *,
    scanner: str,
    roots: tuple[str, ...] | list[str] = DEFAULT_ROOTS,
) -> str:
    lines: list[str] = [
        f"# 依赖落点审计 · `{lib}`",
        "",
        f"> 生成：`tools/deps_audit.py`（工单 228 任务二）· 扫描器：**{scanner}**",
        f"> 日期：{date.today().isoformat()} · 根：`{', '.join(roots)}`",
        "",
        f"## import 落点（{len(imports)} 处）",
        "",
    ]
    if imports:
        lines += ["| # | 文件 | 行 | 原文 |", "|---:|---|---:|---|"]
        for i, h in enumerate(imports, 1):
            text = h["text"].replace("|", "\\|")
            lines.append(f"| {i} | `{h['file']}` | {h['line']} | `{text}` |")
    else:
        lines.append("_无命中_")

    lines += ["", f"## `tests/` 中的 mock / patch 点（{len(mocks)} 处）", ""]
    if mocks:
        lines += ["| # | 文件 | 行 | 原文 |", "|---:|---|---:|---|"]
        for i, h in enumerate(mocks, 1):
            text = h["text"].replace("|", "\\|")
            lines.append(f"| {i} | `{h['file']}` | {h['line']} | `{text}` |")
    else:
        lines.append("_无命中_")

    lines += [
        "",
        "## 决策（S4 矩阵）",
        "",
        f"- 落点 **{len(imports)}** 处 → {decide(len(imports))}",
        "",
        "> 矩阵与阈值定义见 `docs/DEPENDABOT-MAJOR-UPGRADE-SOP.md` 的 S4 节。",
        "",
    ]
    return "\n".join(lines)


def _payload(lib: str, imports: list[dict[str, Any]], mocks: list[dict[str, Any]],
             scanner: str, roots: tuple[str, ...] | list[str]) -> dict[str, Any]:
    return {
        "library": lib,
        "scanner": scanner,
        "date": date.today().isoformat(),
        "roots": list(roots),
        "import_count": len(imports),
        "mock_count": len(mocks),
        "decision": decide(len(imports)),
        "imports": imports,
        "mocks": mocks,
        "thresholds": {"direct": THRESHOLD_DIRECT, "split": THRESHOLD_SPLIT},
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="依赖落点审计器（工单 228 任务二）")
    ap.add_argument("library", help="库名（import 名，如 pandas / anthropic）")
    ap.add_argument("--roots", nargs="+", default=list(DEFAULT_ROOTS), help="扫描根目录")
    ap.add_argument("--out-dir", default=DEFAULT_OUT_DIR, help="产物目录（相对仓根）")
    ap.add_argument("--no-write", action="store_true", help="只打印，不落盘")
    ap.add_argument("--no-rg", action="store_true", help="强制纯 Python 扫描（跳过 ripgrep）")
    args = ap.parse_args(argv)

    roots = tuple(args.roots)
    imports, scanner = scan_imports(args.library, roots, use_rg=not args.no_rg)
    mocks = scan_mocks(args.library)
    markdown = render_markdown(args.library, imports, mocks, scanner=scanner, roots=roots)
    print(markdown)

    if not args.no_write:
        out_dir = ROOT / args.out_dir
        out_dir.mkdir(parents=True, exist_ok=True)
        stem = f"{args.library.lower().replace('/', '_')}-{date.today().isoformat()}"
        (out_dir / f"{stem}.md").write_text(markdown, encoding="utf-8")
        (out_dir / f"{stem}.json").write_text(
            json.dumps(_payload(args.library, imports, mocks, scanner, roots),
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[已落盘] {out_dir / (stem + '.md')} / .json", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
