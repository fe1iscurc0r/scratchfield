"""R67 最小原型测试：多速率 SSM 处理脉冲密度调制（PDM）。

覆盖：
  1. PDM 调制往返：Σ-Δ 调制 → SSM 解码，与原始信号正相关
  2. 多速率抽取：输出长度 = 输入 / ratio
  3. SSM 滤波抽取优于朴素 boxcar 平均（重建 SNR 更高）
  4. 坏参数拒绝

运行：python -m pytest mcpserver/rf_brain/prototypes/test_multirate_ssm.py -q
"""
from __future__ import annotations

import numpy as np
import pytest

from . import multirate_ssm as ms


def _signal(n: int = 4096) -> np.ndarray:
    return 0.5 * np.sin(2.0 * np.pi * 0.02 * np.arange(n))


def test_pdm_roundtrip_recovers_signal():
    """PDM 调制 → SSM 解码恢复原始信号（正相关）。"""
    sig = _signal()
    bits = ms.pdm_modulate(sig, seed=0)
    ratio = 16
    recon = ms.MultirateSSM(ratio=ratio).process(bits)
    ref = sig[: len(recon) * ratio: ratio]
    corr = float(np.corrcoef(recon, ref)[0, 1])
    assert corr > 0.5, f"重建相关系数 {corr:.3f} 过低"


def test_multirate_decimation_length():
    sig = _signal(2048)
    bits = ms.pdm_modulate(sig, seed=0)
    ratio = 16
    out = ms.MultirateSSM(ratio=ratio).process(bits)
    assert out.size == bits.size // ratio


def test_ssm_beats_naive_boxcar():
    """SSM 滤波抽取的重建 SNR 高于朴素 boxcar 平均。"""
    sig = _signal()
    bits = ms.pdm_modulate(sig, seed=0)
    ratio = 16
    naive = ms.naive_decimate(bits, ratio)
    ssm = ms.MultirateSSM(ratio=ratio).process(bits)
    ref = sig[: len(naive) * ratio: ratio]
    assert ms.recon_snr_db(ssm, ref) > ms.recon_snr_db(naive, ref)


def test_rejects_bad_ratio():
    with pytest.raises(ValueError):
        ms.MultirateSSM(ratio=0)
