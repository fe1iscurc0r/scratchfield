"""duckdb 工作台 MCP 工具注册（SPEC-02 Phase 3）。

四个工具：
- duckdb_import   CSV/Excel 导入建表
- duckdb_query    只读 SQL 查询
- duckdb_analyze  一键三个标准分析（描述统计/分组对比/相关性）
- duckdb_report   分析结果渲染 Markdown 报表
"""
from __future__ import annotations

import logging
from typing import Any

from . import workbench

logger = logging.getLogger(__name__)


def register_duckdb_tools(agent) -> None:
    """往 MaterialScienceAgent 注入 duckdb 工作台工具。

    duckdb 未安装时在 import duckdb 处抛 ImportError，
    agent 侧按既有模式静默降级。
    """
    import duckdb  # noqa: F401 —— 显式探测依赖，缺失则注册失败走降级

    def _tool_import(params: dict[str, Any]) -> dict[str, Any]:
        file_path = params.get("file_path") or params.get("path") or ""
        if not file_path:
            return {"success": False, "error": "请提供 file_path"}
        return workbench.import_file(file_path, table=params.get("table"),
                                     db_path=params.get("db_path"))

    def _tool_query(params: dict[str, Any]) -> dict[str, Any]:
        sql = params.get("sql") or params.get("query") or ""
        if not sql:
            return {"success": False, "error": "请提供 sql"}
        return workbench.run_query(sql, db_path=params.get("db_path"),
                                   limit=int(params.get("limit", 100)))

    def _tool_analyze(params: dict[str, Any]) -> dict[str, Any]:
        table = params.get("table") or ""
        if not table:
            return {"success": False, "error": "请提供 table"}
        analyses = workbench.run_standard_analyses(
            table,
            group_col=params.get("group_col"),
            metric_col=params.get("metric_col"),
            db_path=params.get("db_path"),
        )
        ok = sum(1 for a in analyses if a.get("success"))
        return {"success": ok > 0, "table": table, "analyses": analyses,
                "passed": f"{ok}/{len(analyses)}"}

    def _tool_report(params: dict[str, Any]) -> dict[str, Any]:
        table = params.get("table") or ""
        if not table:
            return {"success": False, "error": "请提供 table"}
        # 报表 = 标准分析 + 渲染，一条龙（验收口径：CSV → 3 分析 → 报告）
        analyses = workbench.run_standard_analyses(
            table,
            group_col=params.get("group_col"),
            metric_col=params.get("metric_col"),
            db_path=params.get("db_path"),
        )
        return workbench.generate_report(table, analyses,
                                         output_path=params.get("output_path"))

    agent.tools["duckdb_import"] = _tool_import
    agent.tools["duckdb_query"] = _tool_query
    agent.tools["duckdb_analyze"] = _tool_analyze
    agent.tools["duckdb_report"] = _tool_report
    logger.info("[MCP] duckdb 工作台 4 工具已注入 material_science agent")
