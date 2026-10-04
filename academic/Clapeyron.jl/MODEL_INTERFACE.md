# MODEL_INTERFACE: Clapeyron.jl

- 上游仓库: https://github.com/ClapeyronThermo/Clapeyron.jl
- 许可证: MIT（引用须保留，见 ../LICENSES.md）
- 安装: Julia `Pkg> add Clapeyron`（Julia ≥ 1.10）；Python 侧 `pip install pyclapeyron`（JuliaCall 桥）
- 模块名: Julia `Clapeyron` / Python `pyclapeyron`

## 算法定位

大规模状态方程（EOS）工具库 + 自定义模型框架。覆盖 PR、SRK、PC-SAFT、
CPA、SAFT 家族等，支持纯组分/混合物物性、相包线、Pxy/Txy 图、pT 等值线。

## 核心 API

```julia
using Clapeyron
model = PR(["ethanol","water"])          # Peng-Robinson 混合物
p = saturation_pressure(model, 400.0)    # 饱和压力
T = saturation_temperature(model, 1.0e5) # 泡点温度
v = Clapeyron.volume(model, 300.0, 1e5)  # 摩尔体积
Cp = isobaric_heat_capacity(model, 300.0, 1e5)
```

```python
# Python 桥（pyclapeyron，基于 juliacall）
import pyclapeyron
pyclapeyron.init()                       # 启动 Julia 运行时
model = pyclapeyron.PR(["water"])
```

## 数据格式

- 输入: 组分名列表（内置数据库自动取参数，含关联项如缔合/极性）
- 输出: Julia/Python 数值（SI）
- 注意: 首调用需编译/加载，冷启动约数十秒（Julia 运行时）

## Lumo 工作台用途

- 热解油组分（酚类/呋喃类/水）相平衡的高级 EOS 计算
- 与 thermo（ChEDL）互补：thermo 查常数，Clapeyron 算高级 EOS

## 引用

Walker, P.J., Yew, H.-W., Riedemann, A. Clapeyron.jl: An Extensible,
Open-Source Fluid Thermodynamics Toolkit. Ind. Eng. Chem. Res. 61(20),
7130-7153 (2022). doi:10.1021/acs.iecr.2c00326
