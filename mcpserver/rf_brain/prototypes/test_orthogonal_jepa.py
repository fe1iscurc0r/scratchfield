"""R10 验收测试：Orthogonal JEPA 干扰分离最小原型。

覆盖：
  1. 正交性：分解出的信号分量与干扰分量近乎正交
  2. 信号分量：与真信号相关性高
  3. 干扰分量：与真干扰相关性高
  4. 对号入座：干扰分量与真信号相关性低

运行：python -m pytest mcpserver/rf_brain/prototypes/test_orthogonal_jepa.py -q
"""
from __future__ import annotations

import pytest

from . import orthogonal_jepa as oj


@pytest.fixture(scope="module")
def d():
    return oj.synthesize_iq(4096, 1000.0, seed=0)


@pytest.fixture(scope="module")
def parts(d):
    s_hat, i_hat = oj.orthogonal_decompose(d["x"], d["sr"], d["f_interf"])
    return s_hat, i_hat


def test_orthogonality(parts):
    s_hat, i_hat = parts
    assert oj.corr(s_hat, i_hat) < 0.05


def test_signal_recovered(parts, d):
    s_hat, _ = parts
    assert oj.corr(s_hat, d["signal"]) > 0.5


def test_interference_recovered(parts, d):
    _, i_hat = parts
    assert oj.corr(i_hat, d["interference"]) > 0.9


def test_no_cross_contamination(parts, d):
    _, i_hat = parts
    assert oj.corr(i_hat, d["signal"]) < 0.3
