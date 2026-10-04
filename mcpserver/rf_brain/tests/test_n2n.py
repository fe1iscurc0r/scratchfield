"""D-01 验收测试：Noise2Noise 自监督盲去噪（≥6 用例）。

覆盖：
  1. 合成信号生成（正弦/扫频/脉冲，有限值、非零能量）
  2. 噪声类型（高斯/椒盐/射频包络）均能产生独立带噪观测
  3. 无标签训练对正确（y1/y2 同长、均偏离 clean、互不相同）
  4. 训练收敛（loss 下降）
  5. 去噪后 SNR 提升
  6. 噪声类型鲁棒（椒盐/射频包络去噪后 SNR 仍提升）
  7. 参数规模 < 100K
  8. 坏输入容错（空/过短/维度错/长度不一致）

运行：python -m pytest mcpserver/rf_brain/tests/test_n2n.py -q
"""
from __future__ import annotations

import numpy as np
import pytest

from mcpserver.rf_brain.denoise import eval as ev
from mcpserver.rf_brain.denoise import n2n, synthetic

SR = 1000.0
N = 2048


# ---------- 合成信号 / 噪声 ----------

def test_synthetic_signal_types_finite() -> None:
    """正弦/扫频/脉冲均生成有限值、非零能量的干净信号。"""
    for stype in ("sine", "sweep", "pulse"):
        x = synthetic.make_signal(stype, N, SR)
        assert x.size == N
        assert np.all(np.isfinite(x))
        assert float(np.std(x)) > 0.0


def test_synthetic_noise_types_corrupt_signal() -> None:
    """三种噪声都让信号偏离干净值，且返回有限值。"""
    clean = synthetic.make_signal("sine", N, SR)
    for ntype in ("gaussian", "salt_pepper", "rf_envelope"):
        noisy = synthetic.apply_noise(clean, ntype, seed=1)
        assert noisy.shape == clean.shape
        assert np.all(np.isfinite(noisy))
        assert not np.allclose(noisy, clean)


def test_synthetic_pair_independent_and_same_length() -> None:
    """无标签训练对：y1/y2 同长、均偏离 clean、且互不相同（独立噪声）。"""
    d = synthetic.generate("sine", "gaussian", N, SR,
                           noise_params={"sigma": 0.3}, seed=0)
    assert d["noisy1"].shape == d["noisy2"].shape == d["clean"].shape
    assert not np.allclose(d["noisy1"], d["clean"])
    assert not np.allclose(d["noisy2"], d["clean"])
    assert not np.allclose(d["noisy1"], d["noisy2"])


def test_synthetic_bad_type_raises() -> None:
    """未知信号/噪声类型抛 ValueError。"""
    with pytest.raises(ValueError):
        synthetic.make_signal("bogus", N, SR)
    with pytest.raises(ValueError):
        synthetic.apply_noise(np.ones(16), "bogus")


# ---------- 训练 / 去噪 ----------

def _train_sine_gaussian(seed: int = 0):
    d = synthetic.generate("sine", "gaussian", N, SR,
                           noise_params={"sigma": 0.3}, seed=seed)
    model = n2n.N2NDenoiser(window=15, hidden=(48, 48), seed=seed)
    history = model.train(d["noisy1"], d["noisy2"], epochs=40)
    return d, model, history


def test_training_converges() -> None:
    """训练收敛：末期 loss 显著低于初期（且逼近噪声底 ≈ sigma²）。"""
    _, _, history = _train_sine_gaussian()
    assert len(history) == 40
    assert history[-1] < history[0] * 0.8   # 相对下降 ≥ 20%
    assert history[-1] < history[0]         # 整体下降
    assert history[-1] < 0.15               # 逼近噪声底（sigma=0.3 → 0.09）


def test_denoise_improves_snr() -> None:
    """去噪后 SNR 高于带噪 baseline。"""
    d, model, _ = _train_sine_gaussian()
    denoised = model.denoise(d["noisy1"])
    gain = ev.snr_gain(d["clean"], d["noisy1"], denoised)
    assert gain["snr_out_db"] > gain["snr_in_db"]
    assert gain["gain_db"] > 0.0


def test_robust_to_salt_pepper_and_rf_envelope() -> None:
    """噪声类型鲁棒：椒盐/射频包络噪声下，去噪后 SNR 仍提升。"""
    for ntype, params in (("salt_pepper", {"density": 0.08, "amplitude": 1.5}),
                          ("rf_envelope", {"sigma": 0.3})):
        d = synthetic.generate("sine", ntype, N, SR, noise_params=params, seed=3)
        model = n2n.N2NDenoiser(window=15, hidden=(48, 48), seed=3)
        model.train(d["noisy1"], d["noisy2"], epochs=40)
        denoised = model.denoise(d["noisy1"])
        gain = ev.snr_gain(d["clean"], d["noisy1"], denoised)
        assert gain["gain_db"] > 0.0, f"{ntype} 去噪后 SNR 未提升"


def test_parameter_count_under_100k() -> None:
    """小模型：参数量 < 100K（为 MCU 移植留余地）。"""
    model = n2n.N2NDenoiser(window=15, hidden=(48, 48))
    assert model.parameter_count() < 100_000


def test_bad_input_tolerance() -> None:
    """坏输入容错：空/过短原样返回，维度错与长度不一致抛 ValueError。"""
    d, model, _ = _train_sine_gaussian()
    assert model.denoise(np.zeros(0)).size == 0
    short = np.array([1.0, 2.0, 3.0])
    assert np.allclose(model.denoise(short), short)  # 短于窗口原样返回
    with pytest.raises(ValueError):
        model.denoise(np.zeros((2, 100)))
    with pytest.raises(ValueError):
        model.train(d["noisy1"], d["noisy1"][:-1], epochs=2)
    with pytest.raises(ValueError):
        n2n.N2NDenoiser(window=8)  # 偶数窗口
