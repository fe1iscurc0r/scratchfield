"""R75 验收测试：腕带 FMCW 雷达 + IMU 融合前端（110K MAC/帧，47% 能耗降低）。

运行：python -m pytest mcpserver/rf_brain/prototypes/test_wristband_radar_imu.py -q
"""
from __future__ import annotations

import numpy as np

from . import wristband_radar_imu as wri


def test_mac_budget_within_110k():
    # 典型配置：32 chirp × 256 样本，距离 FFT 64 点
    mac = wri.mac_budget(n_chirps=32, m_samples=256, n_range_fft=64)
    assert mac <= 110_000, f"MAC/帧 {mac} 超过 110K"


def test_fusion_gate_skips_idle_frames():
    rng = np.random.default_rng(0)
    idle_rd = wri.fmcw_range_doppler(rng.standard_normal((32, 256)) * 0.01)
    idle_imu = wri.imu_features(np.zeros((64, 3)))
    assert wri.fusion_gate(idle_rd, idle_imu) is False        # 无活动 → 跳过分类

    # 有目标：加入强目标回波（距离 bin 固定 + 慢时正弦），距离-多普勒图出现强峰
    t = np.arange(256)
    chirps = rng.standard_normal((32, 256)) * 0.01
    target = 8.0 * np.sin(2.0 * np.pi * 0.25 * np.arange(32))[:, None] * np.sin(2.0 * np.pi * 0.1 * t)[None, :]
    act_rd = wri.fmcw_range_doppler(chirps + target)
    assert wri.fusion_gate(act_rd, idle_imu) is True


def test_classifier_energy_reduction_47pct():
    # 确定性活动流：47% 帧无活动（空闲）
    n = 1000
    activity = np.ones(n, dtype=bool)
    activity[: int(n * 0.47)] = False
    r = wri.classifier_energy(activity)
    assert r["gated"] < r["always"]
    assert r["reduction"] >= 0.47, f"能耗降幅 {r['reduction']:.3f} 未达 47%"


def test_fmcw_range_doppler_shape():
    rng = np.random.default_rng(0)
    chirps = rng.standard_normal((32, 256))
    rd = wri.fmcw_range_doppler(chirps, n_range_fft=64)
    assert rd.shape == (32, 64)
