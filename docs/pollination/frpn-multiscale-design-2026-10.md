# FRPN 聚合物跨尺度表示 → 材料 Agent 多尺度编码设计稿（工单226 任务二）

> 日期：2026-10-09 ｜ 料源：arXiv 2609.23611（Uni-Macro-FRPN，digest 在案）。

## 1. 双通道表示拆解（论文核心）

FRPN（Full-Resolution Polymer Network）的关键主张：**不粗粒化**——传统聚合物 ML 把链折成
固定粒度（repeat unit / 链级统计），FRPN 全分辨率联合学习两路：

| 通道 | 输入 | 编码内容 | 论文做法 |
|---|---|---|---|
| **单体语义编码器** | 原子感知的单体表示（SMILES/BigSMILES 衍生的原子级特征） | 局部化学语义（官能团/共轭/电负性环境） | Transformer 逐原子嵌入，pool 成单体向量 |
| **链拓扑编码器** | 链的拓扑序列（单体连接顺序/支化/交联结构） | 全链组装结构（序列位置/分支/链段统计） | Transformer 编码单体序列，保留全分辨率 |

联合训练后双通道拼接 = 聚合物表示。BCDB 层状分类 SOTA（ACC 86.4%）。

**对生物质线的意义**：木质素 NPs / 共聚物体系正是"局部基团（愈创木基/紫丁香基单体）
× 全局组装（交联度/NPs 尺寸）"双因子决定性质——FRPN 的双通道恰好对位。

## 2. 材料 Agent 落点：聚合物结构→性质模块接口

```
输入:  BigSMILES（首选，支化/交联表达力）或 SMILES（线性兜底）
       + 可选上下文（分子量分布/温度）
处理:  ① 单体切分（BigSMIES stochastic block 解析）→ 单体 SMILES 列表 + 拓扑图
       ② 双通道编码（见 §4 可行性）
       ③ 拼接 → MLP 性质头
输出:  { embedding: float[768],  # 下游检索/聚类复用
         props: { Tg?: float, 层状分类?: str, ... } }  # 按训练头可用性
边界:  未训练的性质头不返回（不编数）——接口预留 props 的 schema 声明可用项
```

挂载点：`mcpserver/adapters/material_science/` 侧新增 `polymer_rep` 工具（与 thermo/coolprop
同 registry 注册模式），进 academic_bridge 的 16 项目录表（第 17 项，license 登记照旧）。

## 3. 与现有 material_science 适配器的对接

- **registry 注册**：`mcpserver/material_science/academic_bridge/registry.py` 加
  `"frpn": {"import_name": "frpn_polymer", "pypi": null（自实现）, "call": True}`；
  可用性探测走工单224 加过兜底的 `_check_available`（find_spec 安全版）；
- **快通道数据流**（工单213）：`quick_import` 的实验数据 → embedding 入向量库
  （rag/vecdb_client）→ 材料 RAG 检索时"结构相似性"可用 embedding 直接算，不再依赖
  人工标签——这是比"性质预测"更先落地的价值点；
- **与 ChemFormula/CoolProp 的分工**：小分子量/组成计算（既有）vs 大分子结构表示（新），
  不重叠。

## 4. 可行性：开源实现/权重勘察 + 工作量估算

- **论文 repo**：工单未给链接；GitHub 搜 "Uni-Macro-FRPN"/"FRPN polymer"——截至 10-09
  **未发现官方开源**（BCDB 是公开数据集，模型未见 release）；
- **自实现工作量**（若走 PyTorch + 现成 Transformer 编码器）：
  - BigSMILES 解析：`bigsmiles` 解析库存在但维护弱，预计需自写 stochastic block 切分（~300 行）；
  - 双 Transformer：可用 `torch.nn.TransformerEncoder` 搭（各 ~100 行）；
  - 训练数据：BCDB 公开（分类头）；木质素/生物质性质数据**我们自己产**（快通道）；
  - **合计 PoC ≈ 2-3 天**（不含训练算力）；性质头在自有数据上微调另计。
- **判定**：**设计稿成立，实施排后**——先落 embedding 检索价值点（无需训练，用无监督
  对比学习即可出可用表示），性质头等邵长组数据量到位再上。

## 边界

- 论文数字（86.4%）是 BCDB 基准，与木质素体系无直接可比性；
- repo 未开源的结论基于 GitHub 检索，若官方后续 release 以官方为准。
