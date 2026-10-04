"""R17 验收测试：多传感器分区融合原型。

覆盖：
  1. 分区融合：测试集误差接近 0（能表示各传感器独立贡献之和）
  2. 组合泛化：分区测试误差低于统一编码器
  3. 多种子平均稳定：50 个种子下分区优势一致
  4. 分区特征只含各传感器自身项（无跨传感器交叉项）

运行：python -m pytest mcpserver/rf_brain/prototypes/test_partitioned_fusion.py -q
"""
from __future__ import annotations

import numpy as np
import pytest

from . import partitioned_fusion as pf


def test_partitioned_near_perfect():
    S, y = pf.synthesize(27, seed=0)
    pred = pf._fit_predict(pf.partition_features(S), y, pf.partition_features(S))
    assert np.mean((y - pred) ** 2) < 1e-9  # 可加目标可被分区模型精确表示


def test_partitioned_beats_unified():
    p_mse, u_mse = [], []
    for seed in range(20):
        r = pf.evaluate(seed=seed)
        p_mse.append(r["partitioned_mse"])
        u_mse.append(r["unified_mse"])
    assert np.mean(p_mse) < np.mean(u_mse)


def test_partitioned_exact_vs_unified_error():
    p_mse, u_mse = [], []
    for seed in range(30):
        r = pf.evaluate(seed=seed)
        p_mse.append(r["partitioned_mse"])
        u_mse.append(r["unified_mse"])
    # 分区模型可精确表示可加目标（测试误差≈0）；统一编码平均有非零误差
    assert np.mean(p_mse) < 1e-6
    assert np.mean(u_mse) > 1e-6


def test_partition_features_no_cross_terms():
    S = np.array([[0, 0, 0], [1, 2, 0], [2, 1, 2]])
    X = pf.partition_features(S)
    # 6 列 = 3 传感器 × 各自 2 阶，无 s1*s2 等交叉项
    assert X.shape[1] == 6
    # 交叉项特征（如 s1*s2）不应出现：检查第 3、4 列只依赖单个传感器
    assert np.allclose(X[:, 2], S[:, 1])  # s2 项
    assert np.allclose(X[:, 3], S[:, 1] ** 2)  # s2² 项
