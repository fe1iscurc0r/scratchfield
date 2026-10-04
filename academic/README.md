# academic/ — 16 项目模型弹药索引（SPEC-02 Phase 1）

> 来源：云端 545M academic 中转库（GitHub: fe1iscurc0r/scratchpad-knowledge）
> 每项一个子目录，核心交付物为 `MODEL_INTERFACE.md`（算法定位 / 核心 API / 数据格式 / 用途）。
> 许可声明见 [LICENSES.md](LICENSES.md)。**不内嵌上游源码**，只沉淀接口文档。

| # | 项目 | 领域 | 接入状态 | 调用方式 |
|---|------|------|----------|----------|
| 1 | [thermo](thermo/MODEL_INTERFACE.md) | 物性/热力学 | ✅ 已接入 | `pip install thermo` |
| 2 | [CoolProp](CoolProp/MODEL_INTERFACE.md) | 热物性数据库 | ✅ 已接入 | `pip install coolprop` |
| 3 | [tespy](tespy/MODEL_INTERFACE.md) | 热工系统仿真 | 📖 文档就绪 | `pip install tespy`（重依赖，按需） |
| 4 | [pycalphad](pycalphad/MODEL_INTERFACE.md) | CALPHAD 相图 | 📖 文档就绪 | `pip install pycalphad` |
| 5 | [Clapeyron.jl](Clapeyron.jl/MODEL_INTERFACE.md) | 状态方程 | 📖 文档就绪 | Julia 运行时，按需 |
| 6 | [PyXtal](PyXtal/MODEL_INTERFACE.md) | 晶体结构生成 | 📖 文档就绪 | `pip install pyxtal` |
| 7 | [SLICES](SLICES/MODEL_INTERFACE.md) | 晶体字符串表示 | 📖 文档就绪 | 独立 conda 环境（重依赖） |
| 8 | [gemmi](gemmi/MODEL_INTERFACE.md) | 晶体学文件 | 📖 文档就绪 | `pip install gemmi` |
| 9 | [ChemFormula](ChemFormula/MODEL_INTERFACE.md) | 化学式/计量 | ✅ 已接入 | `pip install chemformula` |
| 10 | [hyalite](hyalite/MODEL_INTERFACE.md) | 序列比对(Rust) | 📖 文档就绪 | Rust 生态，低优先 |
| 11 | [AffineGaps](AffineGaps/MODEL_INTERFACE.md) | 序列比对(Py) | ✅ 已接入 | `pip install affine-gaps` |
| 12 | [WaveBench](WaveBench/MODEL_INTERFACE.md) | 仪器测量台 | 📖 文档就绪 | 独立环境，需硬件 |
| 13 | [rp2daq](rp2daq/MODEL_INTERFACE.md) | 微控制器采集 | 📖 文档就绪 | 需 RP2040 硬件 |
| 14 | [hololinked](hololinked/MODEL_INTERFACE.md) | 仪器 SCADA/IoT | 📖 文档就绪 | `pip install hololinked` |
| 15 | [Pynite](Pynite/MODEL_INTERFACE.md) | 结构有限元 | ✅ 已接入 | `pip install PyniteFEA` |
| 16 | [FEMcy](FEMcy/MODEL_INTERFACE.md) | 连续体有限元 | 📖 文档就绪 | 需 taichi + .inp |

接入调用桥见 `mcpserver/material_science/academic_bridge/`
（工具：`academic_status` / `academic_call`，按需在 `materialscience_agent` 注册）。

✅ = 已在当前环境实测可调用（≥5 项满足 Phase 1 验收）；
📖 = 文档弹药就绪，依赖安装或硬件到位即可接入。
