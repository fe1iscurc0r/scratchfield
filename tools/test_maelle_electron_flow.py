"""M29 机械反应预测（离散流匹配）原型测试（pytest）。

运行：python -m pytest tools/test_maelle_electron_flow.py -q
验收：合成反应数据集产物预测准确率 ≥70%（全向量精确匹配口径）。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import numpy as np
from maelle_electron_flow import (
    ElectronFlowMLP,
    full_match,
    make_dataset,
)


def test_product_prediction_ge_70():
    R, P = make_dataset(seed=0)
    idx = np.random.default_rng(1).permutation(len(R))
    tr, te = idx[: int(len(idx) * 0.7)], idx[int(len(idx) * 0.7):]

    model = ElectronFlowMLP(seed=0).train(R[tr], P[tr].astype(float))
    pred = model.predict(R[te])
    acc = full_match(pred, P[te])
    assert acc >= 0.70, f"产物全向量预测准确率过低: {acc:.3f}"


def test_flow_sample_agrees_with_argmax():
    R, P = make_dataset(seed=0)
    model = ElectronFlowMLP(seed=0).train(R, P.astype(float))
    # 流采样是从「均匀源 → 产物」概率路径的生成式采样，其位级输出应与
    # argmax 预测在绝大多数位点一致（目标分布高度置信时一致性 ≈ 置信度）。
    agree = 0.0
    n = 30
    for i in range(n):
        s = model.flow_sample(R[i], T=30)
        argmax = model.predict(R[i].reshape(1, -1))[0]
        agree += float(np.mean(s == argmax))
    agree /= n
    assert agree >= 0.8, f"流采样与 argmax 一致性过低: {agree:.3f}"
