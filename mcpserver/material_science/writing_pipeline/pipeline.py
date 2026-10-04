"""科研写作管线（SPEC-02 Phase 4 任务 4.1：串流程）。

编排：文献综述 → 实验设计 → 数据分析 → 论文写作。

设计取舍：
- 本模块是确定性编排骨架：引用管理、模板填充、分析调用都是纯函数/已验证链路，
  不掺 LLM。正文润色交给 skills 侧 nature-* 系列（nature-writing/nature-polishing）。
- 有 CSV 时数据分析节直连 duckdb_workbench（导入→三标准分析→报表），
  无 CSV 时输出实验设计占位（列口径对齐 import_template.csv）。
- 初稿落盘 %APPDATA%/Lumo/writing/drafts/<slug>.md（LUMO_WRITING_DIR 可覆盖）。
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any

from . import bibtex
from .templates import NATURE_ARTICLE, SECTION_GUIDELINES, render_template

# 文献综述默认引用 academic 种子条目（Phase 1 已接入/有引用信息的 5 项）
DEFAULT_INTRO_KEYS = [
    "thermo2024", "witte2020tespy", "xiao2023slices",
    "fredericks2021pyxtal", "otis2017pycalphad",
]

TEMPLATE_CSV_COLUMNS = (
    "sample_id,date,material,method,variable_1,variable_2,"
    "temperature_c,duration_min,metric_primary,metric_secondary,notes"
)


def drafts_dir() -> Path:
    base = os.environ.get("LUMO_WRITING_DIR")
    if base:
        d = Path(base) / "drafts"
    else:
        d = Path(os.environ.get("APPDATA", str(Path.home()))) / "Lumo" / "writing" / "drafts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _slug(topic: str) -> str:
    s = re.sub(r"[^\w\u4e00-\u9fff]+", "-", topic.strip()).strip("-")
    return s[:60] or "untitled"


# ---------- 各节生成 ----------

def build_introduction(topic: str, bib_path: Path | None = None) -> dict[str, Any]:
    """文献综述/引言节：挂 bibtex 种子引用，生成带 [n] 标注的骨架段落。"""
    bibtex.seed_academic_refs(bib_path)
    cite = bibtex.cite_section(DEFAULT_INTRO_KEYS, bib_path)
    entries = bibtex.load_entries(bib_path)
    marks = {m.split(" -> ")[0]: m.split(" -> ")[1] for m in cite["marks"]}

    bullets = []
    for key in DEFAULT_INTRO_KEYS:
        f = entries.get(key)
        if not f:
            continue
        bullets.append(f"- {f.get('title', key)}（{f.get('year', '?')}）{marks.get(key, '')}")
    text = (
        f"围绕「{topic}」，现有开源计算工具链已覆盖热力学物性、晶体结构生成与相图计算等关键环节。"
        f"代表性工作如下，本文方法节将复用其可调用接口：\n" + "\n".join(bullets)
    )
    return {"text": text, "cite_keys": DEFAULT_INTRO_KEYS,
            "marks": cite["marks"], "references_md": cite["markdown"]}


def build_methods(topic: str, has_csv: bool) -> str:
    """实验设计/方法节：无数据时给设计框架，有数据时描述实际数据口径。"""
    design = (
        f"**实验设计（围绕 {topic}）**\n\n"
        "1. 变量设计：按 import_template.csv 列口径记录——material（原料）、method（工艺）、"
        "temperature_c/duration_min（工艺参数）、metric_primary（主性能指标）。\n"
        "2. 分组策略：以 material 或 method 为分组列做组间对比，每组 ≥3 平行样。\n"
        "3. 分析计划：描述统计 → 分组对比（最优组）→ 工艺参数与性能的相关性（Pearson）。\n"
        "4. 数据落地：CSV 经 duckdb 工作台导入，三标准分析自动生成 Markdown 报表。"
    )
    if has_csv:
        design += "\n\n**实际数据**：本次初稿已附实验 CSV，Results 节为标准分析实测结果。"
    return design


def build_results(csv_path: str | None = None) -> dict[str, Any]:
    """数据分析节：有 CSV 则走 duckdb 导入→三标准分析→报表；无则返回占位。"""
    if not csv_path:
        return {"text": "_（待补充：导入实验 CSV 后，本节由标准分析自动填充。）_",
                "analyses": [], "report_path": None, "table": None}
    from mcpserver.material_science.duckdb_workbench import workbench

    imp = workbench.import_file(csv_path)
    if not imp["success"]:
        return {"text": f"_（数据分析失败：{imp.get('error')}）_",
                "analyses": [], "report_path": None, "table": None, "error": imp["error"]}
    table = imp["table"]
    analyses = workbench.run_standard_analyses(table)
    ts = time.strftime("%Y%m%d_%H%M%S")
    report = workbench.generate_report(
        table, analyses, str(drafts_dir() / f"analysis_{table}_{ts}.md"))

    ok = [a for a in analyses if a.get("success")]
    lines = [f"实验数据 `{Path(csv_path).name}`（{imp['rows']} 行 × {len(imp['columns'])} 列，"
             f"表 `{table}`）完成 {len(ok)}/3 项标准分析："]
    for a in analyses:
        if not a.get("success"):
            lines.append(f"- {a.get('analysis')}: 失败（{a.get('error')}）")
        elif a["analysis"] == "overview":
            lines.append(f"- 描述统计：{a['total_rows']} 行，数值列 {list(a['numeric_stats'].keys())}")
        elif a["analysis"] == "group_compare":
            lines.append(f"- 分组对比：按 {a['group_col']}，最优组 **{a['best_group']}**")
        elif a["analysis"] == "correlation":
            lines.append(f"- 相关性：{a['col_x']}→{a['col_y']}，r={a['pearson_r']}（{a['strength']}）")
    lines.append(f"\n完整报表：`{report['report_path']}`")
    return {"text": "\n".join(lines), "analyses": analyses,
            "report_path": report["report_path"], "table": table}


def build_abstract(topic: str, results: dict[str, Any]) -> str:
    """摘要：从结果节提取关键数值句；无数据时给结构化占位。"""
    if not results["analyses"]:
        return (f"针对 {topic}，本文建立「文献综述→实验设计→数据分析→论文写作」一体化管线。"
                "_（核心结果待实验数据补充）_")
    ok = [a for a in results["analyses"] if a.get("success")]
    best = next((a for a in ok if a["analysis"] == "group_compare"), None)
    corr = next((a for a in ok if a["analysis"] == "correlation"), None)
    parts = [f"针对 {topic}，本文以 duckdb 工作台完成标准分析。"]
    if best:
        parts.append(f"分组对比显示 {best['best_group']} 的 {best['metric_col']} 均值最优"
                     f"（{best['groups'][0]['mean']}）。")
    if corr:
        parts.append(f"{corr['col_x']} 与 {corr['col_y']} 呈{corr['strength']}相关"
                     f"（r={corr['pearson_r']}）。")
    return "".join(parts)


# ---------- 一条龙 ----------

def run_pipeline(topic: str, csv_path: str | None = None,
                 authors: str = "Lumo (陆墨) 与研究者",
                 bib_path: Path | None = None,
                 output_path: str | None = None) -> dict[str, Any]:
    """选题→初稿一条龙：综述（带引用）→ 实验设计 → 数据分析 → nature 模板成稿。"""
    t0 = time.time()
    intro = build_introduction(topic, bib_path)
    results = build_results(csv_path)
    values = {
        "title": topic,
        "authors": authors,
        "abstract": build_abstract(topic, results),
        "introduction": intro["text"],
        "results": results["text"],
        "methods": build_methods(topic, bool(csv_path)),
        "discussion": "（待撰写：与引言引用的文献逐一对比，解释一致与分歧；"
                      "写作约束见 nature-writing skill。）",
        "data_availability": results["report_path"] or "（待实验数据落盘）",
        "references": intro["references_md"].replace("## References\n", "", 1).strip(),
    }
    draft = render_template(NATURE_ARTICLE, values)

    out = Path(output_path) if output_path else drafts_dir() / f"{_slug(topic)}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(draft, encoding="utf-8")

    return {
        "success": True,
        "topic": topic,
        "draft_path": str(out),
        "chars": len(draft),
        "elapsed_s": round(time.time() - t0, 3),
        "citations": intro["marks"],
        "analysis_report": results["report_path"],
        "section_guidelines": SECTION_GUIDELINES,
    }
