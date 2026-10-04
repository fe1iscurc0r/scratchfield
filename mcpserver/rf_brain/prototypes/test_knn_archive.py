"""R35 验收测试：kNN 存档反演原型。

覆盖：
  1. 建库：存档尺寸正确（N×d 特征 + N 标签）
  2. 查表：干净特征高准确率（≥95%）
  3. 鲁棒：含噪特征仍高于随机（K 类基线 1/K）
  4. 成本：内存/周期估算随 N×d 线性增长

运行：python -m pytest mcpserver/rf_brain/prototypes/test_knn_archive.py -q
"""
from __future__ import annotations

import numpy as np
import pytest

from . import knn_archive as knn


@pytest.fixture(scope="module")
def data():
    N, K, d = 200, 4, 8
    archive, labels = knn.synthesize_archive(N // K, K, d, seed=0)
    return archive, labels, K, d


def test_archive_size(data):
    archive, labels, K, d = data
    assert archive.shape == (200, d)
    assert labels.size == 200


def test_lookup_clean_accuracy(data):
    archive, labels, K, d = data
    acc = knn.classification_accuracy(500, archive, labels, K, d, noise=0.0)
    assert acc >= 0.95


def test_lookup_noisy_above_chance(data):
    archive, labels, K, d = data
    acc = knn.classification_accuracy(500, archive, labels, K, d, noise=0.3)
    assert acc > 1 / K


def test_cost_scales_linearly(data):
    c_small = knn.cost_estimate(100, 8)
    c_large = knn.cost_estimate(400, 8)
    assert c_large["macs_per_query"] == 4 * c_small["macs_per_query"]
    assert c_large["memory_bytes_int8"] > c_small["memory_bytes_int8"]
