"""
duckdb 材料数据分析工作台

SPEC-02 Phase 3：CSV/Excel 导入 → 标准分析查询库 → Markdown 报表。

设计取舍：
- duckdb 每次调用开新连接、用完即关（对照 sqlite3 with 语句不关连接泄漏
  文件锁的缺陷模式，duckdb 的 with 语义同样不保证 close，这里显式 try/finally）。
- 数据库文件默认放 %APPDATA%/Lumo/duckdb/workbench.duckdb，不落主仓。
- duckdb 未安装时 register_duckdb_tools 抛 ImportError，agent 侧静默降级
  （与 matchat/biopred 同一模式）。
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def default_db_path() -> Path:
    """工作台数据库默认路径：%APPDATA%/Lumo/duckdb/workbench.duckdb（LUMO_DUCKDB_PATH 可覆盖）。"""
    override = os.environ.get("LUMO_DUCKDB_PATH")
    if override:
        return Path(override)
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "Lumo" / "duckdb" / "workbench.duckdb"


def _connect(db_path: str | Path | None = None):
    import duckdb

    path = Path(db_path) if db_path else default_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(path))


def import_file(file_path: str, table: str | None = None,
                db_path: str | None = None) -> dict[str, Any]:
    """导入 CSV/Excel 到工作台（表名缺省取文件名）。

    CSV 用 auto_detect；Excel 依赖 openpyxl（duckdb 的 read_xlsx 走其引擎）。
    导入前校验：空文件/零行直接报错，不静默建空表（对齐 fail-fast 原则）。
    """
    import duckdb

    src = Path(file_path)
    if not src.exists():
        return {"success": False, "error": f"文件不存在: {file_path}"}
    suffix = src.suffix.lower()
    if suffix not in (".csv", ".xlsx", ".xls"):
        return {"success": False, "error": f"不支持的格式: {suffix}（仅 .csv/.xlsx）"}

    table = table or src.stem.replace(" ", "_").replace("-", "_")
    # 表名白名单校验：duckdb 标识符，防注入
    if not table.isidentifier():
        return {"success": False, "error": f"非法表名: {table}"}

    t0 = time.time()
    reader = f"read_csv_auto('{src.as_posix()}')" if suffix == ".csv" else f"read_xlsx('{src.as_posix()}')"
    conn = _connect(db_path)
    try:
        conn.execute(f"CREATE OR REPLACE TABLE {table} AS SELECT * FROM {reader}")
        row_count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        cols = [r[0] for r in conn.execute(f"SELECT column_name FROM information_schema.columns "
                                           f"WHERE table_name = '{table}' ORDER BY ordinal_position").fetchall()]
    except duckdb.Error as e:
        return {"success": False, "error": f"导入失败: {e}"}
    finally:
        conn.close()

    if row_count == 0:
        return {"success": False, "error": f"文件无数据行，未建表: {file_path}"}

    return {
        "success": True,
        "table": table,
        "rows": row_count,
        "columns": cols,
        "elapsed_s": round(time.time() - t0, 3),
        "db_path": str(db_path or default_db_path()),
    }


def run_query(sql: str, db_path: str | None = None, limit: int = 100) -> dict[str, Any]:
    """执行只读查询（SELECT/DESCRIBE/SHOW），返回行数据。

    安全边界：拒绝非只读语句——工作台面向分析，不做 DDL/DML 通道。
    """
    head = sql.strip().split(None, 1)[0].lower() if sql.strip() else ""
    if head not in ("select", "describe", "show", "with", "from", "summarize"):
        return {"success": False, "error": f"仅支持只读查询，收到: {head or '空语句'}"}

    conn = _connect(db_path)
    try:
        rel = conn.execute(sql)
        cols = [d[0] for d in rel.description]
        rows = rel.fetchmany(limit)
        truncated = rel.fetchone() is not None
        return {
            "success": True,
            "columns": cols,
            "rows": [list(r) for r in rows],
            "row_count": len(rows),
            "truncated": truncated,
        }
    except Exception as e:
        return {"success": False, "error": f"查询失败: {e}"}
    finally:
        conn.close()


# ============ 标准分析查询库（SPEC 任务 3.2）============

def _numeric_columns(conn, table: str) -> list[str]:
    rows = conn.execute(
        "SELECT column_name, data_type FROM information_schema.columns "
        f"WHERE table_name = '{table}' ORDER BY ordinal_position"
    ).fetchall()
    return [name for name, dtype in rows if any(
        k in dtype.upper() for k in ("INT", "FLOAT", "DOUBLE", "DECIMAL", "REAL", "NUMERIC", "HUGEINT")
    )]


def analysis_overview(table: str, db_path: str | None = None) -> dict[str, Any]:
    """标准分析 1：描述统计（数值列的 count/mean/std/min/max）。"""
    conn = _connect(db_path)
    try:
        num_cols = _numeric_columns(conn, table)
        if not num_cols:
            return {"success": False, "error": f"表 {table} 无数值列，无法做描述统计"}
        stats = {}
        for c in num_cols:
            row = conn.execute(
                f'SELECT COUNT("{c}"), AVG("{c}"), STDDEV("{c}"), MIN("{c}"), MAX("{c}") FROM {table}'
            ).fetchone()
            stats[c] = {
                "count": row[0],
                "mean": round(float(row[1]), 4) if row[1] is not None else None,
                "std": round(float(row[2]), 4) if row[2] is not None else None,
                "min": float(row[3]) if row[3] is not None else None,
                "max": float(row[4]) if row[4] is not None else None,
            }
        total = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        return {"success": True, "analysis": "overview", "table": table,
                "total_rows": total, "numeric_stats": stats}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        conn.close()


def analysis_group_compare(table: str, group_col: str, metric_col: str,
                           db_path: str | None = None) -> dict[str, Any]:
    """标准分析 2：分组对比（按 group_col 聚合 metric_col 的均值/最优值）。"""
    if not group_col.isidentifier() or not metric_col.isidentifier():
        return {"success": False, "error": "非法列名"}
    conn = _connect(db_path)
    try:
        rows = conn.execute(
            f'SELECT "{group_col}", COUNT(*), AVG("{metric_col}"), '
            f'MIN("{metric_col}"), MAX("{metric_col}") '
            f'FROM {table} WHERE "{metric_col}" IS NOT NULL '
            f'GROUP BY "{group_col}" ORDER BY AVG("{metric_col}") DESC'
        ).fetchall()
        if not rows:
            return {"success": False, "error": f"分组无数据（检查列名 {group_col}/{metric_col}）"}
        groups = [
            {"group": r[0], "n": r[1], "mean": round(float(r[2]), 4),
             "min": float(r[3]), "max": float(r[4])}
            for r in rows
        ]
        return {"success": True, "analysis": "group_compare", "table": table,
                "group_col": group_col, "metric_col": metric_col,
                "best_group": groups[0]["group"], "groups": groups}
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        conn.close()


def analysis_correlation(table: str, col_x: str, col_y: str,
                         db_path: str | None = None) -> dict[str, Any]:
    """标准分析 3：两列相关性（Pearson）+ 一次线性拟合斜率。"""
    if not col_x.isidentifier() or not col_y.isidentifier():
        return {"success": False, "error": "非法列名"}
    conn = _connect(db_path)
    try:
        row = conn.execute(
            f'SELECT CORR("{col_x}", "{col_y}"), REGR_SLOPE("{col_y}", "{col_x}"), '
            f'REGR_INTERCEPT("{col_y}", "{col_x}"), COUNT(*) '
            f'FROM {table} WHERE "{col_x}" IS NOT NULL AND "{col_y}" IS NOT NULL'
        ).fetchone()
        if row[3] < 3:
            return {"success": False, "analysis": "correlation",
                    "error": f"有效样本不足（n={row[3]}，需 ≥3）"}
        if row[0] is None or row[1] is None:
            # 常数列（方差为零）时 CORR/REGR 返回 NULL，如实报错不假装零相关
            return {"success": False, "analysis": "correlation",
                    "error": f"{col_x} 或 {col_y} 方差为零（常数列），无法计算相关"}
        corr = float(row[0])
        strength = "强" if abs(corr) >= 0.7 else ("中等" if abs(corr) >= 0.4 else "弱")
        return {
            "success": True, "analysis": "correlation", "table": table,
            "col_x": col_x, "col_y": col_y, "n": row[3],
            "pearson_r": round(corr, 4),
            "strength": strength,
            "linear_fit": {"slope": round(float(row[1]), 6), "intercept": round(float(row[2]), 4)},
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
    finally:
        conn.close()


def run_standard_analyses(table: str, group_col: str | None = None,
                          metric_col: str | None = None,
                          db_path: str | None = None) -> list[dict[str, Any]]:
    """一键跑三个标准分析：描述统计 + 分组对比 + 相关性。

    分组/相关列缺省时自动推断：group_col 取第一个非数值列（如 precursor），
    metric_col/col_x/col_y 取最后两个数值列（实验表习惯：末列是性能指标）。
    单项失败不中断整体，结果里带 error 字段。
    """
    conn = _connect(db_path)
    try:
        all_cols = [r[0] for r in conn.execute(
            "SELECT column_name FROM information_schema.columns "
            f"WHERE table_name = '{table}' ORDER BY ordinal_position").fetchall()]
        num_cols = _numeric_columns(conn, table)
        # 分组列推断：非数值列里排除常数列与每行唯一列（如 sample_id/date），
        # 取基数最小者（实验习惯：原料/工艺列取值最少）
        total_rows = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        candidates = []
        for c in all_cols:
            if c in num_cols:
                continue
            uniq = conn.execute(f'SELECT COUNT(DISTINCT "{c}") FROM {table}').fetchone()[0]
            if 1 < uniq < max(total_rows, 2):
                candidates.append((uniq, all_cols.index(c), c))
        inferred_group = min(candidates)[2] if candidates else None
    except Exception as e:
        return [{"success": False, "analysis": "init", "error": str(e)}]
    finally:
        conn.close()

    if not all_cols:
        return [{"success": False, "analysis": "init", "error": f"表 {table} 不存在或无列"}]

    # 自动推断
    if not group_col:
        group_col = inferred_group
    if not metric_col and num_cols:
        metric_col = num_cols[-1]

    results = [analysis_overview(table, db_path)]
    if group_col and metric_col:
        results.append(analysis_group_compare(table, group_col, metric_col, db_path))
    else:
        results.append({"success": False, "analysis": "group_compare",
                        "error": "无法推断分组列/指标列，请显式传 group_col/metric_col"})
    if len(num_cols) >= 2:
        results.append(analysis_correlation(table, num_cols[-2], num_cols[-1], db_path))
    else:
        results.append({"success": False, "analysis": "correlation",
                        "error": "数值列不足 2 个，无法做相关性分析"})
    return results


# ============ Markdown 报表（SPEC 任务 3.3）============

def generate_report(table: str, analyses: list[dict[str, Any]],
                    output_path: str | None = None) -> dict[str, Any]:
    """把标准分析结果渲染成 Markdown 报表。

    output_path 缺省 → %APPDATA%/Lumo/duckdb/reports/<table>_<时间戳>.md。
    """
    ts = time.strftime("%Y%m%d_%H%M%S")
    lines = [
        f"# 实验数据分析报告：{table}",
        "",
        f"> 生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')} | 引擎：duckdb 工作台",
        "",
    ]

    for item in analyses:
        name = item.get("analysis", "unknown")
        if not item.get("success"):
            lines += [f"## {name}", "", f"- **失败**：{item.get('error', '未知错误')}", ""]
            continue
        if name == "overview":
            lines += [f"## 1. 描述统计（共 {item['total_rows']} 行）", "",
                      "| 列 | count | mean | std | min | max |",
                      "|---|---|---|---|---|---|"]
            for col, s in item["numeric_stats"].items():
                lines.append(f"| {col} | {s['count']} | {s['mean']} | {s['std']} | {s['min']} | {s['max']} |")
            lines.append("")
        elif name == "group_compare":
            lines += [f"## 2. 分组对比（按 {item['group_col']}，指标 {item['metric_col']}）", "",
                      f"**最优组：{item['best_group']}**", "",
                      "| 组 | n | mean | min | max |", "|---|---|---|---|---|"]
            for g in item["groups"]:
                lines.append(f"| {g['group']} | {g['n']} | {g['mean']} | {g['min']} | {g['max']} |")
            lines.append("")
        elif name == "correlation":
            fit = item["linear_fit"]
            lines += [
                f"## 3. 相关性分析（{item['col_x']} → {item['col_y']}）", "",
                f"- Pearson r = **{item['pearson_r']}**（{item['strength']}相关，n={item['n']}）",
                f"- 线性拟合：y = {fit['slope']}·x + {fit['intercept']}",
                "",
            ]

    lines += ["---", "*本报告由 Lumo duckdb 工作台自动生成，统计口径见各节标题。*", ""]
    content = "\n".join(lines)

    if output_path:
        out = Path(output_path)
    else:
        base = os.environ.get("APPDATA") or str(Path.home())
        out = Path(base) / "Lumo" / "duckdb" / "reports" / f"{table}_{ts}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content, encoding="utf-8")
    return {"success": True, "report_path": str(out), "sections": len(analyses),
            "chars": len(content)}
