"""W58-05 验收测试：群体协同频谱感知模拟（≥4 用例）。

运行：python -m pytest tools/test_swarm_collab_sensing.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from swarm_collab_sensing import simulate_collab_sensing


def test_collab_beats_best_single_low_snr():
    """低 SNR 区：协作融合检测率 > 单节点最佳。"""
    res = simulate_collab_sensing(n_nodes=10, snr_db=-10.0, n_trials=5000, seed=0)
    assert res["collab_rate"] > res["best_single_rate"]


def test_collab_beats_mean_single():
    """协作融合检测率 > 单节点平均。"""
    res = simulate_collab_sensing(n_nodes=10, snr_db=-10.0, n_trials=5000, seed=0)
    assert res["collab_rate"] > res["mean_single_rate"]


def test_more_nodes_higher_collab_rate():
    """节点越多，协作检测率越高（多节点降噪）。"""
    few = simulate_collab_sensing(n_nodes=3, snr_db=-10.0, n_trials=5000, seed=0)
    many = simulate_collab_sensing(n_nodes=30, snr_db=-10.0, n_trials=5000, seed=0)
    assert many["collab_rate"] > few["collab_rate"]


def test_higher_snr_higher_detection():
    """SNR 越高，单节点与协作检测率都越高。"""
    low = simulate_collab_sensing(n_nodes=10, snr_db=-15.0, n_trials=3000, seed=0)
    high = simulate_collab_sensing(n_nodes=10, snr_db=-5.0, n_trials=3000, seed=0)
    assert high["collab_rate"] > low["collab_rate"]
    assert high["best_single_rate"] > low["best_single_rate"]


def test_rates_within_unit_interval():
    """检测率在 [0,1] 内。"""
    res = simulate_collab_sensing(n_nodes=10, snr_db=-10.0, n_trials=1000, seed=0)
    assert 0.0 <= res["collab_rate"] <= 1.0
    assert 0.0 <= res["best_single_rate"] <= 1.0
