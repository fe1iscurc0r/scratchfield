"""M34 FM+LoRA 边缘部署 最小原型测试（pytest）。

运行：python -m pytest tools/test_biomass_fm_lora.py -q
验收：LoRA 微调（少量可训练参数）精度接近全量微调，且远高于零样本；参数更省。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
from biomass_fm_lora import (
    D_FEAT,
    N_CLASSES,
    accuracy,
    loRA_param_count,
    make_dataset,
    rank_ablation,
    train_full_head,
    train_lora_head,
)


def test_lora_close_to_full_and_beats_zero_shot():
    X, y = make_dataset(seed=0)
    idx = np.random.default_rng(1).permutation(len(y))
    tr, te = idx[: int(len(idx) * 0.7)], idx[int(len(idx) * 0.7):]

    rng = np.random.default_rng(99)
    W0_zero = rng.normal(0.0, 0.02, size=(N_CLASSES, D_FEAT))
    acc_zero = accuracy(X[te] @ W0_zero.T, y[te])

    W0 = train_full_head(X[tr], y[tr])
    acc_full = accuracy(X[te] @ W0.T, y[te])

    B, A = train_lora_head(X[tr], y[tr], W0_zero, r=4)
    acc_lora = accuracy(X[te] @ (W0_zero + B @ A).T, y[te])

    # LoRA 远高于零样本，且接近全量微调（允许小幅差距）
    assert acc_lora > acc_zero + 0.5, f"LoRA({acc_lora:.3f})未显著高于零样本({acc_zero:.3f})"
    assert acc_lora >= acc_full - 0.10, f"LoRA({acc_lora:.3f})显著落后全量({acc_full:.3f})"


def test_lora_params_much_fewer_than_full():
    full = N_CLASSES * D_FEAT
    lora = loRA_param_count(4)
    assert lora < full, f"LoRA 参数({lora})未少于全量({full})"
    assert full / lora >= 1.5, f"LoRA 参数节省不足: {full / lora:.2f}×"


def test_rank_ablation_params_monotonic_and_accurate():
    X, y = make_dataset(seed=0)
    idx = np.random.default_rng(1).permutation(len(y))
    tr, te = idx[: int(len(idx) * 0.7)], idx[int(len(idx) * 0.7):]
    rng = np.random.default_rng(99)
    W0 = rng.normal(0.0, 0.02, size=(N_CLASSES, D_FEAT))

    res = rank_ablation(X[tr], y[tr], X[te], y[te], W0, ranks=(2, 4, 8, 16))
    # 参数量随 rank 单调递增
    params = [p for _, p, _ in res]
    assert params == sorted(params), f"参数量未随 rank 递增: {params}"
    # 各 rank 下精度都显著高于随机（1/8 = 0.125）
    for r, p, a in res:
        assert a > 0.5, f"rank={r} 精度过低: {a:.3f}"
