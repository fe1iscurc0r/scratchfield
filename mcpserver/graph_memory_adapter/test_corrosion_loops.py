"""工单 262 任务 A 验收：cluster_corrosion_loops。

fixture：5 个节点
    碳钢/碱液/150℃ ×2、不锈钢/中性/80℃ ×2、碳钢/水/40℃ ×1
断言：3 个 loop，分别含 2 / 2 / 1 个 id。
"""
from __future__ import annotations

import logging

import pytest

from mcpserver.graph_memory_adapter.engine import cluster_corrosion_loops


def _nodes() -> list[dict]:
    return [
        {"id": "a1", "attrs": {"material": "碳钢", "fluid": "碱液", "temp_C": 150.0}},
        {"id": "a2", "attrs": {"material": "碳钢", "fluid": "碱液", "temp_C": 152.0}},
        {"id": "b1", "attrs": {"material": "不锈钢", "fluid": "中性", "temp_C": 80.0}},
        {"id": "b2", "attrs": {"material": "不锈钢", "fluid": "中性", "temp_C": 82.0}},
        {"id": "c1", "attrs": {"material": "碳钢", "fluid": "水", "temp_C": 40.0}},
    ]


def test_three_loops_with_expected_sizes() -> None:
    result = cluster_corrosion_loops(_nodes(), ["material", "fluid"], ["temp_C"])

    assert len(result) == 3, f"应得 3 个 loop，实际 {result}"
    sizes = sorted(len(ids) for ids in result.values())
    assert sizes == [1, 2, 2], f"三组应分别为 2/2/1，实际 {sizes}｜{result}"

    # 同组节点必须来自同一 categorical 组合（不能跨组混淆）
    flat = {nid: n for n in _nodes() for nid in [n["id"]]}
    for ids in result.values():
        keys = {(flat[i]["attrs"]["material"], flat[i]["attrs"]["fluid"]) for i in ids}
        assert len(keys) == 1, f"一个 loop 里混入了不同分组: {ids} → {keys}"


def test_label_matches_joined_keys() -> None:
    result = cluster_corrosion_loops(_nodes(), ["material", "fluid"], ["temp_C"])
    # 单簇组的 label 必须是 "-".join(categorical keys)
    assert "碳钢-碱液" in result
    assert "不锈钢-中性" in result
    assert "碳钢-水" in result


def test_nodes_without_attrs_are_skipped_not_raised(caplog) -> None:
    nodes = _nodes() + [
        {"id": "broken1"},  # 无 attrs
        {"id": "broken2", "attrs": {"material": "碳钢", "fluid": "碱液"}},  # 缺 temp_C
    ]
    with caplog.at_level(logging.WARNING):
        result = cluster_corrosion_loops(nodes, ["material", "fluid"], ["temp_C"])

    all_ids = {nid for ids in result.values() for nid in ids}
    assert "broken1" not in all_ids and "broken2" not in all_ids
    assert any("跳过" in rec.getMessage() for rec in caplog.records), "应留下 warning 记录"


def test_single_node_group_becomes_one_loop() -> None:
    nodes = [{"id": "solo", "attrs": {"material": "钛", "fluid": "海水", "temp_C": 25.0}}]
    result = cluster_corrosion_loops(nodes, ["material", "fluid"], ["temp_C"])
    assert result == {"钛-海水": ["solo"]}


def test_identical_values_not_split() -> None:
    """参数完全相同的 4 个节点不应被 KMeans 任意劈开（k 上限 = n//2 的守护）。"""
    nodes = [
        {"id": f"d{i}", "attrs": {"material": "碳钢", "fluid": "水", "temp_C": 60.0}}
        for i in range(4)
    ]
    result = cluster_corrosion_loops(nodes, ["material", "fluid"], ["temp_C"])
    assert len(result) == 1, f"完全相同的点应聚为一簇，实际 {result}"
    assert len(next(iter(result.values()))) == 4


def test_reproducible() -> None:
    a = cluster_corrosion_loops(_nodes(), ["material", "fluid"], ["temp_C"])
    b = cluster_corrosion_loops(_nodes(), ["material", "fluid"], ["temp_C"])
    assert a == b, "random_state 固定后结果必须可复现"


def test_missing_sklearn_gives_readable_error(monkeypatch) -> None:
    """缺 sklearn 时应抛 ImportError（可读提示），不是裸 traceback。"""
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "sklearn" or name.startswith("sklearn."):
            raise ImportError("simulated missing sklearn")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with pytest.raises(ImportError, match="scikit-learn"):
        cluster_corrosion_loops(_nodes(), ["material", "fluid"], ["temp_C"])
