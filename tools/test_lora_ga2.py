"""R92 验收测试：LoRA-GA² 梯度对齐初始化。"""
from __future__ import annotations

import numpy as np

from tools.lora_ga2 import alignment_score, gradient_alignment, init_lora_dw


def test_ga_init_aligns_with_gradient():
    rng = np.random.default_rng(0)
    G = rng.standard_normal((4, 8))                     # 真梯度
    grads = [G + 0.1 * rng.standard_normal((4, 8)) for _ in range(5)]  # 多步梯度（含噪声）
    A, B = gradient_alignment(grads, rank=3)
    dW = init_lora_dw(A, B)
    align = alignment_score(dW, G)
    assert align > 0.9                                   # GA init 与梯度主方向高度对齐


def test_ga_beats_random_init_alignment():
    rng = np.random.default_rng(0)
    G = rng.standard_normal((4, 8))
    A, B = gradient_alignment([G], rank=2)
    dW_ga = init_lora_dw(A, B)
    dW_rnd = rng.standard_normal((4, 2)) @ rng.standard_normal((2, 8)) * 0.01
    assert alignment_score(dW_ga, G) > alignment_score(dW_rnd, G)
