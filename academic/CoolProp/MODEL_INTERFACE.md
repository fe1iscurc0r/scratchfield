# MODEL_INTERFACE: CoolProp

- 上游仓库: https://github.com/CoolProp/CoolProp
- 许可证: MIT-like（灵活许可，商用/学术均可；引用须保留，见 ../LICENSES.md）
- 安装: `pip install coolprop`（预编译二进制，Windows 直接可用）
- Python 模块名: `CoolProp`

## 算法定位

高精度热物性数据库 + 多语言包装器，开源的 REFPROP 替代品。
覆盖纯工质多参数亥姆霍兹状态方程（HEOS）、混合物、制冷循环辅助函数。

## 核心 API

```python
from CoolProp.CoolProp import PropsSI
PropsSI('D', 'T', 300, 'P', 101325, 'Water')   # 密度 [kg/m^3]
PropsSI('C', 'T', 300, 'P', 101325, 'Water')   # 定压热容 [J/kg/K]
PropsSI('H', 'T', 373.15, 'Q', 1, 'Water')     # 饱和蒸汽焓
PropsSI('Tcrit', '', 0, '', 0, 'CO2')          # 临界参数
# 第二参数对可用: T(温) P(压) D(密度) H(焓) S(熵) Q(干度) 等任意两个

from CoolProp.CoolProp import get_global_param_string
get_global_param_string('FluidsList')           # 支持的工质清单
```

## 数据格式

- 输入: 输出属性名 + 两个状态变量名/值 + 工质名（字符串），全 SI 单位
- 输出: float；查不到时抛 ValueError（建议调用方 try/except）
- 支持纯工质 ~120 种 + 预定义混合气（Air, Air.moist 等）

## Lumo 工作台用途

- 热解/干燥工艺的蒸汽表、CO2 超临界参数速查
- 为 tespy 系统仿真提供工质后端

## 引用

Bell, I.H., Wronski, J., Quoilin, S., Lemort, V. Pure and Pseudo-pure Fluid
Thermophysical Property Evaluation and the Open-Source Thermophysical Property
Library CoolProp. Ind. Eng. Chem. Res. 53(6), 2498-2508 (2014).
