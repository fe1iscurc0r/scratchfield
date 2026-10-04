"""PF063 授粉落地验证：时窗自监督盲去噪（N2N）+ MCU 友好漂移补偿（Reservoir/RLS）

授粉点：cs.EE 2608.xxx Noise2Noise 盲去噪 / reservoir 漂移补偿 → rf_brain denoise 链路。
验收：真实信号（合成调制 IQ + 加噪/加漂移）上，补偿/去噪后 MSE 显著下降；
     全链路 _apply_denoise 三种模式(off/static/reservoir)行为正确、异常降级不崩。
"""
from __future__ import annotations

import numpy as np
import pytest

from mcpserver.rf_brain import feature_extractor as fe
from mcpserver.rf_brain.denoise.drift import DriftCompensator, simulate_drift
from mcpserver.rf_brain.denoise.n2n import N2NDenoiser
from mcpserver.rf_brain.denoise.reservoir import Reservoir


def _clean_signal(n: int = 1200, seed: int = 0) -> np.ndarray:
    """确定性多频干净信号（类频谱指纹激励）。

    注意：时间轴用原始样本索引（不归一化），保证信号频率远高于
    ``drift._slow_baseline`` 的慢变基线（0.5/0.25 周期），基线才能被
    reservoir 读出层外推补偿——归一化会把信号压得比基线还慢，补偿失效。
    """
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    return (np.sin(2 * np.pi * 0.05 * t) + 0.4 * np.sin(2 * np.pi * 0.13 * t)
            + 0.2 * np.sin(2 * np.pi * 0.31 * t + 1.0))


class TestReservoirDriftCompensation:
    """Reservoir 读出层漂移补偿（offset/gain/baseline 全模式）。"""

    @pytest.fixture(scope="class")
    def trained(self):
        clean = _clean_signal()
        drifted, _ = simulate_drift(
            clean, mode="offset_gain_baseline",
            offset=0.4, gain=1.15, baseline_amplitude=0.3, seed=1)
        rc = Reservoir(n_units=64, seed=0)
        comp = DriftCompensator(rc)
        comp.fit(drifted[:600], clean[:600])
        return clean, drifted, comp

    def test_drift_reduces_mse(self, trained):
        clean, drifted, comp = trained
        recon = comp.compensate(drifted)
        mse_before = float(np.mean((drifted - clean) ** 2))
        mse_after = float(np.mean((recon - clean) ** 2))
        assert mse_after < mse_before * 0.05, \
            f"漂移补偿未达标: {mse_before:.4f} -> {mse_after:.4f}"

    def test_rls_update_stable(self, trained):
        clean, drifted, comp = trained
        # 在线更新后再补偿，不应劣化
        comp.update(drifted[600:700], clean[600:700])
        recon = comp.compensate(drifted)
        mse_after = float(np.mean((recon - clean) ** 2))
        assert mse_after < 0.01, f"RLS 更新后 MSE 偏高: {mse_after:.4f}"

    def test_offset_only_mode(self):
        clean = _clean_signal(n=800)
        drifted, _ = simulate_drift(clean, mode="offset", offset=0.5, seed=2)
        comp = DriftCompensator(Reservoir(n_units=32, seed=0))
        comp.fit(drifted[:400], clean[:400])
        recon = comp.compensate(drifted)
        assert float(np.mean((recon - clean) ** 2)) < 0.005


class TestN2NDenoising:
    """N2N 盲去噪：两次独立带噪观测互为目标训练。"""

    @pytest.fixture(scope="class")
    def trained(self):
        clean = _clean_signal()
        rng = np.random.default_rng(3)
        y1 = clean + rng.standard_normal(clean.size) * 0.5
        y2 = clean + rng.standard_normal(clean.size) * 0.5
        n2n = N2NDenoiser(window=15, hidden=(32, 32), seed=0)
        history = n2n.train(y1, y2, epochs=30, batch_size=128)
        return clean, y1, n2n, history

    def test_params_under_budget(self, trained):
        _, _, n2n, _ = trained
        assert n2n.parameter_count() < 100_000, "验收硬约束: 参数 < 100K"

    def test_loss_decreases(self, trained):
        _, _, _, history = trained
        assert history[-1] < history[0], "训练损失应下降"
        assert history[-1] < 0.35

    def test_denoise_reduces_mse(self, trained):
        clean, y1, n2n, _ = trained
        out = n2n.denoise(y1)
        mse_in = float(np.mean((y1 - clean) ** 2))
        mse_out = float(np.mean((out - clean) ** 2))
        assert mse_out < mse_in * 0.7, \
            f"N2N 未有效去噪: {mse_in:.4f} -> {mse_out:.4f}"

    def test_edge_short_input(self):
        n2n = N2NDenoiser()
        short = np.array([1.0, 2.0, 3.0])
        assert np.array_equal(n2n.denoise(short), short), "过短输入应原样返回"


class TestFullDenoiseChain:
    """feature_extractor._apply_denoise 全链路（IQ 复信号三种模式）。"""

    def _iq(self, n: int = 800, seed: int = 7):
        rng = np.random.default_rng(seed)
        t = np.arange(n)
        sig = np.exp(1j * 2 * np.pi * 0.05 * t)
        noise = (rng.standard_normal(n) + 1j * rng.standard_normal(n)) * 0.4
        return sig + noise

    def test_off_mode_identity(self):
        iq = self._iq()
        out, mode = fe._apply_denoise(iq, "off", None, None)
        assert mode == "off"
        assert np.array_equal(out, iq)

    def test_static_mode_shape_and_complex(self):
        iq = self._iq()
        out, mode = fe._apply_denoise(iq, "static", None, None)
        assert mode == "static"
        assert out.shape == iq.shape
        assert np.iscomplexobj(out), "复信号去噪后仍应为复数(I/Q)"

    def test_reservoir_mode_runs(self):
        iq = self._iq()
        out, mode = fe._apply_denoise(iq, "reservoir", None, None)
        assert mode == "reservoir"
        assert out.shape == iq.shape

    def test_unknown_mode_degrades(self):
        iq = self._iq()
        out, mode = fe._apply_denoise(iq, "bogus", None, None)
        assert mode == "off"
        assert np.array_equal(out, iq)

    def test_bad_input_no_crash(self):
        # 非数组/空输入应安全降级或原样返回，不抛异常
        out, mode = fe._apply_denoise(np.zeros(0), "static", None, None)
        assert out.shape == (0,)
