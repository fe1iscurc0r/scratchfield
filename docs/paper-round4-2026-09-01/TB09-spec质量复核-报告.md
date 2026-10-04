# TB09 第九批 spec 质量复核报告

> 2026-09-01 · 智能体 53 · 复核对象：第九批 599 份 spec（`docs/paper-round4-2026-09-01/specs/` + UPGRADE-PROJECTS-9）
> 复核维度：编号连续性 / desc 空档 / 泛词误分（rf/signal/训练等）

## 1. 结论总览

| 维度 | 结果 |
|------|------|
| desc 空档 | **0**（无空"核心"、无占位标题） |
| 编号连续性（线内） | **无空档**（各线编号连续） |
| 泛词误分 | **R 线 5 处明确误分 + 4 处边界项**（见下） |
| 总清单表头 vs 实际 | **表头数量/范围与实际不符**（见 §4） |

## 2. 编号连续性

各线内部编号连续、无空档（逐文件核对）：

| 线 | 实际文件数 | 实际范围 | 连续？ |
|----|-----------|----------|--------|
| R 无线电 | 109 | R215–R323 | ✅ 连续 |
| M 材料 | 45 | M153–M197 | ✅ 连续 |
| S 安全 | 32 | S149–S180 | ✅ 连续 |
| K 工具链 | 304 | K406–K709 | ✅ 连续 |
| A Agent | 109 | A172–A280 | ✅ 连续 |
| **合计** | **599** | — | — |

## 3. 泛词误分（待修正清单）

### 3.1 R 线明确误分（5 处）

| 编号 | 标题 | 误分原因 | 建议 |
|------|------|----------|------|
| R227 | 96 kHz on-sky imaging on an adaptive optics system (SPAD) | 天文自适应光学/望远镜成像，非无线电 | 离栈（天文）或删 |
| R261 | Soft proton experiments … astronomical X-ray instrumentation | 天文 X 射线仪器，非无线电 | 离栈（天文）或删 |
| R267 | Spillover Effects under Network Interference (Neighbours' Treatment Effects) | "网络干扰"是因果推断/统计（社会网络），非 RF | 归 A/K 或离栈 |
| R289 | Generative Retrieval for E-commerce | 电商检索（ML），非无线电 | 归 K（工具链） |
| R294 | sbom-unifier: Integration Framework for Heterogeneous SBOMs | SBOM 软件供应链（安全），非无线电 | 归 S（安全） |

### 3.2 边界项（建议人工复核，4 处）

| 编号 | 标题 | 说明 |
|------|------|------|
| R296 | Optical Pathway to Movable Rydberg Atomic Quantum Receivers | Rydberg 原子射频感测，**可保留 R**（RF 感测），仅量子词触发 |
| K505 | Agentic Quantum Deep RL for RAN Slicing | RAN 切片属电信/无线电，量子 RL 是方法；可归 R 或留 K |
| K567 | Quantum-Grassmann-Plucker Token Mixing for Post-Disaster Damage Assessment | 应用是卫星遥感灾评，量子是方法；可离栈 |
| K614 | Uncertainty-Aware End-to-End AI Weather Forecasting | 天气预报，离工具链主线；可离栈 |

## 4. 总清单表头 vs 实际（编号范围不符）

UPGRADE-PROJECTS-9 的"数量分布"表头与实际 spec 不符（合计仍 599，是行间分配漂移）：

| 线 | 表头声明 | 实际 | 差异 |
|----|---------|------|------|
| R 无线电 | 118（R215–R332） | 109（R215–R323） | 表头多 9 |
| K 工具链 | 301（K406–K706） | 304（K406–K709） | 表头少 3 |
| A Agent | 103（A172–A274） | 109（A172–A280） | 表头少 6 |

> 结论：**表头需同步为 R=109/K=304/A=109**，或反查 9 个 R 项是否重分类进 K/A（§3.1 的 R289→K、R294→S 即此类）。

## 5. 复核结论

- **desc 空档：0，达标。**
- **线内编号：连续无空档，达标。**
- **泛词误分：R 线 5 处需修正（R227/R261/R267/R289/R294）+ 4 处边界复核（R296/K505/K567/K614）。**
- **总清单表头数量/范围与正文不符，需同步修正。**
