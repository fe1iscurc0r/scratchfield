"""SLICES MODEL_INTERFACE — 晶体结构可逆字符串表示（重依赖只标注不否决）。

上游：https://github.com/shangzhao/Slices （LGPL-2.1；pip 包 slices 独立分发）
转换对：structure2SLICES（晶体→字符串）/ SLICES2structure（字符串→晶体
+预测能量 eV/atom）。依赖 tensorflow-cpu + m3gnet + pymatgen（版本钉死），
克隆中转库内无 slices 包本体，须 pip install slices。
"""
from __future__ import annotations

from typing import Any

from mcpserver.academic.errors import require

MODEL_INTERFACE: dict[str, Any] = {
    "name": "slices",
    "package": "SLICES",
    "vendor_repo": "https://github.com/shangzhao/Slices",
    "pip": "slices",
    "license": "LGPL-2.1",
    "fusion_level": "MCP",
    "description": "晶体结构 ↔ SLICES 字符串双向转换（逆向设计数据底座）",
    "entrypoints": [
        {
            "command": "slices_encode",
            "params": {"cif_path": "晶体结构 CIF 文件路径"},
            "returns": {"slices": "SLICES 字符串"},
            "example": "slices_encode('NdSiRu.cif')",
        },
        {
            "command": "slices_decode",
            "params": {"slices_str": "SLICES 字符串"},
            "returns": {"formula": "重构结构化学式",
                        "energy_per_atom": "预测能量 eV/atom（m3gnet）",
                        "fidelity_note": "往返保真见 BENCHMARK.md"},
        },
        {
            "command": "slices_check",
            "params": {},
            "returns": {"available": "bool", "missing": "[包名]"},
        },
    ],
    "runtime_deps": ["tensorflow-cpu", "m3gnet", "pymatgen",
                     "smact/ase 版本钉死（GPU 非必需，CPU 可跑）"],
    "degradation": "pip install slices pymatgen 即恢复；重依赖只标注不否决（工单口径）",
    "verified": "2026-08-23 本仓 .venv 未装 slices，降级契约实测通过",
}


def slices_check() -> dict[str, Any]:
    """依赖探测：slices + pymatgen 逐个点名缺失项。"""
    missing = []
    for mod, pip_name in (("slices.core", "slices"), ("pymatgen.core", "pymatgen")):
        try:
            __import__(mod)
        except ImportError:
            missing.append(pip_name)
    if missing:
        return {"available": False, "missing": missing}
    return {"available": True, "missing": []}


def _backend():
    slices_mod = require("slices.core", "slices",
                         "重依赖链见 MODEL_INTERFACE.runtime_deps")
    require("pymatgen.core", "pymatgen")
    return slices_mod.SLICES()


def slices_encode(cif_path: str) -> dict[str, Any]:
    """晶体（CIF）→ SLICES 字符串。"""
    if not (cif_path or "").strip():
        raise ValueError("cif_path 不能为空")
    require("pymatgen.core", "pymatgen")  # 前置探测，友好报错
    backend = _backend()
    from pymatgen.core import Structure
    structure = Structure.from_file(filename=cif_path)
    slices_str = backend.structure2SLICES(structure)
    return {"ok": True, "cif_path": cif_path, "slices": slices_str,
            "source": MODEL_INTERFACE["package"]}


def slices_decode(slices_str: str) -> dict[str, Any]:
    """SLICES 字符串 → 重构晶体（化学式 + 预测能量）。"""
    if not (slices_str or "").strip():
        raise ValueError("slices_str 不能为空")
    backend = _backend()
    structure, energy_per_atom = backend.SLICES2structure(slices_str)
    return {"ok": True,
            "formula": structure.composition.reduced_formula,
            "energy_per_atom": float(energy_per_atom),
            "source": MODEL_INTERFACE["package"]}
