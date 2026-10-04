"""木质素结构图建模最小探针（卷101 W101-04 · MIT 可参考，独立实现）。

设计参考：VlachosGroup/LigninGraphs（MIT）的木质素多尺度图建模——本模块用 networkx
独立实现「木质素单元 → 图表示」最小骨架：G/S/H 单元为节点，键型（β-O-4/β-5/β-β/5-5）
为边，图可作 ML 输入特征源。
"""
from __future__ import annotations

import networkx as nx

# 木质素单元类型（G=愈创木基 / S=紫丁香基 / H=对羟苯基）
_UNIT_NAMES = {"G", "S", "H"}

# 键型与连接位点（β-O-4 等，简化符号）
_LINKAGE_SYMBOLS = {"beta-O-4", "beta-5", "beta-beta", "5-5"}


def build_lignin_graph(units: list[str], linkages: list[tuple[int, int, str]]) -> nx.Graph:
    """构造木质素结构图：节点=单元（含类型），边=键型。

    units: 按序单元类型列表，如 ["G","S","G","H"]。
    linkages: [(i, j, 键型), ...]，键型须在 _LINKAGE_SYMBOLS 内。
    """
    for u in units:
        if u not in _UNIT_NAMES:
            raise ValueError(f"未知木质素单元: {u}")
    g = nx.Graph()
    for i, u in enumerate(units):
        g.add_node(i, unit=u)
    for i, j, lt in linkages:
        if lt not in _LINKAGE_SYMBOLS:
            raise ValueError(f"未知键型: {lt}")
        if i not in g or j not in g:
            raise ValueError(f"连接索引越界: {(i, j)}")
        g.add_edge(i, j, linkage=lt)
    return g


def unit_counts(g: nx.Graph) -> dict:
    """单元类型计数（S/G 比等特征的基础）。"""
    from collections import Counter

    return dict(Counter(g.nodes[i]["unit"] for i in g.nodes))


def linkage_counts(g: nx.Graph) -> dict:
    """键型计数（β-O-4 占比等特征的基础）。"""
    from collections import Counter

    return dict(Counter(g.edges[e]["linkage"] for e in g.edges))


def graph_features(g: nx.Graph) -> dict:
    """图 → ML 输入特征字典：单元数/键数/平均度/S-G 比/β-O-4 占比。"""
    counts = unit_counts(g)
    lc = linkage_counts(g)
    total_link = sum(lc.values()) or 1
    s_g_ratio = counts.get("S", 0) / max(counts.get("G", 0), 1)
    beta_o4_ratio = lc.get("beta-O-4", 0) / total_link
    return {
        "n_units": g.number_of_nodes(),
        "n_linkages": g.number_of_edges(),
        "mean_degree": round(2.0 * g.number_of_edges() / max(g.number_of_nodes(), 1), 3),
        "S_G_ratio": round(s_g_ratio, 3),
        "beta_O_4_ratio": round(beta_o4_ratio, 3),
        "unit_counts": counts,
    }
