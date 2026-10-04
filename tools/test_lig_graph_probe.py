"""lig_graph_probe 验收硬线（卷101 W101-04）。"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.lig_graph_probe import (  # noqa: E402
    build_lignin_graph,
    graph_features,
    linkage_counts,
    unit_counts,
)


def test_build_graph_structure():
    """图构造：节点带单元类型、边带键型。"""
    g = build_lignin_graph(
        ["G", "S", "G", "H"],
        [(0, 1, "beta-O-4"), (1, 2, "beta-O-4"), (2, 3, "5-5")],
    )
    assert g.number_of_nodes() == 4 and g.number_of_edges() == 3
    assert g.nodes[0]["unit"] == "G"
    assert g.edges[1, 2]["linkage"] == "beta-O-4"


def test_unit_and_linkage_counts():
    """单元/键型计数正确。"""
    g = build_lignin_graph(["G", "S", "G"], [(0, 1, "beta-O-4"), (1, 2, "beta-5")])
    assert unit_counts(g) == {"G": 2, "S": 1}
    assert linkage_counts(g) == {"beta-O-4": 1, "beta-5": 1}


def test_graph_features_for_ml():
    """图特征字典：S/G 比与 β-O-4 占比计算正确。"""
    g = build_lignin_graph(["G", "S", "G", "S"], [(0, 1, "beta-O-4"), (1, 2, "beta-O-4"), (2, 3, "beta-5")])
    f = graph_features(g)
    assert f["n_units"] == 4 and f["n_linkages"] == 3
    assert f["S_G_ratio"] == 1.0  # 2S/2G
    assert f["beta_O_4_ratio"] == round(2.0 / 3.0, 3)


def test_invalid_unit_rejected():
    with pytest.raises(ValueError, match="未知木质素单元"):
        build_lignin_graph(["X"], [])


def test_invalid_linkage_rejected():
    with pytest.raises(ValueError, match="未知键型"):
        build_lignin_graph(["G", "G"], [(0, 1, "bad-type")])
