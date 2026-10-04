"""R30 验收测试：PT 对称可编程波形原型。

覆盖：
  1. 本征值：未破缺（γ<κ）→ 纯虚（稳定振荡）；破缺（γ>κ）→ 含实部（增长/衰减）
  2. 未破缺：波形包络稳定（不增长）
  3. 破缺：波形包络增长（对数增长 > 0）
  4. 可编程：不同 (γ,κ) 产生不同本征值（频率/衰减可控）

运行：python -m pytest mcpserver/rf_brain/prototypes/test_pt_symmetric_waveform.py -q
"""
from __future__ import annotations

import numpy as np
import pytest

from . import pt_symmetric_waveform as ptw


def test_eigenvalues_unbroken_real_freq():
    l1, l2 = ptw.pt_eigenvalues(gamma=0.5, kappa=1.0)
    # 未破缺：本征值为纯虚（无实部 → 稳定振荡）
    assert np.real(l1) == pytest.approx(0.0, abs=1e-9)
    assert np.real(l2) == pytest.approx(0.0, abs=1e-9)
    # 频率 = √(κ²-γ²)
    assert abs(np.imag(l1)) == pytest.approx(np.sqrt(1.0 - 0.25))


def test_eigenvalues_broken_has_real_part():
    l1, l2 = ptw.pt_eigenvalues(gamma=1.5, kappa=1.0)
    # 破缺：本征值含实部（增长/衰减）
    assert abs(np.real(l1)) > 0
    assert np.real(l1) == pytest.approx(-np.real(l2))


def test_unbroken_stable_envelope():
    w = ptw.simulate(gamma=0.5, kappa=1.0)
    assert ptw.envelope_growth(w) < 0.5  # 稳定，不显著增长


def test_broken_growing_envelope():
    w = ptw.simulate(gamma=1.5, kappa=1.0)
    assert ptw.envelope_growth(w) > 0.5  # 破缺 → 增长


def test_programmable_frequency():
    l1a, _ = ptw.pt_eigenvalues(0.3, 1.0)
    l1b, _ = ptw.pt_eigenvalues(0.8, 1.0)
    # 不同 γ → 不同振荡频率（可编程）
    assert abs(np.imag(l1a)) != pytest.approx(abs(np.imag(l1b)))
