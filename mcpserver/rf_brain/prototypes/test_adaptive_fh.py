"""R16 验收测试：自适应跳频策略模拟。

覆盖：
  1. 语义感知：L0/L1 送达率高于均匀跳频
  2. 语义感知：L2 与均匀跳频持平（不额外耗资源）
  3. 均匀跳频：L0/L1/L2 送达率一致（无区别对待）
  4. 语义分级：L0 > L1 > L2（重传次数递减）

运行：python -m pytest mcpserver/rf_brain/prototypes/test_adaptive_fh.py -q
"""
from __future__ import annotations

import pytest

from . import adaptive_fh as afh


def test_semantic_beats_uniform_for_important():
    uni = afh.run_simulation("uniform", seed=0)
    sem = afh.run_simulation("semantic", seed=0)
    assert sem["L0"] > uni["L0"] + 0.3
    assert sem["L1"] > uni["L1"] + 0.3


def test_semantic_l2_matches_uniform():
    uni = afh.run_simulation("uniform", seed=1)
    sem = afh.run_simulation("semantic", seed=1)
    assert sem["L2"] == pytest.approx(uni["L2"], abs=0.05)


def test_uniform_treats_all_levels_equally():
    uni = afh.run_simulation("uniform", seed=2)
    assert uni["L0"] == pytest.approx(uni["L2"], abs=0.05)


def test_semantic_gradation():
    sem = afh.run_simulation("semantic", seed=3)
    assert sem["L0"] > sem["L1"] > sem["L2"]
