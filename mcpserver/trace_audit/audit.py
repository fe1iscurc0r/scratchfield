"""Trace Integrity 审计器 —— 七项标准逐项判定 + grep-able 报告。

对一批「交付物/工单/记忆条目」记录做只读审计，七项标准与 checklist.md 一一对应：
  - schema_valid       schema 合法（必需字段齐全、类型正确）
  - timestamp_complete 时间戳齐全（存在且可解析）
  - id_unique          id 唯一（跨记录不重复）
  - source_traceable   来源可溯（source 非空）
  - replayable         回放无缺口（时间戳单调、无断链）
  - boundary_clear     边界明确（type 在已知边界 / 带 scope）
  - owner_identified   责任人明确（owner 非空）

输出纯文本报告，可 grep -E "CRITERION|ISSUE|VERDICT" 检索。
纯 stdlib，零新重依赖。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from mcpserver.trace_audit import schema

# 七项标准（顺序即 checklist.md 顺序）
CRITERIA: tuple[str, ...] = (
    "schema_valid",
    "timestamp_complete",
    "id_unique",
    "source_traceable",
    "replayable",
    "boundary_clear",
    "owner_identified",
)

CRITERION_LABELS: dict[str, str] = {
    "schema_valid": "schema 合法",
    "timestamp_complete": "时间戳齐全",
    "id_unique": "id 唯一",
    "source_traceable": "来源可溯",
    "replayable": "回放无缺口",
    "boundary_clear": "边界明确",
    "owner_identified": "责任人明确",
}


def check_schema(record: dict[str, Any]) -> list[str]:
    """检查单条记录是否 schema 合法；返回问题列表（空列表 = 合法）。"""
    issues: list[str] = []
    for name in schema.REQUIRED_FIELDS:
        if name not in record:
            issues.append(f"缺少必需字段: {name}")
        elif not schema.field_type_ok(name, record[name]):
            issues.append(f"字段类型非法: {name}={record[name]!r}")
    return issues


def _rid(record: dict[str, Any]) -> str:
    return str(record.get("id", "<no-id>"))


def _criterion_schema(records: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    issues: list[str] = []
    for r in records:
        for msg in check_schema(r):
            issues.append(f"[{_rid(r)}] {msg}")
    return (not issues, issues)


def _criterion_timestamp(records: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    issues: list[str] = []
    for r in records:
        if "timestamp" not in r or schema.parse_timestamp(r.get("timestamp")) is None:
            issues.append(f"[{_rid(r)}] 时间戳缺失或不可解析")
    return (not issues, issues)


def _criterion_id_unique(records: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    seen: set[Any] = set()
    issues: list[str] = []
    for r in records:
        rid = r.get("id")
        if rid in seen:
            issues.append(f"[{_rid(r)}] id 重复: {rid!r}")
        seen.add(rid)
    return (not issues, issues)


def _criterion_source(records: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    issues: list[str] = []
    for r in records:
        if not isinstance(r.get("source"), str) or not r["source"].strip():
            issues.append(f"[{_rid(r)}] 来源缺失")
    return (not issues, issues)


def _criterion_replayable(records: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    issues: list[str] = []
    prev: float | None = None
    for r in records:
        ts = schema.parse_timestamp(r.get("timestamp"))
        if ts is None:
            issues.append(f"[{_rid(r)}] 时间戳不可解析，回放断链")
            prev = None
            continue
        if prev is not None and ts < prev:
            issues.append(f"[{_rid(r)}] 时间戳乱序（{ts} < {prev}）")
        prev = ts
    return (not issues, issues)


def _criterion_boundary(records: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    issues: list[str] = []
    for r in records:
        t = r.get("type")
        if not isinstance(t, str) or not t.strip():
            issues.append(f"[{_rid(r)}] 边界不明确: type 缺失")
            continue
        has_scope = isinstance(r.get("scope"), str) and bool(r["scope"].strip())
        if t.strip().lower() not in schema.KNOWN_TYPES and not has_scope:
            issues.append(f"[{_rid(r)}] 边界不明确: type={t!r}")
    return (not issues, issues)


def _criterion_owner(records: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    issues: list[str] = []
    for r in records:
        if not isinstance(r.get("owner"), str) or not r["owner"].strip():
            issues.append(f"[{_rid(r)}] 责任人缺失")
    return (not issues, issues)


@dataclass
class AuditReport:
    """审计报告：verdict(PASS/FAIL) + 七项 criteria + issue 明细。"""

    verdict: str = "PASS"
    criteria: dict[str, bool] = field(default_factory=dict)
    issues: list[str] = field(default_factory=list)
    total_records: int = 0

    def to_text(self) -> str:
        lines = [
            f"TRACE-AUDIT VERDICT: {self.verdict}",
            f"records: {self.total_records}",
        ]
        for c in CRITERIA:
            ok = self.criteria.get(c, False)
            lines.append(f"CRITERION[{c}] {CRITERION_LABELS[c]}: {'PASS' if ok else 'FAIL'}")
        for msg in self.issues:
            lines.append(f"ISSUE: {msg}")
        return "\n".join(lines)

    def __str__(self) -> str:
        return self.to_text()


def audit(records: Iterable[dict[str, Any]]) -> AuditReport:
    """对一批记录做七项审计，返回 AuditReport。"""
    recs = list(records)
    report = AuditReport(total_records=len(recs))

    checks: dict[str, tuple[bool, list[str]]] = {
        "schema_valid": _criterion_schema(recs),
        "timestamp_complete": _criterion_timestamp(recs),
        "id_unique": _criterion_id_unique(recs),
        "source_traceable": _criterion_source(recs),
        "replayable": _criterion_replayable(recs),
        "boundary_clear": _criterion_boundary(recs),
        "owner_identified": _criterion_owner(recs),
    }

    for c, (ok, issues) in checks.items():
        report.criteria[c] = ok
        report.issues.extend(issues)

    report.verdict = "PASS" if all(ok for ok, _ in checks.values()) else "FAIL"
    return report
