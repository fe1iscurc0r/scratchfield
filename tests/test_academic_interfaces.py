"""academic 16 包融合 + MODEL_INTERFACE 测试（W-09 验收）。

验收口径：
1. 16 个包全标注融合层级（levels.py 单一事实源）
2. ≥4 个封装 MODEL_INTERFACE 可调用（grep 断言：mcpserver/academic/ 下
   含 MODEL_INTERFACE 的 .py 文件数 ≥ 4；CoolProp/ChemFormula 真算）
3. 降级契约：tespy/slices 缺依赖时明确报 AcademicDependencyError（含 pip 提示）
4. MCP 注册：scan_and_register 发现 academic，unified_call 真算返回
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from mcpserver.academic import (
    FUSION_LEVELS,
    get_interfaces,
    get_levels,
    levels_summary,
    list_interfaces,
)
from mcpserver.academic.bridge import AcademicBridge
from mcpserver.academic.errors import AcademicDependencyError

ACADEMIC_DIR = Path(__file__).resolve().parents[1] / "mcpserver" / "academic"


# ---------------------------------------------------------- 16 包层级标注

def test_levels_cover_all_16_packages():
    """验收 1：16 个包全标注，层级合法，license 全记。"""
    assert len(FUSION_LEVELS) == 16, sorted(FUSION_LEVELS)
    valid_levels = {"MCP", "Skill", "融合参考", "耦合", "基础设施"}
    for name, info in FUSION_LEVELS.items():
        assert info["level"] in valid_levels, (name, info["level"])
        assert info["license"], f"{name} 缺 license 标注"
        assert "status" in info and "notes" in info
    summary = levels_summary()
    assert sum(summary.values()) == 16
    expected_16 = {
        "thermo", "tespy", "pycalphad", "Clapeyron.jl", "CoolProp",
        "PyXtal", "SLICES", "gemmi", "ChemFormula", "hyalite",
        "AffineGaps", "WaveBench", "rp2daq", "hololinked", "Pynite", "FEMcy",
    }
    assert set(FUSION_LEVELS) == expected_16


# ------------------------------------------------- MODEL_INTERFACE ≥4 可调用

def test_model_interface_grep_assertion():
    """验收 2（grep 口径）：academic 目录下含 MODEL_INTERFACE 的模块 ≥ 4。"""
    files = [p for p in ACADEMIC_DIR.glob("*_interface.py")
             if "MODEL_INTERFACE" in p.read_text(encoding="utf-8")]
    assert len(files) >= 4, [p.name for p in files]
    assert len(list_interfaces()) >= 4


def test_interfaces_metadata_contract():
    for name, iface in get_interfaces().items():
        for field in ("name", "package", "pip", "license", "fusion_level",
                      "description", "entrypoints", "degradation", "verified"):
            assert iface.get(field), f"{name}.{field} 缺失/为空"
        assert isinstance(iface.get("runtime_deps"), list), \
            f"{name}.runtime_deps 必须是列表（可为空=无硬依赖）"
        assert iface["entrypoints"], f"{name} 无 entrypoints"
        # 接口名与注册名对齐（防能力卡片错位）
        assert iface["name"] == name


def test_chemformula_real_compute_offline():
    """ChemFormula 离线真算（vendor 源码，无外部依赖）。"""
    from mcpserver.academic.chemformula_interface import chem_parse
    r = chem_parse("H2O")
    assert r["ok"] is True
    assert r["formula_weight"] == pytest.approx(18.015, abs=0.01)
    assert r["mass_fraction"]["H"] == pytest.approx(0.1119, abs=0.001)
    assert r["element_counts"] == {"H": 2, "O": 1}
    glucose = chem_parse("C6H12O6")
    assert glucose["formula_weight"] == pytest.approx(180.156, abs=0.05)


def test_chemformula_rejects_empty():
    from mcpserver.academic.chemformula_interface import chem_parse
    with pytest.raises(ValueError):
        chem_parse("  ")


def test_coolprop_real_compute():
    """CoolProp 真算（.venv 已装；其他环境缺包则跳过）。"""
    pytest.importorskip("CoolProp.CoolProp")
    from mcpserver.academic.coolprop_interface import coolprop_constant, coolprop_props
    r = coolprop_props("D", "T", 300, "P", 101325, "Water")
    assert r["ok"] is True and r["unit_system"] == "SI"
    assert r["value"] == pytest.approx(996.56, abs=1.0)
    crit = coolprop_constant("Tcrit", "Water")
    assert crit["value"] == pytest.approx(647.096, abs=0.5)


def test_coolprop_whitelist_rejects_typos():
    from mcpserver.academic.coolprop_interface import coolprop_props
    with pytest.raises(ValueError, match="白名单"):
        coolprop_props("Density", "T", 300, "P", 101325, "Water")
    with pytest.raises(ValueError):
        coolprop_props("D", "Temp", 300, "P", 101325, "Water")


# ------------------------------------------------------- 降级契约（只标注不否决）

def test_tespy_degradation_contract():
    """tespy 未装：探测返回 available=False；求解抛含 pip 提示的错误。"""
    from mcpserver.academic.tespy_interface import tespy_check, tespy_solve_network
    chk = tespy_check()
    assert chk["available"] in (True, False)  # 环境自适应
    if chk["available"]:
        pytest.skip("本环境已装 tespy，降级路径跳过")
    with pytest.raises(AcademicDependencyError, match="pip install tespy"):
        tespy_solve_network({"fluids": ["water"], "components": [],
                             "connections": []})


def test_tespy_spec_validation_before_dependency():
    """spec 非法时先报参数错误（不依赖 tespy 是否安装）。"""
    from mcpserver.academic.tespy_interface import tespy_solve_network
    with pytest.raises(ValueError, match="缺字段"):
        tespy_solve_network({"fluids": ["water"]})
    with pytest.raises(ValueError, match="白名单"):
        tespy_solve_network({
            "fluids": ["water"],
            "components": [{"type": "WarpDrive", "id": "w"}],
            "connections": []})


def test_slices_degradation_contract():
    from mcpserver.academic.slices_interface import slices_check
    chk = slices_check()
    if chk["available"]:
        pytest.skip("本环境已装 slices，降级路径跳过")
    assert "slices" in chk["missing"] or "pymatgen" in chk["missing"]
    from mcpserver.academic.slices_interface import slices_encode, slices_decode
    with pytest.raises(AcademicDependencyError, match="pip install"):
        slices_encode("any.cif")
    with pytest.raises(AcademicDependencyError, match="pip install"):
        slices_decode("SLICES string")


# ------------------------------------------------------------ MCP 注册链路

def test_academic_manifest_license_field():
    manifest = json.loads((ACADEMIC_DIR / "agent-manifest.json")
                          .read_text(encoding="utf-8"))
    assert manifest["agentType"] == "mcp"
    assert "license" in manifest and "MIT" in manifest["license"]
    commands = [c["command"] for c in
                manifest["capabilities"]["invocationCommands"]]
    assert {"academic_levels", "coolprop_props", "chem_parse",
            "tespy_solve_network", "slices_encode"} <= set(commands)


def test_registry_scan_and_unified_call():
    """注册链路 + unified_call 真算（Lumo 可调用验收）。"""
    from mcpserver.mcp_manager import MCPManager
    from mcpserver.mcp_registry import (
        clear_registry,
        get_service_instance,
        scan_and_register_mcp_agents,
    )
    clear_registry()
    try:
        assert "academic" in scan_and_register_mcp_agents("mcpserver")
        assert type(get_service_instance("academic")).__name__ == "AcademicBridge"

        manager = MCPManager()
        lv = json.loads(asyncio.run(manager.unified_call(
            "academic", {"tool_name": "academic_levels"})))
        assert lv["status"] == "ok"
        assert len(lv["result"]["packages"]) == 16

        chem = json.loads(asyncio.run(manager.unified_call(
            "academic", {"tool_name": "chem_parse", "formula": "H2O"})))
        assert chem["status"] == "ok"
        assert chem["result"]["formula_weight"] == pytest.approx(18.015, abs=0.01)
    finally:
        clear_registry()


def test_bridge_coolprop_end_to_end():
    pytest.importorskip("CoolProp.CoolProp")
    bridge = AcademicBridge()
    r = json.loads(asyncio.run(bridge.handle_handoff({
        "tool_name": "coolprop_props", "output": "D", "name1": "T",
        "prop1": 300, "name2": "P", "prop2": 101325, "fluid": "Water"})))
    assert r["status"] == "ok"
    assert r["result"]["value"] == pytest.approx(996.56, abs=1.0)
    bad = json.loads(asyncio.run(bridge.handle_handoff({
        "tool_name": "academic_fly"})))
    assert bad["status"] == "error"
