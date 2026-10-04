"""脚本 · 论文池增量自动 digest cron 升级（W60-04）

来源 docs/paper-pipeline-cron-增量.md（K06）：把现有 cron（每天 2:00 只做趋势摘要）
升级为「阈值触发全量 digest 轮」——新增论文数 N ≥ 50 时触发全量 digest（按 ≤100 篇
分块），N < 50 时仅趋势摘要（保留现状行为作为 fallback）。

本脚本只交付「判定 + 分块 + 更新后的 cron prompt 文本」，不直接改用户 cron
（更新说明见 docs/paper-pipeline-cron-增量-说明.md）。
"""
from __future__ import annotations

__all__ = ["THRESHOLD", "MAX_CHUNK", "should_trigger_full_digest", "chunk_papers",
           "plan_run", "build_cron_prompt"]

THRESHOLD = 50          # 触发全量 digest 的新增论文数阈值
MAX_CHUNK = 100         # 每块硬上限（>150 必超时，故 ≤100）


def should_trigger_full_digest(n_new: int, threshold: int = THRESHOLD) -> bool:
    """N ≥ threshold 触发全量 digest；否则仅趋势摘要。"""
    return n_new >= threshold


def chunk_papers(n_papers: int, max_per_chunk: int = MAX_CHUNK) -> list[tuple[int, int]]:
    """把 n_papers 篇按 ≤max_per_chunk 分块，返回 (start, end) 半开区间列表。"""
    if n_papers <= 0:
        return []
    return [(i, min(i + max_per_chunk, n_papers)) for i in range(0, n_papers, max_per_chunk)]


def plan_run(n_new: int, threshold: int = THRESHOLD) -> dict:
    """一次 cron 运行的动作计划：低于阈值 → 趋势摘要；高于阈值 → 全量 digest + 分块。"""
    if n_new < threshold:
        return {"mode": "trend_only", "full_digest": False, "chunks": 0, "n": n_new}
    chunks = chunk_papers(n_new)
    return {"mode": "full_digest", "full_digest": True, "chunks": len(chunks), "n": n_new}


def build_cron_prompt() -> str:
    """更新后的 cron prompt（可直接替换 ad17cd9d341f 的 prompt 文本）。"""
    return (
        "你是论文流水线 cron，每天 2:00 执行：\n"
        "1. 拉取自上次运行以来的 arXiv 增量，计算新论文数 N。\n"
        f"2. 若 N < {THRESHOLD}：只产出趋势摘要（周度/主题趋势，不逐篇）。\n"
        f"3. 若 N ≥ {THRESHOLD}：触发全量 digest 轮——\n"
        f"   a. 按 ≤{MAX_CHUNK} 篇/块分块（硬上限 {MAX_CHUNK}，>150 必超时）；\n"
        "   b. 每块两次调用：先「逐篇一行核心 + Top 模式」，再「最有价值 3 篇 + 跨领域授粉点」；\n"
        "   c. 禁止 digest 前派子代理逐篇预处理（token 浪费无增量）；\n"
        f"   d. 超时块按 {MAX_CHUNK} 重切一次，仍超时降级为「仅标题 + ID」摘要行。\n"
        "4. 输出：趋势摘要（每次）+ 增量 digest（仅 N ≥ 阈值时）。\n"
    )
