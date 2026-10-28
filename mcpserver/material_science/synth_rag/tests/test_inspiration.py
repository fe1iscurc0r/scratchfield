"""synth_rag 灵感素材库测试（工单 237 任务一：索引层）。

覆盖：加载校验（count 一致 / pid 唯一 / 缺文件 / 缺 pid）、主题过滤检索、
排序稳定性、真实语料加载与检索样例。
纯标准库 + 临时目录，不碰真实数据库与 graphrag 主流程。
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcpserver.material_science.synth_rag import (
    available_themes,
    inspiration,
    load_inspiration_pool,
    search_inspiration,
)
from mcpserver.material_science.synth_rag.store import (
    INSPIRATION_POOL_ROOT,
    THEME_DIRS,
    inspiration_theme_path,
)

REAL_POOL = INSPIRATION_POOL_ROOT


def _item(pid: str, target: str, abstract: str = "", composite: float = 80.0) -> dict:
    return {"pid": pid, "composite": composite, "match": "kw",
            "target": target, "abstract": abstract,
            "arxiv_url": f"https://arxiv.org/abs/{pid}"}


def _write_pool(root: Path, theme: str, items: list[dict], count: int | None = None) -> Path:
    """在 root/<THEME_DIRS[theme]>/index.json 写一份小语料，返回目录。"""
    d = root / THEME_DIRS[theme]
    d.mkdir(parents=True, exist_ok=True)
    payload = {
        "meta": {"source": "test", "theme": theme,
                 "count": len(items) if count is None else count, "note": "测试"},
        "items": items,
    }
    (d / "index.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return d


# ---------- 加载与校验 ----------

def test_load_pool_ok(tmp_path: Path):
    _write_pool(tmp_path, "biomass", [_item("a1", "木质素 碳化", "摘要一")],
                count=1)
    items = load_inspiration_pool(inspiration_theme_path("biomass", tmp_path))
    assert len(items) == 1
    it = items[0]
    assert it.pid == "a1"
    assert it.target == "木质素 碳化"
    assert it.abstract == "摘要一"
    assert it.theme == "biomass"
    assert it.arxiv_url.endswith("a1")


def test_load_accepts_index_json_path_directly(tmp_path: Path):
    d = _write_pool(tmp_path, "sdr", [_item("s1", "频谱")], count=1)
    items = load_inspiration_pool(d / "index.json")
    assert [i.pid for i in items] == ["s1"]


def test_load_count_mismatch_raises(tmp_path: Path):
    _write_pool(tmp_path, "biomass", [_item("a1", "x"), _item("a2", "y")], count=99)
    with pytest.raises(ValueError, match="不一致"):
        load_inspiration_pool(inspiration_theme_path("biomass", tmp_path))


def test_load_duplicate_pid_raises(tmp_path: Path):
    _write_pool(tmp_path, "biomass", [_item("dup", "x"), _item("dup", "y")], count=2)
    with pytest.raises(ValueError, match="pid 重复"):
        load_inspiration_pool(inspiration_theme_path("biomass", tmp_path))


def test_load_missing_pid_raises(tmp_path: Path):
    _write_pool(tmp_path, "biomass", [{"composite": 1.0, "target": "x"}], count=1)
    with pytest.raises(ValueError, match="缺 pid"):
        load_inspiration_pool(inspiration_theme_path("biomass", tmp_path))


def test_load_missing_file_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_inspiration_pool(tmp_path / "nope")


def test_unknown_theme_path_raises():
    with pytest.raises(KeyError):
        inspiration_theme_path("not-a-theme")


# ---------- 检索 ----------

def test_search_theme_filter(tmp_path: Path):
    _write_pool(tmp_path, "biomass", [_item("a1", "木质素 碳化 多孔碳")], count=1)
    _write_pool(tmp_path, "sdr", [_item("s1", "频谱监测 异常检测")], count=1)
    inspiration.clear_cache()

    res = search_inspiration("木质素", top_k=10, theme="biomass", root=str(tmp_path))
    assert [i.pid for i in res] == ["a1"]

    # 同词在 sdr 主题下应无命中（词元不重叠）
    res_sdr = search_inspiration("木质素", top_k=10, theme="sdr", root=str(tmp_path))
    assert res_sdr == []


def test_search_without_theme_spans_all(tmp_path: Path):
    _write_pool(tmp_path, "biomass", [_item("a1", "木质素 碳化")], count=1)
    _write_pool(tmp_path, "sdr", [_item("s1", "频谱 木质素 无关")], count=1)
    inspiration.clear_cache()
    res = search_inspiration("木质素", top_k=10, root=str(tmp_path))
    assert {i.pid for i in res} == {"a1", "s1"}


def test_search_ranks_by_score_then_composite(tmp_path: Path):
    # 同分（都精确相等不现实）——用同为子串命中(0.8)的两条，比较 composite 次序
    _write_pool(tmp_path, "biomass", [
        _item("low", "木质素 制备", composite=70.0),
        _item("high", "木质素 制备", composite=95.0),
    ], count=2)
    inspiration.clear_cache()
    res = search_inspiration("木质素", top_k=10, theme="biomass", root=str(tmp_path))
    assert [i.pid for i in res] == ["high", "low"]


def test_search_exact_beats_substring(tmp_path: Path):
    _write_pool(tmp_path, "sdr", [
        _item("sub", "前缀 频谱分析 后缀", composite=99.0),
        _item("exact", "频谱分析", composite=70.0),
    ], count=2)
    inspiration.clear_cache()
    res = search_inspiration("频谱分析", top_k=10, theme="sdr", root=str(tmp_path))
    assert res[0].pid == "exact"  # 1.0 > 0.8，即使 composite 更低


def test_search_empty_query_returns_empty(tmp_path: Path):
    _write_pool(tmp_path, "biomass", [_item("a1", "木质素")], count=1)
    inspiration.clear_cache()
    assert search_inspiration("", top_k=5, theme="biomass", root=str(tmp_path)) == []
    assert search_inspiration("   ", top_k=5, theme="biomass", root=str(tmp_path)) == []


def test_search_top_k_limits(tmp_path: Path):
    _write_pool(tmp_path, "biomass",
                [_item(f"p{i}", "木质素 碳化") for i in range(5)], count=5)
    inspiration.clear_cache()
    res = search_inspiration("木质素", top_k=2, theme="biomass", root=str(tmp_path))
    assert len(res) == 2


def test_available_themes_contains_expected():
    assert set(available_themes()) >= {"biomass", "sdr", "agent", "esp32"}


# ---------- 真实语料（随 PR #326 落仓） ----------

real_only = pytest.mark.skipif(
    not REAL_POOL.is_dir(), reason="灵感素材语料未随仓分发")


@real_only
def test_real_biomass_corpus_loads():
    items = load_inspiration_pool(inspiration_theme_path("biomass"))
    assert len(items) == 2240
    assert len({i.pid for i in items}) == 2240


@real_only
def test_real_sdr_corpus_loads():
    items = load_inspiration_pool(inspiration_theme_path("sdr"))
    assert len(items) == 1010


@real_only
def test_real_biomass_search_returns_sample():
    """真实检索样例（供 PR 证据）：生物质线搜「机器学习势」。"""
    inspiration.clear_cache()
    res = search_inspiration("机器学习势", top_k=5, theme="biomass")
    assert res, "真实 biomass 语料应能命中"
    top = res[0]
    assert top.pid
    assert top.arxiv_url.startswith("https://arxiv.org/abs/")
    assert top.composite > 0
