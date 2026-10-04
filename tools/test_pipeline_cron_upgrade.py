"""W60-04 验收测试：论文池增量自动 digest cron 升级（阈值触发 + 分块）。"""
from __future__ import annotations

from scripts.pipeline_cron_upgrade import (
    MAX_CHUNK,
    THRESHOLD,
    build_cron_prompt,
    chunk_papers,
    plan_run,
    should_trigger_full_digest,
)


def test_below_threshold_skips_full_digest():
    """低于阈值（49 < 50）→ 仅趋势摘要，不触发全量。"""
    plan = plan_run(49)
    assert plan["mode"] == "trend_only"
    assert plan["full_digest"] is False
    assert plan["chunks"] == 0


def test_at_threshold_triggers_full_digest():
    """达到阈值（50）→ 触发全量 digest。"""
    assert should_trigger_full_digest(50) is True
    plan = plan_run(50)
    assert plan["mode"] == "full_digest"
    assert plan["full_digest"] is True


def test_chunking_respects_max():
    """250 篇 → 3 块（100/100/50），每块 ≤ MAX_CHUNK。"""
    chunks = chunk_papers(250)
    assert len(chunks) == 3
    for s, e in chunks:
        assert e - s <= MAX_CHUNK
    assert chunks == [(0, 100), (100, 200), (200, 250)]


def test_build_cron_prompt_contains_threshold():
    p = build_cron_prompt()
    assert str(THRESHOLD) in p
    assert "全量 digest" in p


def test_chunk_empty():
    assert chunk_papers(0) == []
    assert chunk_papers(-1) == []
