"""W71-08 软 LoRa PHY 测试。"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
from soft_lora_phy import demodulate, generate_symbol


def test_round_trip_all_symbols():
    sf, bw = 6, 125e3
    for s in range(2 ** sf):
        assert demodulate(generate_symbol(s, sf, bw), sf, bw) == s


def test_symbol_distinct():
    sf, bw = 7, 125e3
    sigs = [generate_symbol(s, sf, bw) for s in (10, 11, 12)]
    # 不同符号的 chirp 互不相同
    assert not np.allclose(sigs[0], sigs[1])
    assert not np.allclose(sigs[1], sigs[2])


def test_unit_energy():
    sf, bw = 7, 125e3
    sig = generate_symbol(42, sf, bw)
    assert abs(np.mean(np.abs(sig) ** 2) - 1.0) < 1e-12


def test_noise_robust():
    sf, bw = 7, 125e3
    rng = np.random.default_rng(0)
    for s in (0, 63, 127):
        sig = generate_symbol(s, sf, bw) + rng.normal(0, 0.2, size=2 ** sf) * (1 + 1j) / np.sqrt(2)
        assert demodulate(sig, sf, bw) == s
