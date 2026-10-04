"""R18 验收测试：SX1278 物理层指纹原型。

覆盖：
  1. 特征提取：频偏估计接近注入值
  2. 稳定性：同设备多次采集特征散布小（类内距离小）
  3. 判别力：类间距离远大于类内距离
  4. 识别准确率：近邻识别 ≥ 95%

运行：python -m pytest mcpserver/rf_brain/prototypes/test_sx1278_fingerprint.py -q
"""
from __future__ import annotations

import numpy as np
import pytest

from . import sx1278_fingerprint as sf


def test_frequency_offset_estimate():
    p = np.array([12.0, 1.0, 0.0])  # 注入 12 Hz 频偏
    sig = sf.transmit(p, 8192, seed=0)
    feats = sf.extract_features(sig)
    assert feats[0] == pytest.approx(12.0, abs=1.0)


def test_intra_device_stability():
    params = sf.synthesize_device_params(6, seed=0)
    intra = []
    for d in range(6):
        feats = [sf.extract_features(sf.transmit(params[d], 8192, seed=100 + d + r))
                 for r in range(10)]
        c = np.mean(feats, axis=0)
        intra.append(np.mean([np.linalg.norm(f - c) for f in feats]))
    assert np.mean(intra) < 0.1  # 类内散布小


def test_inter_device_discriminability():
    params = sf.synthesize_device_params(6, seed=0)
    tmpl = []
    for d in range(6):
        feats = [sf.extract_features(sf.transmit(params[d], 8192, seed=100 + d + r))
                 for r in range(5)]
        tmpl.append(np.mean(feats, axis=0))
    tmpl = np.array(tmpl)
    inter = [np.linalg.norm(tmpl[a] - tmpl[b]) for a in range(6) for b in range(a + 1, 6)]
    assert np.mean(inter) > 1.0  # 类间距离大


def test_identification_accuracy():
    n = 8
    params = sf.synthesize_device_params(n, seed=0)
    templates, test_feats, test_labels = [], [], []
    for d in range(n):
        feats = [sf.extract_features(sf.transmit(params[d], 8192, seed=1000 + d + r))
                 for r in range(5)]
        templates.append(np.mean(feats, axis=0))
        for r in range(10):
            test_feats.append(sf.extract_features(sf.transmit(params[d], 8192, seed=2000 + d * 100 + r)))
            test_labels.append(d)
    templates = np.array(templates)
    acc = np.mean([sf.identify(f, templates) == l for f, l in zip(test_feats, test_labels)])
    assert acc >= 0.95
