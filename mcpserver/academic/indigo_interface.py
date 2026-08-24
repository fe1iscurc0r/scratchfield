"""Indigo MODEL_INTERFACE — 通用化学信息学工具包（Lumo 科研数据底座 · E-01）。

上游：https://github.com/epam/Indigo （Apache-2.0，PyPI: epam-indigo）
核心入口 Indigo.loadMolecule / loadQueryMolecule + substructureMatcher：
SMILES 解析/分子量/分子式/规范 SMILES/子结构匹配。本仓 venv 实测真算可用
（苯分子量 78.114，阿司匹林 C9H8O4，子结构匹配 1 处）。
"""
from __future__ import annotations

from typing import Any

from mcpserver.academic.errors import require

MODEL_INTERFACE: dict[str, Any] = {
    "name": "indigo",
    "package": "Indigo",
    "vendor_repo": "https://github.com/epam/Indigo",
    "pip": "epam-indigo",
    "license": "Apache-2.0",
    "fusion_level": "MCP",
    "description": "通用化学信息学：SMILES 解析/分子量/分子式/规范 SMILES/子结构匹配/构象",
    "entrypoints": [
        {
            "command": "indigo_molinfo",
            "params": {"smiles": "SMILES 字符串，如 CC(=O)Oc1ccccc1C(=O)O"},
            "returns": {"molecular_weight": "float", "molecular_formula": "str",
                        "canonical_smiles": "str", "atoms": "int", "bonds": "int"},
            "example": "indigo_molinfo('CC(=O)Oc1ccccc1C(=O)O') → "
                       "{molecular_weight: 180.157, molecular_formula: 'C9H8O4'}",
        },
        {
            "command": "indigo_substructure",
            "params": {"query": "子结构 SMILES（可带通配，如 c1ccccc1）",
                       "target": "目标分子 SMILES"},
            "returns": {"match": "bool", "count": "int"},
            "example": "indigo_substructure('c1ccccc1', 'CC(=O)Oc1ccccc1C(=O)O') "
                       "→ {match: true, count: 1}",
        },
    ],
    "runtime_deps": [],
    "degradation": "未安装时抛 AcademicDependencyError（pip install epam-indigo，Windows 有 wheel）",
    "verified": "2026-08-23 本仓 .venv 实测：苯 78.114 g/mol、阿司匹林 C9H8O4、子结构匹配 1",
}


def _indigo() -> Any:
    """惰性加载 Indigo 单例（require 统一降级）。"""
    return require("indigo", "epam-indigo").Indigo()


def indigo_molinfo(smiles: str) -> dict[str, Any]:
    """SMILES → 分子基础信息（分子量/分子式/规范 SMILES/原子与键计数）。"""
    smiles = (smiles or "").strip()
    if not smiles:
        raise ValueError("smiles 不能为空，如 'c1ccccc1'")
    indigo = _indigo()
    try:
        mol = indigo.loadMolecule(smiles)
        mol.aromatize()
        weight = float(mol.molecularWeight())
        formula = str(mol.grossFormula()).replace(" ", "")
        canon = str(mol.canonicalSmiles())
    except Exception as e:
        raise ValueError(f"Indigo 解析 SMILES 失败（{smiles!r}）: {e}") from e
    if weight != weight or weight <= 0:  # NaN/非正 → 脏值拦截
        raise ValueError(f"Indigo 返回非正常分子量: {weight}")
    return {"ok": True, "molecular_weight": weight,
            "molecular_formula": formula, "canonical_smiles": canon,
            "atoms": mol.countAtoms(), "bonds": mol.countBonds(),
            "source": MODEL_INTERFACE["package"]}


def indigo_substructure(query: str, target: str) -> dict[str, Any]:
    """子结构匹配：query 是否出现在 target 中（返回匹配数）。"""
    query = (query or "").strip()
    target = (target or "").strip()
    if not query or not target:
        raise ValueError("query 与 target 均不能为空")
    indigo = _indigo()
    try:
        q = indigo.loadQueryMolecule(query)
        t = indigo.loadMolecule(target)
        matcher = indigo.substructureMatcher(t)
        count = int(matcher.countMatches(q))
    except Exception as e:
        raise ValueError(f"Indigo 子结构匹配失败: {e}") from e
    return {"ok": True, "match": count > 0, "count": count,
            "source": MODEL_INTERFACE["package"]}
