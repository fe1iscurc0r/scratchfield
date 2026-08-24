"""ChEMBL MCP 封装测试（离线，mock 官方客户端）。"""

from __future__ import annotations

import os
import sys
from unittest import mock

import pytest

# 允许从 scratchpad 根目录 import mcpserver.chembl.agent
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from mcpserver.academic.errors import AcademicDependencyError  # noqa: E402
from mcpserver.chembl.agent import ChEMBLAgent, _ChEMBLUnavailable  # noqa: E402

ASPIRIN_SMILES = "CC(=O)Oc1ccccc1C(=O)O"


class FakeClient:
    """模拟 chembl_webresource_client.new_client 的接口面。"""

    def __init__(self):
        self.molecule = _FakeMolecule()
        self.target = _FakeTarget()
        self.activity = _FakeActivity()
        self.similarity = _FakeSimilarity()


class _FakeMolecule:
    def get(self, chembl_id: str) -> dict | None:
        if chembl_id == "CHEMBL25":
            return {
                "molecule_chembl_id": "CHEMBL25",
                "pref_name": "ASPIRIN",
                "molecular_formula": "C9H8O4",
                "molecule_structures": {
                    "canonical_smiles": ASPIRIN_SMILES,
                    "molfile": "fake-molfile-block",
                    "molecular_formula": "C9H8O4",
                },
            }
        return None

    def filter(self, **kw):
        hits = [
            {"molecule_chembl_id": "CHEMBL25", "pref_name": "ASPIRIN", "molecular_formula": "C9H8O4"},
            {"molecule_chembl_id": "CHEMBL448", "pref_name": "ACETYLSALICYLIC ACID", "molecule_formula": "C9H8O4"},
        ]
        if "pref_name__icontains" in kw:
            q = (kw["pref_name__icontains"] or "").lower()
            hits = [h for h in hits if q in (h.get("pref_name") or "").lower()]
        return _Sliceable(hits)


class _FakeTarget:
    def get(self, target_id: str) -> dict | None:
        if target_id == "CHEMBL2368546":
            return {
                "target_chembl_id": "CHEMBL2368546",
                "pref_name": "Cyclooxygenase-1",
                "organism": "Homo sapiens",
                "target_type": "SINGLE PROTEIN",
                "target_components": [
                    {"accession": "P23219", "description": "PTGS1", "component_type": "PROTEIN"},
                ],
            }
        return None


class _FakeActivity:
    def filter(self, **kw):
        rows = [
            {
                "assay_chembl_id": "CHEMBL1213036",
                "target_chembl_id": "CHEMBL2368546",
                "standard_type": "IC50",
                "standard_value": "0.5",
                "standard_units": "uM",
                "pchembl_value": "6.3",
                "standard_relation": "=",
            }
        ]
        return _Sliceable(rows)


class _FakeSimilarity:
    def filter(self, **kw):
        hits = [
            {"molecule_chembl_id": "CHEMBL25", "pref_name": "ASPIRIN", "similarity": 1.0},
            {"molecule_chembl_id": "CHEMBL448", "pref_name": "ACETYLSALICYLIC ACID", "similarity": 0.97},
            {"molecule_chembl_id": "CHEMBL455", "pref_name": "SALICYLIC ACID", "similarity": 0.95},
        ]
        return _Sliceable(hits)


class _Sliceable:
    """支持 [:limit] 切片的假查询结果。"""

    def __init__(self, items: list):
        self._items = items

    def __getitem__(self, key):
        if isinstance(key, slice):
            return self._items[key]
        return self._items[key]

    def __iter__(self):
        return iter(self._items)


def _make_agent() -> ChEMBLAgent:
    return ChEMBLAgent()


@pytest.fixture
def fake_client():
    return FakeClient()


# ---- 6 命令功能 ----


def test_search_compound_by_name(fake_client):
    with mock.patch("mcpserver.chembl.agent._client", return_value=fake_client):
        res = _make_agent().invoke("chembl_search_compound", {"query": "aspirin", "limit": 2})
    assert res["ok"] is True
    assert res["source"] == "ChEMBL"
    assert res["count"] == 1
    assert res["hits"][0]["chembl_id"] == "CHEMBL25"
    assert res["hits"][0]["pref_name"] == "ASPIRIN"


def test_search_compound_by_chembl_id(fake_client):
    with mock.patch("mcpserver.chembl.agent._client", return_value=fake_client):
        res = _make_agent().invoke("chembl_search_compound", {"query": "CHEMBL25"})
    assert res["ok"] is True
    assert res["hits"][0]["pref_name"] == "ASPIRIN"


def test_target_ok(fake_client):
    with mock.patch("mcpserver.chembl.agent._client", return_value=fake_client):
        res = _make_agent().invoke("chembl_target", {"target_id": "CHEMBL2368546"})
    assert res["ok"] is True
    assert res["pref_name"] == "Cyclooxygenase-1"
    assert res["organism"] == "Homo sapiens"
    assert res["components"][0]["accession"] == "P23219"


def test_activity_ok(fake_client):
    with mock.patch("mcpserver.chembl.agent._client", return_value=fake_client):
        res = _make_agent().invoke("chembl_activity", {"chembl_id": "CHEMBL25", "limit": 5})
    assert res["ok"] is True
    assert res["count"] == 1
    assert res["activities"][0]["standard_type"] == "IC50"
    assert res["activities"][0]["standard_value"] == "0.5"


def test_structure_ok(fake_client):
    with mock.patch("mcpserver.chembl.agent._client", return_value=fake_client):
        res = _make_agent().invoke("chembl_structure", {"chembl_id": "CHEMBL25"})
    assert res["ok"] is True
    assert res["canonical_smiles"] == ASPIRIN_SMILES
    assert res["molfile"] == "fake-molfile-block"
    assert res["molecular_formula"] == "C9H8O4"


def test_similarity_ok(fake_client):
    # 报告实测场景：阿司匹林 95% 相似检索返回 3 hits
    with mock.patch("mcpserver.chembl.agent._client", return_value=fake_client):
        res = _make_agent().invoke("chembl_similarity", {"smiles": ASPIRIN_SMILES, "similarity": 95, "limit": 5})
    assert res["ok"] is True
    assert res["count"] == 3
    assert res["hits"][0]["similarity"] == 1.0


def test_batch_ok(fake_client):
    with mock.patch("mcpserver.chembl.agent._client", return_value=fake_client):
        res = _make_agent().invoke("chembl_batch", {"chembl_ids": ["CHEMBL25", "CHEMBL999"]})
    assert res["ok"] is True
    assert res["requested"] == 2
    assert res["found"] == 1
    assert res["molecules"][0]["pref_name"] == "ASPIRIN"
    assert res["molecules"][1]["found"] is False


def test_batch_str_ids(fake_client):
    with mock.patch("mcpserver.chembl.agent._client", return_value=fake_client):
        res = _make_agent().invoke("chembl_batch", {"chembl_ids": "CHEMBL25, CHEMBL999"})
    assert res["ok"] is True
    assert res["requested"] == 2


# ---- 契约：参数非法 → ValueError ----


@pytest.mark.parametrize(
    "cmd,params",
    [
        ("chembl_search_compound", {"query": "  "}),
        ("chembl_target", {"target_id": "P23219"}),
        ("chembl_activity", {"chembl_id": "aspirin"}),
        ("chembl_structure", {"chembl_id": "aspirin"}),
        ("chembl_similarity", {"smiles": ""}),
        ("chembl_similarity", {"smiles": "CCO", "similarity": 150}),
        ("chembl_batch", {"chembl_ids": []}),
        ("chembl_batch", {"chembl_ids": ["CHEMBL25", "P23219"]}),
    ],
)
def test_invalid_params_raise_valueerror(fake_client, cmd, params):
    with mock.patch("mcpserver.chembl.agent._client", return_value=fake_client), pytest.raises(ValueError):
        _make_agent().invoke(cmd, params)


def test_unknown_command_raise_valueerror(fake_client):
    with (
        mock.patch("mcpserver.chembl.agent._client", return_value=fake_client),
        pytest.raises(ValueError, match="未知命令"),
    ):
        _make_agent().invoke("chembl_no_such", {})


# ---- 契约：依赖缺失 → AcademicDependencyError（含 pip 提示） ----


def test_dependency_missing_raises_academic_dependency_error(fake_client):
    err = AcademicDependencyError("chembl-webresource-client", "chembl-webresource-client")
    with (
        mock.patch("mcpserver.chembl.agent._client", side_effect=err),
        pytest.raises(AcademicDependencyError, match="pip install chembl-webresource-client"),
    ):
        _make_agent().invoke("chembl_structure", {"chembl_id": "CHEMBL25"})


def test_dependency_missing_unknown_command_still_raises(fake_client):
    """依赖缺失时未知命令仍优先报 ValueError（参数面契约先于依赖面）。"""
    err = AcademicDependencyError("chembl-webresource-client", "chembl-webresource-client")
    with mock.patch("mcpserver.chembl.agent._client", side_effect=err), pytest.raises(ValueError, match="未知命令"):
        _make_agent().invoke("chembl_no_such", {})


# ---- 契约：网络不可达 → 降级错误（不否决） ----


def test_network_error_raises_unavailable(fake_client):
    def boom(*a, **kw):
        raise RuntimeError("Connection refused")

    fake_client.molecule.get = boom
    with (
        mock.patch("mcpserver.chembl.agent._client", return_value=fake_client),
        pytest.raises(_ChEMBLUnavailable, match="获取失败"),
    ):
        _make_agent().invoke("chembl_structure", {"chembl_id": "CHEMBL25"})
