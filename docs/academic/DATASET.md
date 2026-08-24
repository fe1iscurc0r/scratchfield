# academic 16 包数据集清单（DATASET）

> W-09 · 2026-08-23 · 数据来源：scratchpad-knowledge/_readme_dump/*.txt（16 份全量
> README dump）+ FUSION_REPORT.md 初评 + 本仓落地实况。
> 层级口径与 scratchpad-knowledge/TRAE_PROMPT.md 一致：MCP / Skill / 融合参考 /
> 耦合 / 基础设施。单一事实源为 `mcpserver/academic/levels.py`（本文件是渲染视图）。

## 层级汇总

| 层级 | 数量 | 包 |
| --- | --- | --- |
| MCP（可调用/候选） | 4 | CoolProp✦、tespy✦、SLICES✦、thermo |
| 耦合（源码入仓） | 4 | ChemFormula✦、AffineGaps、Pynite、FEMcy |
| 融合参考 | 4 | Clapeyron.jl、PyXtal、pycalphad、hyalite |
| 基础设施（独立部署） | 4 | gemmi、WaveBench、rp2daq、hololinked |

✦ = 本单已封装 MODEL_INTERFACE（Lumo 可调用，共 4 个，另有 thermo 为候选未封装）。

## 逐包清单

| # | 包 | 定位 | 层级 | License | 直调方式 | 硬依赖（只标注不否决） | 本仓状态 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | CoolProp | 工业级热物性库（REFPROP 开源替代） | MCP | MIT | `pip install coolprop` → `PropsSI` | 无 | ✦ 已封装真算可用（venv 实测 996.56 kg/m³@300K） |
| 2 | tespy | 热力系统组件网络仿真（电厂/ORC/热泵） | MCP | MIT | `pip install tespy` → `Network` | 物性后端可用 CoolProp | ✦ 已封装；未装时明确降级 |
| 3 | SLICES | 晶体结构↔可逆字符串 + 逆向设计 | MCP | LGPL-2.1 | `pip install slices`（克隆无包本体） | tensorflow-cpu/m3gnet/pymatgen 版本钉死 | ✦ 已封装；重依赖降级契约 |
| 4 | thermo | 化工物性（常数+T/P 依赖+相平衡） | MCP(候选) | MIT | `pip install thermo` | pandas 生态 | 未封装（与 CoolProp 同构，下一批） |
| 5 | ChemFormula | 化学式解析/分子量/化学式算术 | 耦合 | MIT | 已 vendor：`mcpserver/adapters/chem_adapter` | 无（casregnum 已内置） | ✦ vendor+接口化，离线真算 18.015 g/mol |
| 6 | AffineGaps | 仿射空位序列比对（修正 Gotoh 数学） | 耦合 | Apache-2.0 | 已 vendor：`mcpserver/adapters/bio_adapter/align.py` | numpy（numba 可选） | 已耦合（bio_adapter） |
| 7 | Pynite | 3D 弹性 FEM（框架/板/模态/pushover） | 耦合(候选) | MIT | `pip install PyniteFEA` | numpy/scipy | knowledge-base 仅残留占位，待正式耦合 |
| 8 | FEMcy | Taichi 并行有限元（CPU/GPU） | 耦合(候选) | MIT | 无 pip，需源码改造 | taichi/numpy/scipy | 脚本式入口需库化改造 |
| 9 | Clapeyron.jl | Julia 热力学 EoS 框架 | 融合参考 | MIT | 不可直调（Julia≥1.10） | Julia | pyclapeyron 桥可后评估 |
| 10 | PyXtal | 晶体随机生成（Wyckoff 位）+XRD | 融合参考 | MIT | `pip install pyxtal` | pymatgen/ase/spglib | 未封装（依赖链重） |
| 11 | pycalphad | CALPHAD 相图（TDB+Gibbs 最小化） | 融合参考 | MIT | `pip install pycalphad` | Cython wheel 自带 | 未封装（相图底座候选） |
| 12 | hyalite | 纯 Rust 精确 SIMD 序列比对 | 融合参考 | MIT | 不可直调（Rust MSRV 1.85） | Rust 工具链 | 与 AffineGaps 职能重叠（后者已耦合） |
| 13 | gemmi | 晶体学文件格式（mmCIF/PDB/MTZ/MRC） | 基础设施 | MPL-2.0 或 LGPL-3.0 | `pip install gemmi` | 无 | 独立服务候选；文件级 copyleft 注意分发边界 |
| 14 | WaveBench | SCPI 仪器自动化台架（自带 HTTP MCP） | 基础设施 | MIT | 源码部署，`--fake` 可离线 | SCPI 仪器 | 独立台架，接仪器后直挂 mcpserver |
| 15 | rp2daq | 树莓派 Pico 数据采集/控制 | 基础设施 | MIT | `pip install rp2daq` | RP2040 硬件+固件 | 平台依赖，独立部署 |
| 16 | hololinked | W3C WoT 设备互操作框架 | 基础设施 | **待核**（dump 无许可文本） | `pip install hololinked` | aiomqtt（MQTT 时） | 融合前须核上游 LICENSE |
| 17 | Indigo | 通用化学信息学（SMILES/子结构/构象） | MCP | Apache-2.0 | `pip install epam-indigo` → `Indigo().loadMolecule()` | 无（Windows 有 wheel） | ✦ 已封装真算可用（venv 实测：阿司匹林 C9H8O4/180.16） |
| 18 | ChEMBL | 欧洲生物活性分子库（CHEMBL_ID/相似检索） | MCP | Apache-2.0 | `pip install chembl-webresource-client` → `new_client` | 在线 EBI REST（requests-cache 自动缓存） | ✦ 已封装在线实测（CHEMBL25=ASPIRIN，相似检索 3 hits） |
| 19 | scikit-fingerprints | 分子指纹库（ECFP/Morgan/MACCS…，>30 种） | MCP(候选) | MIT | `pip install scikit-fingerprints` → `skfp.fingerprints` | rdkit | 候选封装：RDKit 装后可复用 indigo 同构封装 |
| 20 | ODDT | docking/虚拟筛选/rescoring 管线 | 融合参考 | BSD-3-Clause | `pip install oddt` → `oddt.toolkits` | rdkit 或 openbabel + sklearn/pandas | 未封装（v0.8 维护趋缓；主力场景需对接软件） |

## 与中转库的对应关系

- 本地已克隆 8 个：`scratchpad-knowledge/academic/{AffineGaps, ChemFormula,
  Clapeyron.jl, CoolProp, FEMcy, PyXtal, Pynite, SLICES}`。
- 其余 8 个（thermo/tespy/pycalphad/gemmi/hyalite/WaveBench/rp2daq/hololinked）
  仅有 `_readme_dump/*.txt`，克隆待补（不影响层级标注与接口封装）。
- 注意：SLICES 克隆内**无 slices 包本体**（转换 API 走 PyPI 独立分发）。
- 已知许可勘误：chem_adapter `__init__.py` 误标 Apache-2.0，上游实为 MIT
  （本单 levels.py 已按 MIT 记录；adapter 文件本身留待后续工单更正）。
