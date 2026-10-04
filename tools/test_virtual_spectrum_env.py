"""R46 验收测试：虚拟频谱环境生成器（含干扰/空洞/跳变 + 标注完整）。

运行：python -m pytest tools/test_virtual_spectrum_env.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
from virtual_spectrum_env import VirtualSpectrumEnv, demo_env


def test_path_loss_increases_with_distance():
    env = VirtualSpectrumEnv(np.linspace(430e6, 440e6, 128))
    near = env.path_loss_db(100.0, 433e6, "free_space")
    far = env.path_loss_db(1000.0, 433e6, "free_space")
    assert far > near


def test_two_ray_steeper_than_free_space_at_range():
    env = VirtualSpectrumEnv(np.linspace(430e6, 440e6, 128))
    d = 3000.0
    fs = env.path_loss_db(d, 433e6, "free_space")
    tr = env.path_loss_db(d, 433e6, "two_ray")
    # 远场双线损耗应明显大于自由空间（更陡）
    assert tr > fs + 10.0


def test_dataset_contains_all_three_phenomena():
    env = demo_env(seed=0)
    frames = env.generate_dataset(30)
    labels = np.concatenate([f.labels for f in frames])
    assert "interference" in labels
    assert "hole" in labels
    assert "signal" in labels
    # 跳变：跳频信号源中心频率随帧变化
    hop = next(e for e in env.emitters if e.kind == "signal" and e.hop_pattern)
    centers = {hop.current_center(t) for t in range(3)}
    assert len(centers) > 1, "跳频信号源中心频率未随帧变化"


def test_labels_complete_and_valid():
    env = demo_env(seed=1)
    f = env.generate_frame(0)
    assert f.labels.shape == f.psd_dbm.shape == f.freqs_hz.shape
    valid = {"noise", "signal", "interference", "hole"}
    assert set(np.unique(f.labels)).issubset(valid)
    # 每个 bin 都有标注（无 None/空）
    assert not np.any(f.labels == None)  # noqa: E711


def test_psd_finite_and_above_noise_floor():
    env = demo_env(seed=2)
    f = env.generate_frame(0)
    assert np.all(np.isfinite(f.psd_dbm))
    assert float(np.min(f.psd_dbm)) >= env.noise_floor_dbm - 1.0


def test_signal_peak_above_interference_and_noise():
    env = demo_env(seed=3)
    f = env.generate_frame(0)
    # 432 MHz 固定信号处功率应显著高于噪声底
    idx = int(np.argmin(np.abs(f.freqs_hz - 432.0e6)))
    assert f.psd_dbm[idx] > env.noise_floor_dbm + 20.0
    assert f.labels[idx] == "signal"


def test_hop_changes_signal_location_across_frames():
    env = demo_env(seed=4)
    f0 = env.generate_frame(0)
    f1 = env.generate_frame(1)
    # 跳频信号所在的频点应随帧移动
    def signal_bins(fr):
        return set(np.flatnonzero(fr.labels == "signal").tolist())
    assert signal_bins(f0) != signal_bins(f1)


def test_reseed_reproduces_dataset():
    a = demo_env(seed=7)
    b = demo_env(seed=7)
    fa = a.generate_dataset(10)
    fb = b.generate_dataset(10)
    for x, y in zip(fa, fb):
        assert np.array_equal(x.psd_dbm, y.psd_dbm)
        assert np.array_equal(x.labels, y.labels)


def test_jammer_active_prob_controls_interference():
    freqs = np.linspace(430e6, 440e6, 512)
    def make(p):
        e = VirtualSpectrumEnv(freqs, noise_floor_dbm=-100.0, seed=1, jammer_active_prob=p)
        e.add_emitter("jammer", 433e6, 150e3, 20.0, distance_m=600.0)
        return e
    always = make(1.0).generate_dataset(20)
    never = make(0.0).generate_dataset(20)
    assert any(np.any(f.labels == "interference") for f in always)
    assert all(not np.any(f.labels == "interference") for f in never)
