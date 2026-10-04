"""trace 审计 MCP 桥 — TraceAuditBridge（agent-manifest.json entryPoint）。

U-02（UNIFORM 总装线）：把 FOXTROT 线交付的 trace 审计/接入审查门挂成 MCP 工具。
本桥只封装 audit/gate/schema/checklist 现有接口，不重写任何审计逻辑。

工具（4 个）：
- audit_records(records)：对记录列表做七项审计（schema/时间线/唯一性/来源/回放/边界/责任人）
- audit_file(path)：读 JSON 数组或 JSONL 文件后审计
- run_gate(path, source, max_file_size)：外来文件/仓库接入审查门（许可/危险/大文件/二进制/来源）
- list_checklist()：必需字段/已知 type/七项标准（与代码同源）
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from mcpserver.trace_audit.audit import (
    CRITERIA,
    CRITERION_LABELS,
    AuditReport,
    audit,
)
from mcpserver.trace_audit.gate import GateReport, run_gate
from mcpserver.trace_audit.schema import KNOWN_TYPES, REQUIRED_FIELDS

logger = logging.getLogger(__name__)

# 调度层注入的路由键（分发前必须全部剥离，避免污染具名参数）
_ROUTING_KEYS = frozenset({
    "service_name", "tool_name", "agentType", "_tool_call_id",
    "message", "callback_url", "params", "arguments",
})


def _audit_report_to_dict(report: AuditReport) -> dict[str, Any]:
    return {"verdict": report.verdict, "criteria": report.criteria,
            "issues": report.issues, "total_records": report.total_records,
            "text": report.to_text()}


def _gate_report_to_dict(report: GateReport) -> dict[str, Any]:
    return {"verdict": report.verdict,
            "risks": [{"kind": r.kind, "message": r.message, "path": r.path}
                      for r in report.risks],
            "files_scanned": report.files_scanned, "target": report.target,
            "text": report.to_text()}


def _load_records(path: Path) -> list[dict[str, Any]]:
    """读 JSON 数组文件或 JSONL（每行一条记录）。"""
    text = path.read_text(encoding="utf-8")
    stripped = text.strip()
    if stripped.startswith("["):
        data = json.loads(stripped)
        if not isinstance(data, list):
            raise ValueError(f"JSON 顶层必须是数组: {path}")
        return data
    records: list[dict[str, Any]] = []
    for i, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError as e:
            raise ValueError(f"第 {i} 行不是合法 JSON: {e}") from e
        if not isinstance(rec, dict):
            raise ValueError(f"第 {i} 行不是 JSON 对象")
        records.append(rec)
    return records


class TraceAuditBridge:
    """trace 审计 MCP 服务实例（无状态）。"""

    # ---- 工具实现（封装，不重写）----

    def audit_records(self, records: list[dict] | None = None) -> dict[str, Any]:
        """对记录列表做七项审计，返回 verdict/criteria/issues。"""
        if not isinstance(records, list):
            return {"status": "error", "error": "records 必须是数组"}
        return {"status": "ok", **_audit_report_to_dict(audit(records))}

    def audit_file(self, path: str) -> dict[str, Any]:
        """读 JSON/JSONL 文件后审计（不存在或解析失败返回 error）。"""
        p = Path(str(path or "")).expanduser()
        if not p.is_file():
            return {"status": "error", "error": f"文件不存在: {p}"}
        try:
            records = _load_records(p)
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as e:
            return {"status": "error", "error": str(e)}
        return {"status": "ok", "path": str(p),
                **_audit_report_to_dict(audit(records))}

    def run_gate(self, path: str, source: str = "local",
                 max_file_size: int | None = None) -> dict[str, Any]:
        """接入审查门：对外来文件/仓库路径跑风险扫描。"""
        kwargs: dict[str, Any] = {}
        if isinstance(max_file_size, int) and max_file_size > 0:
            kwargs["max_file_size"] = max_file_size
        report = run_gate(str(path or ""), source=str(source or "local"),
                          **kwargs)
        return {"status": "ok", **_gate_report_to_dict(report)}

    def list_checklist(self) -> dict[str, Any]:
        """审计清单：必需字段/已知 type/七项标准（与代码同源）。"""
        return {"status": "ok",
                "required_fields": list(REQUIRED_FIELDS),
                "known_types": sorted(KNOWN_TYPES),
                "criteria": {c: CRITERION_LABELS.get(c, c) for c in CRITERIA}}

    # ---- MCP 分发 ----

    async def handle_handoff(self, tool_call: dict[str, Any]) -> str:
        """MCP 标准入口：按 tool_name 分发，剥离全部调度层路由键。"""
        tool_name = str(tool_call.get("tool_name") or "").strip()
        inner = tool_call.get("params") or tool_call.get("arguments") or {}
        if isinstance(inner, dict):
            params = {k: v for k, v in inner.items() if k not in _ROUTING_KEYS}
        else:
            params = {}
        for k, v in tool_call.items():
            if k not in _ROUTING_KEYS and k not in params:
                params[k] = v
        try:
            if tool_name == "audit_records":
                result = self.audit_records(params.get("records"))
            elif tool_name == "audit_file":
                result = self.audit_file(str(params.get("path") or ""))
            elif tool_name == "run_gate":
                result = self.run_gate(str(params.get("path") or ""),
                                       source=str(params.get("source") or "local"),
                                       max_file_size=params.get("max_file_size"))
            elif tool_name == "list_checklist":
                result = self.list_checklist()
            else:
                raise ValueError(
                    f"trace_audit 不支持的工具: {tool_name!r}（可用: "
                    "audit_records/audit_file/run_gate/list_checklist）")
        except Exception as e:
            logger.exception("[trace_audit] %s 未预期异常", tool_name)
            return json.dumps({"status": "error", "service": "trace_audit",
                               "tool": tool_name, "error": str(e)},
                              ensure_ascii=False)
        return json.dumps({"service": "trace_audit", "tool": tool_name,
                           **result}, ensure_ascii=False)


__all__ = ["TraceAuditBridge"]
