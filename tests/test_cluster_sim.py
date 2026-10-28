"""工单 243 任务一/三：节点空间分簇模拟器 + 弹性仪表盘的回归测试。

覆盖（对应工单 §3.1 的 ≥6 用例要求）：
拓扑生成与可复现 / RSSI 与路损口径 / 分簇确定性与覆盖性 / 簇头与跳数 /
健康度（含快照后退化的簇头失效分支）/ 不稳定链路判定与边界 /
YAML 配置解析与非法值拒绝 / 失活注入 / dashboard 三块图数据与 CLI 产出。

全部用例**完全确定性**（所有随机都吃显式 seed）⇒ 断言不依赖机器/时序。
"""
from __future__ import annotations

import json
import math

import pytest

from mcpserver.esp32 import dashboard
from mcpserver.esp32.cluster_sim import (
    DEFAULT_AREA,
    GRID,
    LORA_DEPLOYMENT,
    RANDOM,
    apply_failure,
    build_clusters,
    cluster_report,
    generate,
    load_config,
    normalize_config,
    simulate,
)
from mcpserver.esp32.cluster_sim.cluster import (
    DEFAULT_UNSTABLE_MARGIN_DB,
    Cluster,
    bfs_hops,
    rssi_links,
    unstable_pairs,
)
from mcpserver.esp32.cluster_sim.node import (
    free_space_path_loss_db,
    max_range_m,
    path_loss_db,
    rssi_dbm,
)

pytestmark = [pytest.mark.core]

AREA_M = 30000.0
THR = -110.0
SEED = 20261014


def _cfg(**over: object) -> dict:
    base: dict = {
        "nodes": 50,
        "area": [AREA_M, AREA_M],
        "rssi_threshold": THR,
        "topology": RANDOM,
        "seed": SEED,
    }
    base.update(over)
    return normalize_config(base)


# ---------------------------------------------------------------- 拓扑


def test_grid_topology_positions_inside_area() -> None:
    topo = generate(GRID, 20, width=1000.0, height=800.0)
    assert topo.size == 20
    assert {n.node_id for n in topo.nodes} == set(range(20))
    for node in topo.nodes:
        assert 0.0 <= node.x <= 1000.0
        assert 0.0 <= node.y <= 800.0


def test_random_topology_is_reproducible_and_seed_sensitive() -> None:
    a = generate(RANDOM, 30, width=AREA_M, height=AREA_M, seed=7)
    b = generate(RANDOM, 30, width=AREA_M, height=AREA_M, seed=7)
    c = generate(RANDOM, 30, width=AREA_M, height=AREA_M, seed=8)
    assert a.positions() == b.positions()
    assert a.positions() != c.positions()


def test_lora_deployment_puts_gateway_at_center() -> None:
    topo = generate(LORA_DEPLOYMENT, 25, width=AREA_M, height=AREA_M, seed=SEED)
    gateway = topo.nodes[0]
    assert gateway.node_id == 0
    assert gateway.position == (AREA_M / 2.0, AREA_M / 2.0)
    assert topo.size == 25


def test_unknown_topology_kind_raises() -> None:
    with pytest.raises(ValueError, match="未知拓扑类型"):
        generate("mesh", 10, width=100.0, height=100.0)


# ---------------------------------------------------------------- 路损 / RSSI


def test_path_loss_matches_free_space_when_exponent_is_two() -> None:
    for dist in (1.0, 10.0, 1000.0, 25000.0):
        assert path_loss_db(dist, exponent=2.0) == pytest.approx(
            free_space_path_loss_db(433.92e6, dist), abs=1e-9
        )


def test_path_loss_clamps_below_reference_distance() -> None:
    # d < 1 m 按 1 m 截断，避免近场公式把 RSSI 推到虚高的无穷大
    assert path_loss_db(0.01) == pytest.approx(path_loss_db(1.0), abs=1e-9)
    with pytest.raises(ValueError):
        path_loss_db(1.0, exponent=0.0)


def test_rssi_decreases_monotonically_with_distance() -> None:
    values = [rssi_dbm(d) for d in (10.0, 100.0, 1000.0, 5000.0, 30000.0)]
    assert all(a > b for a, b in zip(values, values[1:]))


def test_max_range_is_the_threshold_crossing() -> None:
    for thr in (-110.0, -120.0, -100.0):
        rng = max_range_m(thr)
        assert rssi_dbm(rng) == pytest.approx(thr, abs=1e-6)


def test_default_area_sits_below_connectivity_transition() -> None:
    """默认区域/阈值组合的量化依据 —— 「为什么是 30 km」必须可复核，不能拍脑袋。

    文档曾写「30 km 下平均度 ≈ 5.8，落在连通相变附近」，**实测是错的**：
    解析 `λπr² ≈ 3.64`、实测（10 seed）`≈ 3.06`，均在相变（约 4.5）**之下**。
    本用例把解析值与实测值一起钉住，防止再写出拍脑袋的数字。
    """
    r = max_range_m(THR)
    assert r == pytest.approx(4563.8, abs=1.0)  # 参考点路损 25.1982 dB @433.92 MHz
    nodes = 50.0
    analytic = (nodes / (AREA_M * AREA_M)) * math.pi * r**2
    assert analytic == pytest.approx(3.64, abs=0.05)
    assert analytic < 4.5, "相变之下才有多簇"

    # 实测平均度：无向链路数 ×2 / 节点数（含边界效应 ⇒ 低于解析值）
    measured = []
    for seed in range(20261010, 20261015):
        topo = generate(RANDOM, 50, width=AREA_M, height=AREA_M, seed=seed)
        measured.append(2 * len(rssi_links(topo.nodes, threshold_dbm=THR)) / 50)
    mean_measured = sum(measured) / len(measured)
    assert 2.5 < mean_measured < 4.0, measured
    assert mean_measured < analytic, "边界效应 ⇒ 实测必须低于解析值"
    assert mean_measured < 4.5, "实测也在相变之下"

    # 解析簇数上界 ≈ 13.8，与实测 12 簇同量级
    upper = (AREA_M * AREA_M) / (math.pi * r**2)
    assert upper == pytest.approx(13.75, abs=0.3)
    cfg = normalize_config({"nodes": 50, "area": [AREA_M, AREA_M],
                            "rssi_threshold": THR, "topology": RANDOM, "seed": SEED})
    cluster_count = simulate(cfg)["stats"]["cluster_count"]
    assert 0 < cluster_count <= math.ceil(upper)


# ---------------------------------------------------------------- 分簇


def test_cluster_report_covers_every_alive_node() -> None:
    for kind in (GRID, RANDOM, LORA_DEPLOYMENT):
        topo = generate(kind, 40, width=AREA_M, height=AREA_M, seed=SEED)
        apply_failure(topo.nodes, 0.25, seed=SEED)
        report = cluster_report(topo.nodes, threshold_dbm=THR)
        assert report["stats"]["uncovered_alive"] == []
        covered = {m for c in report["clusters"] for m in c["members"]}
        alive = {n.node_id for n in topo.nodes if n.alive}
        assert covered == alive


def test_clustering_is_deterministic() -> None:
    topo = generate(RANDOM, 50, width=AREA_M, height=AREA_M, seed=SEED)
    first = cluster_report(topo.nodes, threshold_dbm=THR)
    second = cluster_report(topo.nodes, threshold_dbm=THR)
    assert first == second


def test_cluster_head_is_member_and_its_hop_is_zero() -> None:
    topo = generate(RANDOM, 50, width=AREA_M, height=AREA_M, seed=SEED)
    clusters = build_clusters(topo.nodes, threshold_dbm=THR)
    assert clusters
    for cluster in clusters:
        assert cluster.head_id in cluster.members
        assert cluster.hops[cluster.head_id] == 0
        assert cluster.size == len(cluster.hops)
        assert set(cluster.members) == set(cluster.hops)


def test_max_hops_zero_yields_singletons() -> None:
    topo = generate(RANDOM, 20, width=AREA_M, height=AREA_M, seed=SEED)
    clusters = build_clusters(topo.nodes, threshold_dbm=THR, max_hops=0)
    assert all(c.size == 1 for c in clusters)
    assert len(clusters) == 20


def test_health_zero_when_head_dies_after_snapshot() -> None:
    """快照之后簇头失效 ⇒ 健康度 0（保守口径：本 PoC 没有簇头重选）。"""
    topo = generate(RANDOM, 50, width=AREA_M, height=AREA_M, seed=SEED)
    clusters = build_clusters(topo.nodes, threshold_dbm=THR)
    cluster = max(clusters, key=lambda c: c.size)
    assert cluster.health() > 0.0
    without_head = frozenset(cluster.alive_ids - {cluster.head_id})
    assert cluster.health(without_head) == 0.0
    # 只掉一个非簇头成员：健康度下降但不为 0
    lone_dead = frozenset(cluster.alive_ids - {next(m for m in cluster.members if m != cluster.head_id)})
    degraded = cluster.health(lone_dead)
    assert 0.0 < degraded < cluster.health()


def test_health_offset_and_invariants() -> None:
    cluster = Cluster(cluster_id=0, head_id=1, members=(1, 2, 3), hops={1: 0, 2: 1, 3: 1},
                      alive_ids=frozenset({1, 2, 3}), max_hops=2)
    assert cluster.health() == pytest.approx(1.0)
    assert cluster.mean_hops() == pytest.approx(2.0 / 3.0)
    # 全部失效 ⇒ 0；空簇 ⇒ 0（不抛异常）
    assert cluster.health(frozenset()) == 0.0
    assert Cluster(cluster_id=0, head_id=0, members=(), hops={}).health() == 0.0


# ---------------------------------------------------------------- 不稳定链路


def test_unstable_pairs_are_the_near_threshold_links() -> None:
    topo = generate(RANDOM, 50, width=AREA_M, height=AREA_M, seed=SEED)
    pairs = unstable_pairs(topo.nodes, threshold_dbm=THR)
    assert pairs
    for pair in pairs:
        assert pair["rssi_dbm"] >= THR
        assert pair["margin_db"] < DEFAULT_UNSTABLE_MARGIN_DB
        assert pair["a"] < pair["b"]
    # 稳定边（裕量 ≥ margin）一条都不该出现在结果里
    all_links = {  # noqa: SIM118 - dict 生成式即可读
        (lk.a, lk.b): lk.rssi_dbm for lk in rssi_links(topo.nodes, threshold_dbm=THR)
    }
    assert len(all_links) >= len(pairs)
    for (a, b), rssi in all_links.items():
        if rssi >= THR + DEFAULT_UNSTABLE_MARGIN_DB:
            assert (a, b) not in {(p["a"], p["b"]) for p in pairs}


def test_unstable_pairs_empty_at_zero_margin() -> None:
    topo = generate(RANDOM, 50, width=AREA_M, height=AREA_M, seed=SEED)
    assert unstable_pairs(topo.nodes, threshold_dbm=THR, margin_db=0.0) == []
    with pytest.raises(ValueError):
        unstable_pairs(topo.nodes, threshold_dbm=THR, margin_db=-1.0)


def test_bfs_hops_respects_max_hops_and_allowed_set() -> None:
    adj = {0: {1}, 1: {0, 2}, 2: {1, 3}, 3: {2}}
    assert bfs_hops(adj, 0) == {0: 0, 1: 1, 2: 2, 3: 3}
    assert bfs_hops(adj, 0, max_hops=1) == {0: 0, 1: 1}
    assert bfs_hops(adj, 0, allowed={0, 1, 2}) == {0: 0, 1: 1, 2: 2}
    assert bfs_hops(adj, 99) == {99: 0}


# ---------------------------------------------------------------- 配置


def test_example_yaml_loads_and_normalizes() -> None:
    cfg = load_config("mcpserver/esp32/cluster_sim/config.example.yaml")
    assert cfg["nodes"] == 50
    assert cfg["area"] == [AREA_M, AREA_M]
    assert cfg["rssi_threshold"] == THR
    assert cfg["simulate_duration"] == 1.0
    assert cfg["topology"] == RANDOM
    assert cfg["max_hops"] == 2
    assert set(cfg) == set(normalize_config({}))


def test_normalize_config_fills_defaults() -> None:
    cfg = normalize_config({})
    assert cfg["area"] == list(DEFAULT_AREA)
    assert cfg["nodes"] == 50
    assert cfg["failure_rate"] == 0.0


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        ({"nodes": 0}, "nodes 必须为正"),
        ({"nodes": True}, "必须是整数"),
        ({"area": [100.0]}, "必须是 \\[宽, 高\\]"),
        ({"area": [0.0, 100.0]}, "区域宽高必须为正"),
        ({"failure_rate": 1.5}, "failure_rate 必须在"),
        ({"simulate_duration": 0.0}, "simulate_duration 必须为正"),
        ({"max_hops": -1}, "max_hops 不能为负"),
        ({"topology": "mesh"}, "未知 topology"),
        ({"rssi_threshold": "low"}, "必须是数值"),
        ({"nonce": 1}, "未知配置项"),
    ],
)
def test_normalize_config_rejects_bad_values(raw: dict, reason: str) -> None:
    with pytest.raises(ValueError, match=reason):
        normalize_config(raw)


def test_apply_failure_count_and_reproducibility() -> None:
    a = generate(RANDOM, 50, width=AREA_M, height=AREA_M, seed=SEED)
    b = generate(RANDOM, 50, width=AREA_M, height=AREA_M, seed=SEED)
    assert apply_failure(a.nodes, 0.2, seed=5) == 10
    assert apply_failure(b.nodes, 0.2, seed=5) == 10
    dead_a = {n.node_id for n in a.nodes if not n.alive}
    dead_b = {n.node_id for n in b.nodes if not n.alive}
    assert dead_a == dead_b
    assert len(dead_a) == 10
    assert apply_failure(generate(RANDOM, 10, width=100.0, height=100.0, seed=1).nodes, 0.0) == 0
    with pytest.raises(ValueError):
        apply_failure(a.nodes, 2.0)


def test_simulate_records_duration_as_static_window() -> None:
    report = simulate(_cfg(simulate_duration=3.5, failure_rate=0.2))
    assert report["simulation"]["simulate_duration_h"] == 3.5
    assert report["simulation"]["deactivated"] == 10
    assert "静态快照" in report["simulation"]["note"]
    assert report["config"]["simulate_duration"] == 3.5
    assert set(report) >= {"clusters", "unstable_pairs", "stats", "topology", "simulation", "config"}


# ---------------------------------------------------------------- dashboard


def test_dashboard_resilience_curve_is_monotone() -> None:
    cfg = _cfg()
    curve = [
        dashboard.reconstruction_success_rate(cfg, failure_rate=rate, trials=40)
        for rate in dashboard.DEFAULT_FAILURE_LEVELS
    ]
    rates = [row["success_rate"] for row in curve]
    assert all(a >= b for a, b in zip(rates, rates[1:])), rates
    assert rates[0] > rates[-1]
    for row in curve:
        assert row["trials"] == 40
        assert 0.0 <= row["success_rate"] <= 1.0
        assert row["k"] == dashboard.DEFAULT_SOURCE_BLOCKS
        # 结局计数**含成功档 "ok"** ⇒ 必须能加总到 trials；
        # 字段曾名 failure_reasons，混入 ok 会让「各档相加当失败数」的读法出错，故锁住新名与不变量。
        counts = row["reason_counts"]
        assert "failure_reasons" not in row, "旧字段名会误导读者把 ok 当失败档"
        assert sum(counts.values()) == row["trials"], counts
        assert counts.get("ok", 0) == row["successes"], counts
        # success_rate 已 round(…, 6) ⇒ 反算只能容差比较，不能 round 回去（会偏 1）
        assert abs(row["successes"] / row["trials"] - row["success_rate"]) < 1e-5


def test_dashboard_cluster_scale_vs_hops_tradeoff() -> None:
    payload = dashboard.cluster_scale_vs_hops(_cfg(), hops=(1, 2, 3, 4), seed=SEED)
    rows = payload["rows"]
    sizes = [r["mean_cluster_size"] for r in rows]
    hops = [r["mean_hops"] for r in rows]
    counts = [r["cluster_count"] for r in rows]
    # 跳数放宽 ⇒ 簇更大、簇数更少，但平均中继跳数上升（这就是权衡本身）
    assert all(a <= b for a, b in zip(sizes, sizes[1:])), sizes
    assert all(a <= b for a, b in zip(hops, hops[1:])), hops
    assert all(a >= b for a, b in zip(counts, counts[1:])), counts


def test_dashboard_redundancy_sweep_is_monotone() -> None:
    payload = dashboard.rlnc_redundancy_sweep(_cfg(), failure_rate=0.2, trials=20, seed=SEED)
    rates = payload["success_rate"]
    assert all(a <= b for a, b in zip(rates, rates[1:])), rates
    assert payload["mean_blocks_sent"] == [
        dashboard.DEFAULT_SOURCE_BLOCKS + math.floor(f * dashboard.DEFAULT_SOURCE_BLOCKS)
        for f in payload["axis"]
    ]


def test_dashboard_default_baseline_matches_cli() -> None:
    """库默认（``build_dashboard()``）必须与 CLI 默认配置**逐项相同**。

    回归背景（实测发现）：曾直接用 ``cluster_sim.DEFAULT_CONFIG``（topology="grid"）当
    dashboard 默认 ⇒ 库调用出 21.7%、CLI 出 45.0%（同为「默认」却是两套数字）；
    且 grid 基线曲线在 5%→10% 系统性反弹（10 seed 仅 4 个单调）。
    """
    args = dashboard.build_parser().parse_args([])
    cli_cfg = normalize_config({
        "nodes": args.nodes,
        "area": list(args.area),
        "rssi_threshold": args.rssi_threshold,
        "topology": args.topology,
        "tx_power_dbm": args.tx_power,
        "seed": args.seed,
    })
    assert normalize_config(dashboard.DASHBOARD_BASELINE) == cli_cfg
    assert dashboard.build_dashboard(trials=6)["config"] == cli_cfg
    # 显式传 CLI 配置与不传（走基线）必须同结果
    assert dashboard.build_dashboard(trials=6) == dashboard.build_dashboard(cli_cfg, trials=6)


def test_dashboard_default_curve_is_monotone_and_decreasing() -> None:
    """默认基线下的曲线单调递减 —— 这是报告要引用的口径，必须锁住。"""
    payload = dashboard.build_dashboard(trials=40)
    rates = payload["resilience_curve"]["success_rate"]
    assert all(a >= b for a, b in zip(rates, rates[1:])), rates
    assert rates[0] > rates[-1], rates
    assert payload["config"]["topology"] == "random"


def test_dashboard_build_is_deterministic_and_has_all_panels() -> None:
    first = dashboard.build_dashboard(_cfg(), trials=12, focus_failure=0.2)
    second = dashboard.build_dashboard(_cfg(), trials=12, focus_failure=0.2)
    assert first == second
    assert set(first) == {"model", "config", "resilience_curve",
                          "cluster_scale_vs_hops", "rlnc_redundancy_sweep", "focus"}
    assert first["model"]["source_blocks_k"] == dashboard.DEFAULT_SOURCE_BLOCKS
    assert "s^h" in first["model"]["summary"]
    assert first["resilience_curve"]["axis"] == list(dashboard.DEFAULT_FAILURE_LEVELS)
    assert first["focus"]["failure_rate"] == 0.2


def test_dashboard_cli_writes_lf_json(tmp_path) -> None:
    out = tmp_path / "dashboard.json"
    code = dashboard.main([
        "--nodes", "50", "--failure", "0.2", "--trials", "8",
        "--output", str(out),
    ])
    assert code == 0
    raw = out.read_bytes()
    assert raw.count(b"\r\n") == 0, "dashboard.json 必须是 LF"
    payload = json.loads(raw.decode("utf-8"))
    assert len(payload["resilience_curve"]["success_rate"]) == 4
    assert payload["focus"]["trials"] == 8


def test_write_dashboard_creates_parent_dir(tmp_path) -> None:
    target = tmp_path / "nested" / "dir" / "d.json"
    path = dashboard.write_dashboard({"a": 1}, target)
    assert path.exists()
    assert path.read_bytes().count(b"\r\n") == 0
