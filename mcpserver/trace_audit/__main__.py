"""trace-audit CLI 入口。

用法：
  python -m mcpserver.trace_audit audit --check-file FILE   # F-01 七项审计
  python -m mcpserver.trace_audit gate PATH [--source SRC]  # F-02 接入审查门

--check-file 支持：JSON 记录列表、{"records": [...]} 包裹、含 ```json 围栏的
markdown；其余 markdown 按一级标题切块做宽松提取（多数文档并非 schema 完整
trace，审计会如实报缺失字段——这正是工具要暴露的盲区）。
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from mcpserver.trace_audit.audit import audit
from mcpserver.trace_audit.gate import run_gate


def _guess_type(path: str) -> str:
    name = Path(path).name
    low = name.lower()
    if low.startswith("batch-workorders"):
        return "workorder"
    if "授粉报告" in name or "报告" in name or "report" in low:
        return "report"
    if "memory" in low or "neko" in low:
        return "memory"
    return "delivery"


def _extract_field(body: str, keys: tuple[str, ...]) -> str:
    for line in body.splitlines():
        s = line.strip().lstrip("-*|> ").strip()
        for k in keys:
            m = re.match(rf"^{re.escape(k)}\s*[:：]\s*(.+)$", s)
            if m:
                return m.group(1).strip()
    return ""


def _records_from_markdown(text: str, path: str) -> list[dict]:
    records: list[dict] = []
    # 1) ```json 围栏
    for block in re.findall(r"```json\s*\n(.*?)```", text, re.DOTALL):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        if isinstance(data, list):
            records.extend(data)
        elif isinstance(data, dict) and "id" in data:
            records.append(data)
    if records:
        return records

    # 2) 一级标题切块做宽松提取
    for block in re.split(r"(?m)^#\s+", text)[1:]:
        lines = block.splitlines()
        if not lines:
            continue
        title = lines[0].strip()
        body = "\n".join(lines[1:])
        rec: dict = {"id": title, "type": _guess_type(path)}
        src = _extract_field(body, ("source", "来源"))
        owner = _extract_field(body, ("owner", "责任人", "组装", "委托"))
        ts = _extract_field(body, ("timestamp", "date", "日期", "时间戳"))
        rec["source"] = src or path
        rec["owner"] = owner
        if ts:
            rec["timestamp"] = ts
        records.append(rec)
    return records


def load_records_from_file(path: str) -> list[dict]:
    """从文件加载可审计记录（JSON 列表 / 围栏 / 宽松 markdown）。"""
    raw = Path(path).read_text(encoding="utf-8", errors="replace")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = None
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        if "records" in data:
            return list(data["records"])
        if "id" in data:
            return [data]
    return _records_from_markdown(raw, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="trace-audit",
        description="Trace Integrity 审计 + 外来文件接入审查门",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_audit = sub.add_parser("audit", help="对记录跑七项审计")
    p_audit.add_argument("--check-file", required=True, help="记录文件（JSON 列表 / 含 ```json 围栏的 md）")

    p_gate = sub.add_parser("gate", help="外来文件/仓库接入审查门")
    p_gate.add_argument("path", help="外来文件或目录路径")
    p_gate.add_argument("--source", default="local", help="来源（URL/包名，用于溯源）")

    args = parser.parse_args(argv)

    if args.cmd == "audit":
        records = load_records_from_file(args.check_file)
        if not records:
            print("未提取到可审计记录（仅支持 JSON 列表 / ```json 围栏 / 一级标题 markdown）")
            return 1
        report = audit(records)
        print(report.to_text())
        return 0 if report.verdict == "PASS" else 1

    if args.cmd == "gate":
        report = run_gate(args.path, source=args.source)
        print(report.to_text())
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
