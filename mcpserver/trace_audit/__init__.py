"""trace_audit —— Trace Integrity 审计 + 外来文件接入审查门。

子模块：
- schema:    记录 schema 定义（必需字段/类型/已知边界/时间戳解析）
- audit:     七项标准审计器（check_schema / audit / AuditReport）
- liccheck:  许可快速核实（LICENSE 存在性 + SPDX 识别 + NOASSERTION）
- gate:      外来文件接入审查门（run_gate，PASS/WARN/FAIL）
- checklist.md: 七项审计标准清单（判定方法）

CLI 入口：python -m mcpserver.trace_audit audit --check-file FILE
         python -m mcpserver.trace_audit gate PATH [--source SRC]
"""

from mcpserver.trace_audit.audit import AuditReport, audit, check_schema
from mcpserver.trace_audit.gate import GateReport, run_gate
from mcpserver.trace_audit.liccheck import LicenseCheck, check_license, detect_spdx
from mcpserver.trace_audit.schema import (
    KNOWN_TYPES,
    REQUIRED_FIELDS,
    field_type_ok,
    parse_timestamp,
)

__all__ = [
    "AuditReport",
    "GateReport",
    "LicenseCheck",
    "KNOWN_TYPES",
    "REQUIRED_FIELDS",
    "audit",
    "check_license",
    "check_schema",
    "detect_spdx",
    "field_type_ok",
    "parse_timestamp",
    "run_gate",
]
