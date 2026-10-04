# MODEL_INTERFACE: tespy (TESPy)

- 上游仓库: https://github.com/oemof/tespy
- 许可证: MIT（Copyright Francesco Witte；引用须保留，见 ../LICENSES.md）
- 安装: `pip install tespy`（依赖 CoolProp）
- Python 模块名: `tespy`

## 算法定位

热工系统稳态仿真框架（Thermal Engineering Systems in Python）：电厂（含 ORC）、
热泵、制冷机、工业过程能量衡算、区域供热、HVAC。组件式架构 + 设计点/变工况
双模式 + 㶲分析 + pymoo 优化接口。oemof 框架成员。

## 核心 API

```python
from tespy.networks import Network
from tespy.components import Sink, Source, Turbine, Pump, Compressor, \
    HeatExchanger, Pipe, Mixer, Splitter, Drum
from tespy.connections import Connection

nw = Network(fluids=['water'], p_unit='bar', T_unit='C')
# 组件实例化 → Connection 串联拓扑 → 设参 → nw.solve('design')
# 变工况: nw.solve('offdesign', design_path=...)
# 㶲分析: tespy.tools.fluid_properties / ExergyAnalysis
```

组件覆盖：透平、泵、压缩机、换热器（多种变体）、管道、混合器/分流器、汽包等。

## 数据格式

- 输入: Python 对象拓扑（组件 + 连接），参数以 SI 或自定义单位设定
- 输出: 收敛后的网络对象，各连接点质量流量/焓/熵/㶲
- 设计点结果可导出为目录（design_path）供变工况复用

## Lumo 工作台用途

- 生物质热电联产 / ORC 余热回收流程的能效预评估
- 热泵干燥系统的 COP 估算

## 引用

```bibtex
@article{Witte2020,
  doi = {10.21105/joss.02178}, year = {2020}, volume = {5}, number = {49},
  pages = {2178}, author = {Francesco Witte and Ilja Tuschy},
  title = {{TESPy}: {T}hermal {E}ngineering {S}ystems in {P}ython},
  journal = {Journal of Open Source Software}}
```
