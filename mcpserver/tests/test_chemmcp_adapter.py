"""ChemMCP SMILES 纯转换工具适配层测试（工单 04-01）。

覆盖：上游示例回归 / 生物质分子（木质素单体）转换 / 坏输入 / RDKit 缺失降级 /
PubChem 网络降级 / adapter 注册契约（validate_adapter + register 门禁三要素）。
真实 PubChem 联网用例默认跳过（设 CHEMMCP_REALNET=1 显式开启，见 mcpserver/README.md
真机验证点），离线跑全仓 pytest 不打外网。
"""
from __future__ import annotations

import pytest

from mcpserver.adapters import chemmcp as m
from mcpserver.adapters import reset_for_tests, validate_adapter

# ---------------------------------------------------------------------------
# 规范化 smiles_canonicalization
# ---------------------------------------------------------------------------


def test_canonicalize_upstream_example():
    """上游 ChemMCP 示例：C(O)C → CCO。"""
    out = m.smiles_canonicalization_impl("C(O)C")
    assert out["ok"] is True
    assert out["canonical_smiles"] == "CCO"


def test_canonicalize_kekulization_default_uppercase_aromatic():
    """kekulization=True（上游默认）：芳香键写成交替单双键（愈创木酚）。"""
    out = m.smiles_canonicalization_impl("COc1ccccc1O")
    assert out["ok"] is True
    assert out["canonical_smiles"] == "COC1=CC=CC=C1O"


def test_canonicalize_aromatic_form_when_not_kekulized():
    """kekulization=False：保留芳香小写形式。"""
    out = m.smiles_canonicalization_impl("c1ccccc1O", kekulization=False)
    assert out["ok"] is True
    assert out["canonical_smiles"] == "Oc1ccccc1"


def test_canonicalize_multicomponent_sorted():
    """多组分按上游 sort_things=True 排序后 "." 拼接。"""
    out = m.smiles_canonicalization_impl("c1ccccc1O.CCO")
    assert out["ok"] is True
    assert out["canonical_smiles"] == "CCO.OC1=CC=CC=C1"


def test_canonicalize_keep_atom_map():
    """keep_atom_map=True（上游默认）保留原子映射编号。"""
    out = m.smiles_canonicalization_impl("[CH3:1][CH2:2]O")
    assert out["ok"] is True
    assert out["canonical_smiles"] == "O[CH2:2][CH3:1]"


def test_canonicalize_invalid_smiles_degrades():
    """坏输入：无效片段 → ok=False，不抛错。"""
    out = m.smiles_canonicalization_impl("not_a_smiles")
    assert out["ok"] is False
    assert "无效 SMILES" in out["error"]


def test_canonicalize_bad_input_types():
    """坏输入：空串/非字符串 → ok=False，不抛错。"""
    for bad in ("", "   ", None, 123):
        out = m.smiles_canonicalization_impl(bad)
        assert out["ok"] is False
        assert "error" in out


# ---------------------------------------------------------------------------
# 分子式 smiles2formula
# ---------------------------------------------------------------------------


def test_formula_upstream_example():
    """上游示例：CCO → C2H6O。"""
    out = m.smiles2formula_impl("CCO")
    assert out["ok"] is True
    assert out["formula"] == "C2H6O"


def test_formula_lignin_monomer_guaiacol():
    """生物质分子：愈创木酚（木质素热解单体）→ C7H8O2。"""
    out = m.smiles2formula_impl("COc1ccccc1O")
    assert out["ok"] is True
    assert out["formula"] == "C7H8O2"


def test_formula_invalid_degrades():
    out = m.smiles2formula_impl("C1CC2XYZ")
    assert out["ok"] is False
    assert "error" in out


# ---------------------------------------------------------------------------
# 合法性检查 molecule_smiles_check
# ---------------------------------------------------------------------------


def test_check_valid_and_invalid():
    assert m.molecule_smiles_check_impl("CCO")["valid"] is True
    bad = m.molecule_smiles_check_impl("C1CC")  # 环未闭合
    assert bad["ok"] is True
    assert bad["valid"] is False
    assert bad["result"] == "The molecular SMILES string is invalid."


def test_check_reaction_smiles_rejected_not_raised():
    """含 ">" 的反应 SMILES：上游抛 ChemMCPInputError，本仓降级 ok=False 不抛错。"""
    out = m.molecule_smiles_check_impl("CCO.O>>CCOCC")
    assert out["ok"] is False
    assert ">" in out["error"]


# ---------------------------------------------------------------------------
# CAS 号 smiles2cas（离线降级路径；联网真机用例见文件尾 realnet 区）
# ---------------------------------------------------------------------------


def test_cas_invalid_input_fails_before_network(monkeypatch):
    """无效 SMILES 在本地校验就被拦，不碰网络。"""
    monkeypatch.setenv("CHEMMCP_PUBCHEM_BASE", "http://127.0.0.1:9")  # 不可达端点
    out = m.smiles2cas_impl("definitely_not_smiles")
    assert out["ok"] is False
    assert "不是有效 SMILES" in out["error"]


def test_cas_offline_degrades_no_raise(monkeypatch):
    """网络不可达 → ok=False + error，绝不抛错（context7 降级惯例）。"""
    monkeypatch.setenv("CHEMMCP_PUBCHEM_BASE", "http://127.0.0.1:9")
    monkeypatch.setenv("CHEMMCP_PUBCHEM_TIMEOUT_S", "0.5")
    out = m.smiles2cas_impl("CCO")
    assert out["ok"] is False
    assert "PubChem 查询失败" in out["error"]


def test_cas_pubchem_cas_section_extraction():
    """_pubchem_cas 段解析：合成 PUG_VIEW 响应验证 CAS 提取与容错（不打网络）。"""
    fake = {
        "Record": {
            "Section": [
                {"TOCHeading": "Other"},
                {
                    "TOCHeading": "Names and Identifiers",
                    "Section": [
                        {
                            "TOCHeading": "Other Identifiers",
                            "Section": [
                                {
                                    "TOCHeading": "CAS",
                                    "Information": [
                                        {"Value": {"StringWithMarkup": [{"String": "64-17-5"}]}}
                                    ],
                                }
                            ],
                        }
                    ],
                },
            ]
        }
    }
    assert m._pubchem_cas(fake) == "64-17-5"
    assert m._pubchem_cas({"Record": {"Section": []}}) == ""
    assert m._pubchem_cas({}) == ""  # 缺键容错，不抛


# ---------------------------------------------------------------------------
# RDKit 缺失降级（工单铁律：RDKit 不可用时 ok=False + error，不抛错）
# ---------------------------------------------------------------------------


def test_all_tools_degrade_without_rdkit(monkeypatch):
    """模拟 RDKit 缺失：四个工具一律 ok=False + 安装提示，绝不抛错。"""
    monkeypatch.setattr(m, "_load_rdkit", lambda: None)
    for fn, kwargs in (
        (m.smiles_canonicalization_impl, {}),
        (m.smiles2formula_impl, {}),
        (m.molecule_smiles_check_impl, {}),
        (m.smiles2cas_impl, {}),
    ):
        out = fn("CCO", **kwargs)
        assert out["ok"] is False
        assert "rdkit" in out["error"]


# ---------------------------------------------------------------------------
# adapter 契约（纳入前门禁）
# ---------------------------------------------------------------------------


def test_adapter_contract_passes_gate():
    """validate_adapter 三要素 + CAPABILITY 必需字段 + name 对齐。"""
    assert validate_adapter(m, "chemmcp") == []
    assert m.healthcheck() is True
    assert m.CAPABILITY["license"] == "Apache-2.0"
    assert m.CAPABILITY["_from_adapter"] == "chemmcp"


class _FakeMCP:
    def __init__(self):
        self.tools: dict[str, object] = {}

    def add_tool(self, fn, name):
        self.tools[name] = fn


class _FakeRegistry:
    def __init__(self):
        self.caps: list[dict] = []

    def register_capability(self, cap):
        self.caps.append(cap)


def test_register_mounts_four_tools_and_capability():
    reset_for_tests()
    server, registry = _FakeMCP(), _FakeRegistry()
    m.register(server, mcp_registry=registry)
    assert set(server.tools) == {
        "chemmcp_canonicalize_smiles",
        "chemmcp_smiles2formula",
        "chemmcp_check_molecule_smiles",
        "chemmcp_smiles2cas",
    }
    assert registry.caps and registry.caps[0]["name"] == "chemmcp"


def test_register_without_add_tool_still_registers_capability():
    """mcp_server 无 add_tool：不抛错，能力卡仍登记（照 context7 惯例）。"""
    reset_for_tests()
    registry = _FakeRegistry()
    m.register(object(), mcp_registry=registry)  # 无 add_tool 的裸对象
    assert registry.caps and registry.caps[0]["name"] == "chemmcp"


def test_register_all_adapters_includes_chemmcp():
    """_ADAPTERS 表含 chemmcp 且可被 register_all_adapters 按开关注册。"""
    from mcpserver.adapters import _ADAPTERS

    assert "chemmcp" in _ADAPTERS
    assert _ADAPTERS["chemmcp"] == ("mcpserver.adapters.chemmcp", "ENABLE_ADAPTER_CHEMMCP")


# ---------------------------------------------------------------------------
# 真机/实网验证点（默认跳过；CHEMMCP_REALNET=1 时跑，结果见 README 诚实标注区）
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not __import__("os").environ.get("CHEMMCP_REALNET"),
    reason="真实 PubChem 联网用例：设 CHEMMCP_REALNET=1 显式开启",
)
def test_cas_realnet_ethanol():
    out = m.smiles2cas_impl("CCO")
    assert out["ok"] is True, out
    assert out["cas"] == "64-17-5"


@pytest.mark.skipif(
    not __import__("os").environ.get("CHEMMCP_REALNET"),
    reason="真实 PubChem 联网用例：设 CHEMMCP_REALNET=1 显式开启",
)
def test_cas_realnet_guaiacol():
    """木质素热解单体愈创木酚：真实 PubChem 应返回 CAS 90-05-1。"""
    out = m.smiles2cas_impl("COc1ccccc1O")
    assert out["ok"] is True, out
    assert out["cas"] == "90-05-1"
