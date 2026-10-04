"""科研写作模板（SPEC-02 Phase 4 任务 4.3）。

Nature 风格论文骨架的 Markdown 模板，供 pipeline 填充。
模板只定结构与写作约束提示，不代写内容——占位符由 pipeline 编排填入。
"""
from __future__ import annotations

# Nature 风格：单栏、开门见山、结果先行。占位符用 {{key}} 标记。
NATURE_ARTICLE = """# {{title}}

{{authors}}

## Abstract

{{abstract}}

## Introduction

{{introduction}}

## Results

{{results}}

## Methods

{{methods}}

## Discussion

{{discussion}}

## Data availability

实验原始数据见 {{data_availability}}；分析口径由 duckdb 工作台报表固化。

## References

{{references}}
"""

# 各节写作约束（供 LLM/人工写作时的风格指引，也写入模板渲染注释）
SECTION_GUIDELINES = {
    "abstract": "≤150 词：一句背景、一句缺口、方法一句、核心结果带数值、意义一句。不用引用。",
    "introduction": "第一段给领域背景与重要性；第二段给现状与未解决问题（引用集中在此）；末句陈述本文贡献。",
    "results": "结果先行：每小节首句给结论，再给数据支撑；数值保留有效位数并注明统计口径。",
    "methods": "可复现为标准：材料来源、工艺参数（温度/时长/配比）、表征手段、统计方法逐项列明。",
    "discussion": "先重申核心发现，再与文献对比（一致/分歧均须解释），最后给局限与展望。",
}


def render_template(template: str, values: dict[str, str]) -> str:
    """把 {{key}} 占位符替换为 values 中的值；未提供的键保留占位符原样。"""
    out = template
    for k, v in values.items():
        out = out.replace("{{" + k + "}}", str(v))
    return out


def empty_article(title: str = "Untitled") -> str:
    """生成一份全部留空的 nature 骨架（供人工写作起步）。"""
    return render_template(NATURE_ARTICLE, {"title": title})
