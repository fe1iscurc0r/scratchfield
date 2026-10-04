"""db_audit.py — 数据库层全量勘察（卷192-A）。

输出两部分：
1. **静态**：本仓自有代码（apiserver/mcpserver/agentserver/system/research）里
   所有 `sqlite3.connect` / `create_engine` 连接点 —— 文件:行 | 库路径表达式 |
   连接参数 | 建表方式（该文件是否用 CREATE TABLE IF NOT EXISTS / ORM create_all）。
2. **动态**：对实际存在的库文件跑 PRAGMA —— 表数 / 索引数 / 行数 / journal_mode。

用法：
    .venv/Scripts/python.exe tools/db_audit.py            # markdown 报告
    .venv/Scripts/python.exe tools/db_audit.py --json     # 机器可读
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SCAN_DIRS = ["apiserver", "mcpserver", "agentserver", "system", "research"]
EXCLUDE_PARTS = ("/tests/", "__pycache__", "/test_", "node_modules", ".venv")

CONNECT_RE = re.compile(r"(sqlite3\.connect|create_engine)\s*\(")
CREATE_RE = re.compile(r"CREATE\s+TABLE\s+(IF\s+NOT\s+EXISTS\s+)?", re.I)
ORM_RE = re.compile(r"metadata\.create_all")

# 运行期实际库文件（相对仓库根 或 绝对路径）
KNOWN_DB_RELATIVE = [
    "memory_maas_data/cards.db",
    "memory_maas_data/entities.db",
    "memory_maas_data/hs.db",
    "memory_maas_data/lineage.db",
    "papers.db",
    "data/tool_calls.db",
]


def _hits() -> list[dict]:
    out: list[dict] = []
    for d in SCAN_DIRS:
        base = ROOT / d
        if not base.exists():
            continue
        for py in sorted(base.rglob("*.py")):
            rel = str(py.relative_to(ROOT)).replace("\\", "/")
            if any(p in "/" + rel for p in EXCLUDE_PARTS):
                continue
            text = py.read_text(encoding="utf-8", errors="ignore")
            lines = text.splitlines()
            if not CONNECT_RE.search(text):
                continue
            has_ine = bool(re.search(r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS", text, re.I))
            has_ct = bool(CREATE_RE.search(text))
            has_orm = bool(ORM_RE.search(text))
            style = ("ORM create_all" if has_orm
                     else "CREATE IF NOT EXISTS" if has_ine
                     else "CREATE TABLE (裸)" if has_ct
                     else "(本文件无建表语句)")
            for i, ln in enumerate(lines, 1):
                if CONNECT_RE.search(ln):
                    # 采集该调用的参数表达式（同行 + 最多向下 2 行）
                    frag = " ".join(x.strip() for x in lines[i - 1:i + 2])
                    frag = frag[:160]
                    out.append({
                        "file": rel, "line": i, "call": frag,
                        "table_style": style,
                    })
    return out


def _db_info(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=3)
    except sqlite3.Error as e:
        return {"path": str(path), "error": str(e)}
    try:
        try:
            jm = conn.execute("PRAGMA journal_mode").fetchone()[0]
        except sqlite3.Error:
            jm = "?"
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name").fetchall()]
        idx = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND name NOT LIKE 'sqlite_%'").fetchall()]
        counts = {}
        for t in tables:
            try:
                counts[t] = conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
            except sqlite3.Error:
                counts[t] = -1
        return {"path": str(path), "journal_mode": jm, "tables": tables,
                "indexes": idx, "row_counts": counts}
    finally:
        conn.close()


def collect() -> dict:
    hits = _hits()
    dbs = []
    roots = [ROOT]
    appdata = os.environ.get("APPDATA")
    if appdata:
        roots.append(Path(appdata) / "lumo")
    for r in KNOWN_DB_RELATIVE:
        info = _db_info(ROOT / r)
        if info:
            dbs.append(info)
    if appdata:
        lumo = Path(appdata) / "lumo"
        if lumo.exists():
            for p in sorted(lumo.rglob("*.db")):
                info = _db_info(p)
                if info:
                    dbs.append(info)
    return {"connect_points": hits, "databases": dbs}


def render_md(data: dict) -> str:
    hits = data["connect_points"]
    lines = ["## A1 连接点清单（静态）", "",
             f"本仓自有代码（apiserver/mcpserver/agentserver/system/research，排除 tests）"
             f"共 **{len(hits)}** 个 `sqlite3.connect`/`create_engine` 调用点。", "",
             "| # | 文件:行 | 建表方式（该文件） | 调用片段 |", "|---|---|---|---|"]
    for i, h in enumerate(hits, 1):
        frag = h["call"].replace("|", "\\|")[:90]
        lines.append(f"| {i} | `{h['file']}:{h['line']}` | {h['table_style']} | `{frag}` |")
    lines += ["", "## A1 库清单（动态，实际存在的库文件）", ""]
    if not data["databases"]:
        lines.append("（未发现实际库文件）")
    else:
        lines += ["| 库文件 | journal | 表数 | 索引数 | 表（行数） |", "|---|---|---|---|---|"]
        for db in data["databases"]:
            if "error" in db:
                lines.append(f"| `{db['path']}` | — | — | — | 打开失败: {db['error']} |")
                continue
            tl = ", ".join(f"{t}({db['row_counts'].get(t, '?')})" for t in db["tables"]) or "（无表）"
            lines.append(f"| `{db['path']}` | {db['journal_mode']} | {len(db['tables'])} | "
                         f"{len(db['indexes'])} | {tl} |")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    data = collect()
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(render_md(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
