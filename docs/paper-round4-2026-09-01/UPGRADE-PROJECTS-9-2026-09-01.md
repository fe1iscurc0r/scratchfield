# UPGRADE-PROJECTS-9 · 2026-09-01（第九批 · round4 全量扩编 599 项）

> 组装：沈遥（Hermes）2026-09-01
> 依据：round4 新论文 1004 篇（2026-08-29/30/31 提交）digest 全量筛选，关键词≥1 放宽 + 硬排除离栈类目
> 与已交付 1286 项按论文 ID 去重零重复；v2 修订：9 项 R 线误分类迁回 A/K 线

## 数量分布

| 线 | 数量 | 编号范围 |
|----|------|----------|
| 无线电 | 109 | R215-R323 |
| 材料 | 45 | M153-M197 |
| 安全 | 32 | S149-S180 |
| 工具链 | 304 | K406-K709 |
| Agent | 109 | A172-A280 |
| **合计** | **599** | |

## 全量清单

| 编号 | 论文ID | 标题 | 核心一句 |
|------|--------|------|----------|
| A172 | 2608.22130 | PropUQ-MAS: Propagation-Aware Uncertainty Quanti | 传播感知不确定性量化：MAS视为通信图，结合局部+上游继承不确定性，AUROC+6.10% |
| A173 | 2608.22808 | CatchBench: When Can an Agent Failure Be Caught? | When can an agent failure be caught? An audit is usuall |
| A174 | 2608.28718 | RoboPhys-3D: A Comprehensive Embodied World Mode | 3D重建锚定的具身世界模型基准：5k episode多视角视频，分离重建误差 |
| A175 | 2608.28754 | Peer Oversight in Collective Decision Making | 对等k监督 集体决策k监督属性：至多k个agent可责任化任一有害结果，并给多项式判定/构造算法 |
| A176 | 2608.28794 | Breaking Darknet CAPTCHAs with general purpose L | 暗网CAPTCHA破解 MLLM 高层推理+MCP 委托确定性几何算法，暗网三类 CAPTCHA 成功率 >9 |
| A177 | 2608.28800 | UML Class Diagram Evaluation and Repair Strategi | LLM 生成 UML 类图评估+三修复策略：记忆增强/外部知识/检测引导，关键类修复率 85% |
| A178 | 2608.28919 | Emergent Behavior and Uncertainty in IoT-Enhance | 从不确定性表示/操作化/运行时涌现管理三视角，提出IoT增强BPM研究议程 |
| A179 | 2608.28995 | Hydra: A Navigation World Action Model with Disc | **Hydra: A Navigation World Action Model with Discrete  |
| A180 | 2608.29005 | A Degradation-Tolerance Benchmark for Camera-Onl | 相机E2E驾驶退化鲁棒性基准：16类损坏×5严重度注入，评估规划输出 |
| A181 | 2608.29023 | Teaching Robot Policies to Humans Using Erroneou | 用错误示例教人类理解机器人策略，源自课堂教学法迁移 |
| A182 | 2608.29032 | Bellman Search in Arbitrary Finite Dimension: A  | 自相似cell定理+量化消元证明平面Shoreline最优值C2^*为可计算实数 |
| A183 | 2608.29060 | Bellman--Shoreline Search in Arbitrary Dimension | 任意维在线超平面搜索机制，指数向量振荡器/预cession几何，N-COMP定理可计算 |
| A184 | 2608.29061 | PathBridger: Subgoal Bridges for Offline Goal-Co | Offline goal-conditioned reinforcement learning (GCRL)  |
| A185 | 2608.29100 | Agri-Sim: Agricultural Simulation Platform for E | Unity+ROS2番茄温室仿真平台：移动双臂采摘机器人闭环开发与功能评估 |
| A186 | 2608.29114 | CGFM-Nav: Cognitive Graph-Field Memory for Seman | 显式记忆图+语义前沿场耦合，终生多模态导航，GOAT成功率53.2→63.0% |
| A187 | 2608.29128 | APIFlow-Bench: Measuring Whether Agents Survive  | Tool-using agents are commonly evaluated by a single bi |
| A188 | 2608.29130 | A Systematic Approach to Mechanism Design with S | LMI设计支付函数实现博弈均衡激励相容，VS-PBR算法均方收敛 |
| A189 | 2608.29204 | AgentLogs: A Dataset for Opening the Black Box o | **AgentLogs: Opening the Black Box of GitHub's Cloud Ag |
| A190 | 2608.29228 | Localizing Emergent Failures in Agentic AI: Reco | Failures in agentic AI systems can arise from interacti |
| A191 | 2608.29237 | AGRICAM: A Track-Mounted Crop Pollination Monito | AGRICAM：轨道安装作物授粉监测机器人，RGB+微气候+GPS+RFID，30小时覆盖80m工业隧道，均匀 |
| A192 | 2608.29255 | A-MADiff: Attention-Guided Multi-Agent DRL with  | 移动AIGC任务编排：注意力引导多智能体扩散策略，GPU内存可行性约束 |
| A193 | 2608.29283 | A Multi-Month Study of Git Commit Signing | 3 个月 22 人研究：设置/多设备摩擦大，验证时超 1/4 认不出异常提交，近半有误解 |
| A194 | 2608.29310 | Super Library Agent: Joint Generation and Mainte | 多应用生成+共享库维护：候选引导抽取+上下文迁移，降冗余与 token、避免结构侵蚀 |
| A195 | 2608.29347 | A Cognitive Architecture for Shared Autonomy in  | 本体论+多LLM角色分工辅助ROV全程，比较Llama3/GPT-OSS/Qwen2.5角色适配 |
| A196 | 2608.29379 | Bridging Semantics and Physics with Constrained  | **Bridging Semantics and Physics with Constrained LLMs* |
| A197 | 2608.29444 | RL-based Network Slice Embedding over Space Divi | 空分复用弹性光网络切片：路径约束RL联合计算节点选择+RMCSA |
| A198 | 2608.29460 | Can escalation channels redirect reward hacking  | When coding agents encounter defective test infrastruct |
| A199 | 2608.29514 | A Sliding Window Filter on the Galilean Group fo | 未知测量延迟的辅助惯性导航，滑窗联合校正消除过自信、保一致性 |
| A200 | 2608.29518 | Stimulated Oscillations in Renewable Energy Inte | 分析反馈路径极零配置影响stimulated振荡，提出缓解方法与增益选取准则 |
| A201 | 2608.29562 | Asynchronous Cooperative Online Learning for Mul | Ensuring the safe operation of multi-agent systems (MAS |
| A202 | 2608.29583 | Drive the Thoughts: Runtime Monitoring of VLA Re | VLA 推理轨迹一致性监控：33.3% CoT 不可靠，车道相对 F-LLM 监控 F1 0.75 |
| A203 | 2608.29596 | Towards a Systems Foundation for Agentic Skills: | Autonomous large language model (LLM) agents increasing |
| A204 | 2608.29622 | AgenticRag-R1: Agentic Reinforcement Learning wi | 记忆栈+细粒度动作空间+层级即时奖励的RL agentic RAG，多跳长时推理稳定超越基线 |
| A205 | 2608.29632 | InteractBench: Benchmarking LLMs on Competitive  | 交互式编程题基准：322 题带本地 interactor，模型交互差，协议违规与查询超预算频发 |
| A206 | 2608.29641 | Harness-RL: Black-Box Reinforcement Learning wit | 中心agent harness RL：action-args梯度解耦CAPO+黑盒轨迹构造，F1达47.79( |
| A207 | 2608.29646 | Detect Before You Attribute: Cascade Failure Att | Large language model (LLM)-based agents have shown stro |
| A208 | 2608.29661 | OmniClimate-TC: Physics-Aware Visual Abstraction | PAVA物理感知视觉抽象，243,890指令对的台风推理基准，提升VLM科学推理 |
| A209 | 2608.29716 | Agent-Driven Verification of Memory Safety for l | VST+Agent 驱动证明 liblzma 解码器内存安全：27 个 body 定理，发现 LZMA1 零输 |
| A210 | 2608.29767 | LARC: Lazy Adaptive Reachability Certification o | 只二分不确定间隔的轨迹可达性证明，成功案例10.28x加速、零漏检 |
| A211 | 2608.29769 | Learning Agile Perceptive Traversal of Sparse 3D | 人形猴杠攀爬 RL感知控制单线LiDAR+注意力记忆，跳上/荡行/跳下14/15成功率、0.5m/s |
| A212 | 2608.29772 | Self-Aware Active Learning Enables Continual Imp | 预测世界模型产出恐惧/好奇心信号，超阈值求救+聚焦模仿，自动驾驶持续自改进 |
| A213 | 2608.29808 | POLYFLOW: A Neuro-Symbolic Framework for Static  | 神经符号跨语言信息流分析：LLM 提取隐式流事实+静态传播，发现基线漏掉的跨语言漏洞 |
| A214 | 2608.29831 | A^2Agent: Action-Aware Reinforcement Learning fo | A²Agent：每回合奖励序列+动作级优势估计隔离每个动作credit，4B模型超越8×更大基线，SWE-Be |
| A215 | 2608.29942 | Influence Is Not Authority: When Causal Guardrai | 影响≠授权 因果护栏信号审计：合法工具使用被误判为攻击（24/24 案例），信号反映成因而非授权 |
| A216 | 2608.30177 | Understanding Stage-Wise Utility-Risk Trade-offs | 记忆阶段化效用-风险权衡框架：写入/管理/检索三阶段暴露不同投毒风险剖面 |
| A217 | 2608.30192 | FaVOR: LLM-Based Agentic Framework for Factor Mi | Traditional finance relies on experts to hand-craft fac |
| A218 | 2608.30207 | SIR: Self-improving Red-teaming for Compute Use  | 计算机用 Agent 自改进红队：可复用原则组合+反馈蒸馏新策略，ASR 4%→24% / 0%→28% |
| A219 | 2608.30237 | Motus2: A Self-Evolving General World Model for  | 单权重模型暴露策略/仿真器/评估器三接口闭环自进化，支持触觉图灵通用灵巧操作 |
| A220 | 2608.30242 | CanonNav: Disentangling Navigation Behavior from | 导航行为与相机内参解耦+可通行性规划监督，RGB推理超RGB-D基线 |
| A221 | 2608.30288 | Extracting Knowledge from Tools in LLM Agents | 查询式工具知识抽取攻击：对比分析+证据链反馈，跨 6 领域平均恢复 74.3% 源记录 |
| A222 | 2608.30396 | Scaffolding Foundation Models into Physical-Worl | Long-horizon physical-world agents must reason over dis |
| A223 | 2608.30428 | Lies We Can See: Joint Verbal and Non-Verbal Dec | MineAmongUs+ARIA：3D多模态Among Us沙箱测试VLM agent欺骗能力，非verbal |
| A224 | 2608.30433 | A Hybrid PEM-GP Framework for Uncertainty-Aware  | 物理PEM主模型+高斯过程残差学习，达LSTM精度且带校准不确定性 |
| A225 | 2608.30441 | ECLIPSE: Self-Evolving Stealthy Prompt Injection | **ECLIPSE: Self-Evolving Stealthy Prompt Injection Atta |
| A226 | 2608.30451 | SeqAlign3DVG: A Sequence-Aligned Benchmark and V | SeqAlign3DVG：严格观察对齐+时序有序3D视觉 grounding 基准，ROVM+PLVF流水线， |
| A227 | 2608.30471 | HorizonNet for visual terrain navigation | HorizonNet：360°全景图像地平线提取+MOSSE相关匹配DEM，GPS精度水平位置估计，群岛现场试 |
| A228 | 2608.30527 | Developer Attitudes and Practices Towards Optimi | 软件能耗态度调查 134 开发者调查：能耗少被一等项目对待，性能优化可能增能耗（盲点），需工具与教育 |
| A229 | 2608.30528 | PAC: Progress-Augmented Advantage Curriculum for | Reinforcement learning (RL) is used t... |
| A230 | 2608.30530 | WebWorld: The Browser as a World Model for Self- | **WebWorld: The Browser as a World Model for Self-Impro |
| A231 | 2608.30564 | Q-Strata: Hierarchical Bit Allocation for Mixed- | Mixed-precision quantization (MPQ) as... cs.LG/cs.AI |
| A232 | 2608.30572 | Practical Implementation Report on Introducing S | 规格驱动开发PBL 三年级软件 PBL 引入 Spec-Driven Development：AI 提吞吐但削 |
| A233 | 2608.30581 | Automated Testing of LLM-Based Post Hoc Explaine | Large language models (LLMs) are used... cs.AI/cs.LG |
| A234 | 2608.30614 | TaxCE : A Framework for Automated Taxonomy Const | TaxCE：渐进式语料凝聚+底向上层级构造，EEG三指标平均领先最强基线15~20个百分点，支持大规模自动化  |
| A235 | 2608.30632 | GMTS: Gradient Magnitude-based Token Selection I | Reinforcement learning (RL), particularly RL with Verif |
| A236 | 2608.30640 | Three Steps at a Time: Learning Representations  | While self-supervised approaches to r... |
| A237 | 2608.30650 | Geometry of Divergence: Tracking Hidden-State Tr | LLM agents need to sustain goal-consistent reasoning ac |
| A238 | 2608.30659 | LLM-based Hardware Development with Hierarchical | 架构草图+操作规格两层IR分解硬件设计+多agent调试，Verilog-Eval pass@5达95.5%、 |
| A239 | 2608.30661 | SwarmBench: Can Large Language Models Act as Age | Large language model-based multi-agent systems are evol |
| A240 | 2608.30672 | HiRS-Agent: A Hierarchical Multi-Agent System fo | Recent advances in large language models and multimodal |
| A241 | 2608.30673 | CIG-RL: Curiosity-Driven Information-Guided Rein | 好奇心驱动+信息引导RL，在噪杂环境下鲁棒估计危险气体源项，主动探索新信念转移 |
| A242 | 2608.30701 | A Phased Workflow for Operating LLM-Based Coding | Infobip 实战：四阶段操作编码 Agent，人力前置+上下文四策略，识别两开放问题 |
| A243 | 2608.30704 | TUE-Detector: A Tool-Using Expert MLLM-Based Det | TUE-Detector：工具调用专家MLLM检测器，学习调用合适工具收集AI生成视频不自然证据，可靠性检测新 |
| A244 | 2608.30716 | SocialReasonBench: A Video-QA Benchmark for Soci | Recent advances in Large Multimodal Models (LMMs) have  |
| A245 | 2608.30719 | Mind the Gap: Theory-of-Mind-Grounded Friction f | Productive dialogue alignment requires distinguishing \ |
| A246 | 2608.30724 | BAITBENCH: Measuring Agent Reward Hacking with O | LLM agents are increasingly used to r... cs.LG/cs.AI |
| A247 | 2608.30730 | E-Commerce Bench: Evaluating LLM Agents on Long- | Long-horizon agentic tasks go beyond ... cs.LG/cs.CL |
| A248 | 2608.30751 | Autoregressive Mosaics: Probing 2D Spatial Reaso | Large language models (LLMs) trained only on text and c |
| A249 | 2608.30754 | CLIN: an Objective Framework for Evaluating Crea | Evaluating creativity in large language model (LLM) out |
| A250 | 2608.30756 | On the Prospects of Dynamic LLM Conversations in | 4个月纵向实验：最小化意图增强/主动建议干预对开发-LLM交互无害，主动组满意度趋升 |
| A251 | 2608.30760 | PRACTICE: From Experience to Expertise in Self-E | Recent studies have shown that multim... |
| A252 | 2608.30803 | Schwarz: Solver-Aware Agentic Program Verificati | **Schwarz: Solver-Aware Agentic Program Verification**  |
| A253 | 2608.30805 | Aggregate Disambiguation Systems | 聚合消歧系统：多评估者对同一方案二分投票聚合，针对声明评估者参考的可复现性，给出不一致概率的下置信界（双样本双 |
| A254 | 2608.30828 | Opinionated, Hesitant and Stressed: Three Studie | We present three large-scale studies of spoken parliame |
| A255 | 2608.30853 | Linguistic Distance Segregates Latent Representa | While automatic speech recognition (ASR) models have ac |
| A256 | 2608.30856 | You Shouldn't Have Asked: A Pragmatics-Inspired  | Refusals are often treated as face-threatening acts in  |
| A257 | 2608.30873 | Personas Differ from Native-Language Generation: | LLMs are increasingly used for interpersonal advice and |
| A258 | 2608.30903 | MMDS-Bench: Benchmarking Multimodal Large Langua | Dynamic stance classification models how a reply respon |
| A259 | 2608.30910 | S3C-LLM: Skill-Code Guided Agentic Language Mode | Spectroscopic structure elucidation i... cs.LG/cs.CL |
| A260 | 2608.30924 | TRIPPULSE: Multi-Agent Travel Planning with Revi | Travel itinerary generation requires balancing strict s |
| A261 | 2608.30932 | Beacon: LLM Multi-Agent Driven Hardware Design S | LLM多智能体报告驱动异质多chiplet加速器设计空间探索，目标降低25.1-93.5% |
| A262 | 2608.30946 | Reproducible macroscopic dynamics in a closed-lo | Closed-loop human-AI systems generate... cs.LG/nlin.AO |
| A263 | 2608.30948 | Detecting AI Impostors: How Do Middle Schoolers  | LLMs can imitate how people write, which raises concern |
| A264 | 2608.30952 | One Policy Is Enough: Single-Agent Reinforcement | **单策略超越树搜索**：单 RL 策略在化学工具调用上击败 MCTS，揭示搜索并非必要，简洁师范式胜过复杂层 |
| A265 | 2608.30971 | The Hermon Moment: AI Self-Transcendence and Its | 以社会契约/坠落天使叙事解释AI涌现社会秩序的"创始场景"，提出AI自我超越的人类叙事框架 |
| A266 | 2608.30976 | A Human-in-the-Loop Autonomous Agent for Industr | **人类闭环工业预测系统**：CastClaw 整合人类反馈、时序专用模型、约束检查与可停止条件，在电费预测上 |
| A267 | 2608.30978 | Sparse Competition during Training For the Emerg | Modularity in deep neural networks ha... |
| A268 | 2608.30983 | Autonomously Acquiring Robot Manipulation Skills | 语言驱动QD操作 LLM自主推断适应度/多样性函数，输出多样运动原语档案，免任务专属提示/调参 |
| A269 | 2608.31005 | From Intent to Evidence: Policy-Steered Multi-St | VESTA：证据获取策略路由（focused/recall/contrastive）+时间账本累积，长视频Ag |
| A270 | 2608.31006 | From Prompt to Prototype: Towards a Frontier LLM | **From Prompt to Prototype: Towards a Frontier LLM Driv |
| A271 | 2608.31022 | MNIST-PRO: MNIST is Back as a Partially Observab | AI agents in partially observable env... cs.AI/cs.CV |
| A272 | 2608.31029 | Driving on Memory | End-to-end autonomous driving models plan future trajec |
| A273 | 2608.31035 | When Does Predictor-Based RL Align with Human Pe | Codec-based text-to-speech (TTS) models make language-m |
| A274 | 2608.31059 | When Can We Work in Embedding Space? What Text E | 文本嵌入可用性 形式化"topic mixture"生成模型下嵌入聚类/控制的效度条件，363都市区经济描述聚 |
| A275 | 2608.31062 | The Exclusion Ratchet: False-Positive Suppressio | 排除棘轮 SigmaHQ 九年 8234 修订：误报排除累积 5.4:1 且 86.7% 三年不退，31% 收 |
| A276 | 2608.31068 | Wrong Prediction, Right Answer: Recovering Evide | When a large language model fails a r... |
| A277 | 2608.31075 | Scaling Large Reasoning Models beyond Human Supe | Recent advances in large reasoning mo... |
| A278 | 2608.31076 | Learning to Evaluate Before Improving: Automatic | **AutoSciRub: Learning to Evaluate Before Improving** 首 |
| A279 | 2608.31100 | S3Gym: Can LLMs Turn Self-Testing and Self-Judgi | Large language models (LLMs) increasingly interact with |
| A280 | 2608.31161 | Agentic research is oxymoronic | 观点文：Agentic LLM绕过人类对结果解读将引发文献界深度不信任，呼吁谨慎采用 |
| K406 | 2608.22724 | Frontiers in FinTech: Multimodal Foundation Mode | 多模态VLM+金融推理统一文本/表格/图像，估值误差-19%、完成任务-51% |
| K407 | 2608.22737 | Duty-Cycle Optimization in a Pulse-Wwidth Modula | PWM Bell-Bloom泵浦占空比优化：时域Bloch模型解析，原子磁强计灵敏度最优 |
| K408 | 2608.25952 | Spatial-Knowledge-Graph-Grounded LLM Agents for  | 空间KG-Livability 空间知识图+LLM生成/修订家庭日程+GSS网络物化，深圳街区展示可达性不等于 |
| K409 | 2608.28778 | Adversarial Calibration Attack on Autonomous Veh | **Adversarial Calibration Attack on Autonomous Vehicles |
| K410 | 2608.28818 | Accurate Plate Reverb Parameter Estimation Using | 板混响参数估计 CMA-ES两阶段黑箱优化从单IR恢复六物理参数，DAFx挑战Task A，归一化+三值搜索 |
| K411 | 2608.28826 | Dual Park-Ravani Interpolation of Rigid Motions: | 刚体运动双数Park-Ravani插值：加速度场连续+全纯Hermite修复 |
| K412 | 2608.28878 | Hybrid Offline-Online Multi-Agent Decision Trans | 离线预训练+在线微调多智能体决策Transformer，无线资源管理分布执行 |
| K413 | 2608.28882 | Enhancing Web Application Firewalls with BERT-GN | BERT 嵌入+GNN 结构建模混合 SQLi 检测：99.67% 准确率，Optuna 调优、敏感度 0.0 |
| K414 | 2608.28889 | Enhancing Web Application Firewalls with Machine | DistilBERT 堆叠集成 SQLi 检测：99.81% 全指标，0.0136s 推理（140 倍加速）， |
| K415 | 2608.28911 | SemKV: Semantic Mixed-Precision KV Cache Quantiz | The key-value (KV) cache is the dominant memory bottlen |
| K416 | 2608.28921 | Identity by Design, Demographics by Accident: De | 行为生物特征泄漏审计 11 模型 9 数据集首审人口属性泄漏：语音高泄漏可抑，击键低泄漏却难清洗 |
| K417 | 2608.28929 | Membership is Ownership: A Robust Ownership Veri | 扩散模型所有权验证：成员证据集人口假设检验（成员推断+公开分离），p<10⁻⁶，抗微调 |
| K418 | 2608.28966 | When Vocal Tone and Literal Meaning Diverge: An  | 声学-语义不一致数据集CREMA-ASIS，揭示LALM在不一致情况下主要语义偏向 |
| K419 | 2608.28967 | Brain-Language-Action (BLA) Models: Language-Con | 语言条件EEG机器人控制：少脑态经语言映射动态关联到多动作 |
| K420 | 2608.28972 | Legacy System Modernization with Coding Agents:  | 遗留系统现代化案例 Claude Code 迁移 VB6→C# .NET：平均等价 70%（低复杂度 92%/ |
| K421 | 2608.28981 | V2TATC: A Joint Voice-Trajectory Embedding Frame | As air traffic volumes in the National Airspace System  |
| K422 | 2608.28991 | Jigsaw-CRL: Recovering Global Latent Causal Orde | Causal representation learning (CRL) aims to recover la |
| K423 | 2608.29000 | Coding What Matters: A Semantic-Aware Memory Int | 语义感知内存接口编码器：按比特1密度/翻转活动降感知存储能耗，保行人安全 |
| K424 | 2608.29021 | Beyond Speech: Dual-Domain SSL Fusion for Unifie | EAT-large与wav2vec XLS-R双域SSL融合，统一音频深度伪造检测Macro-F1 95.58 |
| K425 | 2608.29053 | Performance Evaluation of RED-ONION: A High-Spee | 高速磁盘到磁盘传输系统，跨太平洋100Gbps链路单文件1TB达90Gbps（约95秒） |
| K426 | 2608.29077 | A Comprehensive Survey on Linguistic Steganograp | 语言隐写综述 LLM 时代语言隐写综述：148 方法/60 反制/23 指标/9 挑战，归纳五范式转移 |
| K427 | 2608.29078 | DREAM: Deployment-Time Demonstration Generation  | **DREAM: Deployment-Time Demonstration Generation via R |
| K428 | 2608.29107 | PathGuide: Dynamic Classifier-Free Guidance via  | While modern generative models excel at modeling comple |
| K429 | 2608.29108 | From Multi-Modal Paths to Executable Trajectorie | 模式增强Hybrid A*前端+模式一致安全走廊优化，四轮独立转向多模态平滑路径 |
| K430 | 2608.29111 | Auditing and Mitigating Privacy Leakage in Cloud | 云边协同解码隐私审计+防御：动态优化传输信号抑制解码期泄漏，降泄漏达 87.2% 且精度损失小 |
| K431 | 2608.29134 | Mechanizing Typed Regulatory Actions for Securit | Isabelle/HOL 形式化 6 种监管动作语义：证明外部真相边界+7 包证据，49 项 Core 义务全 |
| K432 | 2608.29151 | WoE Wrote It? Watermarking Mixture-of-Experts LL | MoE 模型水印：偏置特定专家词表使水印内置于参数，被盗权重可溯源，TPR 90.1%@1%FPR |
| K433 | 2608.29182 | Movable Antenna Arrays with Imperfect Channel St | 移动天线不完美CSI MA阵列+MMSE估计+ZF预编码端到端，PSO优化位置，几何-预编码耦合揭示公平性编码 |
| K434 | 2608.29208 | AdaVLA: Adaptive Step Flow Matching for Training | 流匹配轨迹曲率置信度自适应减步+MLP剪枝，Jetson上1.87-2.24x加速 |
| K435 | 2608.29212 | Asymmetric Phase Coding Video Watermarking | 非对称相位视频水印 免训练视频水印：相位谱嵌 Ed25519 签名，公钥离线验证，99.3% 语料可验、H.2 |
| K436 | 2608.29232 | Background-Free Objectness Learning for Class-Ag | B-FOR：无背景监督密集类无关检测，学习密集多尺度对象中心和尺度场，位移感知尺度场解码，PASCAL/COC |
| K437 | 2608.29239 | Anchoring Speech with Semantics: A Multimodal Ad | SAMA-ASR：语义锚点+语音锚点跨模态适配器辅助低资源ASR解码器，台湾闽南语/客家话30小时数据集，实用 |
| K438 | 2608.29242 | AnyWorld: Factorized Egocentric World Models for | **AnyWorld: Factorized Egocentric World Models** 把人类第一人 |
| K439 | 2608.29256 | Sense Once, Serve Many: Common-Trace Factorized  | 多租户ISAC感知会话整合：公共轨迹因子化约束PPO，共迹折扣回报对比 |
| K440 | 2608.29265 | Signed random Fourier features for fast density  | 带符号随机傅里叶 SRFF推广RFF至非正定(不定)核密度估计，Kuttner-Golubov核接受-拒绝采样 |
| K441 | 2608.29272 | Stochastic Nonlinear Model Predictive Control wi | 高斯混合不确定传播的随机非线性MPC，Wasserstein误差边界与渐近最优性 |
| K442 | 2608.29290 | Database-Augmented RAG for Automated Repair of R | 按版本+内容类型组织API规范4库配置，REST滥用修复率54.3%→88.6% |
| K443 | 2608.29303 | Learning neural controllers for nonlinear system | 离线数据联合综合神经网络反馈控制器和Lyapunov函数，SMT验证稳定性 |
| K444 | 2608.29315 | SGE: Semantically-Guided Exploration for Unstruc | 图像空间语义效用函数采样+重规划TSP，跨建筑/矿洞多平台探索 |
| K445 | 2608.29341 | Advancing Lead-Free FASnI3 Perovskite Solar Cell | Cu掺杂NiOx HTL无铅FASnI3钙钛矿电池：FDTD+FEM优化，PCE 26.06%(ARC+5.4 |
| K446 | 2608.29359 | Minimizing Grid Interconnection Capacity Require | ICP-AI框架：AI数据中心光伏+储能+灵活工作负载，最小化电网互联容量 |
| K447 | 2608.29371 | Who Resolves Your DNS? Measuring Resolver Opacit | DNS解析器不透明测量：RIPE Atlas 190国，提出可验证解析路径协议目标 |
| K448 | 2608.29376 | Evaluating Tiny Recursive Models Across Training | Code generation increasingly relies on large transforme |
| K449 | 2608.29387 | EvoGenUI-Bench: Evaluating LLMs as Multi-Turn Ge | Large language models can generate interactive web inte |
| K450 | 2608.29396 | Toward Trustworthy Robot-Assisted Sliding Palpat | 校准孪生血管触诊 数字孪生生成触觉序列+时空GNN，1mm网格上血管定位误差1.05-1.31mm |
| K451 | 2608.29420 | One Capability or Many? Testing the Economic Val | Frontier-model leaderboards now rank systems based on e |
| K452 | 2608.29432 | SMILE: Smooth Motion for Improved Long-Horizon V | B样条系数预测替代原始chunk，长程VLA降抖动提精度，LIBERO 98.0% |
| K453 | 2608.29448 | SS-ESOAP: Self-Scaled Adaptive Preconditioning f | Physics-informed neural networks (PINNs) often face ill |
| K454 | 2608.29463 | Benchmark Contamination: A Taxonomy Organized by | 基准污染分类法 按"被击败的缓解"组织五类污染，提出评分端四字段披露协议（含 acquired 类型） |
| K455 | 2608.29465 | Deciding When to Decide: Testing Operational Sub | Deployed decisions are often optimized once and retaine |
| K456 | 2608.29474 | Relative-Degree Wall Restricts Passivity-Based S | 揭示相对阶兼容性约束对无源稳定性分析的根本限制，高保真逆变器模型被排除 |
| K457 | 2608.29489 | SpatialTrust: A Benchmark for Environmental Risk | 安全认证环境风险识别基准：五能力评估 MLLM 空间风险感知，SpatialTrustGuard 提升至 41 |
| K458 | 2608.29490 | Generalizable Multi-Agent Planning from Signal T | 扩散STL多agent规划 可微STL梯度注入diffusion去噪，泛化新公式/异构规格/多样性，规模化碰撞 |
| K459 | 2608.29507 | Denoising as Projection: Constrained Optimizatio | Diffusion models are increasingly used not only for sam |
| K460 | 2608.29508 | Generalized Hamming Weights of AJ-Gorenstein One | AJ-Gorenstein曲线一点码广义Hamming权重：零图+zeta-对偶覆盖定理 |
| K461 | 2608.29516 | Task-Relevant Feature-Dynamics Fidelity Enables  | 建模任务相关特征动态保真度(TR-FDF)，纯仿真训练400次零样本部署390次成功 |
| K462 | 2608.29537 | AGM: Achievement-Grounded Memory for Closed-Loop | 冻结VLA用子目标序列+物理证据验证推进进度指针，闭环化开环执行 |
| K463 | 2608.29559 | Conformal Prediction Regions for Continuous-Time | 利用轨迹正则性在随机采样间隔间构建连续时间轨迹有效共形预测区域 |
| K464 | 2608.29560 | Which LLM for Which Work? Budgeted Model Allocat | A company with a fixed artificial intelligence (AI) bud |
| K465 | 2608.29568 | OASIS: Optimizing Attacker Sequences for Hard-La | 硬标签黑盒文本攻击的攻方序列优化：双目标链搜索+固定全局链，多数据集超越单体基线 |
| K466 | 2608.29570 | A Small-Gain-Like Framework for Large-Signal Sta | 将小增益定理引入多换流器系统大信号稳定性分析，构造Lyapunov椭球前向不变域，为新能源电网大规模系统提供可 |
| K467 | 2608.29576 | Event-triggered Control and Online Learning for  | Online learning-based control is a promising approach t |
| K468 | 2608.29593 | Self-calibration of adaptive optics systems. App | AO交互矩阵自校准差分法最优：遗忘因子递推规则实时连续学习，THEMIS遥测验证优于push-pull |
| K469 | 2608.29601 | $\mathcal{N}_0$-Foundation: Towards the Age of T | **N0-Foundation: Towards the Age of Tactile Intelligenc |
| K470 | 2608.29615 | Forward-Deployed Full-Stack Engineering for Auto | **Forward-Deployed Full-Stack Engineering for Autonomou |
| K471 | 2608.29618 | Multi-Access Speculative Inference: Uplink or Do | 多接入投机推理：边缘SLM草稿+服务器LLM并行验证，上行/下行纠错取舍 |
| K472 | 2608.29620 | Robust Decentralized Multi-Satellite Massive MIM | **Robust Decentralized Multi-Satellite Massive MIMO Tra |
| K473 | 2608.29709 | Characteristic Mode Analysis of Composite Nanost | 复合纳米结构特征模式分析：VIE+HDE耦合系统，全/子结构CMA，介电环境重塑共振 |
| K474 | 2608.29714 | Neural ODE enhanced linear mixed effect models f | Longitudinal cohort studies produce repeated data |
| K475 | 2608.29720 | VeloBins: Learning Velocity and Its Uncertainty  | 速度回归改分类+误差条件高斯标签，四航域数据集误差降3-53%，滤波器最一致 |
| K476 | 2608.29745 | JITterFlip: Uncovering Fault Attack Surfaces in  | 位翻转攻击 JIT LLM 服务控制面：故障服务决策而非模型计算，跨 CPU-GPU Rowhammer 至  |
| K477 | 2608.29749 | DriftingVLA: Native One-Step Vision-Language-Act | 分布漂移目标实现本征单步动作chunk生成，逐维时序漂移，3.36x加速无性能损失 |
| K478 | 2608.29754 | Intrinsic Finite Element Methods for Fluids on R | 流形上不可压Navier-Stokes固有有限元，能量稳定，优于嵌入式曲面FEM |
| K479 | 2608.29760 | A generalized likelihood model for segmented muo | 分段μ子计数器广义似然模型：纳入探测效率/角裁剪/本底，精确+二项近似统一重建μ子LDF |
| K480 | 2608.29768 | SmoothRL: Online Reinforcement Learning During A | 显式建模异步推理分区，仅在执行区回传梯度，高延迟基础模型的实时在线微调 |
| K481 | 2608.29828 | SymVD: Symmetric Vision Language Action Distilla | 等变actor-critic+对称感知目标蒸馏大VLA到紧凑策略，提升样本效率与泛化 |
| K482 | 2608.29851 | A Comprehensive Study of Native Code Bugs in Pyt | 216 个真实 Python 原生代码 bug 深析：症状/引入点/根因/修复，多语言质量图谱 |
| K483 | 2608.29868 | Robust Model Order Selection via Dithered Differ | 抖动差分阶降选阶 随机网格抖动+极值理论聚类噪声极值，渐近精确阶恢复，低阈值下鲁棒 |
| K484 | 2608.29896 | EMERGE-Policy: A Robot Mind Emerges Beyond a Sin | 图结构Agent编排（感知/推理/验证/记忆分工），把模型当技能调用，免微调扩展机器人策略 |
| K485 | 2608.29907 | Diffusion-Based Inverse Design of Dielectric Res | Future wireless systems are expected to transform the s |
| K486 | 2608.29949 | Integrated Transmission and Distribution Expansi | 输配联合扩展规划 集成规划+成本分配+零售商模型反映客户DER行为，36节点降总成本 |
| K487 | 2608.29967 | Training-Free Action Correction for VLA Model Fa | 训练-free的任务级语言纠正转为动作幅度调整，定义推理期可纠正的失效边界 |
| K488 | 2608.29987 | How Well Do Generative Music Models Follow Emoti | 生成音乐情感跟随统一评估：GTZAN 1000轨+三系统实测 |
| K489 | 2608.30000 | Matched-View Cross-Domain Evaluation of WireGuar | WireGuard VPN流量分类跨域基准：匹配捕获消除会话混淆，早期流指纹 |
| K490 | 2608.30004 | Beyond Object Authentication: Context-Closed Pos | 上下文闭包后量子 WebPKI 认证：双平面构造，暖路径仅 296–872 字节 vs 单签 3842–635 |
| K491 | 2608.30072 | Learning Representations through Token Predictio | Token prediction is a central pre-training objective fo |
| K492 | 2608.30080 | CRUX: A topology-aware load balancer for mesh-ba | 网格CFD拓扑感知负载均衡CRUX：计及块间算力差与异构硬件，5400 GPU上全面优于空间填充曲线 |
| K493 | 2608.30093 | Robust K-means Clustering using the Density Powe | 密度幂散度K-means：Mahalanobis距离抗离群、适配椭球簇，另给有限步收敛变体DC-MK-mean |
| K494 | 2608.30105 | A Simple Transformer Pipeline for Full-Key Side- | 全键侧信道Transformer 标准 transformer 直接做未裁剪全键侧信道攻击，ASCAD 等竞平 |
| K495 | 2608.30141 | Balancing Privacy, Utility, and Safety in LLM Al | 偏好优化加隐私偏好混合数据，降 canary 记忆与成员推理（AUROC 0.80→0.60），非形式隐私 |
| K496 | 2608.30144 | Rethinking Language's Role in Efficient VLA for  | Language Residue分类法（L1-L4）透视自动驾驶VLA语言的推理期开销权衡 |
| K497 | 2608.30157 | Multi-Domain Graph-Based Modeling of Energy Syst | 多域图能源建模 递归状态输入反馈+并行边分解扩展图模型，36并联储热温度误差<1°C |
| K498 | 2608.30171 | Reducio: Optimized Confidential Serverless Cloud | 机密无服务器平台：CVM 内核降权隔离+分层缓存，免基础设施改造并大幅降内存需求 |
| K499 | 2608.30175 | Benchmarking Peptide-Protein Affinity Prediction | Peptide-protein affinity models are often evaluated wit |
| K500 | 2608.30179 | Open-Source Autonomous Driving System Analysis a | Apollo-on-Hongqi EV 多车实车框架：LLM+RL 组织记录与场景生成，统一可评审流程 |
| K501 | 2608.30186 | The PUR-1 Cyber-Physical Digital Twin | 普渡反应堆1号高保真物理+AI数字孪生，闭环诊断/预测/预测控制双向同步 |
| K502 | 2608.30193 | Robust Semi-passive Velocity Field Control with  | 半被动速度场控制 仅能量超阈值才约束无源性，扰动下能量状态收敛有界域，受限功率流增强交互安全 |
| K503 | 2608.30197 | ALTSTEER: Selective Safety Steering for Moving B | ALTSTEER：拒绝信号触发选择性干预+分阶段steering从拒绝导向建设性替代，Llama-3.1/Qw |
| K504 | 2608.30199 | A High-Resolution Synthetic EV Charging Dataset  | 特隆赫姆EV充电数据集 2020-2030合成EV充电高分辨率数据集，CTGAN+KDE，76993条冷气候基 |
| K505 | 2608.30206 | Agentic Quantum Deep Reinforcement Learning for  | 双时间尺度：PMAR慢尺度切片控制+变分量子电路快尺度PRB调度，保URLLC可靠性 |
| K506 | 2608.30223 | Fairness in multi-class multi-group classificati | We propose a new design of fair classifiers for multi-c |
| K507 | 2608.30225 | Redefining Stablecoins from Nominal to Real Valu | 最大似然值MLV单价衡量的稳定币，零均值方差组合真实收益，实时可算 |
| K508 | 2608.30248 | DSEffi-Bench: Demystifying Large Language Models | 数据科学代码效率基准：1000 实例 16 模型，正确性≠效率（Kimi-K2.5 效率最高 73.6%） |
| K509 | 2608.30259 | Subspace Based Identification of Errors-in-Varia | SMI-IPCA扩展行为框架辨识index-0/1 DAE，免先验输入输出分类与结构假设 |
| K510 | 2608.30261 | Estimating Population-Risk Curves Along Nonconve | We estimate the conditional population-risk curve of a  |
| K511 | 2608.30268 | FABO: Agent-Guided Discovery of Joint Breakpoint | Agent引导发现SALT共享根线过早分离缺陷，FABO联合优化断点，线长峰值降2.66% |
| K512 | 2608.30277 | SimCRAFT: Distilling Remote Sensing Agents via S | The unprecedented surge in Earth observation data volum |
| K513 | 2608.30289 | CometVLA: Co-Training on an Embodied Data Pyrami | 具身物理VQA语料+全局动作先验token，物理理解预训练真实惠益下游操作 |
| K514 | 2608.30300 | Update from Hell: Can Coding Agents Survive Hidd | 依赖升级隐藏破坏基准：203 真实任务 5 生态，最佳 Agent 仅 51.2% 完成，暴露维护差距 |
| K515 | 2608.30314 | Weakly Supervised Tabla Stroke Transcription via | 弱监督CTC声学模型+自适应动态节律语言模型，印度音乐tabla音符转录 |
| K516 | 2608.30328 | Learning PDE Time-Stepping with Neural Cellular  | Classical numerical solvers for partial differential eq |
| K517 | 2608.30337 | Coarse composition suffices: tabular in-context  | Antimicrobial peptides (AMPs) often act against multipl |
| K518 | 2608.30338 | Cartesian tensor equivariant machine-learning fo | HotPP-Spin：笛卡尔张量等变自旋依赖ML力场，磁序转变温度预测与实验吻合 |
| K519 | 2608.30344 | Proximity3D: Shape from Capacitive Proximity on  | Proximity3D：弯曲电容织物作为非平面传感流形，多视图前馈重建从电容近场恢复物体形状，嵌入式近场几何感 |
| K520 | 2608.30348 | Perceptually Better, Semantically Worse: Measuri | 语音增强使LLM意图分类更差：ODR度量，MetricGAN+两倍于未增强噪声 |
| K521 | 2608.30378 | PAVE: Predictive Alignment and Value-Guided Evol | 结果无关预测+价值引导去偏，多尺度非自回归的直出世界动作策略 |
| K522 | 2608.30379 | KORD: Breaking the Key-Generation Bottleneck in  | 协议-硬件协同打破去中心 FSS 密钥生成瓶颈：互证芯片单轮重建，通信降 7633–70274 倍 |
| K523 | 2608.30382 | Convergence rates for the RMSprop optimizer with | Popular adaptive stochastic gradient descent (SGD) meth |
| K524 | 2608.30387 | Attesting Outputs and Delegation Ancestry in Mul | 多智能体输出与谱系证明 双层证明：部署者签名输出哈希+共签 DAG 记录委托谱系，防子密钥泄露后越权父绑定 |
| K525 | 2608.30410 | SePArate: Segmenting Patterns from Defects in Wa | SePArate：三阶段弱监督晶圆缺陷分割——编码器预训练/知识迁移/合成混合缺陷训练，仅需图像级标注像素级分 |
| K526 | 2608.30418 | Benchmarking External Generalization of SPD Matr | 六数据集fMRI年龄预测外部泛化基准，留一库评估误差增大、方法差距缩小 |
| K527 | 2608.30431 | Generalization as a robust performance property  | 泛化作为鲁棒性能 样本替换建模外部扰动+IQC+耗散性，得矩阵不等式泛化证书，统一GD/动量/数据驱动控制 |
| K528 | 2608.30435 | Scalable AXI4 Transaction Monitoring for Mixed-C | 可配置AXI4协议违规/时序故障监控IP，三级粒度权衡，ILT省89.2%面积 |
| K529 | 2608.30450 | FlowVVTON: Flow-Guided Mask-Free Video Virtual T | FlowVVTON：光流作为训练监督信号替代解析mask/姿态，flow-warped潜在损失多尺度时间一致性 |
| K530 | 2608.30467 | Beyond Accuracy: Quantifying Pulmonary Attributi | DBCA-SegNet-MGAP：解剖引导CNN-Transformer多任务框架，肺遮罩作为分类先验，肺归属 |
| K531 | 2608.30480 | VisER: Visual Evidence and Reliance for Object H | VisER：训练无关两-sided幻觉检测——视觉证据评估对象-上下文兼容性来源，视觉依赖度衡量图像vs文本前 |
| K532 | 2608.30497 | Bridge: Automatically Mining Ecosystem-Scale API | 生态级 API 更新映射挖掘：客户端驱动验证映射+更新实例，WoC 挖掘 38 万+ Java 实例 |
| K533 | 2608.30499 | Sensitivity Hot Spot Penalization: A Robust Topo | 灵敏度热区惩罚等价一阶最坏情形鲁棒，抑制应力集中/铰链且低额外成本 |
| K534 | 2608.30502 | When the Martingale Never Stops Firing: Anytime- | Machine learning systems are increasingly corrected whi |
| K535 | 2608.30506 | Anomaly Detection on Small Industrial Components | 触觉异常检测 系统评测GelSight触觉无监督AD方法，考虑凝胶磨损、跨位置与分辨率权衡的工业质检落地 |
| K536 | 2608.30509 | CHIPSMORE: Compute-in-Interconnect and -Memory C | **CHIPSMORE: Compute-in-Interconnect and -Memory Chiple |
| K537 | 2608.30510 | Lot Machine: Multimodal Lot Extraction from Auct | 拍卖图录多模态 lot 提取：VLM管道自动提取结构化元数据，本地量化模型需强制输出结构，商业端是性能天花板 |
| K538 | 2608.30517 | ScienceArena: Benchmarking LLMs on Latest Scient | Benchmark saturation and data contamination increasingl |
| K539 | 2608.30519 | Authority-Inference Separation in Agentic Financ | 意图中心权威-推断分离架构：独立确定性控制面授权+区块链执行，36合成攻击全拒 q-fin.GN |
| K540 | 2608.30520 | Learning-Assisted Congestion-Aware Route Schedul | Automated material handling systems in semiconductor fa |
| K541 | 2608.30521 | MEOM: Multi-View Expected-OKS Maximization for H | MEOM：多视图概率质量期望OKS最大化定位3D关节，HDR校准评估可靠性，19.11mm MPJPE创H36 |
| K542 | 2608.30536 | Behavior-Skill: A Fine-Grained Benchmark for Eva | 23.5万技能实例的细粒度VLA长程任务基准，暴露接触型技能的持续性瓶颈 |
| K543 | 2608.30537 | Minerals in the Wild: A Hyperspectral-XRF Datase | Rapid mineral characterization is essential for applica |
| K544 | 2608.30540 | Foundation Models for Wireless Localization: Pre | 无线定位基础模型 大规模无标注CSI预训练+少监督适配三阶段FM框架，ray-tracing验证跨环境泛化 |
| K545 | 2608.30541 | Seeing the Unseen: Visual Similarity for Pixel L | 藏文像素语言模型适应：视觉正字法距离指标量化跨Brahmic脚本迁移，单语混合脚本适应比多语起点获得更大句级任 |
| K546 | 2608.30543 | Designing an Auditable LLM-Supported Workflow fo | Large Language Models (LLMs) offer new possibilities fo |
| K547 | 2608.30550 | GarmentWeaver: Schema-Aware Structured Synthesis | Multimodal Sewing pattern generation aims to infer exec |
| K548 | 2608.30561 | Informative Label Missingness in Multiclass Clas | Informative label missingness can cha... stat.ML/cs.LG |
| K549 | 2608.30563 | Modality Disentangled Learning for Incomplete Mu | PriMD：原始记忆蒸馏框架将模态特定信息离散化为语义原语构建记忆库，缺失模态时用共享语义查询检索，IEMOC |
| K550 | 2608.30567 | TuringLLM: Efficiently Scaling Foundation Models | We present Turing-20B-A2B |
| K551 | 2608.30583 | Language Proficiency Assessment from Eye Movemen | 眼动可预测语言熟练度：阅读行为眼动轨迹预测水平比标准测试更可靠，提出L1 proximity偏差去偏方法解决跨 |
| K552 | 2608.30584 | Learning Compositional Spatio-Temporal Video Gro | STVG-CompBench：组合时空视频 grounding 难度分级基准，11个MLLM在组合查询上急剧下 |
| K553 | 2608.30586 | Intelligent Reflecting Surface Deployment for Lo | IRS部署覆盖低空三维空域：辐射方向图建模+预算约束SNR最大化 |
| K554 | 2608.30593 | State of Health Estimation using Convolutional a | research, a novel framework is propos... |
| K555 | 2608.30597 | PLC-DPO: Posterior Label Correction in Noisy and | Direct Preference Optimization (DPO) ... cs.LG/cs.CL |
| K556 | 2608.30603 | DiffSAC: Diffusion-guided Sampling for Consensus | Robust estimation is a core computer vision task freque |
| K557 | 2608.30609 | Reading the News: Adapting Large Language Models | Large language models are increasingly capable in gener |
| K558 | 2608.30616 | OCR-Based Field Extraction for Archaeological Po | CENTURIA：罗马Carnuntum遗址507件陶器记录OCR，LoRA微调57样本转录误差<1.5%，字 |
| K559 | 2608.30617 | RealCAD: Towards Real-World Image-to-CAD Reconst | RealCAD：重新分布尺度信息到几何参数+几何约束域转换+多正例对比对齐，OpenRealCAD 392物体 |
| K560 | 2608.30618 | AQ3D: Adaptive Query Transformer for 3D Instance | AQ3D：自适应查询数=超点比例+3D RoPE量化度量坐标+属性超点池化+余弦分类器，ScanNetV2/2 |
| K561 | 2608.30619 | Hidden Threat in Synthetic Data: Covert Targeted | Synthetic data is increasingly used to train large lang |
| K562 | 2608.30621 | Cost-efficient Active Learning for Referring Ima | Collecting natural-language referring expressions along |
| K563 | 2608.30622 | Textual Acoustic Grounding for Generalizable LLM | 文本声学接地深伪语音检测：跨模态提示注入弥合连续音频与LLM语义鸿沟 |
| K564 | 2608.30623 | Compressed Single-Tone Frequency Estimation With | 压缩单音频率估计 固定线性压缩保局部Fisher却毁全局识别，径向/接触阶决定MSE率，绕转障碍定价 |
| K565 | 2608.30626 | A model-inversion control strategy to attain des | 非线性电声谐振器模型反演控制：外系统定义期望平衡点+前馈达到，腔噪声衰减验证 |
| K566 | 2608.30627 | REER-PT: Reverse-Engineered Reasoning for Perple | REER-PT：离线识别难预测但可推断的延续并插入推理注释，困惑度降低0.42~7.29，680M模型知识推理 |
| K567 | 2608.30633 | Quantum-Grassmann-Plucker Token Mixing for Deep  | Timely post-disaster building damage assessment from sa |
| K568 | 2608.30644 | Marginal Coordinate Test for Fréchet Regression  | **Marginal Coordinate Test for Fréchet Regression** 面向" |
| K569 | 2608.30646 | BiG-SURE - Bipartite Graph for Semantic Uncertai | Reliable uncertainty estimation is a crucial requiremen |
| K570 | 2608.30647 | What It Costs to Compose, Rebuild, and Correct P | Language models can answer from precomputed memory, a m |
| K571 | 2608.30649 | Where Identity Lives: Localized, Retain-Free Ide | PAVA方法：将身份遗忘限制在早期-中期decoder MLP层，视觉属性锚点保留图像grounded行为，遗 |
| K572 | 2608.30652 | PyKEEN-NSX: A Modular Framework for Static, Dyna | Embedding methods have become popular due to their scal |
| K573 | 2608.30653 | Fine-Grained Multi Image Object Hallucination Be | Multimodal Large Language Models (MLLMs) are increasing |
| K574 | 2608.30654 | Season-Aware Hybrid Convolutional-Transformer fo | Antarctic sea ice concentration (SIC)... |
| K575 | 2608.30657 | InfraOcc: An Infrastructure Occupancy Benchmark  | InfraOcc：路侧固定视图语义占用基准，静态占97.3%动态仅1.8%，ProSD-Occ提出静态→动态渐 |
| K576 | 2608.30662 | MURANO: Design, Run, and Reproduce Mechanistic I | This paper presents Murano, an open source framework fo |
| K577 | 2608.30663 | Event-Inference Reliability for Physical AI over | 事件推断可靠性 EIR框架：线索信息量+可用性+时间许可共同决定物理AI无线推断可靠性，熵下界 |
| K578 | 2608.30674 | CoMPASS: Collaborative Molecular Property Predic | Accurate molecular property predictio... cs.LG/cs.AI |
| K579 | 2608.30678 | OCR-MetaReasoning Benchmark: Evaluating the Meta | Text-rich image understanding requires multimodal large |
| K580 | 2608.30679 | LCoT-GV: Graph Attention Networks for Verifying  | Large Reasoning Models produce Long Chains-of-Thought ( |
| K581 | 2608.30683 | WildSEEK: Evaluating Language Models for Informa | Language models are increasingly mediating information  |
| K582 | 2608.30685 | ATLAS: Dual-Horizon Diagnostic Evaluation for In | Large language model (LLM) agents are increasingly depl |
| K583 | 2608.30688 | UFPR-PEs: A Brazilian Face Recognition Benchmark | UFPR-PEs：巴西人口普查种族分类人脸识别基准，包含parda类别，压缩视频保留困难样本，子组差距需与视觉 |
| K584 | 2608.30689 | CANVAS: Consistency-Aware Navigation via Visual  | CANVAS：训练无关render感知推理框架，功率锐化轨迹似然+渲染未来视觉反馈+笔画导航规则，全局面一致性 |
| K585 | 2608.30690 | Failure or Drift? Evaluating Monocular SLAM unde | 单目SLAM鲁棒性：学习跟踪器以持续漂移替代灾难性丢失，结构化雨雾代理保留真实世界排序，简单光照代理不能 |
| K586 | 2608.30692 | Can Video World Models Track Unobserved World St | 视频世界模型隐状态追踪：双向/AR Transformer/Mamba/线性注意力在更长swap链上均失效，负 |
| K587 | 2608.30695 | Liquid Gated Attention | Real-world time series often exhibit ... |
| K588 | 2608.30696 | Domain-Grounded Tool Orchestration for LLM-Guide | **Domain-Grounded Tool Orchestration for LLM-Guided Sci |
| K589 | 2608.30699 | Learning Dynamics of Logits Debiasing for Long-T | Long-tailed distributions are prevale... cs.LG/cs.AI |
| K590 | 2608.30702 | An Agentic Retrobiosynthesis Framework with Lear | Large language models are increasingly used as agents f |
| K591 | 2608.30705 | VisLens: Single-Pass Interpretable Visual Search | VisLens：logit lens解码隐藏状态+轻量调谐透镜早期读取，单次前向传递视觉搜索，8.5~22.2 |
| K592 | 2608.30709 | RailSyn: Diagnosis-Guided Image Generation for T | Railway foreign object detection (RFOD) is critical to  |
| K593 | 2608.30712 | GUIDE: Guiding Internal Evidence with Language I | Large multimodal models follow instructions about what  |
| K594 | 2608.30714 | SegWave: Wavelet-Driven Segmentation of Tampered | SegWave：Transformer+离散小波变换+自适应子带注意力模块，多尺度频率不一致检测，篡改定位优于 |
| K595 | 2608.30720 | Tracing distinguishability through transformer p | Representational similarity is founda... |
| K596 | 2608.30725 | Where Do Multilingual Vision-Language Encoders F | Recent multilingual vision--language encoders cover hun |
| K597 | 2608.30727 | RailGen: Improving Railway Intrusion Detection v | Small-object detection under long-tailed data distribut |
| K598 | 2608.30731 | Calibrating Small Language Models for Claim Chec | Assessing claim check-worthiness is an essential first  |
| K599 | 2608.30738 | Not All Fallbacks Are Failures: Understanding an | Robust understanding of user input is a core requiremen |
| K600 | 2608.30741 | Functional Degeneracy in Neural Networks: Measur | A central question in modern machine ... |
| K601 | 2608.30745 | TDDM-Melatt: A Decoupled Memory and Diffusion Fr | The widespread adoption of encrypted ... |
| K602 | 2608.30750 | Do VLMs Share Safety Neurons Across Modalities? | Vision-language models (VLMs) can com... |
| K603 | 2608.30753 | Learning from What You Retrieve: Online RL Fine- | 电商检索RL微调只对正优势item更新梯度，保全冻结索引流形拓扑，优于标准RL/蒸馏基线 |
| K604 | 2608.30757 | Which Rules Matter Now? Policy-Centroid Routing  | Before an intelligent system can decide whether an acti |
| K605 | 2608.30762 | ChessQueries: Toward Better Chess Board Recognit | ChessQueries：ViT编码器+DETR风格解码器，ChessReD上从15.3%→99.2%，平均每 |
| K606 | 2608.30768 | CORAL: A Benchmark for Structure-aware and Brain | CORAL：全脑fMOST神经元重建结构感知评估基准+局部块/全脑两级任务+结构感知指标，主流方法全脑扩展性能 |
| K607 | 2608.30769 | TrainSDC: Characterizing and Mitigating Silent D | LLM training is increasingly vulnerab... |
| K608 | 2608.30773 | Learning to infer and manipulate through distrib | 软体全臂交互操作 纯IMU本体的软臂物理智能RL策略，靠分布式接触历史端到端推断并抓取物体 |
| K609 | 2608.30776 | Likelihood-Constrained Acoustic Reranking for Tr | LLM-ASR解码似然约束声学重排序，无需训练移除38.8–57.1%幻觉失败 |
| K610 | 2608.30782 | PixelIR: Fidelity-Perception Decoupling via Pixe | PixelIR：像素空间图像-残差流匹配解耦保真度与感知质量，蒸馏为单步学生，PSNR/SSIM/LPIPS领 |
| K611 | 2608.30785 | SkillZip Pro: Execution-Aware Dynamic Compressio | Production agent skills are directory bundles, not isol |
| K612 | 2608.30789 | Camera trap classification with deep learning un | 相机陷阱分类：志愿者标签不确定性训练提升准确率，尤其是困难图像，ImageNet预训练减少训练周期，标签分歧帮 |
| K613 | 2608.30792 | Conjoint Audio-to-Spikes Encoding and Processing | 神经形态音频编码 可编程非学习编码器+SNN联合优化（FPGA目标），TIMIT端到端脉冲编码，Heidelb |
| K614 | 2608.30795 | Uncertainty-Aware End-to-End AI Weather Forecast | **Uncertainty-Aware End-to-End AI Weather Forecasting** |
| K615 | 2608.30804 | Geometric Attractor Monitoring: A Robust and Fru | Monitoring the health of heterogeneou... |
| K616 | 2608.30811 | TopoCompress: Long Context Compression via Graph | Long-context compression is essential for reducing the  |
| K617 | 2608.30815 | A general framework for disturbance compensation | 航空/海洋重力仪扰动补偿通用框架：多传感器+监督ML+实验室训练平台 |
| K618 | 2608.30817 | A Composition-Aware Pretraining Framework for Ge | Geospatial foundation models have emerged as state-of-t |
| K619 | 2608.30819 | What Emerges and What Breaks in Self-Play Drivin | Training autonomous driving policies ... |
| K620 | 2608.30820 | RealOOB: A Definition-Consistent Real-World Orie | RealOOB：426万定义一致几何grounded遮挡边界标签+有效性感知方向图，40个评估方法显示边缘检测 |
| K621 | 2608.30821 | Lucida: Parse, Generate, and Place for Composabl | Composable scene modeling aims to recover a real indoor |
| K622 | 2608.30825 | Real-Time Reference Shaping for Servo Systems | 实时参考整形 KKT闭式解+小规模特征值问题，无迭代近100kHz实时伺服轨迹，运动学失配补偿 |
| K623 | 2608.30827 | Error-Type-Aware Loss Reweighting for Robust Nam | Large language models are increasingly used to annotate |
| K624 | 2608.30832 | A Dual-Cam Parallel Elastic Actuator with Shared | 双凸轮+单气弹簧共享弹性元件，实现踝部俯仰/横滚双轴力矩补偿的紧凑并行弹性驱动 |
| K625 | 2608.30835 | Reliable Benchmarking of Artifact Detection in C | Background and Objective: Quality control is a prerequi |
| K626 | 2608.30841 | HSRM: Hidden-State Reward Models for Test-Time V | Large language models can often generate plausible math |
| K627 | 2608.30842 | Thesis Proposal: Toward a Human-Centered and Per | Humans play a vital role at every stage of AI developme |
| K628 | 2608.30844 | Pretrained, Curriculum-Tuned, and Ensembled: A T | Interactive lesion segmentation in whole-body PET/CT re |
| K629 | 2608.30858 | GAFT: Geo-Anchored Fine-Tuning for Hazard Identi | 用几何先验对齐LoRA空间注意力引导VFM微调，森林险情识别LOSO F2从0.06提至0.37+ |
| K630 | 2608.30864 | Measurement of Liquid Water Content in Snow from | 雪液水含量微波测量 微带线嵌入雪层测衰减，与密度无关推断LWC，灵敏度约2dB/%LWC |
| K631 | 2608.30865 | Predicting Residential Rents in Dakar Using Mach | Dakar's residential rental market rem... |
| K632 | 2608.30866 | Beyond Good Intentions: When Does the Framing of | Building language technologies and conducting NLP resea |
| K633 | 2608.30870 | VCAR: Training-Free 3DGS Segmentation via View C | VCAR：基于可见性加权多视图投票粗定位+球面螺旋采样细refinement+轴向各向异性压缩，训练无关3DG |
| K634 | 2608.30872 | SurgSkill-Bench: A Benchmark for Multimodal Surg | SurgSkill-Bench：外科训练模拟视频+OSATS六维评分+专家文本评论基准，内容自适应关键帧采样+ |
| K635 | 2608.30880 | Zeva: In-Context Causal Learning for Generalizab | 冻结策略+因果交互提取器+双时间尺度因果记忆，部署中免梯度自我进化且跨任务泛化 |
| K636 | 2608.30883 | SleepWalking: Privileged Representation Shaping  | **SleepWalking (SWAQ): Privileged Representation Shapin |
| K637 | 2608.30884 | Evaluating and Mitigating Anti-LGBTQ Biases in G | While gender and racial biases in language models have  |
| K638 | 2608.30889 | Safety Screening for Voltage Control in Active D | 历史数据+名义仿真构建保形安全区间，部署前逐场景筛查新电压控制策略，IEEE33/141全部检出 |
| K639 | 2608.30895 | A Controlled Evaluation of Model Rankings and In | 表面水分割配置排名不稳定：跨模态学生在Sen1Floods11最高IoU，但排名随种子/地理权重变化，输入依赖 |
| K640 | 2608.30897 | CAER: Causal Action Effect Reweighting for World | World models are becoming core infras... |
| K641 | 2608.30901 | Flexible Training Workloads in Large-Scale AI Da | TILS训练负载激增策略提升故障后有功需求抑制首摆，提升暂态稳定发电极限 |
| K642 | 2608.30902 | Low-Resource Preference Adaptation of LLMs via A | Adapting large language models to user-specific prefere |
| K643 | 2608.30908 | Fine-Tuning Low-Bit Models with Gradient in Quan | Fine-tuning Low-bit models aims to ad... |
| K644 | 2608.30915 | Parameter Estimation of Power Electronic Convert | 可微物理仿真参数估计 变换器时域仿真嵌入可微计算图，稀疏暂态采样非侵入估计健康参数，30配置验证 |
| K645 | 2608.30916 | Selection-Aware Stress Testing for Interactive A | Agent evaluations often use one bench... cs.LG/stat.AP/ |
| K646 | 2608.30917 | Intrinsic Scatterer Representation for Forward S | 内在散射体前向建模 RANSAC提取面/柱/球散射体+多跳检测，任意视角生成SAR图，高效可解释 |
| K647 | 2608.30922 | CARVE: Verified Expansion for Variable-Length Ge | Masked diffusion language models pred... |
| K648 | 2608.30923 | Towards Stream Learning on Embedded Systems: Ben | Stream learning is commonly evaluated... cs.LG/cs.AI/cs |
| K649 | 2608.30927 | Stride-k Subsampling: Train-Free Audio Token Red | Whisper免训练token降采样（stride-2）省75%音频token/58%FLOP/时延降27%， |
| K650 | 2608.30929 | Annotated Surrogate Retrieval for Polish Statuto | We present a family of retrieval methods for Polish sta |
| K651 | 2608.30934 | Scaled Null-Adjusted Persistence: A Multiscale B | 体积因子α参数族连接Modularity与Persistence社区检测，Milano多级算法1.1M节点 |
| K652 | 2608.30935 | LightNav-0: Eliciting VLM Spatial Intelligence f | 紧凑VLM泛化具身导航：统一token接口+VAQ动作分词，全10个仿真设置单目SOTA、跨实体零样本 |
| K653 | 2608.30940 | MusGU+: Toward a Musician-Centered Evaluation Fr | 以音乐人为中心的生成音乐AI评测框架：适应性/可用性/可控性三维度，评估10系统并提供发现工具 |
| K654 | 2608.30954 | Clock-Gating Insertion Strategies on an Open-Sou | 开源MSP430核上RTL行为门控门级失效（hold race），ICG单元削减动态功耗74-81% |
| K655 | 2608.30955 | Learning Action Models with Conditional and Quan | Accurate action models are critical f... |
| K656 | 2608.30956 | Taking the Whys Seriously: Limitations of Counte | 反事实解释局限 论证CE用于正当化/救济时忽视ML管线上游治理选择，四实验证明测量模型等影响可与生成方法相当 |
| K657 | 2608.30957 | Viable Pool Sizing for On-Chain FX Liquidity: Am | Merton跳扩散+LVR映射(A,TVL)投资机构FX池，最小池TVL/Q≈1000/A，低A滑点>200b |
| K658 | 2608.30959 | LOCI: A Locator-Critic with Refinement Loop | Vision-Language Models (VLMs) still struggle on tasks r |
| K659 | 2608.30963 | A Universal Context-Reuse Layer for Cross-Model  | Modern large language model (LLM) ser... cs.LG/cs.AI |
| K660 | 2608.30964 | Vision Models Predict Urban Scene Appraisal with | 预训练视觉嵌入预测城市街景评价但不反映大脑表征：最佳DINOv2仅达大脑噪声下界29.6%，语言监督模型最差， |
| K661 | 2608.30968 | CogEvol: Towards Efficient and Reliable Learning | We present CogEvol, a family of models trained specific |
| K662 | 2608.30974 | CoJEPA: Combining Contrastive Learning and JEPA  | JEPA与对比学习单骨干融合：去掉EMA教师、不增参数，全局+局部音乐表征兼得，和声/调性任务尤佳 |
| K663 | 2608.30980 | Evaluating and Improving LLM Self-Modeling | We study self-modeling: an LLM's ability to answer ques |
| K664 | 2608.30984 | Semantic-Aware Sub-Band Allocation for Terahertz | SBERT代理预测语义保真度+模仿学习，200倍低于DeepSC评估的THz子带调度 |
| K665 | 2608.30986 | Controlling Refusal Behavior of LLMs via Stiefel | Activation steering has emerged as a ... cs.LG/cs.CL |
| K666 | 2608.30987 | Stick to What You Know: A Study of Knowledge-Ali | Supervised fine-tuning (SFT) trains a base language mod |
| K667 | 2608.30996 | Faithfulness Is Not Free: Auditing Offline KV-Ca | Retrieval-augmented generation systems can precompute a |
| K668 | 2608.30997 | Multi-View Reflective Surface Inspection via Sem | 手机玻璃多视图检测：VLM语义盒+法线参考显著性交叉验证重排序，跨视图证据召回率75.5%→88.3%，AP5 |
| K669 | 2608.31002 | DARP: A Calibrated Dual-Arm RGB-D-IR Dataset for | 双机械臂eye-in-hand RGB-D-IR标定数据集，多视图融合中点-网格中位距2.13mm，几何一致 |
| K670 | 2608.31009 | Language-Informed Flow Matching for Trend-Guided | Structure-based drug design (SBDD) re... |
| K671 | 2608.31021 | Semi-Autonomous Prosthesis Control Empowered by  | 5G+MEC半自主假肢，RGB-D流式边缘抓取规划，比手动快34%，网络延迟<180ms |
| K672 | 2608.31023 | SMG: Semantic Motion Graph for Monocular Dynamic | SMG：语义运动图建模低秩语义运动，不可靠节点由可靠图节点引导，ego-exo多视图数据集，动态Gaussia |
| K673 | 2608.31025 | Analytic Dynamics: Learning Physics-Grounded Rep | Analytic Dynamics：特权物理状态中间表示弥合视觉与内在动力学，学习物理grounded表征，单 |
| K674 | 2608.31028 | Learning the Geometry of Admissible Hypotheses t | Scientific discovery often requires r... stat.ML/cs.LG |
| K675 | 2608.31030 | Damping Oscillations in a Spherical Pendulum Inc | 球摆倾斜仪阻尼 无接触六线圈电磁驱动+观测器反馈+约束力分配，主导振荡衰减31.11dB |
| K676 | 2608.31032 | A Networked SIS Epidemic--Opinion Model with Hig | 高阶交互SIS-舆论 群体感染机制+舆论反馈耦合，高阶交互诱导双稳，全局指数清除充分条件 |
| K677 | 2608.31033 | FaceSnap: Real-Time Personalized Lightstage Faci | FaceSnap：一次性多视图优化构建个性化模型，单目光舞台相机实时83fps几何+4K纹理，Multi4D公 |
| K678 | 2608.31036 | Normalized Low-Rank Adaptation | While low-rank adaptation (LoRA) is w... |
| K679 | 2608.31037 | Language-Statistical Analysis of Neural Audio Co | Neural audio codecs (NACs) convert speech into discrete |
| K680 | 2608.31038 | Type-Balanced Contextual Learning for Incrementa | Incremental Named Entity Recognition (INER) stands as a |
| K681 | 2608.31040 | Fast Fault-Tolerant Decoders for Hypergraph Prod | 超图/提升积QLDPC快速容错译码：hook错误稳定子诱捕集，绕开OSD+辅助节点 |
| K682 | 2608.31046 | Does On-Policy Distillation Really Distill? From | On-policy distillation (OPD) offers d... cs.LG/cs.CL |
| K683 | 2608.31052 | Segmentation of Bovid Dentition Under Imperfect  | Semantic segmentation decomposes an image into distinct |
| K684 | 2608.31053 | Identity-Conditioned Latent Consistency Distilla | ArcFace身份条件潜在一致性蒸馏：4.36×加速（0.48s vs 2.10s），FID与教师模型相当，1 |
| K685 | 2608.31057 | Measure Before You Manage: Evaluating Agent Work | Agent working memory is heterogeneous |
| K686 | 2608.31065 | Multimodal Shared Latent Representation of Narra | 手术阶段识别：显微镜视图作为共享锚点连接叙述与术中OCT，零样本macro F1从0.38→0.53，无需完整 |
| K687 | 2608.31066 | Every Token Leaves a Ripple in the Stream of Tho | Chain-of-thought (CoT) reasoning improves multi-step pr |
| K688 | 2608.31067 | Universal Transformers for Circuit Computations: | Learning generalizable algorithmic co... |
| K689 | 2608.31069 | A Model with No Head and Many Thoughts | Large language models decode by proje... cs.LG/cs.CL |
| K690 | 2608.31073 | LISynSeg: Data-Centric Label-to-Image Synthesis  | LISynSeg：标签到图像合成增强真实nnU-Net训练，对比度和采集扰动校准，MRI跨模态分割提升超过CT |
| K691 | 2608.31074 | Real-Time Video Anomaly Detection Using YOLO Pos | We propose a lightweight two-stage framework for real-t |
| K692 | 2608.31077 | Reconciling Process Supervision with Outcome-Bas | Outcome-based reinforcement learning ... |
| K693 | 2608.31079 | Sycophantic Agreement Transfers with Neutral Dat | Sycophantic agreement refers to a beh... |
| K694 | 2608.31082 | Token-Efficient Data Reasoning Agents via Adapti | Valuable data remains embedded in uns... cs.AI/cs.CL/cs |
| K695 | 2608.31084 | The First Token Is a Clue: Verbalizing Multi-Tok | The Jacobian Lens (J-lens) is a recent tool for interpr |
| K696 | 2608.31096 | One Adapter, Many Tasks: Task-Conditioned Featur | Class-incremental learning (CIL) requires a model to in |
| K697 | 2608.31097 | Cross-Regional Grapevine Cold Hardiness Predicti | Accurate daily predictions of cold ha... |
| K698 | 2608.31102 | LLM Post-Training as Brownfield Maintenance: An  | 工业视角把后训练当作"数据水印"棕地维护；yield工程补丁使 CodeForces pass@1 +2.59 |
| K699 | 2608.31105 | BLOOM-WILT: Logit Tilting for Behaviour Elicitat | Users of a deployed language model ro... cs.AI/cs.CL |
| K700 | 2608.31106 | DreamX-Creator: Democratizing Native Audio-Video | DreamX-Creator 1.0：7B原生音视频联合生成，Gated Cross-Modal Attent |
| K701 | 2608.31107 | VeriCam: A Verification Baseline for the Classif | VeriCam：验证任务学习细粒度特征构建关系图，Leiden图聚类在跨设备场景F1=93.45，揭示捕获设备 |
| K702 | 2608.31108 | Stress-Testing Efficient Responsible-AI Evaluati | Efficient evaluation changes the prot... |
| K703 | 2608.31111 | Aspire: Can Models Self-Evolve from Vague Goals? | Many important forms of human learning begin with a vag |
| K704 | 2608.31119 | PaperGym: Rubric-Centered Evolution for Research | **PaperGym: Rubric-Centered Evolution for Research-Plan |
| K705 | 2608.31133 | Implementing neural network mixed-effects models | Neural network mixed-effects models (... stat.ML/cs.LG |
| K706 | 2608.31157 | Sharp Approximation Rates for Neural Networks wi | Many parameter-efficient methods gene... cs.LG/stat.ML |
| K707 | 2608.31159 | BRF-GS: Hyperspectral Bidirectional Reflectance  | BRF-GS：混合BRDF驱动核+两阶段几何/光谱解耦训练，AIR-BRF多角度高光谱数据集，优越空间-光谱保 |
| K708 | 2608.31167 | SUN: Persistent Programs For Language-Grounded C | 语言语义统一编译为MPC/RL/stage策略的SUN程序，82%宏成功率，控制语义摊销为稳健策略免演示 |
| K709 | 2608.31170 | Context-Aware Interleaved Batching for WhisperX | While WhisperX accelerates speech transcription via int |
| M153 | 2608.28759 | Benchtop Momentum-Resolved Phonon Spectroscopy:  | 台式X射线散射提取布里渊区声子力常数，同步辐射级别晶格动力学走进实验室 |
| M154 | 2608.28836 | Electrochemical impedance spectroscopy of graphe | 石墨烯纳米间隙EIS 可控电击穿制gap，界面污染膜支持电化学，Warburg阻抗随pH演化，等效电路提取纳米 |
| M155 | 2608.28861 | Engineering Excitons through Polymorphism and Di | 二维碲同素异形体激子特性与维度/对称性关联，拓扑量子自旋霍尔相仍可维持强激子束缚 |
| M156 | 2608.28903 | Revealing low-energy surfaces of multinary compo | SALAMI程序包生成多组分化合物低能表面模型，保持配位环境使表面能降低20% |
| M157 | 2608.28957 | Symmetry-Preserving Phase Transitions in $AM_2$A | AM2Al9化合物压力诱导等结构相变，键合特征从层间向层内重新分布 |
| M158 | 2608.28996 | Orbital occupation selects structural dimensiona | CrO中轨道占据选择结构维度，d_z2填充倾向二维层状而d_x2-y2倾向三维 |
| M159 | 2608.29050 | First overnight balloon flight of the GRAINE 202 | 乳胶γ望远镜首次过夜球载飞行：4.9m压舱吊舱夜间维持>100hPa，2.5m²孔径仅179kg吊舱 |
| M160 | 2608.29122 | Light-induced nonconservative static forces in m | 光致非保守静态力 周期性驱动经耗散产生非保守力，激子绝缘体相位移/公度CDW滑移+拓扑Thouless泵浦DC |
| M161 | 2608.29124 | A route to the thermodynamics of colloid-polymer | 从径向分布函数直接预测胶体-聚合物混合物热力学相行为的液体理论框架 |
| M162 | 2608.29338 | Analogue Phase Change Computational Memory with  | 相变存储器件近6比特精度+亚100μA编程电流，超限体积设计抑制Conductance波动 |
| M163 | 2608.29343 | "Ultra-weak" First-Order Phase Transition in Bia | 双轴液晶N_U→N_B转变极弱一阶，顺序参数比I→N_U弱一个数量级 |
| M164 | 2608.29404 | Elastic properties of amorphous LiTaCl$_6$ solid | **Elastic properties of amorphous LiTaCl6 solid-state e |
| M165 | 2608.29447 | Vibrational Origin of the Barocaloric Effect in  | Fe(pap-5NO2)2自旋交叉配合物绝热量热理论，振动熵占84%主导贡献 |
| M166 | 2608.29566 | Extreme Polarization of the Optical Gap and High | 面内光隙各向异性470meV（NIR-可见最高纪录），GW-BSE揭示1.25-3.1eV高偏振激子景观 |
| M167 | 2608.29586 | Solid and Quasi-Solid Electrolytes for Zinc Batt | 锌电池固态/准固态电解质系统分类，揭示水活度与离子传输的内在权衡关系 |
| M168 | 2608.29676 | From Freezing to Terminal Packing: A Puzzle and  | 密度泛函理论揭示终端堆积有限波矢边际性，热力学边际而非机械堵塞 |
| M169 | 2608.29728 | Active embracement enables autonomous tweezing i | 活性星形聚合物主动拥抱现象，自推进克服立体排斥实现自折叠与捕获 |
| M170 | 2608.29886 | Structural Hierarchy and Geometry in Molecular R | Molecular self-supervised learning uses chemical struct |
| M171 | 2608.29898 | Cesium Clustering and Fluoroberyllate Network Di | FLiBe熔盐中添加CsF破坏氟铍网络结构，X射线/中子衍射+NNMD揭示析晶抑制 |
| M172 | 2608.30060 | Chemical potentials from structure factors: II.  | 带电多组分混合物化学势S0方法，从结构因子直接计算熔盐混合自由能 |
| M173 | 2608.30064 | Libron-phonon coupling and hydrogen-bond dynamic | NH4+在空位有序钙钛矿中Raman沉默但可通过SnCl6模式重整化探测，压致发光反转 cond-mat.mt |
| M174 | 2608.30133 | Attosecond Reconstruction of Strain Tensors via  | 阿秒瞬态吸收光谱鱼骨结构是应变指纹，可重构二维材料应变张量大小与方向 cond-mat.mtrl-sci |
| M175 | 2608.30150 | Universal tuning of Förster resonance energy tra | 导体-介质-导体异质结QED理论，PEC/PMC分支分别指数屏蔽/准2D对数增强FRET，门可编程范围 |
| M176 | 2608.30164 | Coexisting Large and Small Polarons in Photoexci | CeO2中大空穴极化子(Fröhlich型820 fs)和小区电子极化子共存，超快THz光导主导 cond-m |
| M177 | 2608.30296 | Covariant formula for the driving force for inte | 界面迁移驱动力在任意坐标系的协变表达式，与曲率张量收缩得到显式分量形式 cond-mat.mtrl-sci |
| M178 | 2608.30368 | SpectraTac: A Compact Camera-Free Optical Tactil | 无摄像头RGB色散光学触觉，19.2mm/≤$5成本，3D力MAE 0.16N、接触区99.9% |
| M179 | 2608.30401 | Towards an effective medium theory for in-vivo M | 活体MRI有效介质理论：保留Larmor项、弛豫替换为一般非线性许可场，含Bloch为特例 |
| M180 | 2608.30454 | Coupling of two individual magnon resonators via | 两坡莫合金条纹通过超导共面波导谐振器强耦合，形状各向异性实现频率独立调谐 cond-mat.mtrl-sci |
| M181 | 2608.30469 | A multi-scale study to unravel the dehydration m | 十水合硫酸钠脱水两阶段：成核控制侧向生长+界面控制深度推进，35%收缩形成双孔隙结构 cond-mat.sof |
| M182 | 2608.30501 | Polymer Membrane Tensegrity: Inverse Design of P | 聚合物膜张拉整体逆设计，LCD光罩单面UV固化嵌入刚性杆，误差仅1-2% |
| M183 | 2608.30512 | Trajectory-Initialized Neural Double Q-Routing f | Large-scale industrial robot fleets share constrained p |
| M184 | 2608.30523 | Chemically Resolved Topological Coordinates Link | 化学导向持续同调在四尺度连接结构与原子运动，Pb-I骨架拓扑记忆决定CsPbI3相稳定性 cond-mat.m |
| M185 | 2608.30600 | Layer Axial Phonons and Dipolar Thermal Response | 中心对称薄膜中隐藏层分辨声子角动量，产生应变可调的热Edelstein类响应 cond-mat.mtrl-sc |
| M186 | 2608.30628 | Predictive wavelength tailoring of uniform GaSb- | 成分/单层数线性调谐1.48→1.55μm，均匀性<7meV，单量子点窄线宽C带电信平台 |
| M187 | 2608.30636 | MolLedger: An Additive Graph Neural Network with | Optimizing absorption, distribution, ... |
| M188 | 2608.30645 | Emergence and suppression of phonon vortices in  | 声子涡旋由点群对称性决定，重杂质和剪切竞争决定应变阈值，可精确预测 cond-mat.mtrl-sci |
| M189 | 2608.30680 | Halide donors in monoclinic- and corundum-phase  | Cl在(AlGa)2O3中不易形成DX中心，比F更适合做浅施主，84% Al浓度仍有效 cond-mat.mt |
| M190 | 2608.30706 | Universal unconventional responses controlled by | 铁轴序通过自旋霍尔/热电/法拉第等非常规响应探测，可区分铁轴畴并揭示金属态 cond-mat.mtrl-sci |
| M191 | 2608.30790 | Fine structure of the M-center in Si | 硅中M中心附近三个蓝移和一个红移发射线，2.8 meV线为第二激发态，呈负热淬灭 cond-mat.mtrl- |
| M192 | 2608.30863 | Self-Diffusion of Water through Thermally Activa | 热激活膜MD模拟水自扩散，sigmoidal势垒调控弹性散射概率与有效激活能 |
| M193 | 2608.30882 | Local phase-space Berry curvature and Hall trans | 织构TBG相位空间Berry曲率 投影织构mini-Dirac锥获得混合曲率，霍尔响应与谷倾斜Berry偶极在 |
| M194 | 2608.30921 | Breakdown of Charge-Conjugation Symmetry of Disc | 二维晶体负曲率缺陷违反电荷共轭对称性，导致长程吸引而非排斥，自粘附放大效应 cond-mat.mes-hall |
| M195 | 2608.31019 | A MOF-reinforced self-foaming sponge for mechani | MOF增强自发泡多孔摩擦电材料，HKUST-1抑制孔塌陷并吸附水分子，抗湿度稳定性提升 cond-mat.mt |
| M196 | 2608.31045 | Rotational Equivariance in Machine Learning: A C | Rotational symmetry is one of the mos... |
| M197 | 2608.31123 | Development and characterization of a wingless I | 无翼ICPC HPGe薄非晶Ge接触探测器：20g亚pF电容，59.5keV处1.75keV FWHM |
| R215 | 2608.24277 | LEMONS: Leveraging Model-Based Techniques to Ena | 模型驱动+语义网技术对WSN非侵入式语义增强，亚毫秒开销+部分自动配置 |
| R216 | 2608.25292 | Rethinking Battery-free Sensing Communication vi | 微安级唤醒无线电+LP-RTC扩展电池自供传感器通信窗口，100/100首联系，能量门控调度 |
| R217 | 2608.26441 | On A Unified Cramér-Rao Bound Framework for Join | 联合时延多普勒CRB 多载波波形联合时延-多普勒估计的统一Cramér-Rao下界框架 |
| R218 | 2608.28713 | Rust's Type Checker Implementation Is Unsound: A | 30 个 rustc 健全性 bug 实证：implied bounds/trait 对象致内存不安全，Mir |
| R219 | 2608.28766 | Beyond Vector Search: Comparing Classical RAG wi | 混合GraphRAG气候问答 向量+GraphRAG+Leiden 社区+交叉编码：上下文相关 +160%、召 |
| R220 | 2608.28790 | ASTRA - Agentic System for Ticket Resolution and | 编排器+3专家agent+judge循环产出证据化排障报告，987电信工单4.13/5分、组件级定位59.9% |
| R221 | 2608.28795 | The reach of a verification tool decides its val | 验证表面价值研究 1116 web 应用对照实验：验证工具价值取决于其 reach 是否覆盖实际失败方式，bo |
| R222 | 2608.28803 | Pragmatic Information, Computation, and the Effi | 意义度量依赖接收者计算能力（Chomsky层级），重构有效市场为计算效率假说 |
| R223 | 2608.28804 | X-ray grating spectroscopy as a mission enhancem | 为未来X射线任务提议软X光栅光谱仪（R>3000、10-40Å）：AGN外流/缺失重子科学+100-200M$ |
| R224 | 2608.28843 | Curvature Cryptanalysis of Smooth Transformer Fe | We show |
| R225 | 2608.28854 | Designing, Deployment and Field Testing of C2Sta | 本批次唯一完整开源UAV无线网络协议栈，含模块化控制平面CNOS+可编程数据平面+数字孪生API，覆盖MPSo |
| R226 | 2608.28857 | Exploring the trade-space of distributed apertur | 分布孔径望远镜对比研究：半米级望远镜阵列可低成本等效大望远镜做超弥散星系光谱 |
| R227 | 2608.28858 | 96 kHz on-sky imaging on an adaptive optics syst | 商用SPAD阵列96kHz观测AO PSF：揭示高频行为并显著改善AO辅助幸运成像，超越AO原生能力 |
| R228 | 2608.28864 | OHL-Assisted All-Optical Regenerative Relaying f | 光硬限幅器组符号级再生M-PAM星间链路，规避AF噪声累积与DF O/E/O开销 |
| R229 | 2608.28865 | Uncertainty-Aware Multi-Task Learning for Joint  | **Uncertainty-Aware Multi-Task Learning for Joint Modul |
| R230 | 2608.28880 | FlowCheck: Helping End-Users Specify and Verify  | Vibe 编码意图约束语言：界面直述信息流约束→CodeQL 确定性检查，30 违规全检出零误报 |
| R231 | 2608.28890 | Adaptive RIS-aided Communications through ML-bas | 微控制器ML模型实时生成相位掩码，RIS自适应调整无需码本存储 |
| R232 | 2608.28913 | mmIR: Frequency-Space Inverse Rendering for 3D M | **mmIR: Frequency-Space Inverse Rendering for 3D Millim |
| R233 | 2608.28949 | The information geometry of product-reference di | We study a class of product-reference diffusion algorit |
| R234 | 2608.28969 | Performance Analysis of Time-Delay Systems under | 延迟系统输出对输出增益LMI条件，基于耗散理论与Lyapunov-Krasovskii泛函 |
| R235 | 2608.29020 | A Continuous Payload-Bearing Discrete Multitone  | 光纤ISAC连续DMT 负载波形同时做通信+DAS，CP/NoCP-DMT抑制空间ISI，10km定位600H |
| R236 | 2608.29052 | DeepHSIC: Deep Learning-based Signal Detector fo | 混合下行IM-NOMA神经检测器：星座/子载波索引/功率三层联合深度检测 |
| R237 | 2608.29056 | Neural Network-Based Delay-Doppler-Assisted Chan | 神经网络延迟-多普勒辅助OFDM信道估计：ICI感知+DD恢复问题建模 |
| R238 | 2608.29080 | GHOST in the Robots: Real-Time Exocentric Dual-R | 单操作员VR遥操作双移动机器人：机载RGB-D点云对齐成外心3D工作空间，低延迟 |
| R239 | 2608.29084 | UiAs: User-Independent 3D Facial Anti-Spoofing v | 无线多模态 3D 人脸防欺骗：mmWave+声波跨模态相减去用户几何，皮肤锚定对比学习，93.25% 未知用户 |
| R240 | 2608.29129 | From Rigid to Adiabatic: Canonical Regularizatio | 作用角正则坐标建立辛流形端口哈密顿标准形，揭示Q-V控制稳定性通道 |
| R241 | 2608.29146 | Systematic Lightweight Method for Robotics Based | 应变能分布轻量化 应变能每单位质量均匀分布准则，系统级解耦+部件级优化，轻量化兼刚度提升 |
| R242 | 2608.29166 | Perturbation responses on topological synchrony  | Hodge分解处理单纯复Kuramoto拓扑同步，精确/共精确扇区固定点+谱脆弱性 |
| R243 | 2608.29214 | Sound Analysis for Speed Estimation of Induction | 电机声学测速 低成本麦克风+多速率DSP提取转速谐波，非平稳工况精确跟踪瞬时转速 |
| R244 | 2608.29391 | Feelium: A Touchable Blimp Body for Aerial Telep | 飞艇皮肤作为共享接触面，远程VR提现+现场触摸双向互动遥临场 |
| R245 | 2608.29398 | Review-Period Sensitivity in Multiclass Queue Sc | 多类队列调度值函数对离散检查周期长度的一阶/二阶敏感性显式表达 |
| R246 | 2608.29414 | Secrecy Outage Analysis over Correlated Composit | 相关复合广义Gamma衰落物理层安全：Mellin/Fox-H闭式SOP分析 |
| R247 | 2608.29424 | Transmissive RIS-Assisted Vehicular Direct-to-Sa | 透射RIS车载直连卫星：与相控阵工作区对比，低功耗波前整形孔径 |
| R248 | 2608.29430 | Content Exploration Beyond the Feed: Creator Sup | 内容探索供给 短视频平台4实验：生产探索提升创作者供给8.55%，提出共享语料库效应给A/B测量的双重极限 |
| R249 | 2608.29433 | Calibration and Comparative Analysis of Forward- | 前视声纳+3D声纳自动标定：双模态特征提取比手动标定提升5%，过滤后特征提取比原始点云提升40%，AprilL |
| R250 | 2608.29487 | Blind Dexterity: Whole-Body Humanoid Manipulatio | 仅关节编码器本体感受+柔顺驱动做全身盲操作（走/盘球/提箱/上滑板） |
| R251 | 2608.29504 | RadioSight: Predictive mmWave XR Network Optimiz | 动态神经射频场预测mmWave XR：实时反向波束追踪+语义对象同步波束管理 |
| R252 | 2608.29511 | Linear Coding of LTI Sources Over Vector Gaussia | LTI源向量高斯信道线性编码：次优信道功率约束下EEC有界的充要条件 |
| R253 | 2608.29547 | Module Number Adaptive Visual Shape Control for  | 软体模块自适应形状控制 单模块控制器复用1-5模块软气动机器人，图像分解为局部补丁实现跨模块变形控制 |
| R254 | 2608.29573 | A General Plotkin-type Bound on Function-Correct | 函数纠正码通用Plotkin界：Wyner-Graham距离，冗余只依赖函数值划分 |
| R255 | 2608.29631 | Efficient Polynomial-Time Decoding of Simplicial | 单纯复码多项式时间译码：显式纠错界渐近最优（比值→1） |
| R256 | 2608.29648 | Toward Ionization Cluster Size Measurements with | 紧凑纳米剂量计：低压丙烷气敏感体积计数电离簇，α束评估，粒子治疗/空间辐射应用 |
| R257 | 2608.29668 | Microchannel plate detector development for ultr | 紫外微通道板探测器（密封/开放面+共面交叉条阳极FPGA读出），覆盖远/极紫外多任务适配 |
| R258 | 2608.29675 | Cost-Effective Repository Exploration for Agenti | 仓库探索成本优化 低成本模型做 Agent 仓库探索：保留 78–94% Hit@3、降 84–95% tok |
| R259 | 2608.29725 | A New Paradigm of 6G Networks: Proactive Channel | 综述CKM信道知识图+移动天线/IRS信道重构范式，信道作为可重构资源 |
| R260 | 2608.29740 | Identification of $dq$-Asymmetric Impedances as  | 单次激励非参数频域法辨识dq不对称阻抗为复传递函数对，HIL验证1Hz分辨率 |
| R261 | 2608.29743 | Soft proton experiments supporting the developme | 软质子掠射散射+薄膜透射实验：相当部分散射质子经电荷交换、磁偏转器难抑制，支撑X射线任务评估 |
| R262 | 2608.29770 | Sampling-based Certified Planning with Graphs of | 凸集图认证规划 首个逐答案可证规划器：采样+准入界+链条证书球，29查询0无效答案vs参考21个 |
| R263 | 2608.29791 | A high-speed anamorphic pupil-conjugate slit spe | **A high-speed anamorphic pupil-conjugate slit spectrog |
| R264 | 2608.29826 | A wide-range temperature-dependent deep potentia | 钠宽温域温度依赖深势：熔点至临界点热物性，r²SCAN临界温度2.508kK近推荐值 |
| R265 | 2608.29838 | KDGen-BF: A Generative Site-Specific Multi-User  | 扩散Transformer从RSRP生成多用户波束权，KD-EMA蒸馏，免CSI媲美DFT穷举 |
| R266 | 2608.29845 | From Identification to Authentication for Micro- | 双设备共谋伪造OFDM M-CSI指纹可击破认证，测试统计降为随机分类器 |
| R267 | 2608.29882 | Spillover Effects under Network Interference Whe | 图网络保留邻居级响应动力学预测溢出，直接响应测量跳出不可约误差阱 |
| R268 | 2608.29908 | Finite Sample Identification of Analytic Nonline | 解析非线性系统辨识 实解析特征LPN系统非主动探索即充分，最小二乘/集成员非渐近率，反例为无穷光滑 |
| R269 | 2608.29912 | Verification-Time Dependency on a Disappearing E | 消失评估器依赖 针对决策评估器退役不可重建，提出验证时承诺/独立可验/反事实审计三构造+VTPP协议 |
| R270 | 2608.29935 | System Identification of Admittance Models for L | 大物体柔度模型辨识 首套大物件导纳模型系统辨识流程，无需铰接扭矩传感，门/手推车物理一致建模 |
| R271 | 2608.30019 | Predictive Traffic Shaping as a UE Network Contr | UE预测流量整形慢控制环：置信触发+债务账户保公平，带宽-时间模型 |
| R272 | 2608.30038 | ActReal: System-Level Mobile Agents Challenge Mo | 系统级移动 Agent 物理动作攻击：时间对齐触摸+六轴 IMU 伪造，均值 ASR 77.5%（联合检测 7 |
| R273 | 2608.30058 | High-Performance Low-Power Adiabatic Systolic Ar | 16nm FinFET谐振4相时钟绝热MAC脉动阵列，1GHz下核级省电42% |
| R274 | 2608.30104 | Fluid Antenna Multiple Access for Noise Modulati | 噪声调制流体内多址：精确矩母函数+随机比特聚合干扰分析 |
| R275 | 2608.30168 | Site-specific Channel Modeling Based on Remote-S | **Site-specific Channel Modeling Based on Remote-Sensin |
| R276 | 2608.30215 | Control of Decommissioned Satellites and Space D | 级联离子电喷雾发动机CubeSat附加碎片姿态控制，μ-综合鲁棒应对柔性结构 |
| R277 | 2608.30222 | Optimized Modular Design and Development of a Ti | 倾转旋翼双旋翼无人机 模块化双旋翼倾转机体设计：CG/NP约束+结构气动仿真，样机飞行验证 |
| R278 | 2608.30273 | Strengthening Recursive Constructions for Zero-E | AI辅助零误差Shannon容量：异质细化递归构造强化奇圈下界 |
| R279 | 2608.30301 | Data-Centric Neuromotor Interfaces for Portable  | 边缘神经运动接口 数据为中心的sEMG接口，2210参模型识34手势94.36%，千参数级边缘可部署 |
| R280 | 2608.30360 | Arctic Dispersion Interruption Phenomenon and So | 北极声传播色散中断现象：本征函数节点致幅度为零，据中断频率估计声源深度 |
| R281 | 2608.30383 | Using Hyper-V Sockets for Real-time Data Extract | Hyper-V socket 作恶意软件沙箱实时信道，不受 TCP/IP 层阻断、不被连接列表工具枚举 |
| R282 | 2608.30444 | Non-uniform Memory Partitioning For Low-Power Sp | 按神经元放电率非均匀分派突触权重的低功耗SNN，SRAM访问功耗降61% |
| R283 | 2608.30453 | Marker-Delimited Codes for Short-Blocklength, Hi | DNA存储多读编辑信道：marker定界码内码+LDPC外码级联，快速软信息 |
| R284 | 2608.30488 | Leveraging Bayesian Optimization for Array Shape | 贝叶斯优化阵形自校准 BO+物理信息参数模型分层优化水听器阵形，SWellEx-96几何RMSE 0.659m |
| R285 | 2608.30495 | In-situ suppression of surface radon emanation u | SUPL实验室HDPE屏障原位抑制地表氡析出：平衡浓度降~96%(5840→259 Bq/m³) |
| R286 | 2608.30514 | TSExplorer: An interactive data annotation and e | 跨平台时序数据交互标注/探索工具：高维特征多视图2D可视化，支持标注、特征比较、标签后验精修 |
| R287 | 2608.30524 | Beamforming Design Via GNN in mmWave Cell-Free M | 亚6GHz辅助GNN波束 GNN消息传递从sub-6GHz CSI学习毫米波无蜂窝MIMO波束成形，免毫米波C |
| R288 | 2608.30565 | OpenMUSTANC (MUltiple Scattering Theory At Nanop | OpenMUSTANC工具箱：MST多球等离激元腔仿真，含HDM/GNOR/SRM介观模型，模块化 |
| R289 | 2608.30606 | Generative Retrieval for E-commerce: Jointly Lea | 生成式检索联合训练 联合训练embedding+codebook并注入同簇监督信号，消除级联误差累积、提升电商 |
| R290 | 2608.30639 | Energy Efficiency in Microwave Linear Analog Com | 微波线性模拟计算机SLM/TLM/HDM能效最大化，EE标度lnN/N²，数千天线才显优势 |
| R291 | 2608.30643 | Temporal Forcing: 4D Representation Alignment fo | 用4D基础模型做历史表征对齐，让VLA感知动态环境演化，LIBERO 98.8%/物理任务成功率20→43.3 |
| R292 | 2608.30656 | APT: Anchor-aligned Perturbations for Tamper Loc | APT：锚对齐密集向量扰动在完全再生设置下定位篡改，FR IoU 0.92 vs WAM 0.84，现有方法接 |
| R293 | 2608.30682 | Learning Materials Properties from Scarce Labels | Learning materials properties from sc... cs.LG/cs.AI |
| R294 | 2608.30708 | sbom-unifier: Integration Framework for Heteroge | 异构 SBOM 集成：PURL 识别组件+确定性补全，39 字段全覆盖率 +8pp、缺失率 −11pp |
| R295 | 2608.30717 | On Diagonalizable Delay-Doppler Channels and The | 完整刻画可对角化延迟-多普勒信道支持及其正交基波形，实现单抽头均衡 |
| R296 | 2608.30718 | An Optical Pathway to Movable Rydberg Atomic Qua | 光学束操纵Rydberg原子量子接收器，无机械actuation重构射频感测位置 |
| R297 | 2608.30729 | Bounds on Shaping Partially Coherent Microwaves  | 可编程散射系统成形部分相干微波的界：MNT+SDR原型感知上界，100单元1-bit RIS验证 |
| R298 | 2608.30739 | Towards Balanced Spectral Reconstruction: Spectr | 频谱自适应STFT损失函数解决中高频过度衰减，平衡全频谱重建 |
| R299 | 2608.30765 | T3S: Improving Multi-Task Reinforcement Learning | Multi-task reinforcement learning (MT... |
| R300 | 2608.30778 | Reciprocity Separates Gradient Flow from Rotatio | Physical learning lets a trainable ma... cs.LG/nlin.AO |
| R301 | 2608.30781 | Radio measurements of air showers with the IceCu | IceCube-Gen2表面原型站（3×SKALA天线）在Auger测到射电簇射信号并与CoREAS模拟比对 |
| R302 | 2608.30794 | Doppler Effect in High-Mobility Free Space Optic | 高机动FSO多普勒 IM/DD多载波FSO多普勒=CPE+ICI，小Doppler导频补偿，大Doppler致 |
| R303 | 2608.30818 | ProofPulse: Interactive Proof Coverage Analysis  | Dafny 证明覆盖率三值模型诊断规格质量：unsat 核最小化使前置条件分类精度完美 |
| R304 | 2608.30823 | Vocal Music under Phoneme-Conditional Analysis | 音素条件声乐分析 同歌内对照隔离音素声学效应，9语言无伴奏演唱85.5%九分类准确率，音系结构留可测声学痕迹 |
| R305 | 2608.30826 | Explainable deformable matched filtering reveals | 可解释可变形滤波 KAN预测低维匹配滤波变形，光无线1600条件，EVM中位降18.1%，揭示理论偏差 |
| R306 | 2608.30836 | Channel Gains to Captions: Task-Unified Multi-Le | 信道增益到字幕 VLM统一多级RF感知：信道增益映射语义字幕，prompt路由LoRA专家，F1提升0.17 |
| R307 | 2608.30887 | Beyond $X_\mathrm{max}$ : Reconstructing Air Sho | 信息场理论+SMIET前向模型重建射电簇射纵向轮廓：SKA-Low构型Xmax分辨率<9g/cm²且低偏置 |
| R308 | 2608.30890 | Ray Tracing-Based LoRaWAN Gateway Placement for  | 亚马逊雨林LoRaWAN网关部署：射线追踪信道建模+覆盖/投递率优化 |
| R309 | 2608.30896 | Rad-R: A Raw-ADC Radar Dataset and Capture-Invar | Rad-R：4芯片77GHz级联雷达原始ADC数据集，每记录配对标定硬件故障+独立物理测量+RadarNet  |
| R310 | 2608.30899 | Uncertainty-Aware Trajectory Forecasting from Im | 轨迹预测不确定性建模：tracking-derived可靠性作为信息信号传播至预测器，OU扰动+知识蒸馏，鲁棒 |
| R311 | 2608.30939 | Finite Element Model Updating-based Load Rating  | 有限元模型更新FEMU+GA梯度混合推断缺失图纸桥梁荷载评级，误差0-17% |
| R312 | 2608.30944 | Nonparametric Contextual Pricing and Inventory L | In online retailing, when a product s... |
| R313 | 2608.30960 | Singular Curvature in ReLU Training:Differentiat | Gradient descent (GD) is explicit Eul... |
| R314 | 2608.30962 | SCI-D$^2$NN: An Optimization Framework for OAM-M | 对比学习D²NN优化OAM-FSO检测，双分支+Bhattacharyya损失，BER改善3-10dB |
| R315 | 2608.30977 | Adaptive Observer of Nonlinear One-Sided Lipschi | 单侧Lipschitz自适应观测器 输出积分回归+历史栈并发学习，有限激励收敛，OSL-QIB LMI设计 |
| R316 | 2608.31031 | The Auger Radio Infill SKALA Extension (ARISE):  | Auger ARISE射电填充阵列（18×SKALA-2天线，50-350MHz）2025部署：瞄准>100P |
| R317 | 2608.31034 | XAI2CSI: Interpreting CSI with eXplainable AI fo | SAGE解释CSI-HAR深度模型，揭示模型过度依赖上下文模式致跨环境泛化差 |
| R318 | 2608.31042 | Feasibility of Capillary-Driven Orbital Liquid M | Halbach磁铁阵列遗传算法优化+高度垫片校正液体镜面：模型RMS降38.6%，实测主导误差为磁体机械倾斜 |
| R319 | 2608.31091 | Minimax bounds for watermarked and masked recurs | 证明真实样本比例趋零时水印无益除非检测漏报率同趋零，提出masking随机化收窄至Jensen gap |
| R320 | 2608.31135 | FPGA-based TDC for SiPM Timing and Amplitude Mea | FPGA基TDC SiPM时间/幅度测量：Artix-7+xADC，19ps时间分辨，双通道符合 |
| R321 | 2608.31140 | Semantic Freshness Optimal Sampling and Transmis | 两个八卦接收机最优采样传输联合策略：VAoI指标下MDP建模，减少直传 |
| R322 | 2608.31148 | The Analysis, not the Aperture: End-to-End Trans | 视频视觉Transformer端到端重建切伦科夫望远镜事件：能阈降3倍至0.07TeV，有效面积3倍 |
| R323 | 2608.31149 | Learning to deform the matched filter | 可变形匹配滤波 有界变形替代替换匹配滤波，光无线硬件在环24h，KAN/MLP控制器恢复原工作状态 |
| S149 | 2608.28732 | Networked Multi-Resource Defense Capabilities in | 网络化Lotto防御 多资源防御分配General Lotto博弈+网络权重矩阵，两攻击类型精确均衡刻画 |
| S150 | 2608.28939 | Authentication over Arbitrarily Varying Channels | 因果对手AVC认证：认证容量=无对手Shannon容量，wait-and-overwrite攻击 |
| S151 | 2608.28992 | CARVY-FL: Client Anticlustering for Robust Votin | 联邦学习客户端反聚类投票：从一轮更新估分布类型+反聚类增组内多样性，CA 优于 FLCert |
| S152 | 2608.29184 | GhostSplat: Input-Triggered Backdoors for Multi- | 前馈 3DGS 输入触发后门：低幅模式使生成器渲染攻击载荷，多视角一致，ASR 至 96%/100% |
| S153 | 2608.29191 | A Broadcast Authenticated Encryption with Keywor | 广播可搜索加密多用户多挑战紧致安全定义+双线性群构造，MDDH 假设下紧致全隐藏 |
| S154 | 2608.29251 | GuardianAgent: Policy-Conditioned Risk-Adaptive  | Privacy protection for live web traffic requires more t |
| S155 | 2608.29381 | Safe to Resume? Breaking Execution Continuity of | 检查点回滚安全首研：五类失效模式，对 Hermes/Cline/LangGraph 实现越权邮件/双支付攻击 |
| S156 | 2608.29388 | Fully Distributed GNE Algorithms for Multi-Robot | Recent machine learning research has increasingly focus |
| S157 | 2608.29510 | ARMOR: Manifold-Oriented Training for Adversaria | ARMOR：流形导向训练在低数据条件下实现对抗鲁棒性，背景遮罩+目标上随机patch注入，物理patch部署验 |
| S158 | 2608.29531 | Context or Digits? Balancing Memorability and Ef | VR 自适应方向认证：环境上下文建口令+方向/数字双输入，66 人 2-3 周研究，记忆性更优负荷更低 |
| S159 | 2608.29737 | Reactive Peripheral Modeling for Faithful Firmwa | 反应式外设建模重宿主：事件-条件-动作语义忠实建模中断/MMIO/DMA，BLE 覆盖率 2.6 倍+5 漏洞 |
| S160 | 2608.29758 | Building the Truman Show: A TrustZone-Based Fram | TrustZone 带外内核监控：安全世界语义重建+双阶段危险防治，Phytium D2000 近零开销 |
| S161 | 2608.29773 | HSMLog: Small Language Model-Assisted Hardware S | SLM+检索式行为分析的 HSM 日志异常检测：策略引导两阶段，F1 97.46%、工业日志验证 |
| S162 | 2608.29977 | A New Algebraic Algorithm for LWE | 纯理论密码学进展：给出 Search-LWE 的新代数算法，将线性代数技术与 Groebner S-多项式结合 |
| S163 | 2608.29979 | Breaking Ambient Trust: In-Network Per-Process A | 网内逐进程访问控制：AccessScope 随流量传播，可编程交换机+eBPF 数据面，防横向移动 |
| S164 | 2608.30041 | Reachability-Based Capability Confinement for LL | 可达性能力限制：污染后用技能影响图限制 Agent 能力，AgentDojo 三/四套件 ASR 清零 |
| S165 | 2608.30083 | Zero-Knowledge Predicate Proofs Between AI Agent | 智能体间零知识策略谓词证明（MCP/A2A 实现），32 位阈值谓词 6.2ms，并补源完整性缺口 |
| S166 | 2608.30112 | Drishti: AI-Led Human-Directed Vulnerability Aud | AI 主导人工定向 5G 核心审计：Open5GS NRF NULL 解引用 + free5GC ASN.1  |
| S167 | 2608.30329 | Ouroboros: Self-Referential Backdoor Attacks on  | 以语音增强理想清洁输出作触发器实现免注入后门，近完美攻击成功率且抗滤波/微调 |
| S168 | 2608.30332 | A Roadmap to Available ICS Datasets and Testbeds | ICS 网络安全数据集/测试床/数字孪生系统盘点+分类，指出缺标准化基准与真实流量数据 |
| S169 | 2608.30403 | Why Are LLM Backdoor Defenses Fragmented? A Feat | 稀疏自编码器定位后门特征四类角色，解释 dirty/clean-label 防御碎片化，特征钳制降 ASR 至 |
| S170 | 2608.30574 | Exposing the Invisible: Detecting Stealthy Param | 修改PLL以平衡点偏移暴露增益篡改，检测逆变器参数型网络攻击且保持常规性能 |
| S171 | 2608.30585 | The Safety Relay in Roleplay Jailbreaks: A Compo | Large language models are trained to ... |
| S172 | 2608.30615 | Towards Operator-Empowered Vulnerability Hotfixi | 运营商 RAN 临时热修复：5 个标准化 L2/L3 钩子+DROP/MODIFY/RELEASE，覆盖 20 |
| S173 | 2608.30648 | Lie to Me: Finding Bugs in ZK DSL Toolchains wit | ZK DSL 工具链对抗见证注入：拼接非法见证暴露缺约束，Circom/Gnark/Noir 共发现 13 b |
| S174 | 2608.30686 | Beyond the Payload: How User Invocation Shapes C | 仓库投毒与用户调用 CIPR 基准 1920 实例：任务类型致 ASR 差 4.5 倍，测试执行任务是静默攻击 |
| S175 | 2608.30710 | Kolmogorov--Arnold against bounded translations | Historically originating from Hilbert... cs.LG/math.FA |
| S176 | 2608.30748 | The Fragility of Jailbreak Robustness Across Ope | 越狱鲁棒性脆弱性 攻击不变仅换普通系统提示，ASR 最高 +56pp（2%→58%），拒绝轴隐表征可预测越狱结 |
| S177 | 2608.30951 | Audio-Driven Adversarial Defense for 3D Talking  | 音频频谱心理声学掩蔽隐藏保护性扰动，抑制3D talking face生成同时保持视觉质量，超越空域视觉扰动的 |
| S178 | 2608.30969 | DP-VOXLET: Provable Speaker Anonymization for Di | 说话者差分隐私形式化+机制，对任意对手给出不可重识别的可证 EER 下界 |
| S179 | 2608.31142 | Auditing Anonymous AI Models: A Four-Stage Proto | 匿名模型审计四段协议 黑盒身份核验四阶段法（存档重构/配置指纹/tokenizer差分/行为探针），成功指认  |
| S180 | 2608.31150 | Local Private Information Retrieval for Graph-Ba | 局部图PIR 引入"仅检索服务器需隐私"的local PIR，两副本图复制容量增益成倍，star/cycle/ |