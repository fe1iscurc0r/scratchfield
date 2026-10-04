"""W71-05 卫星链路预算测试。"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from sat_link_budget import (
    doppler_shift,
    free_space_loss,
    received_power,
    snr_db,
)


def test_doppler_sign():
    f = 100e6
    # 逼近（v>0）→ 正频移；远离（v<0）→ 负频移
    assert doppler_shift(f, 3000.0) > 0
    assert doppler_shift(f, -3000.0) < 0
    # 数值正确性
    assert abs(doppler_shift(100e6, 3e5) - 100e3) < 1.0   # v=c/1000 → 100kHz


def test_path_loss_increases_with_distance():
    f = 1e9
    assert free_space_loss(1000.0, f) < free_space_loss(10000.0, f)


def test_received_power_budget():
    rx = received_power(tx_dbm=10, tx_gain_db=3, rx_gain_db=5,
                        distance_m=1000.0, freq_hz=1e9)
    # 手算：L = 20log10(4π·1e3·1e9/3e8) ≈ 92.44 dB；P_r = 10+3+5-92.44 ≈ -74.44 dBm
    assert abs(rx - (-74.44)) < 0.5


def test_snr():
    assert snr_db(-70.0, -100.0) == 30.0
