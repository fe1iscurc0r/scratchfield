"""PF029 授粉落地验收测试：可变形匹配滤波 x 可解释 DSP → SDR 自校准接收链。

覆盖：
  1. CFO 平方律估计：多种 CFO 下估计误差小（可解释状态描述符）
  2. 自校准有效性：CFO 失配下符号错误率/EVM 显著改善
  3. 无失配基线：不校准也能正确解调（低噪声）
  4. 幅度失配不破坏判决（BPSK 幅度不敏感）
  5. EVM 计算正确性
  6. 容错：空输入/短输入不崩
"""
from __future__ import annotations

import numpy as np
import pytest

from mcpserver.rf_brain.deformable_mf import (
    derotate_symbols,
    estimate_cfo_bpsk,
    estimate_snr,
    evm_db,
    matched_filter_demod,
    matched_filter_soft,
    synthesize_mismatch,
)

SPS = 16
N_SYM = 64


class TestCFOEstimation:
    """状态描述符：平方律 CFO 估计（可解释、确定性）。"""

    @pytest.mark.parametrize("cfo", [0.0, 0.02, 0.05, 0.1, -0.03])
    def test_estimate_close(self, cfo):
        iq, _, _ = synthesize_mismatch(N_SYM, SPS, cfo=cfo, noise=0.0, seed=0)
        est = estimate_cfo_bpsk(iq, SPS)
        assert abs(est - cfo) < 0.01, f"CFO 估计偏差过大: est={est:.4f} true={cfo}"

    def test_noisy_estimate_still_usable(self):
        iq, _, _ = synthesize_mismatch(N_SYM, SPS, cfo=0.05, noise=0.1, seed=1)
        est = estimate_cfo_bpsk(iq, SPS)
        assert abs(est - 0.05) < 0.02

    def test_short_input(self):
        assert estimate_cfo_bpsk(np.zeros(4), SPS) == 0.0


class TestSelfCalibration:
    """低维修正有效性（论文指标：失配下 EVM/误码显著下降）。"""

    def test_cfo_mismatch_improves_ber(self):
        iq, bits, ref = synthesize_mismatch(N_SYM, SPS, cfo=0.05, noise=0.15,
                                            seed=0)
        rx_plain = matched_filter_demod(iq, ref, N_SYM, SPS, self_calibrate=False)
        rx_cal = matched_filter_demod(iq, ref, N_SYM, SPS, self_calibrate=True)
        n = min(rx_plain.size, rx_cal.size, bits.size)
        ber_plain = float(np.mean(rx_plain[:n] != bits[:n]))
        ber_cal = float(np.mean(rx_cal[:n] != bits[:n]))
        assert ber_cal < ber_plain, \
            f"自校准未改善误码: {ber_plain:.3f} -> {ber_cal:.3f}"
        assert ber_cal < 0.05, f"自校准后误码仍过高: {ber_cal:.3f}"

    def test_cfo_mismatch_improves_evm(self):
        iq, bits, ref = synthesize_mismatch(N_SYM, SPS, cfo=0.05, noise=0.1,
                                            seed=2)
        soft_plain = matched_filter_soft(iq, ref, N_SYM, SPS,
                                         self_calibrate=False)
        soft_cal = matched_filter_soft(iq, ref, N_SYM, SPS, self_calibrate=True)
        n = min(soft_plain.size, soft_cal.size, bits.size)
        # 幅度归一化后再算 EVM（匹配滤波输出是符号能量倍数）
        norm = float(np.mean(np.abs(soft_cal[:n]))) + 1e-12
        ideal = bits[:n].astype(float) * norm
        evm_plain = evm_db(ideal, np.real(soft_plain[:n]))
        evm_cal = evm_db(ideal, np.real(soft_cal[:n]))
        assert evm_cal < evm_plain - 3.0, \
            f"EVM 未显著改善: {evm_plain:.1f}dB -> {evm_cal:.1f}dB"

    def test_no_mismatch_still_works(self):
        iq, bits, ref = synthesize_mismatch(N_SYM, SPS, cfo=0.0, noise=0.05,
                                            seed=3)
        rx = matched_filter_demod(iq, ref, N_SYM, SPS, self_calibrate=True)
        n = min(rx.size, bits.size)
        assert float(np.mean(rx[:n] != bits[:n])) < 0.02

    def test_amplitude_mismatch_ok(self):
        # BPSK 幅度不敏感：即使幅度失配 0.5 倍仍能解调
        iq, bits, ref = synthesize_mismatch(N_SYM, SPS, cfo=0.02,
                                            amplitude_mismatch=0.5, noise=0.1,
                                            seed=4)
        rx = matched_filter_demod(iq, ref, N_SYM, SPS, self_calibrate=True)
        n = min(rx.size, bits.size)
        assert float(np.mean(rx[:n] != bits[:n])) < 0.05


class TestTools:
    def test_derotate_pure_tone(self):
        sps = 16
        cfo = 0.05
        n = 64
        t = np.arange(n * sps)
        sig = np.exp(1j * 2 * np.pi * cfo * t / sps)
        # 平方去调制 + 去旋转 → 相位应基本恒定
        syms = sig[::sps]
        derot = derotate_symbols(syms, cfo, sps, start_offset=0)
        assert np.std(np.angle(derot)) < 0.2

    def test_evm(self):
        ideal = np.array([1.0, -1.0, 1.0])
        assert evm_db(ideal, ideal) < -40.0
        # 10% 幅度误差 ≈ 20log10(0.1) = -20dB
        assert -30.0 < evm_db(ideal, ideal * 1.1) < -10.0
        assert evm_db(np.array([]), np.array([])) == float("inf")

    def test_snr_high_no_noise(self):
        iq, _, ref = synthesize_mismatch(N_SYM, SPS, cfo=0.0, noise=0.0, seed=0)
        assert estimate_snr(iq, ref) > 20.0

    def test_empty_input(self):
        assert estimate_snr(np.zeros(0), np.zeros(8)) == 0.0
        assert estimate_cfo_bpsk(np.zeros(0), SPS) == 0.0
