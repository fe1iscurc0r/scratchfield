"""duckdb 材料数据分析工作台（SPEC-02 Phase 3）。

用法（MCP 工具）：
1. duckdb_import   导入 CSV/Excel 建表（模板见 import_template.csv）
2. duckdb_analyze  一键三个标准分析（描述统计/分组对比/相关性）
3. duckdb_report   生成 Markdown 报表
4. duckdb_query    任意只读 SQL 深挖

数据库默认 %APPDATA%/Lumo/duckdb/workbench.duckdb（LUMO_DUCKDB_PATH 可覆盖）。
"""
from . import workbench
from .duckdb_tools import register_duckdb_tools

__all__ = ["workbench", "register_duckdb_tools"]
