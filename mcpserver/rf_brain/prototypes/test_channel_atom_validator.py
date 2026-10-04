"""R09 验收测试：信道字典原子验证器。

覆盖：
  1. 物理诊断：物理原子的延迟扩展小于白噪声伪影
  2. 共享物理响应排序：物理原子得分高于伪影
  3. top-k 精度：top-20（=物理原子数）里物理原子占多数
  4. 伪影筛选：用阈值可把物理原子与伪影分开

运行：python -m pytest mcpserver/rf_brain/prototypes/test_channel_atom_validator.py -q
"""
from __future__ import annotations

import numpy as np
import pytest

from . import channel_atom_validator as cav


@pytest.fixture(scope="module")
def data():
    atoms, labels = cav.synthesize_dictionary(20, 40, 64, seed=0)
    anchor = cav.shared_physics_anchor(atoms)
    return atoms, labels, anchor


def test_delay_spread_physical_smaller(data):
    atoms, labels, _ = data
    d_phys = np.mean([cav.delay_spread(a) for a, l in zip(atoms, labels) if l])
    d_art = np.mean([cav.delay_spread(a) for a, l in zip(atoms, labels) if not l])
    assert d_phys < d_art


def test_physical_score_higher(data):
    atoms, labels, anchor = data
    s_phys = np.mean([cav.physical_score(a, anchor) for a, l in zip(atoms, labels) if l])
    s_art = np.mean([cav.physical_score(a, anchor) for a, l in zip(atoms, labels) if not l])
    assert s_phys > s_art


def test_top_k_precision(data):
    atoms, labels, anchor = data
    order = cav.rank_atoms(atoms, anchor)
    assert cav.top_k_precision(order, labels, 20) >= 0.8


def test_artifact_filtering(data):
    atoms, labels, anchor = data
    scores = np.array([cav.physical_score(a, anchor) for a in atoms])
    thr = np.median(scores)
    pred_phys = scores >= thr
    # 阈值筛出的"物理"原子里，真物理占多数（精度 > 伪影误入率）
    tp = (pred_phys & labels).sum()
    fp = (pred_phys & ~labels).sum()
    assert tp > fp
