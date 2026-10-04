# MODEL_INTERFACE: Pynite

- 上游仓库: https://github.com/JWock82/Pynite
- 许可证: MIT（README/仓库徽章；引用须保留，见 ../LICENSES.md）
- 安装: `pip install PyniteFEA[all]`（核心依赖 numpy/scipy）
- Python 模块名: `Pynite`

## 算法定位

易用的弹性 3D 结构有限元分析库：静力分析、P-Δ 分析、模态分析、
钢框架非线性推覆分析；梁/板单元（DKMQ 四边形板、矩形板）、弹簧单元/支座、
荷载工况与组合、剪力/弯矩/挠度结果与图表、PDF 报告。

## 核心 API

```python
from Pynite import FEModel3D

model = FEModel3D()
model.add_node('N1', 0, 0, 0); model.add_node('N2', 10, 0, 0)
model.add_member('M1', 'N1', 'N2', 'W12X26')   # 或自定义截面属性
model.add_def_support('N1', True, True, True, True, True, True)
model.add_member_dist_load('M1', 'Case1', -1, -1, 0, 10)
model.add_load_combo('Combo1', {'Case1': 1.4})
model.analyze()
model.get_node_reactions('N1', 'Combo1')
model.get_member_results('M1', 'Combo1')        # 剪力/弯矩/挠度数组
```

## 数据格式

- 输入: 节点坐标、杆件（内置型钢库或自定义截面）、支座、荷载工况
- 输出: 反力、内力数组、位移；可渲染变形图（pyvista）、导出 PDF/HTML 报告
- 单位制自定义（内部一致即可）

## Lumo 工作台用途

- 实验装置/支架/夹具的结构强度快速校核
- 材料力学课程/毕设的梁弯曲数值对照实验

## 引用

Wock, J. W. Pynite: Simple Finite Element Analysis in Python.
GitHub: JWock82/Pynite. MIT License. 文档: https://pynite.readthedocs.io
