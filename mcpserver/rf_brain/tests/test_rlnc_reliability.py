"""APC-RLNC C-01 · 链路可靠度 EWMA + 动态聚类测试。

覆盖：EWMA 更新公式 / 丢包率收敛 / α 可配 / 滑动窗口 / 三档聚类 / 阈值迁移 /
空邻居表 / 重分组幂等 / PeerState 上报查询。
"""
from __future__ import annotations

from mcpserver.rf_brain.rlnc import (
    EWMAReliability,
    LossWindow,
    PeerState,
    ReliabilityClusterer,
)

# ---------- EWMA ----------

def test_ewma_update_math() -> None:
    """EWMA 更新公式：α=0.5, init=1.0 → 连续两次丢包后 1.0→0.5→0.25。"""
    e = EWMAReliability(alpha=0.5, init_reliability=1.0)
    assert e.update_ewma(0.0) == 0.5
    assert e.update_ewma(0.0) == 0.25
    assert e.reliability == 0.25
    assert e.samples == 2
    assert e.lost_count == 2


def test_ewma_loss_rate_converges() -> None:
    """连续丢包 → 可靠度趋近 0 / 丢包率趋近 1；连续成功 → 趋近 1。"""
    e = EWMAReliability(alpha=0.5)
    for _ in range(10):
        e.on_loss()
    assert e.reliability < 0.01
    assert e.loss_rate > 0.99

    e2 = EWMAReliability(alpha=0.5, init_reliability=0.0)
    for _ in range(10):
        e2.on_success()
    assert e2.reliability > 0.99


def test_ewma_alpha_configurable() -> None:
    """α 越大对新样本越敏感：同样一次丢包，α=0.8 比 α=0.1 掉得更快。"""
    fast = EWMAReliability(alpha=0.8).on_loss()
    slow = EWMAReliability(alpha=0.1).on_loss()
    assert fast < slow


def test_loss_window_bounded() -> None:
    """滑动窗口只统计最近 window 个样本，窗口外样本自动淘汰。"""
    w = LossWindow(window=4)
    for _ in range(3):
        w.add(False)  # 3 连丢
    w.add(True)
    assert len(w) == 4
    assert abs(w.loss_rate - 0.75) < 1e-9
    for _ in range(4):
        w.add(True)  # 填满成功，旧丢包被淘汰
    assert w.loss_rate == 0.0


# ---------- 聚类 ----------

def test_cluster_three_tiers() -> None:
    """阈值三档：≥0.8 high，[0.5,0.8) mid，<0.5 low。"""
    c = ReliabilityClusterer()
    assert c.classify(0.9) == "high"
    assert c.classify(0.8) == "high"
    assert c.classify(0.7) == "mid"
    assert c.classify(0.5) == "mid"
    assert c.classify(0.49) == "low"
    assert c.classify(0.0) == "low"


def test_cluster_threshold_migration() -> None:
    """同一邻居随可靠度下降 high→mid→low（每轮重分组跟随链路质量）。"""
    c = ReliabilityClusterer()
    assert c.cluster({"A": 0.95}) == {"A": "high"}
    assert c.cluster({"A": 0.6}) == {"A": "mid"}
    assert c.cluster({"A": 0.2}) == {"A": "low"}


def test_empty_neighbor_table() -> None:
    """空邻居表：cluster 返回空，PeerState 查询回退默认（high/零冗余）。"""
    c = ReliabilityClusterer()
    assert c.cluster({}) == {}
    ps = PeerState()
    assert ps.cluster_all() == {}
    assert ps.get_peer_class("UNKNOWN") == "high"
    assert ps.get_redundancy_factor("UNKNOWN") == 0.0
    assert ps.query("UNKNOWN")["samples"] == 0


def test_regroup_idempotent() -> None:
    """同一可靠度表重复聚类结果一致（幂等）。"""
    c = ReliabilityClusterer()
    table = {"A": 0.9, "B": 0.6, "C": 0.1}
    assert c.cluster(table) == c.cluster(table)


def test_peer_state_report_and_query() -> None:
    """PeerState 上报收包/丢包 → 查询可靠度/档位/冗余率/样本数。"""
    ps = PeerState(alpha=0.5)
    ps.report_success("B")
    ps.report_success("B")
    ps.report_loss("B")
    # α=0.5：1.0 →(成功) 1.0 →(成功) 1.0 →(丢包) 0.5 → mid（0.5>=0.5）
    assert ps.get_reliability("B") == 0.5
    q = ps.query("B")
    assert q["samples"] == 3
    assert q["lost_count"] == 1
    assert q["class"] == "mid"
    assert q["redundancy_factor"] == 0.3
    assert ps.get_redundancy_factor("B") == 0.3
