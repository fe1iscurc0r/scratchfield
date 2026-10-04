"""R43 验收测试：信息熵频谱压缩采样（压缩 ≥5× 时关键信号检测率 ≥90%）。

运行：python -m pytest tools/test_spectrum_entropy_sampler.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
from spectrum_entropy_sampler import (
    adaptive_keep,
    band_info_scores,
    compress,
    retention_curve,
)

BAND_SIZE = 32
N_BANDS = 64
N_BINS = BAND_SIZE * N_BANDS
NOISE_DB = -100.0
SIGNAL_DB = -80.0  # +20 dB 窄带峰


def _synthetic_spectrum(seed: int = 0, signal_bands=(10, 25, 40, 55)):
    """噪声底 + 4 个窄带关键信号（确定性）。"""
    rng = np.random.default_rng(seed)
    psd = np.full(N_BINS, NOISE_DB, dtype=float)
    psd += rng.normal(0, 0.5, N_BINS)
    for b in signal_bands:
        c = b * BAND_SIZE + BAND_SIZE // 2
        # 高斯峰，落在该频段中心附近
        sigma = 3.0
        x = np.arange(N_BINS) - c
        psd += (SIGNAL_DB - NOISE_DB) * np.exp(-(x**2) / (2 * sigma**2))
    freqs = np.arange(N_BINS, dtype=float)
    return freqs, psd, list(signal_bands)


def test_flat_noise_band_has_near_zero_info():
    psd = np.full(N_BINS, NOISE_DB)  # 完全平坦
    scores = band_info_scores(psd, BAND_SIZE)
    assert scores.shape == (N_BANDS,)
    assert float(np.max(scores)) < 0.2  # 噪声频段信息量低


def test_signal_band_scores_higher_than_noise():
    freqs, psd, signals = _synthetic_spectrum()
    scores = band_info_scores(psd, BAND_SIZE)
    # 每个信号频段的分数应高于所有非信号频段
    noise = [i for i in range(N_BANDS) if i not in signals]
    for s in signals:
        assert scores[s] > float(np.max(scores[noise]))


def test_adaptive_keep_top_ratio():
    psd = np.full(N_BINS, NOISE_DB)
    psd[100:120] = SIGNAL_DB  # 落到 band 3
    mask = adaptive_keep(psd, BAND_SIZE, keep_ratio=0.1)
    assert mask.shape == (N_BANDS,)
    assert bool(mask[3])
    assert int(np.count_nonzero(mask)) >= 1


def test_compress_matches_roundtrip_and_ratio():
    freqs, psd, signals = _synthetic_spectrum()
    out = compress(freqs, psd, BAND_SIZE, keep_ratio=0.15)
    # 压缩率：原始频点数 / 保留频点数（0.15 → ≈6.67×）
    assert out.compression_ratio >= 5.0
    # 保留片段的频点总长与掩码一致
    kept_bins = sum(len(x) for x in out.kept_freqs)
    assert kept_bins == int(np.count_nonzero(out.keep_mask)) * BAND_SIZE


def test_acceptance_compression_5x_detection_90pct():
    """核心验收：≥5× 压缩时关键信号检测率 ≥90%。"""
    freqs, psd, signals = _synthetic_spectrum()
    out = compress(freqs, psd, BAND_SIZE, keep_ratio=0.15)
    assert out.compression_ratio >= 5.0
    kept = set(int(i) for i in out.kept_band_indices)
    hit = sum(1 for s in signals if s in kept)
    det = hit / len(signals)
    assert det >= 0.90, f"检测率 {det} 低于 90%"


def test_retention_curve_holds_at_5x_operating_point():
    freqs, psd, signals = _synthetic_spectrum()
    # 细粒度扫描（高保留→低保留），找到首个达到 ≥5× 压缩的工作点
    keep_ratios = np.arange(0.30, 0.03, -0.01)
    ratios, rets = retention_curve(psd, BAND_SIZE, signals, keep_ratios)
    assert ratios.shape == rets.shape and ratios.size > 0
    crossing = int(np.argmax(ratios >= 5.0))
    assert ratios[crossing] >= 5.0
    assert rets[crossing] >= 0.90, (
        f"压缩率 {ratios[crossing]}× 时保留率 {rets[crossing]} 低于 90%"
    )
    # 曲线应随压缩加深单调不增（保留率不随压缩变松而上升）
    assert np.all(np.diff(rets) <= 1e-9)


def test_bad_params_rejected():
    psd = np.full(N_BINS, NOISE_DB)
    try:
        adaptive_keep(psd, BAND_SIZE)  # 两者都没给
        raised = False
    except ValueError:
        raised = True
    assert raised
    try:
        adaptive_keep(psd, BAND_SIZE, keep_ratio=0.5, threshold=0.1)  # 都给
        raised = False
    except ValueError:
        raised = True
    assert raised
