# -*- coding: utf-8 -*-
"""chem_conversions 测试（W63-04 验收）。"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from chem_conversions import smiles2cas, smiles2formula


def test_smiles2formula_ethanol_explicit_atoms():
    # mock 只数显式原子，不补隐式氢（诚实降级，真实分子式需 RDKit）
    assert smiles2formula("CCO") == "C2O"


def test_smiles2formula_water():
    assert smiles2formula("O") == "O"


def test_smiles2formula_aromatic_benzene():
    # 苯环 c1ccccc1 → 6 个 C
    assert smiles2formula("c1ccccc1") == "C6"


def test_smiles2cas_mock_none():
    assert smiles2cas("CCO") is None  # mock：无 CAS 库


def test_smiles2formula_empty():
    assert smiles2formula("") == ""
