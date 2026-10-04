"""R83 验收测试：LoRA 秩选择（rank-error bound）。"""
from __future__ import annotations

import numpy as np

from tools.lora_rank import low_rank_approx, rank_error_bound, select_rank


def test_rank_error_bound_recovers_true_rank():
    rng = np.random.default_rng(0)
    U = rng.standard_normal((12, 3))
    V = rng.standard_normal((12, 3))
    W = U @ V.T                     # 真秩 3
    assert rank_error_bound(W, 3) < 1e-10   # 秩 3 截断零误差
    assert rank_error_bound(W, 2) > 0.0     # 秩 2 有误差


def test_select_rank_meets_target():
    rng = np.random.default_rng(0)
    U = rng.standard_normal((12, 3))
    V = rng.standard_normal((12, 3))
    W = U @ V.T
    r = select_rank(W, target_error=1e-6)
    assert r == 3                      # 满足极小误差的最小秩 = 真秩
    assert rank_error_bound(W, r) <= 1e-6


def test_low_rank_approx_close():
    rng = np.random.default_rng(0)
    W = rng.standard_normal((10, 10))
    Wr = low_rank_approx(W, 4)
    assert Wr.shape == W.shape
    assert np.linalg.matrix_rank(Wr) <= 4
