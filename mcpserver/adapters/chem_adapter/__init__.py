"""chem_adapter —— 确定性化学计算适配层（Phase A1）。

源码来自上游 `ChemFormula`（Apache 2.0），原样复制、零修改：
- `core.py`  ← chemformula.py（ChemFormula 主类）
- `config.py` ← config.py
- `data/elements.py` ← elements.py（原子量数据，独立存放便于整体替换）

注意：上游 `core.py` 用 `from . import elements`、`data/elements.py` 用
`from .config import ...` 的相对导入，因此顶层 `elements.py` 是一层再导出桥，
`data/config.py` 是其相对导入所需的同级配置副本（均非改动上游内容）。

导出接口（SPEC 2.2）：ChemFormula / ChemFormulaString / ChemFormulaDict。
"""
from __future__ import annotations

from .core import ChemFormula, ChemFormulaDict, ChemFormulaString

__all__ = ["ChemFormula", "ChemFormulaString", "ChemFormulaDict"]