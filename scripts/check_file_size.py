"""check_file_size.py — 巨石文件防复发闸门（卷190-C）。

规则：单文件（.py/.ts/.vue）行数 > 阈值（默认 800）即**报警**。

- 存量巨石记入**红名单**（`scripts/file_size_baseline.json`）豁免——只豁免"已经在案"的，
  新文件/新膨胀一律报出来（防止"拆完又长回去"）。
- 默认**不阻塞**（exit 0，供 CI 报警用）；`--strict` 时红名单外的新增超限 → exit 1。
- `--update-baseline` 重写红名单（**只应在拆分完成后收窄，不应为了过闸门而加宽**）。

用法：
    python scripts/check_file_size.py                 # 报警（exit 0）
    python scripts/check_file_size.py --strict        # CI 闸门（有新增超限则 exit 1）
    python scripts/check_file_size.py --update-baseline
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = Path(__file__).with_name("file_size_baseline.json")

THRESHOLD = 800
SCAN_ROOTS = ["apiserver", "mcpserver", "agentserver", "system", "scripts", "tools",
              "frontend/src", "research"]
EXTS = {".py", ".ts", ".vue"}
SKIP_PARTS = ("__pycache__", "node_modules", "/dist/", "/build/", ".venv")


def _iter_files():
    for rel in SCAN_ROOTS:
        base = ROOT / rel
        if not base.exists():
            continue
        for p in base.rglob("*"):
            if not p.is_file() or p.suffix not in EXTS:
                continue
            s = "/" + p.as_posix()
            if any(k in s for k in SKIP_PARTS):
                continue
            yield p


def _count_lines(p: Path) -> int:
    try:
        with p.open(encoding="utf-8", errors="ignore") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def scan() -> list[tuple[int, str]]:
    """返回 [(行数, 相对路径)]，按行数降序。"""
    out = []
    for p in _iter_files():
        n = _count_lines(p)
        if n > THRESHOLD:
            out.append((n, p.relative_to(ROOT).as_posix()))
    out.sort(reverse=True)
    return out


def load_baseline() -> dict[str, int]:
    if not BASELINE.exists():
        return {}
    try:
        return json.loads(BASELINE.read_text(encoding="utf-8")).get("files", {})
    except (json.JSONDecodeError, OSError):
        return {}


def save_baseline(rows: list[tuple[int, str]]) -> None:
    payload = {
        "_comment": "巨石文件红名单（卷190-C 闸门）。只应在拆分后收窄——不要为了过闸门加宽。",
        "threshold": THRESHOLD,
        "files": {rel: n for n, rel in sorted(rows, key=lambda r: r[1])},
    }
    BASELINE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="巨石文件防复发闸门")
    ap.add_argument("--strict", action="store_true", help="红名单外的超限 → exit 1")
    ap.add_argument("--update-baseline", action="store_true", help="重写红名单")
    ap.add_argument("--threshold", type=int, default=THRESHOLD)
    args = ap.parse_args()

    rows = scan()
    if args.update_baseline:
        save_baseline(rows)
        print(f"✓ 红名单已更新：{len(rows)} 个文件（阈值 {args.threshold}）")
        return 0

    baseline = load_baseline()
    known = [(n, r) for n, r in rows if r in baseline]
    new = [(n, r) for n, r in rows if r not in baseline]
    # 已拆小的（在红名单但不再超限）→ 提示可从名单移除
    shrunk = sorted(set(baseline) - {r for _, r in rows})

    print(f"阈值 {args.threshold} 行 | 扫描 {len(SCAN_ROOTS)} 个根目录")
    print(f"超限文件 {len(rows)} 个：在案 {len(known)} / **新增 {len(new)}**")
    if new:
        print("\n⚠️ 新增超限（不在红名单）：")
        for n, r in new:
            print(f"  {n:6d}  {r}")
    if shrunk:
        print(f"\n✓ 已拆到阈值以下，可从红名单移除（{len(shrunk)} 个）：")
        for r in shrunk:
            print(f"        {r}")
    if known:
        print(f"\n（在案的 {len(known)} 个巨石）")
        for n, r in known:
            print(f"  {n:6d}  {r}")

    if args.strict and new:
        print("\n✗ strict 模式：存在新增超限文件", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
