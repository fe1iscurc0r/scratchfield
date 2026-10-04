"""W59-03 MM-Spectrum 多模态光谱推断原型测试（pytest，≥4 用例）。

运行：python -m pytest tools/test_mm_spectrum.py -v
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
from mm_spectrum import (
    N_FRAGMENTS,
    concat_features,
    fragment_probabilities,
    make_dataset,
)


def _train_test():
    X_ir, X_nmr, X_uv, Y = make_dataset(seed=0)
    idx = np.random.default_rng(1).permutation(len(Y))
    tr, te = idx[: int(len(idx) * 0.7)], idx[int(len(idx) * 0.7):]
    return X_ir, X_nmr, X_uv, Y, tr, te


def test_dataset_shapes():
    X_ir, X_nmr, X_uv, Y = _train_test()[:4]
    assert X_ir.shape[1] == X_nmr.shape[1] == X_uv.shape[1] == 4
    assert Y.shape[1] == N_FRAGMENTS


def test_fragment_probabilities_in_01():
    X_ir, X_nmr, X_uv, Y, tr, te = _train_test()
    X = concat_features(X_ir, X_nmr, X_uv)
    probs, _ = fragment_probabilities(X, Y, tr, te)
    assert np.all(probs >= 0.0) and np.all(probs <= 1.0)


def test_fused_accuracy_high():
    X_ir, X_nmr, X_uv, Y, tr, te = _train_test()
    X = concat_features(X_ir, X_nmr, X_uv)
    _, acc = fragment_probabilities(X, Y, tr, te)
    assert acc > 0.8, f"融合片段准确率过低: {acc:.3f}"


def test_fused_beats_single_modality():
    X_ir, X_nmr, X_uv, Y, tr, te = _train_test()
    acc_single = []
    for X in (X_ir, X_nmr, X_uv):
        _, a = fragment_probabilities(X, Y, tr, te)
        acc_single.append(a)
    X_fused = concat_features(X_ir, X_nmr, X_uv)
    _, acc_fused = fragment_probabilities(X_fused, Y, tr, te)
    assert acc_fused > max(acc_single), \
        f"融合({acc_fused:.3f})未优于最优单模态({max(acc_single):.3f})"
