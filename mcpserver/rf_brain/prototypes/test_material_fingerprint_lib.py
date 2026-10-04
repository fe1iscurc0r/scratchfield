"""R31 验收测试：材料指纹频谱库原型。

覆盖：
  1. 特征 schema：MaterialFingerprint 含频率轴/吸收谱/特征峰字段
  2. 库构建：3 种材料，各有特征吸收带
  3. 匹配：观测谱（含噪声）识别到正确材料
  4. 识别准确率：噪声下仍 ≥ 90%

运行：python -m pytest mcpserver/rf_brain/prototypes/test_material_fingerprint_lib.py -q
"""
from __future__ import annotations

import numpy as np
import pytest

from . import material_fingerprint_lib as mfl


@pytest.fixture(scope="module")
def library():
    return mfl.build_library()


def test_schema_fields(library):
    m = library[0]
    assert m.name
    assert m.freq_thz.size == m.absorbance.size
    assert len(m.peak_freqs_thz) >= 1
    assert "band" in m.metadata


def test_library_three_materials(library):
    assert len(library) == 3
    names = {m.name for m in library}
    assert len(names) == 3


def test_match_correct_material(library):
    for m in library:
        obs = mfl.observe(m, noise=0.2, seed=0)
        assert mfl.match(obs, library) == m.name


def test_identification_accuracy(library):
    for m in library:
        acc = np.mean([mfl.match(mfl.observe(m, noise=0.3, seed=10 + i), library) == m.name
                       for i in range(50)])
        assert acc >= 0.9, f"{m.name} 识别率过低: {acc}"
