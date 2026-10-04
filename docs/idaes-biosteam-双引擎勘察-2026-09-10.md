# IDAES + bioSTEAM 生物质流程仿真双引擎勘察（F2 · 三方向决策 P0 追加）

> 2026-09-10 · 勘察（不写实现）· 依据：docs/2026-09-10-三方向决策-架构-UI-功能.md A3/F2
> 上游：IDAES/idaes-pse（通用 PSE 框架）+ BioSTEAMDevelopmentGroup/biosteam（生物精炼 TEA/LCA）
> 源码：shallow clone 到本机 D:/my git/haul-backfill/{idaes-pse,biosteam}——以下引用为实读行号。

## 〇、许可裁定（实读 LICENSE 原文，含一处纠错）

| 项目 | 许可（实读） | 裁定 |
|------|-------------|------|
| IDAES | 自研 BSD 式许可（源/二进制再分发需保留版权声明，IDAES PSE Framework Copyright 2018-2026） | ✅ 宽松，可借鉴/可依赖 |
| bioSTEAM | **University of Illinois/NCSA Open Source License**（BSD 式宽松） | ✅ 宽松，可借鉴/可依赖 |

> **纠错**：93 号批次曾记「biosteam 无 LICENSE 暂缓」——实读 LICENSE.txt 确认其为 NCSA
> 宽松许可（非无许可），该暂缓依据不成立，本勘察已解除。

## 一、架构拆解（实读）

- **bioSTEAM（生物精炼专项）**：
  - 系统模拟：`System`（biosteam/_system.py:795）+ `simulate`（:3363）——生物精炼流程模拟主干。
  - **TEA 全套**：IRR/NPV/贷款/税务（biosteam/_tea.py:51-102）——技术经济分析函数族。
  - 流程/热/功工具：_flowsheet.py / _heat_utility.py / _power_utility.py。
- **IDAES（通用 PSE）**：
  - 物性包：models/properties（IAPWS95/Helmholtz/活度系数族）。
  - 单元模型：models/unit_models（cstr/flash/equilibrium_reactor 等）。
  - core：base（单元模型基类）/ dmf（数据管理）/ scaling（缩放）。

## 二、授粉三大件①：源→目标映射（决策 A3/F2）

| 源组件 | 目标模块 | 授粉方式 | 收益 |
|--------|---------|---------|------|
| bioSTEAM 生物精炼模拟 + TEA | 材料科研线「生物质流程仿真」 | 引擎接入（评估级先行） | 生物质热解/精炼 TEA/LCA 能力 |
| IDAES 通用 PSE（物性+单元模型） | 材料科研线（通用流程仿真） | 引擎接入/架构参考 | 通用 PSE 底座 |
| bioSTEAM TEA 函数族 | 科研 Agent 技能库 | 封装为本地 Skill | 「算一下这套工艺的经济性」 |

## 三、授粉三大件②：核心数据结构共鸣（2-3 处，实读引用）

1. **System.simulate 全厂收敛**（biosteam/_system.py:795/3363）：生物精炼厂级物料/能量平衡
   的收敛模型——材料线「流程级模拟」的入口形态。
2. **TEA 经济函数族**（biosteam/_tea.py:51-102 IRR/NPV/贷款/税务）：与 F2「TEA/LCA」需求
   直接对口，封装面清晰（纯函数可测）。
3. **IDAES 物性包-单元模型分层**（models/properties 与 unit_models 并列）：通用 PSE 的
   「物性↔单元」解耦——与 feos（93号已授粉）互补（feos 偏 EoS、IDAES 偏流程）。

## 四、难度×收益与落地评估

| 维度 | bioSTEAM | IDAES |
|------|----------|-------|
| 上手难度 | 低（纯 Python，无解算器重依赖） | 中（Pyomo 建模层） |
| 与本线契合 | 高（生物精炼正是用户专业） | 中（通用 PSE 底座） |
| 依赖 | 轻（numpy/scipy 级） | 重（Pyomo + 求解器） |
| 结论 | **立即接入候选** | **参考/后置** |

## 五、落地建议（对齐决策「追加进树通道」）

1. **bioSTEAM 引擎接入**（P0，薄封装级）：`pip install biosteam`（NCSA 许可）+ tools/ 薄封装
   （流程模拟 + TEA 计算），测试 ≥5；后续批次按 F2 出 SPEC。
2. **IDAES 勘察后置**（P1）：Pyomo 求解器依赖重，仅架构/物性包参考，暂不接入。
3. **本地 Skill**：材料科研 Agent 技能库（F1）补「biosteam 流程模拟」技能（待引擎接入后）。

## 六、结论

双引擎定位清晰：**bioSTEAM 为主（生物精炼 TEA/LCA 直对口，NCSA 宽松，立即接入候选）；
IDAES 为底座参考（后置）**。93 号「无 LICENSE」暂缓依据经实读撤销。

---
*勘察：fe1iscurc0r · 2026-09-10 · 行号引用基于 shallow clone 实读（D:/my git/haul-backfill）*
