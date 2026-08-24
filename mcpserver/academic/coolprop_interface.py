"""CoolProp MODEL_INTERFACE — 工业级热物性计算（Lumo 科研数据底座）。

上游：https://github.com/CoolProp/CoolProp （MIT，PyPI: coolprop）
核心入口 CoolProp.PropsSI：双参形式（流体常量）/ 六参形式（两点定态），
SI 单位制。本接口加白名单校验 + 结构化返回（value/unit_system/source）。
"""
from __future__ import annotations

from typing import Any

from mcpserver.academic.errors import require

MODEL_INTERFACE: dict[str, Any] = {
    "name": "coolprop",
    "package": "CoolProp",
    "vendor_repo": "https://github.com/CoolProp/CoolProp",
    "pip": "coolprop",
    "license": "MIT",
    "fusion_level": "MCP",
    "description": "热物性计算：给定两独立态量（如 T,P）求任意物性（密度/焓/熵/…）",
    "entrypoints": [
        {
            "command": "coolprop_props",
            "params": {
                "output": "物性名，如 D/H/S/T/P/U/Cpmass/V/Q",
                "name1": "第一态量名（P/T/H/S/Q）",
                "prop1": "第一态量数值（SI）",
                "name2": "第二态量名",
                "prop2": "第二态量数值（SI）",
                "fluid": "流体名，如 Water / HEOS::Water[0.5]&Ethanol[0.5]",
            },
            "returns": {"value": "float（SI 单位制）", "unit_system": "SI"},
            "example": "coolprop_props('D', 'T', 300, 'P', 101325, 'Water')"
                       " → 996.56 kg/m³",
        },
        {
            "command": "coolprop_constant",
            "params": {"output": "常量名，如 Tcrit/Pcrit/M/RhoCritical",
                       "fluid": "流体名"},
            "returns": {"value": "float"},
            "example": "coolprop_constant('Tcrit', 'Water') → 647.096 K",
        },
    ],
    "runtime_deps": [],
    "degradation": "未安装时抛 AcademicDependencyError（pip install coolprop）",
    "verified": "2026-08-23 本仓 .venv 实测：D@300K/1atm=996.56，Tcrit=647.096",
}

# 常用输出/态量白名单（拦截拼错，报错即恢复提示）
_KNOWN_OUTPUTS = {"D", "H", "S", "T", "P", "U", "Cpmass", "Cp0mass",
                  "Cvmass", "V", "Q", "Vmass", "L", "SRSGas", "Z"}
_KNOWN_STATE = {"P", "T", "H", "S", "Q", "U", "D"}


def coolprop_props(output: str, name1: str, prop1: float,
                   name2: str, prop2: float, fluid: str) -> dict[str, Any]:
    """六参形式：两点定态求物性（SI）。"""
    for field, val, known in (
            ("output", output, _KNOWN_OUTPUTS),
            ("name1", name1, _KNOWN_STATE),
            ("name2", name2, _KNOWN_STATE)):
        if val not in known:
            raise ValueError(
                f"{field}={val!r} 不在白名单 {sorted(known)}"
                f"（CoolProp 全量键见官方文档，白名单防拼错）")
    if not fluid:
        raise ValueError("fluid 不能为空，如 'Water'")
    cp = require("CoolProp.CoolProp", "coolprop")
    try:
        value = float(cp.PropsSI(output, name1, float(prop1),
                                 name2, float(prop2), fluid))
    except Exception as e:
        raise ValueError(f"CoolProp 计算失败（检查流体名/态量区间）: {e}") from e
    if value != value or value in (float("inf"), float("-inf")):  # NaN/Inf
        raise ValueError(f"CoolProp 返回非有限值（态量可能在两相区外）: {value}")
    return {"ok": True, "value": value, "unit_system": "SI",
            "source": MODEL_INTERFACE["package"]}


def coolprop_constant(output: str, fluid: str) -> dict[str, Any]:
    """双参形式：流体临界常量等（SI）。"""
    if not fluid:
        raise ValueError("fluid 不能为空")
    cp = require("CoolProp.CoolProp", "coolprop")
    try:
        value = float(cp.PropsSI(output, fluid))
    except Exception as e:
        raise ValueError(f"CoolProp 常量查询失败: {e}") from e
    return {"ok": True, "value": value, "unit_system": "SI",
            "source": MODEL_INTERFACE["package"]}
