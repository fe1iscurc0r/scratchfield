"""R63 验收测试：协议感知特征缓存（PASK 结构感知 → SDR 特征分级缓存）。

覆盖：
  1. demod_importance：协议关键 bin 即使低能量也获高重要性（结构先验）
  2. ProtocolAwareCache：按重要性保留 top-K；关键特征保留率
  3. 缓存减量 ≥50% 时关键特征保留率 ≥90%（且优于朴素随机缓存）
  4. 坏参数拒绝

运行：python -m pytest mcpserver/rf_brain/test_protocol_aware_cache.py -q
"""
from __future__ import annotations

import numpy as np
import pytest

from . import protocol_aware_cache as pac


def _synthetic_spectrum(n: int = 200, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """合成谱：若干强噪声峰（高能量、非协议）+ 一组低能量协议关键 bin。"""
    rng = np.random.default_rng(seed)
    power = np.ones(n) * 1.0                                  # 底噪
    # 强噪声峰（高能量但无协议语义）
    for _ in range(12):
        power[int(rng.integers(0, n))] = rng.uniform(20, 200)
    # 协议关键 bin：低能量（导频/前导/同步字，被噪声淹没）
    protocol_bins = np.arange(40, 60)                          # 20 个关键 bin
    power[protocol_bins] = 2.0
    return power, protocol_bins


def test_demod_importance_prioritizes_protocol_bins():
    power, pb = _synthetic_spectrum()
    imp = pac.demod_importance(power, protocol_bins=pb)
    # 协议 bin 即使低能量也获高重要性（结构先验保底）
    assert float(imp[pb].min()) >= 0.9
    # 噪声峰（高能量、非协议）重要性不高于 1.0
    assert float(imp.max()) <= 1.0 + 1e-9


def test_cache_retention_above_90pct_at_50pct_reduction():
    """缓存减量 ≥50%（容量=一半）时关键特征保留率 ≥90%。"""
    power, pb = _synthetic_spectrum()
    imp = pac.demod_importance(power, protocol_bins=pb)
    capacity = power.size // 2  # 50% 减量
    cache = pac.ProtocolAwareCache(capacity).store(imp)
    crit = np.zeros(power.size, dtype=bool)
    crit[pb] = True
    retention = pac.ProtocolAwareCache(capacity)
    retention.indices = cache
    assert retention.retention(crit) >= 0.90


def test_aware_beats_naive():
    """协议感知缓存保留率高于朴素随机缓存（结构感知的价值）。"""
    power, pb = _synthetic_spectrum()
    r = pac.run_cache_tradeoff(power, pb, capacities=[power.size // 2], seed=0)
    assert r.aware_retention[0] > r.naive_retention[0]


def test_rejects_bad_input():
    with pytest.raises(ValueError):
        pac.ProtocolAwareCache(-1)
    with pytest.raises(ValueError):
        pac.demod_importance(np.zeros(0))
