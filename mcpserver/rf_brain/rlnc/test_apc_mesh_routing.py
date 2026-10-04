"""R50 验收测试：APC-RLNC Mesh 弹性路由（分层网络编码 + 断电重同步）。

覆盖：
  1. delivery_probability：解析交付率边界 + 冗余单调性
  2. 弱链路（PER 30%）交付率较无编码提升 ≥50%（≥1.5×）
  3. Monte Carlo 与解析模型自洽
  4. HierarchicalMeshRouter：EWMA 聚类 → 冗余率映射（high/mid/low）
  5. 编码 → 丢块 → 增量解码往返（RLNC「任意 k 块可解」）
  6. 断电重同步：清解码缓冲 + epoch 保留 + 世代头重发恢复交付
  7. 帧兼容：系统式编码前 k 块 = 原始块（v1/v1.5 可直用）

运行：python -m pytest mcpserver/rf_brain/rlnc/test_apc_mesh_routing.py -q
"""
from __future__ import annotations

import numpy as np
import pytest

from . import apc_mesh_routing as amr


def _blocks(k: int, size: int = 8) -> list[bytes]:
    """k 个可区分的原始块。"""
    return [bytes([b, (i % 251) + 1]) + bytes(size - 2) for i, b in enumerate(range(k))]


# ============ 1. 解析交付率 ============


def test_delivery_probability_bounds_and_monotonic():
    for per in (0.0, 0.3, 0.7, 1.0):
        p0 = amr.delivery_probability(8, 0, per)
        p4 = amr.delivery_probability(8, 4, per)
        assert 0.0 <= p0 <= 1.0 and 0.0 <= p4 <= 1.0
        assert p4 >= p0  # 冗余越多交付率越高
    assert amr.delivery_probability(8, 0, 0.0) == 1.0  # 无丢包必然交付


def test_delivery_probability_rejects_bad_input():
    with pytest.raises(ValueError):
        amr.delivery_probability(0, 1, 0.3)
    with pytest.raises(ValueError):
        amr.delivery_probability(8, -1, 0.3)
    with pytest.raises(ValueError):
        amr.delivery_probability(8, 1, 1.5)


# ============ 2. 弱链路交付率提升 ≥50% ============


def test_rlnc_improves_delivery_over_50pct():
    """PER=30% 弱链路：分层 RLNC（factor=0.6）交付率较无编码提升 ≥50%（≥1.5×）。"""
    k, per = 10, 0.3
    r = amr.redundancy_for_class("low")  # 0.6 → r=6
    gain = amr.delivery_gain(k, per, int(np.floor(k * r)))
    assert gain >= 1.5, f"交付率增益 {gain:.2f}× 未达 1.5×"
    # 无编码基线在 PER=30% 下极低（(0.7)^10 ≈ 2.8%），编码后显著提升
    assert amr.delivery_probability(k, 0, per) < 0.05
    assert amr.delivery_probability(k, int(np.floor(k * r)), per) > 0.8


# ============ 3. Monte Carlo 与解析自洽 ============


def test_simulate_mesh_matches_analytic():
    k, per, factor = 8, 0.3, 0.6
    r = int(np.floor(k * factor))
    mc = amr.simulate_mesh(k, per, factor=factor, trials=20000, seed=1)
    analytic = amr.delivery_probability(k, r, per)
    assert abs(mc["coded"] - analytic) < 0.03
    assert abs(mc["uncoded"] - (1 - per) ** k) < 0.02
    assert mc["gain"] >= 1.5


# ============ 4. EWMA 聚类 → 冗余率映射 ============


def test_hierarchical_redundancy_by_class():
    router = amr.HierarchicalMeshRouter(k=10)
    # 初始可靠度 1.0 → high → 零冗余
    assert router.redundancy_for("peer") == 0.0
    # 1 次丢包：R=0.7 → mid → 0.3
    router.on_loss("peer")
    assert router.redundancy_for("peer") == 0.3
    # 2 次丢包：R=0.49 → low → 0.6
    router.on_loss("peer")
    assert router.redundancy_for("peer") == 0.6
    # 冗余块数 r = ⌊k×factor⌋
    assert router.redundancy_blocks_for("peer") == 6


# ============ 5. 编码 → 丢块 → 解码往返 ============


def test_router_encode_decode_roundtrip_after_loss():
    router = amr.HierarchicalMeshRouter(k=6, generation=1)
    original = _blocks(6)
    # 驱动该链路到 low 档（2 次丢包 → R=0.49）→ factor=0.6 → r=3
    router.on_loss("peer")
    router.on_loss("peer")
    assert router.redundancy_blocks_for("peer") == 3
    encoded = router.encode(original, "peer", seed=3)
    assert len(encoded) == 6 + 3

    # 丢 3 个系统块（模拟弱链路），剩 3 系统块 + 3 冗余块 = 6 块仍可解（任意 k 块）
    drop = {0, 1, 2}
    decoder = amr.RlncDecoder(6, generation=1)
    for i, blk in enumerate(encoded):
        if i not in drop:
            decoder.add_block(blk)
    assert decoder.rank == 6
    assert decoder.decode() == original


# ============ 6. 断电重同步 ============


def test_power_cycle_preserves_epoch_and_resync_recovers():
    router = amr.HierarchicalMeshRouter(k=4, generation=2)
    blocks = _blocks(4)
    for blk in router.encode(blocks, "peer", seed=1)[:3]:
        router.add_block(blk)
    assert router.rank() == 3  # 已缓冲 3 个线性无关块

    router.power_cycle()  # 断电：清易失解码缓冲
    assert router.rank() == 0
    assert router.epoch == 1  # RTC 保留 epoch

    req = router.resync_request()  # 唤醒即重同步：凭世代头请求重发
    assert req.generation == 2 and req.epoch == 1

    # 源端按世代头重发 → 全新世代块到达 → 解码恢复
    for blk in router.encode(blocks, "peer", seed=2):
        router.add_block(blk)
    assert router.decode() == blocks


# ============ 7. 帧兼容（系统式编码） ============


def test_systematic_blocks_are_backward_compatible():
    router = amr.HierarchicalMeshRouter(k=4, generation=0)
    original = _blocks(4)
    encoded = router.encode(original, "peer", seed=5)
    # 前 k 块 = 原始块（单位系数向量），旧 v1/v1.5 接收端可直用，冗余块忽略即可
    for i in range(4):
        assert encoded[i].data == original[i]
        assert list(encoded[i].coefficients) == [1 if j == i else 0 for j in range(4)]


def test_router_rejects_bad_k():
    with pytest.raises(ValueError):
        amr.HierarchicalMeshRouter(k=0)
