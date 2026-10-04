"""M28 MM-Spectrum 多模态光谱→结构 原型测试（pytest）。

运行：python -m pytest tools/test_mm_spectrum_fusion.py -q
验收：合成光谱数据集结构推断准确率 ≥70%；且三模态融合优于任一单模态。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
from mm_spectrum_fusion import (
    N_CLASSES,
    SoftmaxClassifier,
    concat_features,
    make_dataset,
)


def _train_test():
    X_ir, X_ms, X_nmr, y = make_dataset(seed=0)
    idx = np.random.default_rng(1).permutation(len(y))
    tr, te = idx[: int(len(idx) * 0.7)], idx[int(len(idx) * 0.7):]
    return X_ir, X_ms, X_nmr, y, tr, te


def test_fused_accuracy_ge_70():
    X_ir, X_ms, X_nmr, y, tr, te = _train_test()
    X_fused = concat_features(X_ir, X_ms, X_nmr)
    clf = SoftmaxClassifier(X_fused.shape[1], N_CLASSES, seed=0).fit(X_fused[tr], y[tr])
    acc = clf.accuracy(X_fused[te], y[te])
    assert acc >= 0.70, f"融合准确率过低: {acc:.3f}"


def test_fusion_beats_single_modality():
    X_ir, X_ms, X_nmr, y, tr, te = _train_test()
    single = []
    for X in (X_ir, X_ms, X_nmr):
        clf = SoftmaxClassifier(X.shape[1], N_CLASSES, seed=0).fit(X[tr], y[tr])
        single.append(clf.accuracy(X[te], y[te]))
    X_fused = concat_features(X_ir, X_ms, X_nmr)
    clf = SoftmaxClassifier(X_fused.shape[1], N_CLASSES, seed=0).fit(X_fused[tr], y[tr])
    fused = clf.accuracy(X_fused[te], y[te])
    # 融合应优于最优单模态（证明多模态互补而非冗余）
    assert fused >= max(single), f"融合({fused:.3f})未优于最优单模态({max(single):.3f})"
