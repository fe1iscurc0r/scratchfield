# 升级项目清单 — 来自 5648 篇论文全量精读（Round2）

日期：2026-08-30
来源：~/research/papers/round2/digests/（44 份 digest）+ SUMMARIES-2026-08-30.md
规模：**117 项**（三位数达标），按线分类，每项含来源与落点

优先级：P0=今天能开 / P1=1-2 周 / P2=观察跟进
落点缩写：RF=射频大脑 rf_brain / ESP=ESP32 固件 / SW=软件组件 / 陆墨=材料科研线 / AG=Agent 体系 / SEC=安全

---

## R 线 · 无线电 / SDR / ESP32（42 项）

| # | 项目 | 来源 | 落点 | 优先级 |
|---|------|------|------|--------|
| R01 | 事件驱动频谱缓存："完成-固化"信号事件替代逐帧 FFT | G2-1/G2-4b | RF/ESP | P0 |
| R02 | Channel2World 环境级无线基础模型 → 频谱基础模型 | G8-1b | RF/SW | P0 |
| R03 | SPOTLIGHT 双极化 RFI 缓解（误检↓98%） | G6-1 | RF/SW | P0 |
| R04 | 语义分裂 UEP：MI 梯度不等差错保护 | GX-1 | ESP/SW | P0 |
| R05 | Score-based Ideal Observer 轻量频谱检测 | G8-3a | ESP | P0 |
| R06 | TACAN 信道 token 注意力动态频谱接入（92.5%） | GX-3b | RF/SW | P1 |
| R07 | RIS 相位优化闭合解 → MCU 级波束控制 | GX-2 | ESP | P1 |
| R08 | 自回归谱约束 → 可证明稳定信道预测 | G1-4 | RF/SW | P1 |
| R09 | 物理响应共享排序 → 信道字典原子验证 | G1-2 | RF | P1 |
| R10 | Orthogonal JEPA → 多径/干扰正交分离 | G1-1 | RF/SW | P1 |
| R11 | 神经形态 autoencoder → ESP32 声学/振动异常检测 | GX-1 | ESP | P1 |
| R12 | 双梳光子信道化 → 实时宽带频谱感知 | G5-3b | RF/SW | P1 |
| R13 | PFB 逆重建 → SDR 信道化硬件工程 | G6-2a | RF/SW | P1 |
| R14 | 唤醒无线电 + 低功耗相位保持 → ESP32 无源节点 | GX-5a | ESP | P1 |
| R15 | 事件触发稀疏计算 → SDR 信号稀疏休眠 | GX-3a | ESP | P1 |
| R16 | 信息驱动 UEP → ESP32 自适应跳频策略 | GX-1 | ESP | P1 |
| R17 | 约束证据可见性 → 多传感器按物理过程分区融合 | G1-3 | ESP | P1 |
| R18 | 物理层指纹（RF/EM 侧信道）→ SX1278 信任根 | G3-1 | SEC/ESP | P1 |
| R19 | LLM 语义编排 → SDR 认知无线电指令映射 | GX-5a | RF/SW | P1 |
| R20 | 语音 LLM → SDR 频谱管理 Agent | G8-2b | AG/RF | P2 |
| R21 | AirMoE 空中计算 → ESP32 分布式传感网 | G8-2b | ESP | P2 |
| R22 | 自注入锁定超分辨率雷达 → ESP32 本振稳定 | G8-1b | ESP | P2 |
| R23 | SonicNudge 物理攻击 → SDR 感知安全审计 | G8-3a | SEC | P2 |
| R24 | 自适应稀疏交互 → 频谱监测计算资源分配 | G1-2 | RF | P2 |
| R25 | Agent 协作原语 → 多跳频谱感知分配 | G1-4 | AG/RF | P2 |
| R26 | 因果干预分析 → SDR 信道模型偏差检测 | G1-3 | RF | P2 |
| R27 | 扩散模型无线电地图修复 → ESP32 边缘无线电地图 | G8-1b | ESP | P2 |
| R28 | 地理扩展分类器 → 频谱感知物种识别 | G1-2 | RF | P2 |
| R29 | 环状强制记忆 → 频谱事件长历史查询 | G2-4b | RF | P2 |
| R30 | PT 对称 odd viscosity → SDR 可编程波形平衡增益 | G5-3a | RF/SW | P2 |
| R31 | MXene THz 量子流体 → 材料指纹频谱库 | G5-3a | RF | P2 |
| R32 | 语义通信 + MAPD → 频谱语义传输 | GX-5b | RF/SW | P2 |
| R33 | 分布式雷达共识 → Agent 群体协同感知 | G8-1a | AG/RF | P2 |
| R34 | 电磁孪生稀疏重建 → 1% 探测点补全频谱 | weekly_pollination | RF/SW | P1 |
| R35 | kNN 存档反演 → ESP32 实时分类查表 | weekly_pollination | ESP | P1 |
| R36 | LQG/积分器混合控制 → 无线电 AGC/锁相 | weekly_pollination | ESP | P2 |
| R37 | OT 正则动态重建 → 频谱序列去卷积 | 8-30 论文轮 | RF/SW | P1 |
| R38 | OTA-ELM → ESP32-S3 零梯度轻量推理 | 授粉 round10 | ESP | P0 |
| R39 | 乘法免费特征提取 → SX1278 收包分类 | 8-23 论文轮 | ESP | P1 |
| R40 | THz 多智能体通讯芯片 → 高频 SDR 参考 | G5-2 | RF | P2 |
| R41 | 跨模拟器基础模型 → 21cm SBI 零样本迁移 | G6-2b | RF/SW | P2 |
| R42 | 分布式 Trotter 化 → 纠缠消耗自适应（量子侧） | G4-4 | 观察 | P2 |

## M 线 · 材料 / 生物质（陆墨，22 项）

| # | 项目 | 来源 | 落点 | 优先级 |
|---|------|------|------|--------|
| M01 | 物理引导符号回归（RUPF）→ 生物质热稳定性预测 | G4-2 | 陆墨 | P0 |
| M02 | TIP 热力学原子间势 → 水凝胶溶胶-凝胶相变 | G4-2 | 陆墨 | P1 |
| M03 | 主动学习 + MLIP → 生物质电化学性能预测 | G4-1 | 陆墨 | P1 |
| M04 | 量子几何工程 → 界面极化水凝胶/太阳能蒸发 | G4-1 | 陆墨 | P2 |
| M05 | 化学语言模型 + 不确定量化 → 组分-性能闭环 | G4-4 | 陆墨 | P1 |
| M06 | 量子储层超扩展 → 软物质非平衡建模 | G4-4 | 陆墨 | P2 |
| M07 | 离散-连续神经采样（JANUS）→ 多组分逆设计 | G4-1/G4-4 | 陆墨 | P1 |
| M08 | DPA4C 通用分子势 → 10⁵ 原子生物质 MD | G5-1a | 陆墨 | P1 |
| M09 | UBio-MolFM → 嵌入式分子模拟 | G5-2 | 陆墨 | P2 |
| M10 | 自监督结构发现 → 生物质显微自动解析 | G4-2 | 陆墨 | P1 |
| M11 | DOSSIER 组分直接预测电子态密度 | G4-4 | 陆墨 | P2 |
| M12 | Little Scientist Agent → 材料实验自动设计 | G7-1 | 陆墨/AG | P1 |
| M13 | NestyNet 符号回归 → 经验方程自动发现 | G6-2b | 陆墨 | P1 |
| M14 | 物理引导神经 PDE → 生物质热解动力学 | G1-3 | 陆墨 | P2 |
| M15 | 物理信息剪枝 → 材料传感网稀疏部署 | G1-4 | 陆墨/ESP | P2 |
| M16 | 流匹配能量 → 燃烧/热解 ODE 残差约束 | G1-1 | 陆墨 | P2 |
| M17 | 水冰结合能 ML → 低温表面催化 | G6-2a | 陆墨 | P2 |
| M18 | 微藻活性增强乳液 → 生物质胶体增强 | 8-25 论文轮 | 陆墨 | P2 |
| M19 | Polymer Genome 编码策略 → 木质素 NP 建模 | 8-25 论文轮 | 陆墨 | P1 |
| M20 | 数据高效 MLIP → 水凝胶体系性能预测 | 8-23 论文轮 | 陆墨 | P1 |
| M21 | 熵与 Frenesy → 活性生物质统一语言 | G5-2 | 陆墨 | P2 |
| M22 | 主动学习 + 无监督 → 生物质光谱表征边界学习 | G4-2 | 陆墨 | P2 |

## A 线 · Agent 系统（20 项）

| # | 项目 | 来源 | 落点 | 优先级 |
|---|------|------|------|--------|
| A01 | Credit Without Ground Truth → Agent 后训练评估修正 | G1-1 | AG | P1 |
| A02 | Recuris 递归工作记忆 → 长时域 Agent | G1-3 | AG | P1 |
| A03 | Thinkingbox 测量失效 → pass²⁰ 式可靠性评测 | G2-1 | AG | P1 |
| A04 | MemToC 仲裁缺陷 → 工具/记忆仲裁重构 | G2-4b | AG | P1 |
| A05 | MoRE 单 Agent 多角色（20× token 省） | GX-5b | AG | P1 |
| A06 | 代码世界模型采样验证≠正确 → Agent 代码生成护栏 | G1-2 | AG | P1 |
| A07 | EMRB 电磁原始信号评测 → 无线电 Agent 能力 | G1-3 | AG/RF | P0 |
| A08 | RAG ingest-time 编译 → 固定语料摊销 | G1-2 | AG/SW | P1 |
| A09 | Agent 记忆投毒防护 → 写时筛查/来源分级 | 8-25 论文轮 | SEC/AG | P0 |
| A10 | Little Scientist Kuhn 机制 → Agent 跳出局部最优 | G7-1 | AG | P2 |
| A11 | 事件驱动记忆 → 嵌入式 Agent 记忆淘汰 | G2-2 | AG/ESP | P2 |
| A12 | 工具返回主导记忆 → 记忆写入优先级策略 | G2-4b | AG | P2 |
| A13 | Q-Planning 小 Q 函数 → 嵌入式策略自改进 | GX-3a | ESP/AG | P1 |
| A14 | CLAP 跨形态世界模型 → 仿真到真机迁移 | GX-5b | AG | P2 |
| A15 | Agentic RAG 归因诊断 → 记忆失效定位 | G2-2 | AG | P2 |
| A16 | 显式记忆 + 势场路由 → 多 Agent 调度 | GX-5a | AG | P2 |
| A17 | LLM-MAS 资源感知共识控制 | G8-3b | AG | P2 |
| A18 | 预测 Agent 社会机制规模极限 → MAS 可靠性 | GX-3c | AG | P2 |
| A19 | PropUQ-MAS 不确定性传播建模 | GX-3c | AG | P2 |
| A20 | Physical Agentic AI 验证门控 → 物理执行安全 | GX-3c | AG/ESP | P1 |

## S 线 · 安全（12 项）

| # | 项目 | 来源 | 落点 | 优先级 |
|---|------|------|------|--------|
| S01 | MaliciousSkillBench → 供应链安全评测基线 | G3-1 | SEC | P0 |
| S02 | PLCBench → 物理域 Agent 安全沙箱 | G3-2 | SEC/ESP | P1 |
| S03 | SPA Plan-First 信息流控制 → 跨查询信任边界 | G3-2 | SEC/AG | P1 |
| S04 | 物理层指纹 → MCU 不可克隆信任根 | G3-1 | SEC/ESP | P1 |
| S05 | 连续学习灾难性攻击 → 模型更新安全 | G3-1 | SEC | P2 |
| S06 | SBOM → RF 固件供应链清单 | G3-2 | SEC | P2 |
| S07 | 联邦梯度安全 → 材料数据隐私 | G3-2 | SEC/陆墨 | P2 |
| S08 | aiXamine 统一安全评估（safety tax/蒸馏崩溃） | G3-1 | SEC | P2 |
| S09 | 记忆定向偏移注入 → 持久化攻击面 | G3-1 | SEC/AG | P1 |
| S10 | 声纹谬误批判 → 语音生物特征安全 | G8-2b | SEC | P2 |
| S11 | SonicNudge 惯性攻击 → 传感器物理安全 | G8-3a | SEC/ESP | P2 |
| S12 | 恶意技能检测跨源 F1 骤降 → 检测器鲁棒性 | G3-1 | SEC | P2 |

## K 线 · 知识 / 数据 / 工具链（11 项）

| # | 项目 | 来源 | 落点 | 优先级 |
|---|------|------|------|--------|
| K01 | ZotPilot 文献管理 MCP → 材料文献库 | 扫货 8/29 | SW | P1 |
| K02 | TanStack/cli Agent Skills 安装机制 → skill 分发管线 | 扫货 8/29 | SW | P2 |
| K03 | 逐篇评价表自动化 → digest 流水线升级 | 本轮经验 | SW | P1 |
| K04 | 超时重试策略固化（≤100 篇/块）→ 流水线参数 | 本轮经验 | SW | P1 |
| K05 | 授粉点格式统一（44 份 digest 异构）→ 模板化 | 本轮经验 | SW | P2 |
| K06 | 论文池自动增量 → 每日 cron 已就位，补全量 digest 轮 | paper-pipeline | SW | P1 |
| K07 | 授粉矩阵 → 知识库 MatChat 索引 | 汇总文档 | SW/陆墨 | P2 |
| K08 | 符号回归工具链（NestyNet/RUPF）→ ELN 分析模块 | G6/G4 | 陆墨/SW | P1 |
| K09 | 频谱事件缓存 → rf_brain 新模块 + MCP 注册 | G2 | SW/RF | P0 |
| K10 | 三线授粉合并（论文/扫货/round10）→ 统一 backlog | 本轮 | SW | P1 |
| K11 | 材料性能预测管线（主动学习闭环）→ 实验指导 | G4 | 陆墨/SW | P2 |

## I 线 · 基础设施 / 杂项（10 项）

| # | 项目 | 来源 | 落点 | 优先级 |
|---|------|------|------|--------|
| I01 | MPC 分布式量子计算路径 → 远期量子组件 | G4-3 | 观察 | P2 |
| I02 | 分布式超导量子 → 百万比特工程路径 | G4-3 | 观察 | P2 |
| I03 | 3D-IC 开源基准套件 | GX-5b | 观察 | P2 |
| I04 | Redwood AI 全流程加速器（2 周 tape-out） | GX-5c | 观察 | P2 |
| I05 | 鞅论/信息几何统一框架 → 统计工具 | G9 | SW | P2 |
| I06 | 尾敏感条件独立检验 → 因果发现 | G9 | 陆墨 | P2 |
| I07 | OrbitalALIF SNN 联邦学习 → 去云低功耗 | GX-4b | ESP | P2 |
| I08 | NeuralNexus 开源机械臂 → 机器人参考平台 | GX-3b | ESP | P2 |
| I09 | 图灵机硬件实现（ESP32-CAM 光学读卡）→ 教学/原型 | GX-4a | ESP | P2 |
| I10 | MAPPO+Stackelberg → ESP32 集群编队调度 | GX-4a | ESP | P2 |

---

## 统计

- **总计 117 项**：R42 + M22 + A20 + S12 + K11 + I10
- P0（今天能开）：R01/R02/R03/R04/R05/R38 + M01 + A07/A09 + S01 + K09 = 12 项
- 来源覆盖：44 份 digest 全部 + 论文轮授粉点 + 扫货候选 + 授粉 round10

## 使用说明

- P0 项是"有硬件/纯软件/立即可做"的，挑 1-2 个开工即可
- 每项详细背景见对应 digest（文件名在来源列）
- 清单可增量扩充：每轮论文增量后跑 digest → 新授粉点自动加入
