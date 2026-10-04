# -*- coding: utf-8 -*-
"""ChemMCP 纯转换工具（W63-04 · 落地三件之一）。

依据 docs/ChemMCP-授粉报告.md P1a：smiles2cas / smiles2formula 纯转换工具。
无 RDKit 依赖，用正则做 SMILES 元素解析；CAS 号查询无本地库，mock 并显式标注。

纯标准库。运行：python tools/chem_conversions.py
"""
from __future__ import annotations

import re

# 元素解析：识别大写字母开头（可带小写字母）的元素符号 + 括号内元素（忽略芳香小写前缀）
_ELEMENT = re.compile(r"([A-Z][a-z]?|\bBr\b|\bCl\b)")

# 芳香小写前缀（如苯环 c1ccccc1 里的小写 c）视作 C
_AROMATIC = re.compile(r"[a-z]")


def smiles2formula(smiles: str) -> str:
    """SMILES → 分子式（按元素计数，Hill 排序：C 在前，H 次之，其余字母序）。

    mock 标注：不处理环闭合/电荷/同位素，只做元素出现次数统计。
    """
    if not smiles:
        return ""
    # 芳香小写字母按 C 计
    s = _AROMATIC.sub("C", smiles)
    counts: dict[str, int] = {}
    for m in _ELEMENT.finditer(s):
        sym = m.group(0)
        # 简化：把 Br/Cl 也按单元素计（正则 [A-Z][a-z]? 已覆盖）
        counts[sym] = counts.get(sym, 0) + 1

    def _order(sym: str) -> tuple:
        if sym == "C":
            return (0, "")
        if sym == "H":
            return (1, "")
        return (2, sym)

    parts = []
    for sym in sorted(counts, key=_order):
        n = counts[sym]
        parts.append(f"{sym}{n if n > 1 else ''}")
    return "".join(parts)


def smiles2cas(smiles: str) -> str | None:
    """SMILES → CAS 号。

    mock 标注：无本地 CAS 数据库，无法真实解析；返回 None 并标注「待接 CAS 库」。
    """
    return None


if __name__ == "__main__":
    print("乙醇 CCO 分子式:", smiles2formula("CCO"))
    print("苯环 c1ccccc1 分子式:", smiles2formula("c1ccccc1"))
    print("SMILES→CAS (mock):", smiles2cas("CCO"))
