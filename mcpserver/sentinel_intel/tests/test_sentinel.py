"""tests/test_sentinel.py — K-01 验收 10 用例。

覆盖（工单清单）：
1-3   alias 三级回退各 1（硬编码/JSON/图 alias_of）
4     alias 未命中原样返回
5     add_node 幂等（同 value 不重复建）
6     add_edge + get_neighbors
7     traverse 2 层
8     get_entity_timeline 按 ts 排序
9     BG5GXO 两频段归并同一 canonical_id（主断言）
10    intel_query 返回含画像字段
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from mcpserver.sentinel_intel.alias_resolver import AliasResolver
from mcpserver.sentinel_intel.bridge import (
    IntelBridge,
    get_graph,
    reset_graph,
)
from mcpserver.sentinel_intel.graph import IntelGraph, IntelGraphError


@pytest.fixture
def graph() -> IntelGraph:
    g = IntelGraph(":memory:")
    yield g
    g.close()


# ------------------------------------------------------- 1-4 别名三级回退

def test_alias_hardcoded_hit(graph: IntelGraph):
    """① 硬编码：fancy bear → apt28（照 zettelforge 样例）。"""
    resolver = AliasResolver(graph.conn)
    assert resolver.resolve("actor", "Fancy Bear") == "apt28"
    assert resolver.resolve("actor", "pawn-storm") == "apt28"  # 连字符归一
    assert resolver.resolve("actor", "Cozy Bear") == "apt29"


def test_alias_json_hit(graph: IntelGraph, tmp_path: Path):
    """② JSON 外部扩展：entity_aliases.json 存在则读入合并。"""
    alias_file = tmp_path / "entity_aliases.json"
    alias_file.write_text(json.dumps({
        "infra": {"evil-cdn example": "bulletproof-host-xx"},
        "actor": {"雪 风": "apt99"},  # 与硬编码合并共存
    }), encoding="utf-8")
    resolver = AliasResolver(graph.conn, alias_file=alias_file)
    assert resolver.resolve("infra", "EVIL-CDN Example") == "bulletproof-host-xx"
    assert resolver.resolve("actor", "雪风") == "apt99"
    # 硬编码不受 JSON 影响
    assert resolver.resolve("actor", "fancy bear") == "apt28"


def test_alias_graph_fallback(graph: IntelGraph):
    """③ 图回退：查 intel_edge 的 rel='alias_of' 边（自家 SQLite，非 TypeDB）。"""
    graph.add_node("actor", "apt28")
    graph.add_alias("actor", "Sofacy", "actor", "apt28")
    resolver = AliasResolver(graph.conn)
    # 清掉硬编码干扰：Sofacy 不在硬编码表 → 直落图回退（返回存储值，仅大小写归一）
    assert resolver.resolve("actor", "sofacy") == "apt28"
    # 命中后登记 intel_alias 缓存，source='graph'
    row = graph.conn.execute(
        "SELECT canonical_id, source FROM intel_alias "
        "WHERE alias='sofacy' AND etype='actor'").fetchone()
    assert row is not None and row["source"] == "graph"
    # 链式 alias（A→B→C）追到底
    graph.add_alias("actor", "apt28 group", "actor", "apt28")
    assert resolver.resolve("actor", "APT28 Group") == "apt28"


def test_alias_miss_returns_normalized(graph: IntelGraph):
    """未命中：返回规范化形式（lower+连字符转空格），不抛错。"""
    resolver = AliasResolver(graph.conn)
    assert resolver.resolve("actor", "Brand-New-Actor") == "brand new actor"
    assert resolver.resolve("infra", "192.0.2.1") == "192.0.2.1"


# --------------------------------------------------------- 5-8 图操作

def test_add_node_idempotent(graph: IntelGraph):
    """同 etype+value 不重复建行：返回同 id，表内一行，props 合并、last_seen 刷新。"""
    id1 = graph.add_node("indicator", "BG5GXO", props={"band": "20m"},
                         ts="2026-08-20T10:00:00")
    id2 = graph.add_node("indicator", "bg5gxo", props={"mode": "FT8"},
                         ts="2026-08-21T10:00:00")  # 大小写规范化后同实体
    assert id1 == id2
    rows = graph.conn.execute(
        "SELECT * FROM intel_entity WHERE etype='indicator'").fetchall()
    assert len(rows) == 1
    ent = graph.get_node("indicator", "BG5GXO")
    assert ent["properties"] == {"band": "20m", "mode": "FT8"}  # props 合并
    assert ent["last_seen_at"] == "2026-08-21T10:00:00"
    assert ent["canonical_id"] == ent["id"]  # 新实体自成画像


def test_add_edge_and_get_neighbors(graph: IntelGraph):
    a = graph.add_node("actor", "apt28")
    d = graph.add_node("infra", "evil-cdn.example")
    graph.add_edge(a, d, "uses", props={"first_seen": "2026-01-01"},
                   ts="2026-01-01T00:00:00")
    nbs = graph.get_neighbors(a)
    assert len(nbs) == 1
    assert nbs[0]["rel"] == "uses" and nbs[0]["direction"] == "out"
    assert nbs[0]["peer_value"] == "evil-cdn.example"
    # 反向也是邻居（direction=in）
    nbs_rev = graph.get_neighbors(d)
    assert nbs_rev[0]["direction"] == "in" and nbs_rev[0]["peer_value"] == "apt28"
    # 白名单 fail-fast
    with pytest.raises(IntelGraphError, match="白名单"):
        graph.add_edge(a, d, "hacks")
    # 端点缺失 fail-fast
    with pytest.raises(IntelGraphError, match="端点不存在"):
        graph.add_edge(a, "deadbeef00000000", "uses")


def test_traverse_two_levels(graph: IntelGraph):
    """A uses B，B indicates C：depth=1 到 B，depth=2 到 C（DFS+环预防）。"""
    a = graph.add_node("actor", "apt28")
    b = graph.add_node("infra", "relay-node-1")
    c = graph.add_node("indicator", "bad.example")
    graph.add_edge(a, b, "uses")
    graph.add_edge(b, c, "indicates")
    # 环：C 指回 A —— traverse 不得死循环
    graph.add_edge(c, a, "uses")

    depth1 = graph.traverse("actor", "apt28", max_depth=1)
    values1 = [r["node"]["value"] for r in depth1]
    assert "apt28" in values1 and "relay-node-1" in values1
    assert "bad.example" not in values1

    depth2 = graph.traverse("actor", "apt28", max_depth=2)
    values2 = [r["node"]["value"] for r in depth2]
    assert "bad.example" in values2
    assert len(depth2) == 3  # 环预防：每个节点只访问一次
    # 路径结构：bad.example 的 path 应经 relay-node-1
    c_entry = next(r for r in depth2 if r["node"]["value"] == "bad.example")
    assert c_entry["depth"] == 2
    assert c_entry["path"][0]["via"] == "relay-node-1"


def test_timeline_sorted_by_ts(graph: IntelGraph):
    """乱序入库，时间线按 ts 升序返回，且支持 [start,end] 过滤。"""
    g = graph
    a = g.add_node("indicator", "BG5GXO")
    f1 = g.add_node("infra", "freq-40m")
    f2 = g.add_node("infra", "freq-20m")
    g.add_edge(a, f1, "observed_at", ts="2026-08-02T09:00:00")
    g.add_edge(a, f2, "observed_at", ts="2026-08-01T08:00:00")
    g.add_edge(a, f1, "observed_at", ts="2026-08-03T07:00:00")
    tl = g.get_entity_timeline("indicator", "BG5GXO")
    assert [t["ts"] for t in tl] == sorted(t["ts"] for t in tl)
    assert len(tl) == 3 and tl[0]["peer_value"] == "freq-20m"
    # 时间窗过滤
    window = g.get_entity_timeline("indicator", "BG5GXO",
                                   start="2026-08-02T00:00:00",
                                   end="2026-08-03T00:00:00")
    assert [t["ts"] for t in window] == ["2026-08-02T09:00:00"]


# ------------------------------------------- 9 主断言：BG5GXO 两频段归并

def test_bg5gxo_bands_merge_same_canonical(graph: IntelGraph):
    """工单验收断言：BG5GXO@20m 与 BG5GXO@40m 归并到同一 canonical_id。"""
    # 场景一：同呼号不同频段观测（同实体幂等 + 不同 observed_at 边）
    callsign = graph.add_node("indicator", "BG5GXO",
                              props={"band": "20m"}, ts="2026-08-01T08:00:00")
    again = graph.add_node("indicator", "BG5GXO",
                           props={"band": "40m"}, ts="2026-08-02T09:00:00")
    assert callsign == again  # 同实体
    ent = graph.get_node("indicator", "BG5GXO")
    assert ent["canonical_id"] == ent["id"]

    # 场景二：别名变形输入（"BG5GXO/QRP" 呼号变体）经 alias_of 归并到同一画像
    variant_id = graph.add_alias("indicator", "BG5GXO/QRP", "indicator", "BG5GXO")
    variant = graph.get_node("indicator", "BG5GXO/QRP")
    assert variant["canonical_id"] == variant_id == ent["canonical_id"]
    # resolve 三级回退（图路）也归并到同一 canonical（返回存储值，仅大小写归一）
    assert graph.resolver.resolve("indicator", "BG5GXO/QRP") == "bg5gxo"
    # 画像：canonical + 两成员（本呼号 + 变体，连字符/斜杠保留原貌）
    profile = graph.get_profile("indicator", "BG5GXO")
    assert profile["canonical_id"] == ent["canonical_id"]
    assert {m["value"] for m in profile["members"]} == {"bg5gxo", "bg5gxo/qrp"}


# ------------------------------------------------- 10 MCP 桥画像查询

def test_bridge_intel_query_returns_profile(tmp_path: Path, monkeypatch):
    """bridge 三命令闭环：ingest → query 画像字段 → timeline。"""
    monkeypatch.setenv("SENTINEL_INTEL_DB", str(tmp_path / "intel.db"))
    reset_graph()
    try:
        bridge = IntelBridge()

        ing = asyncio.run(bridge.handle_handoff({
            "tool_name": "intel_ingest",
            "entities": [
                {"etype": "actor", "value": "apt28"},
                {"etype": "indicator", "value": "BG5GXO",
                 "props": {"band": "20m"}},
            ],
            "edges": [
                {"src": {"etype": "indicator", "value": "BG5GXO"},
                 "dst": {"etype": "actor", "value": "apt28"},
                 "rel": "indicates", "ts": "2026-08-01T08:00:00"},
            ]}))
        assert json.loads(ing)["status"] == "ok"
        assert json.loads(ing)["result"]["total_entities"] == 2

        # 幂等：重复 ingest 不重复建
        ing2 = asyncio.run(bridge.handle_handoff({
            "tool_name": "intel_ingest",
            "entities": [{"etype": "actor", "value": "apt28"}],
            "edges": []}))
        assert json.loads(ing2)["result"]["total_entities"] == 2

        # 画像查询（含归并解析 + 成员 + 出边 + 时间线字段）
        q = json.loads(asyncio.run(bridge.handle_handoff({
            "tool_name": "intel_query", "value": "BG5GXO",
            "etype": "indicator"})))
        assert q["status"] == "ok"
        profile = q["result"]
        for field in ("canonical_id", "canonical_value", "members",
                      "edges", "timeline", "resolved_from", "resolved_to"):
            assert field in profile, f"画像缺字段 {field}"
        assert profile["resolved_from"] == "BG5GXO"
        assert any(e["rel"] == "indicates" for e in profile["edges"])

        # 时间线命令
        tl = json.loads(asyncio.run(bridge.handle_handoff({
            "tool_name": "intel_timeline", "etype": "indicator",
            "value": "BG5GXO"})))
        assert tl["status"] == "ok" and len(tl["result"]["timeline"]) == 1

        # 未知工具 fail-fast
        bad = asyncio.run(bridge.handle_handoff({"tool_name": "intel_fly"}))
        assert json.loads(bad)["status"] == "error"
    finally:
        reset_graph()
