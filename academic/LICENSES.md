# LICENSES — academic 16 项目许可声明（SPEC-02 硬约束）

> 本目录仅沉淀各上游项目的**接口文档**（MODEL_INTERFACE.md），不含上游源码。
> 以下许可信息摘自各项目上游仓库/官方文档（采集于 2026-08）。
> 使用任一项目时，须遵守其上游 LICENSE 原文，本文件不替代上游许可。

| 项目 | 许可 | 上游声明要点 |
|------|------|--------------|
| thermo | MIT | CalebBell/thermo LICENSE.txt |
| CoolProp | MIT-like（灵活） | 官方：Commercial ok, Academic ok |
| tespy | MIT | Copyright (c) Francesco Witte |
| pycalphad | MIT | LICENSE.txt |
| Clapeyron.jl | MIT | ClapeyronThermo/Clapeyron.jl |
| PyXtal | MIT | MaterSim/PyXtal |
| SLICES | MIT* | README 声明；上游 LICENSE 全文待复核 |
| gemmi | MPLv2 或 LGPLv3（二选一） | ⚠️ 与"全白名单"口径不同：MPLv2 为文件级 copyleft，LGPLv3 为弱 copyleft。动态链接/调用通常不受传染，但分发修改版文件时须开源。使用前由用户确认 |
| ChemFormula | MIT | molshape/ChemFormula（PyPI badge） |
| hyalite | MIT | Psy-Fer/hyalite（注明为 Opal 的独立重实现，不复制其代码） |
| AffineGaps | Apache-2.0 | ashvardanian/affine-gaps |
| WaveBench | MIT | README 声明 |
| rp2daq | MIT | FilipDominec/rp2daq LICENSE |
| hololinked | BSD-3-Clause | hololinked-dev/hololinked |
| Pynite | MIT | JWock82/Pynite |
| FEMcy | 上游仓库许可* | 中转库未提取到 LICENSE 全文，使用前复核上游 |

\* = 标注项在集成/分发前需补一次上游 LICENSE 原文核对。

## 通用合规约定

1. 调用/引用这些项目的产出物（报告、论文）应保留相应项目的引用与许可致谢
   （各项目 MODEL_INTERFACE.md 末尾均给出引用建议）。
2. 不将上游源码提交进本仓库；如确需源码，在独立环境 `pip install` 获取。
3. gemmi 因许可特殊性，默认列为"文档就绪"，不自动安装/调用。
