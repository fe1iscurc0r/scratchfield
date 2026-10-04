# Agent 卷 A40-A119 批量评估报告（第九期/第七批，80 单）

> 智能体 34 · Agent 卷 A40~A119（80 单）· 批量纪律：同类合并、每单一行验收、执行清单
> 总清单：`docs/paper-round2-2026-08-30/UPGRADE-PROJECTS-7-2026-08-31.md`（A 线 80 项）
> 来源：round2 存量全量扩编（第七批）；重要 8 单为第六批「深挖扩编」spec（工单指定）
> 落点：NEKO/Agent 线，原型落 `mcpserver/agent_lab/`（numpy/stdlib，无新依赖）

---

## 0. 数据质量说明（诚实标注，务必先读）

1. **编号冲突**：`specs/group3-agent安全/` 下同时存在「第六批（深挖扩编）」与「第七批（全量扩编）」两套
   A40~A119 spec，编号重叠但指向不同论文（每号两份）。本报告**以第七批总清单编号为准**，
   论文 ID 作唯一键；重要 8 单按工单指定走第六批标题，两者关系在 §1 各节标注。
2. **重要 8 单**（工单指定）全部是第六批深挖 spec：A40 Agentic Travel Behavior、A43 KernelArc、
   A45 Drift Recovery Graph、A46 AgenticTwin、A48 Harness Paradigm Enterprise、A52 AgentWeave、
   A57 Paritok-4B 意图编码、A61 Pivot-and-Station MAPF。已在 `mcpserver/agent_lab/prototypes/`
   各落一个原型模块 + 配套测试（32 例全绿）。
3. **离栈项**：放宽筛选使 3 篇物理类论文（A58 QMC、A94 反 Jaynes-Cummings、A95 奇异吸引子）
   落入 Agent 卷，§9 仅登记不硬套借鉴。
4. **无数据/无原型**：除重要 8 单外均为「评估/勘察」（读论文摘要方向→机制拆解→借鉴），
   无真实实验数据，结论标注「方向性」；重要 8 单原型全部使用 mock 数据并显式标注。

---

## 1. 重要 8 单深挖（工单指定，原型 + 测试已交付）

原型目录：`mcpserver/agent_lab/prototypes/`，测试：`mcpserver/agent_lab/tests/`（32 passed）。

### 1.1 A40 Agentic Travel Behavior（第六批 2608.20320；第七批同号 = Robust Data-Collection Policy 2608.24146v1）
- **核心**：三 Agent 工作流——对话数据采集 + 结构化处理 + 行为预测，多模态 LLM 预测超越随机森林。
- **原型**：`agentic_travel_workflow.py`——CollectionAgent（mock 对话语料）→ StructuringAgent
  （规则抽取 23 维特征）→ PredictorAgent（numpy softmax 逻辑回归）。
- **验收指标**：预测准确率 1.000 ≫ 多数类基线 0.146；特征维 23；种子可复现。✅
- **借鉴**：NEKO 出行对话（travel_notifications）可直接套「采集→结构化→预测」三段式，
  规则抽取层先上、模型层后换。

### 1.2 A43 KernelArc 多 Agent GPU 内核协调（第六批 2608.17071；第七批同号 = Data-Driven Dynamic Algorithm Dispatch 2608.21584v1）
- **核心**：多 Agent GPU 内核优化框架，H100/B200 上 6 项任务排名第一；多角色共享黑板协同进化。
- **原型**：`kernelarc_orchestrator.py`——Generator/Profiler/Reviser/Planner 四 Agent 黑板循环，
  mock 耗时模型（tile 效率 + 共享内存罚项）。
- **验收指标**：最优耗时 37.50 < 朴素基线 102.36（↓63%）；黑板留痕 3 类角色。✅
- **借鉴**：黑板协调模式可迁移到 rf_brain 多策略调参（生成→测量→修订→择优同构）。

### 1.3 A45 Drift Recovery Graph 漂移恢复图（第六批 2608.14109；第七批同号 = StarHarness 2608.24804v1）
- **核心**：状态机恢复图 + 小语言模型专精化节点，AppWorld 上正确恢复决策。
- **原型**：`drift_recovery_graph.py`——恢复图（错误签名→动作概率）+ 决策表小模型 mock +
  episode 模拟环境。
- **验收指标**：决策表恢复率 0.912 > 随机策略 0.482；未知签名回退 retry。✅
- **借鉴**：apiserver 工具调用失败分类（超时/鉴权/缺参）可挂恢复图做自动重试决策，
  替代现在的统一重试。

### 1.4 A46 AgenticTwin 数字孪生（第六批 2608.11679；第七批同号 = When Do Supervised UQ Ensembles 2608.24492v1）
- **核心**：LLM 推理 + 数字孪生异常检测管道，自然语言查询支持，人工评测诊断质量提升。
- **原型**：`agentic_twin.py`——EWMA+z 分数在线检测（单遍）+ 规则查询解析（中文）。
- **验收指标**：检测 F1 = 1.000（8 注入异常全召回、零误报）；「温度/异常」查询命中正确指标。✅
- **借鉴**：NEKO 设备遥测（温度/内存）可挂同款轻量孪生层，查询解析后续换 LLM。

### 1.5 A48 Harness Paradigm Enterprise 企业级评估（第六批 2608.20622；第七批同号 = LLM-Driven Datasheet-Aware Hardware 2608.25217）
- **核心**：企业 LLM Agent at Scale——harness 作为企业基础设施而非工具，凭证作用域 + 授权逻辑。
- **原型**：`harness_enterprise.py`——Credential（主体/作用域/过期）+ PolicyEngine（三重检查 +
  审计留痕）+ Harness 闸口门面。
- **验收指标**：6 例决策矩阵（放行/作用域不足/过期/未知动作）零错判；每次决策留审计。✅
- **借鉴**：agentserver 的 dogtag 凭证体系可按「动作→作用域」映射补最小权限闸口 + 审计链。

### 1.6 A52 AgentWeave 路由先于推理（第六批 2608.23078；第七批同号 = AI agents in Algorithmic Electricity Markets 2608.26896）
- **核心**：海量工具集合下先路由筛子集再推理，兼顾召回与成本。
- **原型**：`agentweave_router.py`——8 域×25 工具，TF-IDF 两级路由（域质心粗筛→域内 top-k）。
- **验收指标**：recall@5 = 1.000 ≫ 随机基线 0.025；域路由准确率 1.000；候选成本比 2.5%。✅
- **借鉴**：mcpserver/tool_registry 工具超百个时，先按域路由再进 LLM 工具选择，
  可大幅压上下文成本。

### 1.7 A57 Paritok-4B 意图编码（第六批 2608.24188；第七批同号 = LumiXAI 2608.24524v1）
- **核心**：编码 Agent 每轮重发大文件/工具输出；意图条件化选择性压缩。
- **原型**：`intent_conditioned_compression.py`——意图词元重叠打分，30% 预算保留高分块（规则版
  替代 4B 小模型，显式标注）。
- **验收指标**：关键证据召回 1.000 > 头部截断 0.333；预算约束与原序保持。✅
- **借鉴**：apiserver/context_compressor 现有压缩可加「意图条件」维度——按当前任务意图
  打分保块，而非位置/新鲜度截断。

### 1.8 A61 Pivot-and-Station 多 Agent 调度（第六批 2608.24585；第七批同号 = MOSAIC ToM Benchmark 2608.20975v1）
- **核心**：高密度仓储场景多 Agent 路径规划的可解性/完备性/复杂度（pivot 转向位 + station 缓冲位）。
- **原型**：`pivot_station_mapf.py`——网格仓库 + 优先级时空 A*，station 缓冲位豁免预留（让行语义）。
- **验收指标**：4 Agent 交叉实例全部到达，零顶点冲突，makespan = 11。✅
- **借鉴**：多 Agent 并发写同一仓库（本仓 8+ agent 并行场景）的任务调度可借「缓冲位让行」
  思想做冲突窗口设计。

---

## 2. Harness 与自改进线（逐单一行验收）

| 单 | 一行验收 |
|---|---|
| A45 StarHarness（2608.24804v1） | 环境特化 harness 进化 + 分层搜索，模型权重冻结——借鉴：与 §1.3 恢复图组合做 harness 层自愈（重要单 ⭐见 §1.3） |
| A70 HarnessRisk（2608.17597） | harness 生命周期风险基准（工具/扩展/持久态）——借鉴：为本仓 harness 类组件建风险清单模板 |
| A86 VideoHarness-RSI（2608.24302v1） | 长视频上下文构建的 harness 递归自改进——借鉴：上下文构建策略可进化（方向性，视频离栈） |
| A88 Auto-Policy, not Auto-Skill（2608.25091） | 自进化技能应是编译的「策略」而非建议式编排——借鉴：skills/ 下技能产出物向可执行策略收敛 |
| A102 EnvHarness（2608.19880） | 可编程环境包装层，不改底层逻辑即适配 Agent 弱点——借鉴：测试环境包装层做失败模式注入 |
| A111 TRUSS（2608.17588） | 证据引导技能生成 + 九安全属性静态门 + 影子执行，ASR 38.7%→19.4%——借鉴：技能入库前加静态安全门 |
| A84 Recursive Experiential-Working Memory（2608.24876v1） | 经验+工作记忆递归进化支撑长程任务 RSI——借鉴：memory_maas 可加「经验→工作记忆」晋升链 |
| A107 What Missing AI Post-Training（2608.19072） | Agent 困于初始策略局部调整、无法自发重估策略本身——借鉴：评估结论入知识库（诊断型，无需原型） |

## 3. 评估与基准线（逐单一行验收）

| 单 | 一行验收 |
|---|---|
| A44 Dual-Dimensional LLM Framework（2608.24825v1） | 自动题目事件双维框架——借鉴：评估框架双维度设计（方向性） |
| A60 LACE（2608.16210） | 局部增强控制变量估计条件性能，廉价信号提效——借鉴：本仓回归抽样评估可用控制变量降方差 |
| A61 MOSAIC ToM（2608.20975v1） | 多模态社会行为推理基准，VLM 不合 ToM 约束（重要单 ⭐编号对应 §1.8，见其说明） |
| A63 Judge Construct Validity（2608.24419v1） | 判官应知道什么变了：构念效度评测——借鉴：LLM-judge 评测需注入「已知变化」做效度检验 |
| A64 FrontierChallenge（2608.24979） | 科学工作流完备性评估——借鉴：科研 agent 验收看工作流闭环而非单点 |
| A65 BixBench3（2608.25286） | 研究规模生物计算分析 agent 基准——借鉴：长程多工具基准构造方法（方向性） |
| A66 CorporateBench（2608.27391） | 企业级文档 Q&A 基准（时间感知）——借鉴：RAG 评测需带文档时间维 |
| A68 Hardware Design Automation（2608.26199） | 本地 LLM agent 硬件设计自动化基准——借鉴：EDA agent 验收对标（接本仓 fix_*.py 线） |
| A71 aiXamine（2608.20554） | 跨维度统一黑盒评估——借鉴：单维高分不掩盖跨维失败，评估矩阵化 |
| A72 OdinEval（2608.18595） | Odin 语言仓库级修复基准——借鉴：小众语言修复评测补位思路（方向性） |
| A73 ECP（2608.19263） | 评估上下文协议：可移植评估——借鉴：评估资产协议化封装 |
| A76 BC-Bench（2608.20851） | 真实场景 agentic engineering 评估——借鉴：通用基准→领域基准落差意识 |
| A77 Testing & Evaluation Agentic AI（2608.20597） | 军事 C2 agentic AI 测试评估方法论——借鉴：非确定性系统的测试纪律（方向性） |
| A80 Benchmarking the Titans（2608.22529v1） | LLM 代码生成多维实证评估——借鉴：代码评估不止 pass/fail |
| A81 XREPOTEST（2608.25939v1） | 多语言仓库级单测生成基准——借鉴：本仓测试生成评估参照 |
| A97 ContractScrub（2608.20204） | 首个合同审查基准，前沿模型宏平均召回仅 0.75——借鉴：领域基准暴露通用能力鸿沟（登记） |
| A104 DeltaML-Bench（2608.19653） | ML agent 研究仓库基准，ARG scaffold 9.4%→49.0%——借鉴：scaffold（脚手架）比模型更提分 |
| A110 Structured Info Extraction（2608.18289） | OCR+LLM 文档抽取基准，输入质量比模型规模更关键——借鉴：上游数据质量优先（方向性） |

## 4. 安全与对抗线（逐单一行验收）

| 单 | 一行验收 |
|---|---|
| A53 Zero-Shot Threat Detection（2608.16508） | 两阶段 LLM 零样本内部威胁检测——借鉴：告警文本→结构化→判定两段式 |
| A56 SeriCrypt（2608.24498v1） | LLM 上下文感知序列化助协议状态机学习——借鉴：协议报文序列化需密码学有效性约束（接 rf_brain 协议线） |
| A67 NeuronFuzz（2608.26222） | 安全神经元引导的越狱 fuzzing——借鉴：红队测试按敏感神经元定向（方向性，无白盒条件） |
| A74 SNIPTEST（2608.17396） | 多层级代码切片模糊测试静态分析工具——借鉴：静态分析工具的切片级验证思路 |
| A78 TrustShiftProbe（2608.23763v1） | MCP 阶段式信任转移攻击刻画+基准+防御——借鉴：**本仓 mcpserver 直接相关**，工具后端变更时重验信任 |
| A79 MMJailBench（2608.25490v1） | 多模态越狱因子化基准——借鉴：攻击因子解耦评测设计（方向性） |
| A90 AdaptPrint（2608.22213） | 响应自适应黑盒模型指纹——借鉴：供应商模型识别/计费审计场景（方向性） |
| A117 FedLNS（2608.18736） | LayerNorm 签名检测恶意联邦更新，40% 恶意节点下最优——借鉴：联邦聚合异常检测（方向性，无联邦场景） |

## 5. RL / 决策 / Bandit 线（逐单一行验收）

| 单 | 一行验收 |
|---|---|
| A40 Robust Data-Collection Policy（2608.24146v1） | 低方差 on-policy 数据收集策略学习（重要单 ⭐编号对应 §1.1，见其说明） |
| A41 Sparse Additive OPE（2608.22595v1） | 稀疏加性非线性离策略评估框架——借鉴：策略评估方差控制思路（方向性） |
| A47 Best Practice Critic Optimization（2608.23566v2） | 组式 RL 免训练 critic 的最佳实践批评优化——借鉴：评估/训练方法学登记 |
| A50 CAV Platoon RL（2608.26860） | 网联车编队汇入/退出 RL 控制——离栈（车辆控制，仅登记） |
| A51 Safety by Design（2608.26755） | 上下文 bandit 的实现成本约束——借鉴：在线决策加「事后成本」约束意识 |
| A52 Electricity Markets（2608.26896） | 学习式投标 agent 在电力市场的涌现行为（重要单 ⭐编号对应 §1.6，见其说明） |
| A93 Self-Referential Differential Testing（2608.22284v1） | 从测试中学习的自指差分测试——借鉴：DRL 系统测试自生成思路（方向性） |
| A118 SIGMA Traffic Control（2608.18263） | LLM 引导多目标 RL 交通灯控制 + 旋转增强跨路口迁移——借鉴：跨拓扑迁移的数据增强手法（方向性） |
| A119 GL Bandits Memory（2608.15848） | 带记忆广义线性 bandit，√T regret 统一处理——借鉴：记忆型决策理论登记（方向性） |

## 6. Agent 架构 / 记忆 / 搜索线（逐单一行验收）

| 单 | 一行验收 |
|---|---|
| A59 GEI Survey（2608.19794） | 通用具身智能路线图，5 挑战（闭环知识整合/符号-神经混合推理）——借鉴：NEKO 具身路线对齐 |
| A82 AutoResearch（2608.17906v2） | 自主研究工作流幻觉传播审计——借鉴：长工作流需逐环节幻觉审计点 |
| A83 Dynamic Internal Field（2608.24319v1） | 动态内部场治理 transformer 计算预算——离栈（理论猜想，登记） |
| A85 CAFE（2608.24794v1） | 自改进搜索 agent 需反馈共同进化——借鉴：rag 检索策略与反馈信号联动进化 |
| A87 Autonomous Math Discovery（2608.23691v1） | 开放世界多 agent 站点自主数学发现——借鉴：开放任务空间的 agent 组织（方向性） |
| A89 Self-Improving RAG（2608.26706v1） | 财务 QA 自改进三 Agent，Lazarus 率 36.4% 回收初始错误——借鉴：rag 错误答案回收回路 |
| A96 MidTool（2608.20314） | 中训练数据合成提升工具使用（优于纯 post-training）——借鉴：工具使用训练阶段前移（方向性） |
| A98 Software 3.0 Thesis（2608.20201） | 软件第三范式收敛于数据库+大模型+Agent 三层——借鉴：本仓 apiserver+rag+agent 架构同构佐证 |
| A100 Brain Researcher（2608.19902） | agentic 神经影像研究 harness，工具选择精度 23.3%→93.6%——借鉴：可辩护研究框架=工具选择门控（方向性） |
| A106 Outcome Monitors（2608.19303） | 结果合同监测器检测静默工具失败，完成率 10.9%→28.1%——借鉴：**直接可用**：工具输出加结果合同校验 |
| A112 Physics of Agents（2608.16578） | 统计力学预测 agent 集体行为——离栈（社会物理模型，登记） |
| A113 Metacognition LLM Ensemble（2608.15400） | 五维元认知监控 + System1/2 切换 PoC——借鉴：多模型集成加元认知路由 |
| A115 CLaST（2608.20025） | 对比 VAE 上下文感知时序预测，CRPS -16.4%——借鉴：时序预测保上下文相似性（方向性） |

## 7. 软件工程与开发 Agent 线（逐单一行验收）

| 单 | 一行验收 |
|---|---|
| A42 CRA Agentic RAG（2608.19509） | EU CRA 合规评估 agentic RAG 框架——借鉴：合规类任务的 RAG+评估组合（方向性） |
| A43 Dynamic Algorithm Dispatch（2608.21584v1） | LLM 生成动态算法调度启发式（重要单 ⭐编号对应 §1.2，见其说明） |
| A46 UQ Ensembles（2608.24492v1） | 监督 UQ 集成何时改善幻觉检测（重要单 ⭐编号对应 §1.4，见其说明） |
| A48 Datasheet-Aware Hardware（2608.25217） | LLM 数据手册感知的早期硬件兼容性验证（重要单 ⭐编号对应 §1.5，见其说明） |
| A49 LLMs Design OR Algorithms（2608.27296） | LLM 设计近最优运筹算法——借鉴：规约清晰的问题 LLM 算法生成可行（方向性） |
| A54 GADR（2608.17694） | 架构决策记录收集——借鉴：本仓 docs/adr/ 可加自动化 ADR 抽取 |
| A55 ADEMM（2608.16580） | 开发者效率纵向监测方法——借鉴：多 agent 并行产出效率监测（方向性） |
| A57 LumiXAI（2608.24524v1） | 模块化全栈特征归因框架（重要单 ⭐编号对应 §1.7，见其说明） |
| A62 Terminal Agents Survey（2608.20485v1） | 终端 agent 综述：七维能力画像 + 学习-评估差距——借鉴：agent_cli_anything 能力画像对标 |
| A69 5G LLM Fault Analysis（2608.21021） | 轻量 LLM 自由文本故障分析 90%，零样本规范召回是缺口——借鉴：故障知识库规范化（接 rf_brain 故障线） |
| A75 Graphectory Viewer（2608.17195） | 过程中心的 agent 轨迹可视化——借鉴：trace_audit 可加轨迹过程视图 |
| A91 Auditing Feedback-Driven Evolution（2608.19626） | 执行反馈非自验证信号：审计与分解——借鉴：测试进化勿盲信执行通过信号 |
| A92 Beyond the Traceback（2608.20896） | LLM 自适应错误消息解释——借鉴：面向新手的错误转译（方向性） |
| A101 Axon DSL（2608.19889） | 强类型 DSL 跨框架编译，中位加速 58-107%——借鉴：跨后端统一中间层价值（方向性） |

## 8. 领域应用与跨卷线（逐单一行验收）

| 单 | 一行验收 |
|---|---|
| A99 Manifold Drift DPO（2608.20011） | 流匹配 DPO 流形漂移 + ThermoDPO 锚定——跨卷（M 卷已评估），A 线登记：偏好优化漂移通病 |
| A103 LLM Materials Acquisition（2608.19790） | 开放权重 LLM 材料采集策略——跨卷（M 卷 A103 主责），A 线登记：LLM 作贝叶斯优化替代 |
| A105 Confidence Black-Box LLM（2608.19323） | 相似查询正确性分类器提升黑盒置信度——借鉴：无 logit 场景的置信估计 |
| A108 DentAgent（2608.18878） | 口腔五专科 agent + 证据黑板，超专科医生 17.3pp——借鉴：多专科协调的证据黑板模式（同 §1.2 黑板） |
| A109 CTIFoundry（2608.18613） | agent 原生 CTI 语料支架，+0.19-0.28 F1——借鉴：本体图+工具+程序技能三件套支架（接 sentinel_intel） |
| A114 SocialRL Small LLM（2608.13787） | 4B 社会推理 RL recipe 匹敌 GPT-5 家族——借鉴：小模型社会推理训练配方（方向性） |
| A116 G-MARK Coop Driving（2608.19964） | 接地多 agent 协同驾驶，遮挡推理 +42.2%、通信 -25.6×——借鉴：多 agent 通信压缩（方向性） |

## 9. 离栈登记（物理类放宽筛选误入，不做借鉴）

| 单 | 一行说明 |
|---|---|
| A58 Quantum Monte Carlo（2608.23231v1） | QMC 方法综述——离栈（量子数值方法） |
| A94 Anti-Jaynes-Cummings Cascades（2608.22298v1） | Kerr 腔 Fock 态自主稳定——离栈（量子光学） |
| A95 Strange attractor（2608.17169v1） | 气泡浮体动力学奇异吸引子——离栈（流体物理） |

---

## 10. 执行清单

| # | 动作 | 结果 |
|---|---|---|
| 1 | 读总清单（UPGRADE-PROJECTS-7 A 线 80 行）+ A40~A119 全部 160 份 spec（第六/七批各 80） | ✅ |
| 2 | 重要 8 单原型 × 8：`mcpserver/agent_lab/prototypes/`（A40 旅行工作流/A43 KernelArc/A45 恢复图/A46 数字孪生/A48 企业 harness/A52 AgentWeave 路由/A57 意图压缩/A61 MAPF） | ✅ 全部可运行 |
| 3 | 配套测试 × 8：`mcpserver/agent_lab/tests/` | ✅ 32 passed |
| 4 | 验收指标（均为 mock 数据，显式标注） | 准确率 1.000 / 耗时 ↓63% / 恢复率 0.912 / F1 1.000 / 决策矩阵 0 错判 / recall@5 1.000 / 证据召回 1.000 / 零冲突 makespan 11 |
| 5 | 72 单第七批评估：§2~§9 分组报告，80/80 每单至少一行验收 | ✅ |
| 6 | 离栈标注：3 单（A58/A94/A95）+ 1 单弱相关（A50） | ✅ |
| 7 | 纪律：无新依赖（numpy/stdlib）；中文注释/输出；分组 commit；推 trae/agent-34 | ✅ |

**遗留/阻塞**：无硬阻塞。重要 8 单原型均为 mock 数据验证机制方向性，接真实数据/真实
模型（随机森林→XGBoost、决策表→微调小模型、规则解析→LLM）需后续工单。
