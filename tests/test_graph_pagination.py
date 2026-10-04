"""卷148 图谱分页/聚合纯函数单测。

覆盖 apiserver/routes/extensions.py 新增的三个辅助函数：
  - _quintuple_degree        实体度数计算
  - _apply_quintuple_filters 过滤 + 排序（含向后兼容的空参形态）

只测纯函数，不启动 FastAPI（端点行为由 router 层薄的参数透传保证，
避免为了测端点把 summer_memory 依赖拖进单测环境）。
"""
from __future__ import annotations

import pytest  # noqa: E402  (卷173 分层标注；与文件既有 import pytest 重复无害)

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.core]

import pytest

from apiserver.routes.extensions import (
    _apply_quintuple_filters,
    _quintuple_degree,
)


@pytest.fixture
def rows() -> list[dict]:
    """样例五元组：构造出度数差异明显的图，便于验证排序。

    度数分布（subject 或 object 出现即 +1）：
      A: A→B, A→C          = 2
      B: A→B, B→D          = 2
      C: A→C               = 1
      D: B→D, D→D          = 2
    """
    return [
        {"subject": "A", "subject_type": "Person", "predicate": "knows", "object": "B", "object_type": "Org"},
        {"subject": "A", "subject_type": "Person", "predicate": "owns", "object": "C", "object_type": "Tool"},
        {"subject": "B", "subject_type": "Org", "predicate": "knows", "object": "D", "object_type": "Org"},
        {"subject": "D", "subject_type": "Org", "predicate": "self", "object": "D", "object_type": "Org"},
    ]


def test_degree_counts_both_ends(rows):
    deg = _quintuple_degree(rows)
    assert deg["A"] == 2
    assert deg["B"] == 2
    assert deg["C"] == 1
    assert deg["D"] == 3  # B→D 记 1 次 + D→D 里作为 subject 和 object 各 1 次


def test_degree_ignores_empty_names():
    deg = _quintuple_degree([{"subject": "", "object": "X"}, {"subject": "X", "object": None}])
    assert deg == {"X": 2}


def test_no_params_is_passthrough(rows):
    """向后兼容：不带参数时原样返回（顺序都不变）。"""
    out = _apply_quintuple_filters(rows)
    assert out == rows


def test_filter_by_entity_type_hits_both_sides(rows):
    # Person 只作 subject_type 出现 → 2 条
    assert len(_apply_quintuple_filters(rows, entity_type="Person")) == 2
    # Org 两侧都有 → A→B / B→D / D→D 三条
    assert len(_apply_quintuple_filters(rows, entity_type="Org")) == 3
    # 大小写不敏感
    assert len(_apply_quintuple_filters(rows, entity_type="person")) == 2


def test_filter_by_entity_type_no_match(rows):
    assert _apply_quintuple_filters(rows, entity_type="Nope") == []


def test_search_hits_any_field(rows):
    assert len(_apply_quintuple_filters(rows, q="knows")) == 2   # predicate
    assert len(_apply_quintuple_filters(rows, q="a")) >= 2        # subject/object 含 a/A
    assert _apply_quintuple_filters(rows, q="zzz") == []


def test_order_by_degree_desc(rows):
    out = _apply_quintuple_filters(rows, order_by="degree")
    # D 相关两条（度数 2+3、3+3）应排在 Person/A 相关之前
    assert out[0]["subject"] in {"B", "D"}
    # 单调不增
    deg = _quintuple_degree(rows)
    scores = [deg.get(r["subject"], 0) + deg.get(r["object"], 0) for r in out]
    assert scores == sorted(scores, reverse=True)


def test_order_by_time_is_stable(rows):
    """order_by='time' 无时间字段时退化为原序（不抛错）。"""
    out = _apply_quintuple_filters(rows, order_by="time")
    assert out == rows


def test_combined_filter_and_order(rows):
    # entity_type=Org 命中 A→B（object_type=Org）与 B→D（两侧 Org）；
    # 再叠加 q=knows（predicate）后两条都满足，按度数倒序 B→D 在前（B=2,D=3 → 5 > A=2,B=2 → 4）
    out = _apply_quintuple_filters(rows, entity_type="Org", q="knows", order_by="degree")
    assert len(out) == 2
    assert out[0]["subject"] == "B"
    assert out[0]["object"] == "D"


def test_combined_filter_narrows_to_one(rows):
    """三条件叠加能收窄到单条：entity_type=Tool 仅 A→C 命中。"""
    out = _apply_quintuple_filters(rows, entity_type="Tool", q="owns", order_by="degree")
    assert len(out) == 1
    assert out[0]["subject"] == "A"
    assert out[0]["object"] == "C"
