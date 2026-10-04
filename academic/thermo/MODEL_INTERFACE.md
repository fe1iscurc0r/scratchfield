# MODEL_INTERFACE: thermo (ChEDL)

- 上游仓库: https://github.com/CalebBell/thermo
- 许可证: MIT（引用须保留，见 ../LICENSES.md）
- 安装: `pip install thermo`（纯 Python，依赖 chemicals/fluids/pandas/scipy）
- Python 模块名: `thermo`

## 算法定位

化学品常数检索 + 温压依赖物性计算（热力学与传递性质），含混合物相平衡。
属于 ChEDL（Chemical Engineering Design Library）的物性分量，内置大量实验关联式。

## 核心 API

```python
# 简单接口：单组分
from thermo.chemical import Chemical
tol = Chemical('toluene')          # 名称/化学式检索，默认 298.15 K, 101325 Pa
tol.Tm, tol.Tb, tol.Tc             # 熔点/沸点/临界温度 [K]
tol.rho, tol.Cp, tol.k, tol.mu     # 密度/热容/导热/黏度（自动判相）
tol.rhog, tol.Cpl                  # 指定假想相取物性（后缀 l/g/s）
tol.calculate(T=310, P=2e6)        # 快速换工况
Chemical('toluene').VaporPressure.solve_property(2e5)  # 反解温度

# 简单接口：混合物
from thermo.chemical import Mixture
vodka = Mixture(['water', 'ethanol'], Vfls=[.6, .4], T=300, P=1e5)

# 严格接口：状态方程闪蒸（PR EOS）
from thermo import ChemicalConstantsPackage, PRMIX, CEOSLiquid, CEOSGas, FlashPureVLS
constants, correlations = ChemicalConstantsPackage.from_IDs(['decane'])
eos_kwargs = dict(Tcs=constants.Tcs, Pcs=constants.Pcs, omegas=constants.omegas)
liquid = CEOSLiquid(PRMIX, HeatCapacityGases=correlations.HeatCapacityGases, eos_kwargs=eos_kwargs)
gas = CEOSGas(PRMIX, HeatCapacityGases=correlations.HeatCapacityGases, eos_kwargs=eos_kwargs)
flasher = FlashPureVLS(constants, correlations, gas=gas, liquids=[liquid], solids=[])
res = flasher.flash(T=300, P=1e5)  # res.H()/S()/rho()/Cp()...
```

## 数据格式

- 输入: 化学品名称/化学式（内部数据库解析为 CAS）；状态点全部 SI 单位（K, Pa, J/mol）
- 输出: float（物性）或闪蒸结果对象（H, S, V, rho, Cp, 声速, JT 系数等）
- 交互参数库: `thermo.interaction_parameters.IPDB`（kij 矩阵）

## Lumo 工作台用途

- 溶剂/前驱体物性速查（生物质热解工艺的载气、萃取溶剂）
- 热解气相产物（甲烷/乙烷/氮混合气）露点与相平衡估算

## 引用

Caleb Bell and Contributors (2016-2024). Thermo: Chemical properties component of
Chemical Engineering Design Library (ChEDL). https://github.com/CalebBell/thermo
