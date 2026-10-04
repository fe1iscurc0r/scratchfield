# MODEL_INTERFACE: pycalphad

- 上游仓库: https://github.com/pycalphad/pycalphad
- 许可证: MIT（引用须保留，见 ../LICENSES.md）
- 安装: `pip install pycalphad`（依赖 numpy/scipy/symengine/xarray）
- Python 模块名: `pycalphad`

## 算法定位

CALPHAD 法相图计算与相平衡：读取 Thermo-Calc TDB 热力学数据库，
求解多组分多相 Gibbs 能最小化问题，绘制相图（二元/三元截面）。

## 核心 API

```python
from pycalphad import Database, equilibrium, binplot, ternplot
dbf = Database('alfe_sei.TDB')          # 读 TDB 热力学数据库
dbf.elements                             # 数据库含的元素
dbf.phases.keys()                        # 数据库含的相

# 平衡计算：指定体系/组分/状态变量
eq = equilibrium(dbf, ['AL','FE','VA'], {'ALFE2': 0.5},
                 {'P': 101325, 'T': (500, 2000, 100), 'N': 1})
eq.GM                                    # 摩尔 Gibbs 能
eq.Phase                                 # 稳定相

# 相图绘制
my_map = binplot(dbf, ['AL','FE','VA'], {'N': 1, 'P': 101325, 'T': (300, 1200, 10)})
```

## 数据格式

- 输入: TDB 文件（Thermo-Calc 文本格式热力学数据库，社区有开源库）
- 输出: xarray Dataset（相分数、成分、Gibbs 能等）；可直接喂 pandas/绘图
- 状态变量: P [Pa]、T [K]、N（摩尔数）、组分摩尔分数

## Lumo 工作台用途

- 灰分体系（SiO2-Al2O3-CaO 等）相平衡初筛需自备/寻找开源 TDB
- 合金/催化剂载体相图辅助分析

## 引用

Otis, R. & Liu, Z.-K. (2017). pycalphad: CALPHAD-based Computational
Thermodynamics in Python. Journal of Open Research Software, 5(1), p.1.
DOI: http://doi.org/10.5334/jors.140
