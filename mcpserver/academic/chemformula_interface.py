"""ChemFormula MODEL_INTERFACE — 化学式解析与计算（离线零外部依赖）。

上游：https://github.com/mol-radius/chemformula （MIT）
已耦合形态：mcpserver/adapters/chem_adapter/（源码拷贝，零修改），
本接口在其上加结构化返回 + fail-fast 校验。离线可跑（BENCHMARK 实测项）。
"""
from __future__ import annotations

from typing import Any

from mcpserver.adapters.chem_adapter import ChemFormula

MODEL_INTERFACE: dict[str, Any] = {
    "name": "chemformula",
    "package": "ChemFormula",
    "vendor_repo": "https://github.com/mol-radius/chemformula",
    "pip": "chemformula（本仓已 vendor 于 mcpserver/adapters/chem_adapter，无需安装）",
    "license": "MIT",
    "fusion_level": "耦合（已入仓）+ 本单 MODEL_INTERFACE 化",
    "description": "化学式解析：分子量/质量分数/元素计数/Hill 式/Unicode 式",
    "entrypoints": [
        {
            "command": "chem_parse",
            "params": {"formula": "化学式，如 H2O / (C6H5)CHCHCOOC2H5",
                       "charge": "电荷数（默认 0）", "name": "物质名（可选）"},
            "returns": {
                "formula_weight": "g/mol",
                "mass_fraction": "{元素: 质量分数}",
                "element_counts": "{元素: 原子数}",
                "hill_formula": "Hill 记数式",
                "unicode_formula": "Unicode 下标式",
            },
            "example": "chem_parse('H2O') → formula_weight=18.015, H=0.1119",
        },
    ],
    "runtime_deps": [],
    "degradation": "无需降级（vendor 源码随仓分发，纯标准库+casregnum 已内置）",
    "verified": "2026-08-23 离线实测：H2O=18.015 g/mol，H 质量分数 0.1119",
}


def chem_parse(formula: str, charge: int = 0,
               name: str | None = None) -> dict[str, Any]:
    """解析化学式 → 结构化物性（离线）。"""
    if not (formula or "").strip():
        raise ValueError("formula 不能为空")
    try:
        cf = ChemFormula(formula, charge=charge,
                         name=name) if name else ChemFormula(formula,
                                                             charge=charge)
    except Exception as e:
        raise ValueError(f"化学式解析失败 {formula!r}: {e}") from e
    return {
        "ok": True,
        "formula": formula,
        "formula_weight": round(cf.formula_weight, 6),
        "mass_fraction": {k: round(v, 6)
                          for k, v in dict(cf.mass_fraction).items()},
        "element_counts": dict(cf.element),
        "hill_formula": str(cf.hill_formula),
        "unicode_formula": cf.unicode,      # 'H₂O'
        "latex_formula": cf.latex,
        "charge": charge,
        "is_radioactive": bool(cf.radioactive),
        "source": MODEL_INTERFACE["package"],
    }
