"""academic — Lumo 科研数据底座（W-09：scratchpad-knowledge academic 16 包融合）。

- levels.py：16 包融合层级总表（单一事实源，MCP/Skill/融合参考/耦合/基础设施）
- *_interface.py：高价值纯库 MODEL_INTERFACE（CoolProp/ChemFormula/tespy/SLICES）
- bridge.py：AcademicBridge MCP 服务（Lumo 经 mcpserver 可调用全部接口）

文档：docs/academic/{DATASET,BENCHMARK,MODEL_INTERFACE}.md
硬约束：不碰 NEKO/apiserver 主流程；重运行依赖（GPU/付费 API）只标注不否决。
"""
from __future__ import annotations

from typing import Any

from mcpserver.academic.levels import FUSION_LEVELS, levels_summary

# 已封装 MODEL_INTERFACE 的模块（注册表：name → (module, interface)）
_REGISTRY: dict[str, tuple[str, str]] = {
    "coolprop": ("mcpserver.academic.coolprop_interface", "MODEL_INTERFACE"),
    "chemformula": ("mcpserver.academic.chemformula_interface", "MODEL_INTERFACE"),
    "tespy": ("mcpserver.academic.tespy_interface", "MODEL_INTERFACE"),
    "slices": ("mcpserver.academic.slices_interface", "MODEL_INTERFACE"),
    "indigo": ("mcpserver.academic.indigo_interface", "MODEL_INTERFACE"),
    "chembl": ("mcpserver.academic.chembl_interface", "MODEL_INTERFACE"),
}


def list_interfaces() -> list[str]:
    """已封装 MODEL_INTERFACE 名单（验收：≥4）。"""
    return sorted(_REGISTRY.keys())


def get_interfaces() -> dict[str, dict[str, Any]]:
    """name → MODEL_INTERFACE 元数据（惰性导入）。"""
    import importlib
    out: dict[str, dict[str, Any]] = {}
    for name, (module, attr) in _REGISTRY.items():
        out[name] = getattr(importlib.import_module(module), attr)
    return out


def get_levels() -> dict[str, dict[str, Any]]:
    """16 包层级总表（浅拷贝防误改）。"""
    return {k: dict(v) for k, v in FUSION_LEVELS.items()}


__all__ = ["list_interfaces", "get_interfaces", "get_levels",
           "levels_summary", "FUSION_LEVELS"]
