# MODEL_INTERFACE: ChemFormula

- 上游仓库: https://github.com/molshape/ChemFormula
- 许可证: MIT（PyPI badge 标注；引用须保留，见 ../LICENSES.md）
- 安装: `pip install chemformula`（纯 Python，依赖 casregnum）
- Python 模块名: `chemformula`

## 算法定位

化学式解析与化学计量计算：解析复杂化学式（含括号/结晶水/电荷/同位素），
计算式量、元素质量分数，格式化输出（LaTeX/HTML/Unicode/Hill 式），
支持化学式四则运算与比较排序。原子量基于 IUPAC 最新推荐值。

## 核心 API

```python
from chemformula import ChemFormula

cu = ChemFormula("[Cu(NH3)4]SO4.H2O")
cu.formula_weight        # 式量 [g/mol]
cu.mass_fractions        # {'Cu': ..., 'N': ..., ...} 各元素质量分数
cu.element               # {'Cu': 1, 'N': 4, 'S': 1, 'O': 5, 'H': 14}
cu.sum_formula           # 展开括号的总式（ChemFormula 对象）
cu.hill_formula.latex    # Hill 记法 + LaTeX
cu.latex, cu.html, cu.unicode

# 化学计量运算
ATP = ChemFormula("C10H12N5O13P3", -4)
water = ChemFormula("H2O")
AMP = ATP + 2 * water - 2 * ChemFormula("H2PO4", -1)

# 放射性/电荷判定
ChemFormula("Ca(UO2)2(SiO3OH)2.(H2O)5").is_radioactive  # True
```

## 数据格式

- 输入: 化学式字符串（括号、`.`/`*` 结晶水、电荷、同位素需开关）
- 输出: float（式量）、dict（元素计数/质量分数）、格式化字符串
- 氢同位素需 `chemformula.config.AllowHydrogenIsotopes = True`

## Lumo 工作台用途

- 生物质前驱体/灰分组成的式量与元素分析换算（实验数据标准化）
- 论文中化学式的 LaTeX 排版自动化

## 引用

molshape/ChemFormula, PyPI: chemformula. 原子量数据来源见上游仓库
misc/AtWt23.html（IUPAC CIAAW 2016-2025 推荐值）。
