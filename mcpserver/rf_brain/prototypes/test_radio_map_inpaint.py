"""R27 验收测试：边缘无线电地图修复原型。

覆盖：
  1. 稀疏采样：掩码比例正确
  2. 扩散修复：重建误差低于双线性基线
  3. 数据一致性：已测像素值被保留
  4. 采样密度：采样越密重建误差越低

运行：python -m pytest mcpserver/rf_brain/prototypes/test_radio_map_inpaint.py -q
"""
from __future__ import annotations

import numpy as np
import pytest

from . import radio_map_inpaint as rmi


@pytest.fixture(scope="module")
def truth():
    return rmi.synthesize_radio_map(64, 64, seed=0)


def test_sparse_sampling_mask(truth):
    sampled, mask = rmi.sample_sparse(truth, frac=0.1, seed=0)
    assert abs(mask.mean() - 0.1) < 0.02
    assert np.allclose(sampled[~mask], 0.0)


def test_diffusion_beats_bilinear(truth):
    sampled, mask = rmi.sample_sparse(truth, frac=0.05, seed=0)
    bil = rmi.inpaint_bilinear(sampled, mask)
    dif = rmi.inpaint_diffusion(sampled, mask)
    assert rmi.mse(truth, dif) < rmi.mse(truth, bil)


def test_data_consistency(truth):
    sampled, mask = rmi.sample_sparse(truth, frac=0.05, seed=0)
    dif = rmi.inpaint_diffusion(sampled, mask)
    assert np.allclose(dif[mask], sampled[mask], atol=1e-6)  # 已测像素被拉回


def test_more_samples_lower_error(truth):
    s1, m1 = rmi.sample_sparse(truth, frac=0.03, seed=0)
    s2, m2 = rmi.sample_sparse(truth, frac=0.2, seed=0)
    e1 = rmi.mse(truth, rmi.inpaint_diffusion(s1, m1))
    e2 = rmi.mse(truth, rmi.inpaint_diffusion(s2, m2))
    assert e2 < e1
