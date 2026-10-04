# 升级项目组 3-1：无线电/射频线（R55-R62）

> 生成：2026-08-31 · 实验田维护者 · 第三批（全量一行核心筛选）
> 用法：每项含【SPEC】目标/验收、【工单】动作、【提示词】可丢给执行 AI

---

# R55 Agentic Autoresearch 功率控制

> 来源分组：group1-无线电（第三批）

【SPEC】rf_brain 增加 Agentic Autoresearch 功率控制：LLM 自动设计无线资源管理算法，替代人工调参。验收=方案 + 原型。
【工单】①读 digest-g1-4 2608.26093 条目 ②分析 Agentic Autoresearch 流程 ③设计功率控制 Agent ④原型评估。
【提示词】你是无线资源 AI。读 digest-g1-4-2026-08-30.md 中 2608.26093（Agentic Autoresearch for Cell-Edge Power Control：LLM 自动设计无线资源管理算法），为 rf_brain 设计功率控制自动研究 Agent：LLM 生成候选功率控制策略→仿真验证→迭代改进。输出方案 + 原型（规则池+LLM 选择循环）。验收：合成小区场景功率控制较固定策略吞吐提升 ≥10%。推 trae/agent-r55 分支。

---

# R56 TRACE-CRC 信道预测

> 来源分组：group1-无线电（第三批）

【SPEC】rf_brain 信道预测加 trajectory-adaptive conformal risk control：给 R08 谱约束预测补覆盖率保证。验收=模块 + 覆盖率测试。
【工单】①读 digest-g1-4 2608.27124 条目 ②设计 conformal 校准 ③实现 ④覆盖率验证。
【提示词】你是信道预测 AI。读 digest-g1-4-2026-08-30.md 中 2608.27124（TRACE-CRC：Trajectory-Adaptive Conformal Risk Control for CSI），为 rf_brain 的谱约束信道预测（R08）增加 conformal risk control：轨迹自适应校准，输出带覆盖保证的 CSI 预测区间。输出 mcpserver/rf_brain/conformal_channel_pred.py + 测试。验收：合成信道数据覆盖率达标的预测区间，覆盖率 ≥90% 且区间宽度可控。推 trae/agent-r56 分支。

---

# R57 结构化 RF 干扰抑制

> 来源分组：group1-无线电（第三批）

【SPEC】rf_brain 结构化干扰抑制升级：AI 干扰抑制综述落地，承接 R03 滤波链。验收=模块 + 对比测试。
【工单】①读 digest-g1-4 2608.24974 条目 ②梳理干扰抑制方法 ③实现结构化抑制 ④对比。
【提示词】你是干扰抑制 AI。读 digest-g1-4-2026-08-30.md 中 2608.24974（Clearing the Underbrush: AI-Enhanced RF Interference Suppression），为 rf_brain 实现结构化干扰抑制：将窄带/脉冲/宽带干扰按结构分类抑制，与 R03 RFI 缓解模块衔接。输出 mcpserver/rf_brain/structured_interference.py + 测试。验收：合成多类干扰场景抑制后信号保真度较 R03 提升 ≥15%。推 trae/agent-r57 分支。

---

# R58 Omega-S 弹性惩罚 LoRA

> 来源分组：group1-无线电（第三批）

【SPEC】工具链增加 Omega-S 弹性惩罚 LoRA：无需先前数据/Fisher，微调保留率 62.9%→84.1%。验收=方案 + 原型。
【工单】①读 digest-g1-2 2608.03887 条目 ②设计弹性惩罚 ③实现 ④对比。
【提示词】你是微调优化 AI。读 digest-g1-2-2026-08-30.md 中 2608.03887v1（Omega-S：无需先前数据/Fisher 的弹性惩罚，LoRA 微调保留率 62.9%→84.1%），实现弹性惩罚 LoRA：以弹性加权惩罚保护重要权重，不依赖 Fisher 信息。输出 tools/omega_lora.py + 测试（小模型微调保留率对比）。验收：保留率提升 ≥10pp，不引入新依赖。推 trae/agent-r58 分支。

---

# R59 Thermo-FL 热感知联邦 LoRA

> 来源分组：group1-无线电（第三批）

【SPEC】勘察 Thermo-FL 热感知联邦 LoRA：温度感知鲁棒聚合，Jetson 实测参考。验收=勘察报告。
【工单】①读 digest-g1-2 2608.21172 条目 ②分析热感知聚合 ③出勘察。
【提示词】你是联邦学习 AI。读 digest-g1-2-2026-08-30.md 中 2608.21172v1（Thermo-FL：热感知联邦 LoRA，TERRA 鲁棒聚合，Jetson 物理测试台），勘察温度感知鲁棒聚合对分布式 LoRa/边缘联邦的可行性。输出 docs/thermo-fl-勘察.md：聚合机制 + 温度感知建模 + 自建门槛。验收：含 3 条可落地借鉴点。推 trae/agent-r59 分支。

---

# R60 RIS 序贯拍卖

> 来源分组：group1-无线电（第三批）

【SPEC】勘察 RIS 序贯拍卖：MARL 物理层安全分析，R07 相位解之外加资源分配机制。验收=勘察报告。
【工单】①读 digest-g3-2 2608.22169 条目 ②分析 RIS 拍卖机制 ③出勘察。
【提示词】你是 RIS 资源 AI。读 digest-g3-2-2026-08-30.md 中 2608.22169v1（MARL-Based Sequential RIS Auctions: A Physical-Layer Security Analysis），勘察序贯拍卖机制对 R07 RIS 相位控制之外资源分配的补充价值。输出 docs/ris-auction-勘察.md：拍卖机制 + 安全分析 + 与 R07 衔接。验收：含机制对比 + 3 条借鉴。推 trae/agent-r60 分支。

---

# R61 隐私语义通信

> 来源分组：group1-无线电（第三批）

【SPEC】勘察隐私语义通信：无线边缘语义传输加隐私，承接 R32 频谱语义传输。验收=勘察报告。
【工单】①读 digest-g3-2 2608.21773 条目 ②分析隐私保护语义通信 ③出勘察。
【提示词】你是语义通信 AI。读 digest-g3-2-2026-08-30.md 中 2608.21773v1（Privacy Preserving Semantic Communications in Wireless Edge Networks），勘察隐私保护机制（本地特征提取/加密语义）对 R32 频谱语义传输的补充。输出 docs/privacy-semcomm-勘察.md：隐私机制 + 边缘场景适配。验收：含 3 条可落地隐私设计。推 trae/agent-r61 分支。

---

# R62 PCI 分配干扰管理

> 来源分组：group1-无线电（第三批）

【SPEC】勘察 PCI 分配：稠密网络小区标识分配邻区干扰管理，对自组网/节点 ID 分配参考。验收=勘察报告。
【工单】①读 digest-g1-3 2608.21485 条目 ②分析 PCI 分配算法 ③出勘察。
【提示词】你是网络规划 AI。读 digest-g1-3-2026-08-30.md 中 2608.21485v1（Congruence Decomposition with Neural Block Solvers for PCI assignment），勘察 PCI 分配（稠密 5G 小区标识冲突/混淆避免）对 LoRa 自组网节点 ID 分配/频点规划的借鉴。输出 docs/pci-assignment-勘察.md。验收：含算法拆解 + 3 条自组网借鉴。推 trae/agent-r62 分支。

---
