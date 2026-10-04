"""W69-01 融合测试：材料 3D 可视化适配器（mock 降级 + 分子数据结构）。

运行：python -m pytest tools/test_avogadro_viz.py -q
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from avogadro_viz import Molecule, render


def test_mock_degradation_without_avogadro():
    """无 PyAvogadro 时 mock 降级。"""
    assert Molecule().degraded is True  # 本环境未装 PyAvogadro → mock


def test_add_atom_and_bond():
    m = Molecule()
    h1 = m.add_atom("H", (0.0, 0.0, 0.0))
    o = m.add_atom("O", (0.0, 0.0, 0.96))
    h2 = m.add_atom("H", (0.96, 0.0, 0.0))
    m.add_bond(o, h1, 1)
    m.add_bond(o, h2, 1)
    assert len(m.atoms) == 3
    assert len(m.bonds) == 2


def test_to_xyz_format():
    m = Molecule()
    m.add_atom("H", (0.0, 0.0, 0.0))
    m.add_atom("O", (0.0, 0.0, 0.96))
    xyz = m.to_xyz()
    lines = xyz.splitlines()
    assert lines[0] == "2"  # 原子数
    assert len(lines) == 4  # 原子数行 + 注释行 + 2 原子行


def test_render_mock_returns_xyz():
    m = Molecule()
    m.add_atom("H", (0.0, 0.0, 0.0))
    out = render(m)
    assert "H" in out  # mock 渲染 = XYZ 文本
