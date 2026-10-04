# MODEL_INTERFACE: PyXtal

- 上游仓库: https://github.com/MaterSim/PyXtal
- 许可证: MIT（引用须保留，见 ../LICENSES.md）
- 安装: `pip install pyxtal`（依赖 numpy/scipy，可选 pymatgen/ASE 做格式互转）
- Python 模块名: `pyxtal`

## 算法定位

晶体结构生成与对称性分析：给定空间群 + 化学计量比随机生成原子/分子晶体
（0-3D），子群/超群对称关系操作，内置几何优化，粉末 XRD 模拟。

## 核心 API

```python
from pyxtal import PyXtal
c = PyXtal()
c.from_random(3, 36, ['H2O'], [4])       # 3D, 空间群36, 4个水分子
c.to_file('output.cif')                   # 导出 CIF（也支持 POSCAR/xsd 等）

# 对称信息
c.valid                                    # 是否有效结构
c.get_1D_diffraction()                     # 1D XRD 谱
# Wyckoff 位置、位点对称、国际符号均可查询
```

## 数据格式

- 输入: 维度(0-3)、空间群号(1-230)、物种列表、原子数列表；可指定体积/键长约束
- 输出: PyXtal 结构对象；CIF/VASP/xsd/POSCAR 文件（pymatgen/ASE 中转）
- XRD: 2θ-强度数组

## Lumo 工作台用途

- 晶体材料候选结构的对称性约束生成
- 实验 XRD 图谱的物相初判辅助（模拟对照）

## 引用

Fredericks S, Parrish K, Sayer D, Zhu Q (2021). PyXtal: a Python Library for
Crystal Structure Generation and Symmetry Analysis. Computer Physics
Communications, 261, 107810. doi:10.1016/j.cpc.2020.107810
