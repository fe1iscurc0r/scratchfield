"""scikit-fingerprints MCP 封装测试（离线，mock skfp/rdkit）。"""

from __future__ import annotations

import os
import sys
from unittest import mock

import pytest

# 允许从 scratchpad 根目录 import mcpserver.scikit_fingerprints.agent
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from mcpserver.academic.errors import AcademicDependencyError  # noqa: E402
from mcpserver.scikit_fingerprints.agent import (  # noqa: E402
    ScikitFingerprintsAgent,
)

ASPIRIN_SMILES = "CC(=O)Oc1ccccc1C(=O)O"
ETHANOL_SMILES = "CCO"


class FakeFingerprint:
    """模拟 skfp.fingerprints.*Fingerprint.transform → 位向量矩阵。"""

    def __init__(self, **kw):
        self.kw = kw

    def transform(self, smiles_list):
        # 每分子一个固定 6 位向量（含非零位），用于断言
        vecs = {
            ASPIRIN_SMILES: [1, 0, 1, 1, 0, 1],
            ETHANOL_SMILES: [0, 1, 0, 1, 0, 0],
        }
        return [vecs.get(s, [0, 0, 0, 0, 0, 0]) for s in smiles_list]


class FakeSkfp:
    """模拟 skfp 模块：fingerprints 子模块 + 各指纹类。"""

    class fingerprints:
        ECFPFingerprint = FakeFingerprint
        MorganFingerprint = FakeFingerprint
        MACCSFingerprint = FakeFingerprint
        TopologicalFingerprint = FakeFingerprint


class FakeMol:
    pass


class FakeMurckoScaffold:
    @staticmethod
    def MurckoScaffoldSmiles(mol=None, smiles=None):
        return "c1ccc(cc1)C(=O)O" if mol is not None else None

    @staticmethod
    def MakeScaffoldGeneric(mol=None):
        return "c1ccccc1"


class FakeRdkChem:
    @staticmethod
    def MolFromSmiles(smiles):
        if smiles == "NOT-A-MOLECULE":
            return None
        return FakeMol()


def _make_agent() -> ScikitFingerprintsAgent:
    return ScikitFingerprintsAgent()


# ---- 4 命令功能 ----


def test_fingerprint_ok():
    with mock.patch("mcpserver.scikit_fingerprints.agent._skfp", return_value=FakeSkfp):
        res = _make_agent().invoke(
            "skfp_fingerprint",
            {"smiles_list": [ASPIRIN_SMILES], "fingerprint_type": "ECFP", "radius": 2, "fp_size": 2048},
        )
    assert res["ok"] is True
    assert res["source"] == "scikit-fingerprints"
    assert res["fingerprint_type"] == "ECFP"
    assert res["radius"] == 2
    assert res["count"] == 1
    assert res["fingerprints"][0]["bit_indices"] == [0, 2, 3, 5]


def test_fingerprint_maccs_no_radius():
    with mock.patch("mcpserver.scikit_fingerprints.agent._skfp", return_value=FakeSkfp):
        res = _make_agent().invoke("skfp_fingerprint", {"smiles_list": ASPIRIN_SMILES, "fingerprint_type": "MACCS"})
    assert res["ok"] is True
    assert res["radius"] is None  # MACCS 无 radius


def test_similarity_matrix_ok():
    with mock.patch("mcpserver.scikit_fingerprints.agent._skfp", return_value=FakeSkfp):
        res = _make_agent().invoke(
            "skfp_similarity_matrix", {"smiles_list": [ASPIRIN_SMILES, ETHANOL_SMILES], "fingerprint_type": "ECFP"}
        )
    assert res["ok"] is True
    assert res["n"] == 2
    # ASPIRIN(0,2,3,5) vs ETHANOL(1,3)：交集 {3}，并集 {0,1,2,3,5} → 0.2
    assert res["matrix"][0]["row"][1]["similarity"] == 0.2
    assert res["matrix"][1]["row"][0]["similarity"] == 0.2


def test_transform_ok():
    with mock.patch("mcpserver.scikit_fingerprints.agent._skfp", return_value=FakeSkfp):
        res = _make_agent().invoke(
            "skfp_transform",
            {"smiles_list": [ASPIRIN_SMILES, ETHANOL_SMILES], "fingerprint_type": "ECFP", "fp_size": 6},
        )
    assert res["ok"] is True
    assert res["rows"] == 2
    assert res["cols"] == 6
    # ASPIRIN 4 非零位 + ETHANOL 2 非零位 = 6 / (2*6) = 0.5
    assert res["density"] == 0.5
    assert res["features"][0]["nonzero_positions"] == [0, 2, 3, 5]


def test_scaffold_ok():
    with mock.patch(
        "mcpserver.scikit_fingerprints.agent._load_rdkit_scaffold", return_value=(FakeRdkChem, FakeMurckoScaffold)
    ):
        res = _make_agent().invoke("skfp_scaffold", {"smiles": ASPIRIN_SMILES})
    assert res["ok"] is True
    assert res["scaffold_smiles"] == "c1ccc(cc1)C(=O)O"
    assert res["generic_scaffold"] == "c1ccccc1"


def test_scaffold_smiles_string_ok():
    """MurckoScaffoldSmiles 也可按 SMILES 字符串输入（部分 rdkit 版本）。"""
    with mock.patch(
        "mcpserver.scikit_fingerprints.agent._load_rdkit_scaffold", return_value=(FakeRdkChem, FakeMurckoScaffold)
    ):
        res = _make_agent().invoke("skfp_scaffold", {"smiles": ASPIRIN_SMILES})
    assert res["scaffold_smiles"] is not None


# ---- 契约：参数非法 → ValueError ----


@pytest.mark.parametrize(
    "cmd,params",
    [
        ("skfp_fingerprint", {"smiles_list": []}),
        ("skfp_fingerprint", {"smiles_list": ["CCO"], "fingerprint_type": "SPKI"}),
        ("skfp_fingerprint", {"smiles_list": ["CCO"], "radius": -1}),
        ("skfp_fingerprint", {"smiles_list": ["CCO"], "fp_size": 0}),
        ("skfp_similarity_matrix", {"smiles_list": ["CCO"]}),
        ("skfp_similarity_matrix", {"smiles_list": "  "}),
        ("skfp_transform", {"smiles_list": ""}),
        ("skfp_scaffold", {"smiles": "  "}),
    ],
)
def test_invalid_params_raise_valueerror(cmd, params):
    with (
        mock.patch("mcpserver.scikit_fingerprints.agent._skfp", return_value=FakeSkfp),
        mock.patch(
            "mcpserver.scikit_fingerprints.agent._load_rdkit_scaffold", return_value=(FakeRdkChem, FakeMurckoScaffold)
        ),
        pytest.raises(ValueError),
    ):
        _make_agent().invoke(cmd, params)


def test_scaffold_invalid_smiles_raise_valueerror():
    with (
        mock.patch(
            "mcpserver.scikit_fingerprints.agent._load_rdkit_scaffold", return_value=(FakeRdkChem, FakeMurckoScaffold)
        ),
        pytest.raises(ValueError, match="无效 SMILES"),
    ):
        _make_agent().invoke("skfp_scaffold", {"smiles": "NOT-A-MOLECULE"})


def test_unknown_command_raise_valueerror():
    with pytest.raises(ValueError, match="未知命令"):
        _make_agent().invoke("skfp_no_such", {})


# ---- 契约：依赖缺失 → AcademicDependencyError（含 pip 提示） ----


def test_skfp_missing_raises_academic_dependency_error():
    err = AcademicDependencyError("scikit-fingerprints", "scikit-fingerprints")
    with (
        mock.patch("mcpserver.scikit_fingerprints.agent._skfp", side_effect=err),
        pytest.raises(AcademicDependencyError, match="pip install scikit-fingerprints"),
    ):
        _make_agent().invoke("skfp_fingerprint", {"smiles_list": ["CCO"]})


def test_rdkit_missing_raises_academic_dependency_error():
    err = AcademicDependencyError("rdkit", "rdkit")
    with (
        mock.patch("mcpserver.scikit_fingerprints.agent._load_rdkit_scaffold", side_effect=err),
        pytest.raises(AcademicDependencyError, match="pip install rdkit"),
    ):
        _make_agent().invoke("skfp_scaffold", {"smiles": ASPIRIN_SMILES})


# ---- 契约：source 字段 ----


def test_all_commands_carry_source():
    with (
        mock.patch("mcpserver.scikit_fingerprints.agent._skfp", return_value=FakeSkfp),
        mock.patch(
            "mcpserver.scikit_fingerprints.agent._load_rdkit_scaffold", return_value=(FakeRdkChem, FakeMurckoScaffold)
        ),
    ):
        agent = _make_agent()
        for cmd, params in [
            ("skfp_fingerprint", {"smiles_list": ["CCO"]}),
            ("skfp_similarity_matrix", {"smiles_list": ["CCO", "CCN"]}),
            ("skfp_transform", {"smiles_list": ["CCO"]}),
            ("skfp_scaffold", {"smiles": "CCO"}),
        ]:
            res = agent.invoke(cmd, params)
            assert res["source"] == "scikit-fingerprints", cmd
