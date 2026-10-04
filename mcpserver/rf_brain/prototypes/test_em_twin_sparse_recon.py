"""R34 验收测试：电磁孪生稀疏重建原型。

覆盖：
  1. 采样掩码：比例正确
  2. 误差随采样率下降：10% 采样误差 < 1% 采样误差
  3. 重建有效：1% 采样重建误差远小于零重建基线
  4. 图拉普拉斯：对称且行和≈0（内部节点）

运行：python -m pytest mcpserver/rf_brain/prototypes/test_em_twin_sparse_recon.py -q
"""
from __future__ import annotations

import numpy as np
import pytest

from . import em_twin_sparse_recon as etr


@pytest.fixture(scope="module")
def setup():
    nx = ny = 32
    truth = etr.synthesize_spectrum_map(nx, ny, seed=0)
    L = etr.graph_laplacian(nx, ny)
    return nx, ny, truth, L


def test_sampling_mask_ratio(setup):
    nx, ny, truth, L = setup
    y, mask = etr.sample_sparse(truth, frac=0.01, seed=0)
    assert abs(mask.mean() - 0.01) < 0.005


def test_error_decreases_with_sampling(setup):
    nx, ny, truth, L = setup
    e1 = etr.rel_error(truth, etr.reconstruct(*etr.sample_sparse(truth, 0.01), L).reshape(ny, nx))
    e2 = etr.rel_error(truth, etr.reconstruct(*etr.sample_sparse(truth, 0.1), L).reshape(ny, nx))
    assert e2 < e1


def test_reconstruction_meaningful(setup):
    nx, ny, truth, L = setup
    y, mask = etr.sample_sparse(truth, 0.01)
    pred = etr.reconstruct(y, mask, L).reshape(ny, nx)
    # 重建误差远小于「全零」基线（相对误差 1.0）
    assert etr.rel_error(truth, pred) < 0.9


def test_laplacian_structure(setup):
    nx, ny, truth, L = setup
    assert np.allclose(L, L.T)  # 对称
    # 内部节点行和 ≈ 0（度平衡）
    interior = L[~np.isclose(L.sum(axis=1), 0, atol=1e-9)]
    assert np.allclose(interior.sum(axis=1), 0, atol=1e-6)
