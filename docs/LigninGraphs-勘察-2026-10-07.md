# LigninGraphs 勘察报告（只读）

> 工单203 任务三落地 · 2026-10-07 · 来源：`docs/授粉轮34-糖链与聚合物拓扑候选-授粉报告-2026-10-06.md`（P0③）
> 勘察对象：`VlachosGroup/LigninGraphs`（**实测 ★3 · MIT · push 2023-02-19 · 10.6MB**）
> 附带对象：`ibmm-unibe-ch/glycosylator`（实测 ★19 · MIT · push 2026-06-19 · **327MB**）
> 方法：GitHub API 拉源码逐文件读（未 clone、未安装、未改任何文件）

## 0. 结论摘要

**判定：不融合**（作为成品依赖引入）；**重定位为「木质素结构生成/反演的参考设计」**。

**关键发现：轮34 报告对 LigninGraphs 的定位有误。** 报告称其为
「木质素→水凝胶交联网络图模型（交联度、溶胀与网络拓扑的桥）」，
实测其在 `crosslink` / `swelling` / `hydrogel` 三个概念上**零命中**——它做的是
**木质素聚合物（monomer/polymer）结构的生成与表征**，不含水凝胶/交联/溶胀模型。
→ 结论：它**不是**「木质素 NPs → 水凝胶」的理论桥；那条缺口仍然存在（见 §4）。

## 1. LigninGraphs 实测解剖

### 1.1 是什么（README 原文口径）

> "an open-source software package in Python to **generate feasible lignin structures**…
> graph-based multiscale modeling framework for **lignin structure generation and visualization**.
> employs accelerated rejection-free polymerization and hierarchical Metropolis Monte Carlo optimization…
> generate feasible lignin structures **to match experimental or literature data**."

即：**用实验/文献数据（键型分布等）反推/生成可行的木质素分子结构**，并可视化。

### 1.2 代码结构与 API（实测）

| 文件 | 行数 | 内容 |
|---|---|---|
| `ligning/polymer.py` | 897 | `PolymerGraph` / `Polymer`（结构生成核心） |
| `ligning/optimization.py` | 1110 | Metropolis Monte Carlo 优化（结构 ↔ 实验数据匹配） |
| `ligning/characterization.py` | 735 | `CharacterizeGraph` / `Characterize` / `Population`、`get_metrics_polymer` / `get_counts_polymer`（结构指标） |
| `ligning/monomer.py` | ~250 | 单体定义 |
| `ligning/rules.py` | ~280 | 连接规则（键型） |
| `ligning/utils.py` | ~750 | 工具 |

依赖：RDKit / NetworkX / pysmiles / matplotlib / numpy / scipy / pandas（**重依赖链**）。

### 1.3 概念命中（关键证据）

在 `polymer.py` / `characterization.py` / `optimization.py` 三个核心文件中检索：

| 概念 | 命中次数 |
|---|---|
| `monomer` / `polymer` | **197+72+87 / 307+44+94**（贯穿全代码） |
| `network` | 1 + 0 + 1（仅零星提及） |
| **`crosslink` / `swelling` / `hydrogel`** | **0 / 0 / 0**（三文件全零） |
| `beta-O-4`（木质素特征键型） | 1 + 2 + 0 |

→ **它是木质素分子结构工具，不是交联网络/水凝胶模型**（实锤）。

## 2. 与 scratchpad 的真实对接面（重定位后）

| 潜在用途 | 对接点 | 判断 |
|---|---|---|
| **木质素结构生成** | 轮30 木质素 MD 构建线（需要可行的木质素初始结构） | ✅ 真实价值：可用它生成的键型分布化结构做 MD 起点 |
| **结构反演方法论** | 工单202 的 EIS/DRT 谱反演（`mcpserver/eis`） | ✅ 同范式（实验数据 → 反推结构参数），但其实现是 MC 采样、EIS 是正则化反卷积，**不共用代码**，仅方法论对照 |
| **LCC 复合体建模** | 工单203 任务二（glypy 糖链树） | ⚠️ **互补但不同层**：LigninGraphs 管木质素骨架（RDKit 图/SMILES），glypy 管碳水单元（IUPAC 树）。两者拼 LCC 需要**自写的桥接层**，两边都不提供 |
| 水凝胶交联理论 | 邵组路线 | ❌ **它没有这个能力**（见 §0） |

## 3. glycosylator 评估（附带）

| 维度 | 实测 |
|---|---|
| 元数据 | ★19 · MIT · push **2026-06-19**（活跃）· size **327MB** |
| 定位（README） | 糖链的**原子级建模**框架：build atomic models of glycans / **glycosylate proteins and membranes** / 构象优化（minimize clashes）/ 多格式支持 / 与 RDKit 协作 |
| 底座依赖 | 基于 `BuildAMol` |

**评估**：
- 它做「糖链 → 3D 原子结构」+「把糖链接到 **protein/membrane** 上」——**没有木质素支持** → **不能直接做 LCC**；
- 可参考的是**管线设计**：糖链识别 → 原子建模 → 接到宿主分子 → 构象优化（这套分层对 LCC 建模有借鉴价值）；
- **不引入**：327MB 仓库 + BuildAMol 依赖链，远超体积红线（对照 AutoEIS 792MB 的教训）。

## 4. 缺口仍在（重要）

轮34 报告把 LigninGraphs 当作「木质素 NPs → 水凝胶**中间缺失的理论桥**」。
本勘察确认：**该缺口的候选来源判断错误，缺口依然存在**。

现状盘点（谁管哪一层）：
```
木质素结构生成        ← LigninGraphs（本件，★3 停更 2023，可参考/自写）
碳水单元结构          ← glypy / glycowork（工单203 任务二）
LCC 复合体 3D 建模    ← 无（glycosylator 只管糖链→蛋白/膜）
交联网络/溶胀理论     ← 无（LigninGraphs 不含；这是真正的缺口）
```
→ **建议**：若要补「交联网络 → 溶胀/力学」这一层，需**另找来源**（下一轮扫货时把检索词改为
"polymer network theory / Flory-Rehner / hydrogel swelling model / crosslink density"，
而不是从"lignin"方向找）。已记入待办。

## 5. 建议

1. **不引入 LigninGraphs**（★3 + 2023 停更 + RDKit 重依赖 + 仓库体积），**不融合**进材料 KG；
2. **保留为参考设计**：若轮30 木质素 MD 线需要"按实验键型分布生成结构"，可**自写轻量版**
   （其算法思路清晰：rejection-free 聚合 + MC 优化，无私有算法）；
3. **不在本件基础上做水凝胶理论**（能力不存在，硬套会造成"看起来接上了、实际不对"的假连接）；
4. glyphosylator 同理：**只读参考**，不引入。

— 砚 · 工单203 任务三 · 勘察完毕，定位已纠正
