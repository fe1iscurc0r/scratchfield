"""S18 验收测试：LVQMark 时序水印（编辑攻击后检出率 ≥80%，数据质量影响 ≤5%）。

运行：python -m pytest mcpserver/rf_brain/test_ts_watermark.py -q
"""
from __future__ import annotations

import numpy as np

from .ts_watermark import (
    correlation,
    detect,
    edit_add_noise,
    edit_crop,
    edit_perturb,
    embed,
    quality_impact,
)

KEY = "rf_brain/spectrum/secret-2026"
N = 4096


def _spectrum(seed: int) -> np.ndarray:
    """合成一帧频谱（含结构 + 噪声，模拟 rf_brain 传感数据）。"""
    rng = np.random.default_rng(seed)
    t = np.arange(N)
    base = 3.0 * np.sin(2 * np.pi * 7 * t / N) + 2.0 * np.sin(2 * np.pi * 51 * t / N)
    return base + rng.normal(0.0, 1.0, N)


def test_quality_impact_within_5pct():
    s = _spectrum(0)
    w = embed(s, KEY)
    assert quality_impact(s, w) <= 0.05


def test_detect_present_and_absent():
    s = _spectrum(1)
    w = embed(s, KEY)
    assert detect(w, KEY) is True
    assert detect(s, KEY) is False  # 未嵌入不应误报


def _attacks():
    # 统一 (series, seed) -> edited 的调用接口（crop 无需 seed）
    return [
        ("noise", edit_add_noise),
        ("perturb", edit_perturb),
        ("crop", lambda s, seed=0: edit_crop(s)),
    ]


def test_detection_under_edits_at_least_80pct():
    """三类编辑攻击各跑 20 帧，检出率 ≥80%。"""
    for name, attack in _attacks():
        hits = 0
        for seed in range(20):
            w = embed(_spectrum(seed), KEY)
            w_edited = attack(w, seed=seed)
            hits += int(detect(w_edited, KEY))
        assert hits / 20 >= 0.8, f"{name} 检出率 {hits}/20 低于 80%"


def test_unwatermarked_low_false_positive_under_edits():
    """未嵌入数据即使被编辑也不应误报。"""
    fp = 0
    for seed in range(20):
        s = _spectrum(seed)
        for _, attack in _attacks():
            fp += int(detect(attack(s, seed=seed), KEY))
    assert fp == 0


def test_crop_aligns_chip_by_position():
    """截断后仍按位置对齐码序列 → 相关性保持。"""
    w = embed(_spectrum(2), KEY)
    cropped = edit_crop(w, frac=0.6)
    assert correlation(cropped, KEY) > 0.01
    assert detect(cropped, KEY) is True
