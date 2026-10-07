# UPGRADE-PROJECTS-8 · 2026-09-01（第八批 · round3 全量扩编 363 项）

> 组装：沈遥（Hermes）2026-09-01
> 依据：round3 新论文 618 篇（2026-08-27/28 提交）digest 全量筛选，关键词≥1 放宽 + 硬排除离栈类目（quant-ph/math/q-bio/天体物理/纯凝聚态）
> 与已交付 923 项（round2 各批）按论文 ID 去重，零重复

## 数量分布

| 线 | 数量 | 编号范围 |
|----|------|----------|
| 无线电 | 78 | R137-R214 |
| 材料 | 23 | M130-M152 |
| 安全 | 22 | S127-S148 |
| 工具链 | 188 | K218-K405 |
| Agent | 52 | A120-A171 |
| **合计** | **363** | |

## 全量清单

| 编号 | 论文ID | 标题 | 核心一句 |
|------|--------|------|----------|
| K218 | 2608.28589 | QGPINNs: A Physics-Informed Neural Network Framewo | 提出量子图上非局部微分方程的物理信息神经网络框架，含分数阶椭圆/演化方程及逆问题识别 |
| R137 | 2608.28564 | Learning between the peaks: sharp asymptotics for  | 推导功率谱衰减各向异性下核岭回归的渐近精确泛化误差，揭示方差峰值被抑制与偏差突变规律 |
| K219 | 2608.28557 | Blog: Survey of Optimizers | 2025-2026 优化器设计空间从坐标/固定 horizon 扩展到矩阵/策略 horizon，无通用 Adam 替代 |
| A120 | 2608.28547 | DARTS: Decoder-Aware Representation Tuning via Sur | 用熵加权 L1 损失+逐位偏置修正解码器模型的表示漂移，0.1% 参数量提升模型融合质量 |
| A121 | 2608.28541 | An Enclosed Mode Is a Gauge Choice: Topology Relat | 用拓扑相对可达性刻画采样门下的代码世界模型误差维度和传感器极限，环域模式不可 falsify |
| S127 | 2608.28499 | REPLICANT: Learning Policies for Evading and Harde | 深度强化学习框架在 label-only 黑盒假设下学习恶意软件规避策略，78.8% 攻击成功率 |
| A122 | 2608.28482 | How Proper Scoring Rules Shape LLM Forecasting | 评分规则预测 五种 Proper Scoring Rules 训练 LLM 预测器产生不同偏差结构，Brier 最低 B |
| K220 | 2608.28442 | Curvature-Conditioned Multiscale Momentum with Sph | 曲率动量 沿平曲率方向的多尺度动量+球约束防止参数膨胀，加速 LLM 预训练（0.12B-2.3B） |
| K221 | 2608.28408 | SymboLLM-FE: LLM-Accelerated Symbolic Regression f | 结合符号回归与 LLM 做自动化特征工程，单次低调用量生成高解释性公式特征 |
| R138 | 2608.28393 | Timing-Aware Repurchase Prediction for Web-Scale E | 生存模型推荐 用生存分析 AFT 模型替代多个人工 horizon 二分类器，3x 少树且跨 horizon 排名一致 |
| K222 | 2608.28375 | Localizing Global Discrepancies: Marginal Contribu | 局部异常检测 用条件/边际贡献框架将全局差异统计量定位到具体观测，pairwise MMD 达 0.9993 相关性 |
| A123 | 2608.28361 | GRACE:Gradient-guided Coreset Selection for LLM Un | 梯度导向 coreset 选择从种子示例推断遗忘/保留集，提升 LLM 遗忘质量同时保持模型效用 |
| K223 | 2608.28308 | Deriving Scaling Laws for OpenEuroLLM Models: Lear | 联合学习率+批大小缩放规律研究，Warmup-Stable-Decay _schedule 下退火阶段的最优 LR 可迁 |
| K224 | 2608.28273 | Learning to Transfer Across Modes: Towards Unified | 统一 zone 级空间表示对齐不同粒度出行模式，跨模态知识迁移到数据稀缺新模式 |
| K225 | 2608.28267 | Residual-Guided Randomized Neural Networks | 残差引导随机网 残差下降闭式准则贪心构建随机神经网络的隐层，单调训练目标下降，71 数据集一致超越基线 |
| K226 | 2608.28262 | SinkSLOT: Sinkhorn via Sparse Lifted Optimal Trans | 稀疏升维最优传输计划加速 Sinkhorn，每步 O(LN)，提供收敛+不需去偏的保障 |
| R139 | 2608.28245 | I-FLOP: Fast Learning of Order and Parents from In | 从观测扩展到干预数据的 FLOP 算法，干预 BIC 分数+Cholesky 加速，从 DAG 同干预等价类恢复 |
| K227 | 2608.28237 | Efficient Online Continual Foundation Model Fine-T | 首个基础模型在线持续微调框架用于过程监控，自适应子空间+损失平台漂移检测任务边界 |
| K228 | 2608.28236 | D-TAIA: Domain-Aware LLM Adaptation for Multi-Task | 域感知三元组损失+FAISS 近邻+TAIA 推理策略微调 LLM 做双任务过程预测，10M 参数即 SOTA |
| K229 | 2608.28229 | Stay Within Your Bounds: Distance-Guided Decoding  | 上下文无关文法解码 lookahead 下推自动机引导解码，上下文无关文法合规有保证，JSON/SQL/LTL 验证质量 |
| K230 | 2608.28198 | Performative Privacy: When Differential Privacy Ma | 执行隐私 差分隐私减少数据泄漏提升长期参与度，有限隐私预算可在长期打败非私有估计 |
| K231 | 2608.28188 | Beyond Flat Netlist: Hierarchical Graph Representa | 两层图神经网络学习电路组合子图+寄存器转移结构，状态中心预训练降 BMC 时间 18% |
| K232 | 2608.28184 | Biologically Inspired Mechanisms for Facilitating  | 生物启发groking 输入门/结构可塑性/稳态等生物启发机制促进 MLP 的 groking 现象，稳态最有效 |
| R140 | 2608.28179 | Conformal Risk-Averse Decision Making with Optimiz | 风险决策共形 OCE 风险度量下最优策略退化为预测集，OCE 数据驱动校准策略用于无线波束成形 |
| K233 | 2608.28158 | HARTS: Efficient Agentic Reinforcement Learning fo | 任意 rollout 树共享前缀的差分混合注意 RL 系统，MoE 语义多重性恢复，4.81-4.87x 加速 |
| K234 | 2608.28150 | The Approximation Rank of Softmax Attention: Sharp | 精确刻画最大行-ℓ1 近似秩与支持几何/交互维度的关系，给出 sharp 上下界与 BERT 实验验证 |
| K235 | 2608.28142 | Conditional Diffusion Models for Energy-Efficient  | 可学习权重差分替代手工阶次差分，双阶段训练分离结构发现与重构，8 个基准 SOTA，33.7x 加速 |
| K236 | 2608.28134 | Learning to Difference: Adaptive Reversible Differ | Learning to Difference: Adaptive Reversible Differencing (Ad |
| K237 | 2608.28116 | Generalized Gibbs Ensemble Weighting for Forecast  | Gibbs 风格指数损失加权框架+UCB-型在线超参适应，M4+Monash 数据集验证竞争力 |
| K238 | 2608.28010 | When Can Conditional Flow Matching Replace Pointwi | 线性高斯路径下精确分解端点 NLL 与 CFM 目标的关系，指出何时 CFM 可替代 NLL，何时不可以 |
| K239 | 2608.28007 | Exact Risk Ratios for Weighted Data Selection in L | 加权线性回归风险 解决 COLT 2025 开放问题：d<n<2d 区间最差风险比率精确值，证明 F_w(d,2d-1) |
| K240 | 2608.28003 | A Method for Layer Bit-Width Allocation in LLM Qua | Gemma-3-1B 分层位分配，性能最大化约束质量退化，RTX 5090 上 11% 延迟降低/19.1% 加速 |
| A124 | 2608.27985 | Is Monte Carlo Tree Search Just Every-Visit Monte  | 论证 MCTS 四阶段本质即每访蒙特卡洛控制，将搜索语言与 RL 语言统一 |
| K241 | 2608.27978 | PhyMamba: Physics-Modulated Mamba for Robust Batte | 两阶段物理调制 Mamba 将电化学老化融入序列建模，误差降低 31.8%，可部署精度-效率权衡 |
| K242 | 2608.27948 | Temporal Memory-Aware Online Test-Time Adaptation  | 时序记忆感知动态图测试时自适应，缓解灾难遗忘+时空一致性引导，在 DGNN 上显著 |
| K243 | 2608.27931 | TI$^2$PS: A Topology-Informed Inverse Design Frame | Betti 向量+逆代理模型从靶多细胞模式推断 ABM 参数，仅 10% 数据胜过 PointNet++ 全量 |
| A125 | 2608.27911 | TACIT-Switch: Cost-Aware Model Escalation for LLM  | 区间删失观测的混合治愈阈值模型学习何时升级到大型 LLM，ALFWorld/DABench 验证 |
| K244 | 2608.27885 | There and Back Again: Bidirectional Diffusion Brid | 随机微分方程推导双向图文扩散桥，实现 text→image 与 image→text 统一生成框架 |
| K245 | 2608.27882 | SOMTab: Set-Order Mamba for Efficient Tabular In-C | 集合阶 Mamba 分离表示构建与条件检索，行列 token 稳定槽+Mamba 状态混合，GPU 效率优 |
| K246 | 2608.27831 | RealSWE: A Compositional Evaluation of Coding Agen | 提出 RealSWE 评测集：真实用户请求远比 SWE-bench 短且随意，揭示 benchmark 输入信息结构与真 |
| K247 | 2608.27808 | CURA: Certified Runtime Alarms for Computer-Use Ag | 提出 CURA：仅用外部遥测信号实现计算机使用 Agent 的运行时故障检测，以统计过程控制（CUSUM）在认证虚警率约 |
| K248 | 2608.27794 | Node-wise Feature Encoding for Neural Performance  | 提出 FeatureFormer：将节点级 FLOPs/参数量/内存代理显式编码进图注意力架构，结合 NNEQ 数据集， |
| K249 | 2608.28553 | Logos: An Agent Harness on a Cross-Process Bus | 提出 Logos：跨进程 Agent Harness，以仅追加的 transcript 为共享状态，将插件形式从单进程扩 |
| R141 | 2608.28534 | InstructMesh: Selective Refinement of Generative 3 | 提出 InstructMesh：在生成式 3D 模型的中间潜空间做局部修复选择，无需专业建模技能即可补洞/调厚度，普通人 |
| A126 | 2608.28518 | When Robots Mishear Us: Mapping the Safety Risks o | 揭示语音识别（ASR）错误可导致 Embodied AI 接受并执行不安全指令，系统性量化 ASR 错误对 EAI 安全 |
| K250 | 2608.28511 | Training Communication-Efficient Mixture-of-Expert | 提出 CE-MoE：解耦 token-mixing 与 channel-mixing 深度，将专家集中在少数路由层，31 |
| A127 | 2608.28491 | AcrossVAM1.0: Particle World Modeling for Text-Ass | 提出 AcrossVAM1.0：以语义粒子因子化机器人视频预测的运动与外观，0.28M 参数时空 Transformer |
| A128 | 2608.28475 | COVER: Identifiable Evaluation of Coalition Routin | 提出 COVER：多 Agent 路由评估方法，通过固定信息边界与堆栈条件，将端到端精度差距中的路由效应精确归因，消除评 |
| A129 | 2608.28447 | Learning to Use Tools: Reinforcement Learning for  | 将强化学习（Tool-DAPO）引入 LLM 计算器工具调用，pass@1 从 35.8% 提升至 66.0%，揭示 R |
| A130 | 2608.28433 | Prove2Me: An Open Collaborative Platform for Scali | 构建 Prove2Me：众包式 Lean 4 数学形式化平台，AI Agent 可接力贡献证明片段，将数学形式化转变为可 |
| A131 | 2608.28421 | Program Learning with Verifiable Rewards: Symbolic | 提出 PLVR：以符号反向传播在程序结构上逐层分配信用，将推理外化为可验证的确定性+神经混合程序，30B 模型超越 RL |
| R142 | 2608.28402 | VERA-8B: Evidence-Grounded Audit Risk Reasoning fr | 构建 VERA-8B：首个预执法审计风险推理系统，统一 SFT + GRPO 训练范式，引入弃权与不确定性限定机制，输出 |
| A132 | 2608.28399 | RetailAgent: Structured Adverse Timing in Self-Con | 通过 RetailAgent 揭示 LLM 交易 Agent 存在持续性负向择时结构（暴露匹配测量下跨模型/模态稳健）， |
| K251 | 2608.28384 | MAP: A Benchmark on Multimodal Accessibility Plann | 提出 MAP：首个多模态可访问性规划 benchmark，评估 AI 系统为残障用户核查/推荐场所的能力，包含声明验证与 |
| K252 | 2608.28334 | Real-Valued Hyperdimensional Sequence Representati | 提出三种实值位置编码（Sinusoid/Cosine-only/RFT 基线），在保持位移等变性下支持 Hadamard |
| A133 | 2608.28315 | MAIL: Memory-driven, Adaptive, Incremental, and Li | 提出 MAIL：记忆驱动的化学假设生成框架，将假设形成建模为时间接地推理过程，在 TOMATO-Chem 与高新颖度 N |
| K253 | 2608.28281 | LoopArena: Benchmarking Models as Runtime Controll | 提出 LoopArena：评估模型作为长程编码 Agent 循环控制器的 benchmark，揭示当前最高严格成功率仅  |
| A134 | 2608.28264 | Finding Where the Buck Stops: An Automated Failure | 提出 DoCtOR：多 Agent 协作中仅让「决定性错误 Agent」做针对性反思，在 HotPotQA/ChartQ |
| K254 | 2608.28256 | Physics-Guided Flow Matching for CT Image Reconstr | 将 Flow Matching 作为 CT 重建的扩散模型替代方案，两阶段训练生成高分辨率解剖一致图像，PSNR/SSI |
| A135 | 2608.28252 | Regime-Aware Portfolio Management via Retrieval-Au | 检索增强的专家切换框架：通过双流 VAE 表示市场状态，LLM 在推理时选择最优专家，股票市场累计收益从 26% 提升至 |
| K255 | 2608.28241 | Beyond Task-Only Matching: Personalized Skill Rout | 提出 SkillFeed：档案条件化的技能路由，将任务-技能对齐与用户档案约束解耦，在 SkillFeed-Bench  |
| K256 | 2608.28233 | REINS: Refusal-Enhanced Inhibitory Steering with S | 提出 REINS：在 SAE 特征空间同时抑制有害延续特征与增强安全拒绝特征，解决复杂包装指令绕过单方向 SAE 导向难 |
| K257 | 2608.28228 | Generative AI Alignment with Hinduism's Theologica | 对孟加拉国印度教用户进行 15 次访谈，揭示 AI 在宗教知识与虔诚实践中可及但存在神学扁平化、文化误代表、的神圣权威模 |
| A136 | 2608.28178 | Expert Knowledge & Machine Understanding: Bridging | 证明 Reactome 人类注释的文本元数据可重建专家定义的通路全局层级结构，SPECTER2 + 凝聚层次算法证实语义 |
| A137 | 2608.28165 | CrabOS: An Operating System for Human-AI Co-inhabi | 提出 CrabOS：人-AI 共栖操作系统，以自然语言文本对象作为共享工作状态，消除任务切换桥接，复杂任务支持从「桥接方 |
| K258 | 2608.28144 | The Shape of Power: A Multilingual Framework for S | 构建多语言社会权力推理框架（法语+埃及阿拉伯语），揭示可观察属性标注一致、而权力不对称与意图对齐等解释性维度存在文化争议 |
| K259 | 2608.28067 | SEPO: Evidence-Grounded Prompt Optimization via St | 提出 SEPO：以编辑效果溯源反馈驱动结构化提示优化，每次编辑作用于 typed prompt schema 的稳定单元 |
| K260 | 2608.27910 | AI Alignment through a Game-theoretic Lens: A Surv | 综述 AI 对齐的游戏论视角，体系化地沿偏好多样性、对齐优先级、时间动态三个挑战组织文献，厘清游戏论在何处真正助力对齐、 |
| A138 | 2608.27797 | CEDAR: Automata as Verifiable Interfaces for Langu | 以确定性有限自动机（DFA）作为语言引导 Embodied Agent 的可验证接口：约束被转化为有限状态对象，与技能交 |
| K261 | 2608.27768 | Why Didn't It Check? Unsupported Final Claims and  | 精确测量工具赋能 LLM 做出无证据最终声称的发生率（Qwen3-32B: 33/512），并证明自动检查规则仅需添加  |
| A139 | 2608.27763 | Fast Weight Attention for Continual Learning | 推导快权重的读后写语义最优更新（Falcon-1/2/3 及其内积变体），在变长数字加法等任务上展示优于标准 SSM 的 |
| K262 | 2608.27750 | The Calls are Coming from Inside the Model: Invest | 用线性探针从 LLM 隐藏状态检测工具调用错误，跨 18 个工具调用 LLM 验证有效性，发现模型规模、探测层位、后训练 |
| K263 | 2608.27634 | Curvature-Aware Radius Shrinkage for Adaptive Near | 提出 CARSANN：根据局部流形曲率自适应调整 KNN 邻域半径，高曲率区域强收缩、低曲率区域保持宽支持，70+ 数据 |
| K264 | 2608.27704 | RiskBlend: A Multi-Signal Framework for Test Input | 提出 RiskBlend：融合历史失败模式、预测漂移、决策边界漂移、邻域变化四信号的回归测试优先级框架，1200 配置中 |
| R143 | 2608.27540 | Towards a mathematical theory of superposition | 用框架理论与压缩感知建立神经网络叠加的数学理论：证明 ReLU 编码-解码模型在随机支撑与最坏支撑两种设定下的恢复保证， |
| K265 | 2608.27500 | Optimal Transport for Network Comparison: A Review | 综述最优传输在网络比较中的应用：Wasserstein/Gromov-Wasserstein/Bures-Wassers |
| R144 | 2608.27992 | GOD: Govern, Observe, and Direct - A Real-Time Con | 提出 GOD：Agent 社群的本地优先控制室，融合设置向导、空间回放、提问/干预命令与可移植实验包，同一浏览器工作流实 |
| K266 | 2608.27791 | Initialization Is Critical: Advancing Federated Sh | 揭示联邦短期电力负荷预测中的结构性负载异质性问题，提出全局与本地两类初始化策略（预训练+SLIAvg），减少客户端漂移并 |
| K267 | 2608.28458 | Acquire, Repair, Preserve: A Diagnosis-Guided Post | Interactive dialogue games test a capability that static ben |
| A140 | 2608.28444 | Sliding-window beats linear attention | Due to the nature of quadratic attention, Large Language Mod |
| K268 | 2608.28406 | Post-Training VLMs for Video Mistake Detection | Post-Training VLMs for Video Mistake Detection Human mistake |
| A141 | 2608.28018 | Twin Worlds: Equivariance-Based Abstention for Evi | Knowledge-intensive reasoning requires Large Language Models |
| K269 | 2608.27899 | OpenStamp: A Watermark for Open-Source Language Mo | With the growing prevalence of large language model (LLM) ge |
| K270 | 2608.27879 | What Do Interaction Representations Actually Measu | What Do Interaction Representations Actually Measure? P… Art |
| K271 | 2608.28549 | Video Generative Models as Geometry Learner | Video Generative Models as Geometry Learner Recent generativ |
| A142 | 2608.28481 | NL2AGBench: Benchmarking LLM Auto-Formalization fo | Recent advances in large language models (LLMs) have demonst |
| K272 | 2608.28439 | Fidelity Is Not Enough: Dispatch-Level Instrumenta | One model passed our fidelity check without ever opening the |
| K273 | 2608.28432 | Are These Modules Worth Their Cost? A Paradigm-Lev | Are These Modules Worth Their Cost? A Paradigm-Level Ac… Rec |
| R145 | 2608.28382 | When Linguistic and Internal Confidence Diverge in | When Linguistic and Internal Confidence Diverge in Larg… Use |
| K274 | 2608.28293 | A Probabilistic Interpretation of KV Cache Evictio | Probabilistic Interpretation of KV Cache Eviction The premis |
| K275 | 2608.28283 | Embedding Models for Stance-Aware Argument Retriev | Embedding Models for Stance-Aware Argument Retrieval In comp |
| K276 | 2608.28247 | A comprehensive and trustworthy benchmark of AI me | comprehensive and trustworthy benchmark of AI methods f… Cha |
| R146 | 2608.28170 | Text Restoration of Ancient Documents with Languag | Text Restoration of Ancient Documents with Language Models P |
| K277 | 2608.28151 | Nested Byte-Level Vocabularies Are Cheap to Deploy | Nested Byte-Level Vocabularies Are Cheap to Deploy and … A b |
| K278 | 2608.28069 | VersaGauss: A Versatile Framework for Generating M | Recent progress has been made in 3D Gaussian representation  |
| R147 | 2608.28508 | Phoneme- and Word-Level Metrics Using Self-Supervi | Phoneme- and Word-Level Metrics Using Self-Supervised S… For |
| R148 | 2608.28496 | Ladders in Chaos: When, How, (and Perhaps Why) Doe | Two forms of test-time scaling for Large Language Models (LL |
| K279 | 2608.28478 | Blind Men and the Elephant: Probing the Epistemic  | Factual question answering (QA) typically assumes a single c |
| K280 | 2608.28467 | Stranger, Fan, or Peer? A Systematic Study on the  | Stranger, Fan, or Peer? A Systematic Study on the Role … Per |
| K281 | 2608.28407 | A Unified Framework to Elicit Structured Feedback  | Unified Framework to Elicit Structured Feedback for Int… Mul |
| K282 | 2608.28405 | CultureConverse: A Multilingual Multi-turn Simulat | Current cultural evaluations for large language models (LLMs |
| K283 | 2608.28383 | Semantic Head Specialization Guides Hybrid ViT Att | Semantic Head Specialization Guides Hybrid ViT Attentio… Hyb |
| K284 | 2608.28378 | PersonaForge: Realistic Multi-Turn User Simulation | Large language models are increasingly used as agentic workf |
| K285 | 2608.28312 | AIM: Anchor Identity Features, Then Match for Mult | Multimodal large language models (MLLMs) can memorize identi |
| K286 | 2608.28248 | Synth-JDoc: Synthesizing a Japanese Document Image | The ability of Large Vision Language Models (LVLMs) to read  |
| A143 | 2608.28155 | FinExam-10K: When Retrieval Helps Financial Reason | Professional financial examinations require models to combin |
| K287 | 2608.28113 | H-Scale: Hessian-Guided Scale Refinement for NVFP4 | The NVIDIA Blackwell architecture, with native support for t |
| K288 | 2608.28053 | CNeo-Bench: Diagnosing Large Language Models on Ch | Chinese neologisms exploit diverse and unique linguistic mec |
| K289 | 2608.28042 | SimpCue: Cue-Based Prompting for Multilingual Text | Text simplification aims to make complex texts easier to und |
| R149 | 2608.28040 | A Shaky Voice Is Not Always a Dodge: Benchmarking  | Existing approaches to evasion detection in earnings calls f |
| K290 | 2608.28009 | Beyond Global Scalars: Synergizing Token-Level Sta | The rapid evolution of large language models necessitates ro |
| R150 | 2608.27988 | Predicting Turn-Taking Outcomes in Multi-Party Con | Predicting Turn-Taking Outcomes in Multi-Party Conversa… Smo |
| A144 | 2608.27974 | QUORUM: QUality-Optimized Routing Using Multiple a | Data annotation remains a central bottleneck in natural lang |
| R151 | 2608.27966 | Lexically conditioned realization ambiguity in Kor | Lexically conditioned realization ambiguity in Korean p… Thi |
| K291 | 2608.27925 | Entity-Memory Graph Retrieval Improves Evidence Co | Entity-Memory Graph Retrieval Improves Evidence Coverag… Ent |
| A145 | 2608.27924 | What Makes Agent Memory Useful for Reliable Unansw | What Makes Agent Memory Useful for Reliable Unanswerabl… Rel |
| K292 | 2608.27902 | LandingAgent: A Reference-Annotated Dataset and Ag | Landing pages are goal-oriented web interfaces that must com |
| R152 | 2608.27855 | AI Writers Have a Consistent Stylometric Footprint | AI Writers Have a Consistent Stylometric Footprint, but… Tex |
| K293 | 2608.27844 | EvoHarmBench: Breaking Content Moderation with Ite | Existing evaluations of harmful content detection rely predo |
| A146 | 2608.27843 | Synthetic Linguistic Agency: How an Embodied Morta | Contemporary language models can converse fluently and influ |
| R153 | 2608.27816 | PersonaEdit: Representative Sample Selection for P | Personalization has attracted growing interest in LLM applic |
| A147 | 2608.27813 | Representation of syntax in LLMs through the lens  | Representation of syntax in LLMs through the lens of li… Str |
| A148 | 2608.27785 | Compositional Failure in Audio-Visual LLMs: Late-L | Compositional Failure in Audio-Visual LLMs We study audio-vi |
| A149 | 2608.27760 | Informational Antilocality and the Locality Bias i | Informational Antilocality and the Locality Bias in LLMs We  |
| A150 | 2608.27756 | Load-Bearing Context: The Question Damage Score fo | Determining whether large language models derive answers fro |
| A151 | 2608.27672 | First Make It Playable, Then Make It Good: Staged  | 用三阶段 SFT（成功轨迹→加权轮次→教师引导）微调 2B 对话游戏 Agent，clemscore 从基线提升约 36 |
| R154 | 2608.27661 | Knowing Before Answering: Decoding Language Models | 用隐藏层激活状态训练线性路由器判断 RAG 证据是否充足/冲突/不足，中间层信号最有效 NLP/LLM |
| K294 | 2608.27658 | When Tokenizers Fail: Byte-Level Chunking for Zero | When Tokenizers Fail Byte-Level Chunking 提出分层字节网络框架，通过 chunk |
| K295 | 2608.28568 | SignRR: Retrieve and Refine Real Motion for Sign L | 检索-细化范式：先从真实手势段检索，再通过残差 VQ-VAE 全局细化，解决罕见手势和跨签名者一致性难题 深度/光流/姿 |
| R155 | 2608.28567 | GeBDA: Building Damage Assessment as Text-Based Se | GeBDA Building Damage Assessment as Text-Based 将建筑损伤评估建模为自回归 |
| K296 | 2608.28517 | Learning the Target Priors Before Image Translatio | Learning Target Priors Before Image Translation LTP-BIT 先学目标 |
| K297 | 2608.28429 | Lossy Event Compression: From Event Stream Distort | Lossy Event Compression From Event Distortion 事件相机有损压缩任务驱动评估 |
| A152 | 2608.28404 | How Far Can 5,500 Hours of Driving Take You? A Sca | 5,500 Hours Driving Scaling Law Analysis 驾驶视频扩散模型 scaling la |
| K298 | 2608.28386 | GraspHOI: Full-Body 3D Human-Object Reconstruction | GraspHOI Full-Body 3D Human-Object Reconstruction 首次从单张野外图像同 |
| K299 | 2608.28343 | Denoising-Aware Temporal Point Cloud Completion fo | Denoising-Temporal Point Cloud for Crop Architecture SynthCr |
| K300 | 2608.28339 | Abstract4D: A Large-Scale Dataset and Framework fo | Abstract4D Large-Scale Abstract Art Dataset 12 万张抽象画配多维感知标注（ |
| R156 | 2608.28316 | Conditional Visual Evidence Utility: State-Depende | Conditional Visual Evidence Utility State-Dependent 冻结 CLIP/ |
| R157 | 2608.28302 | FUSED: Forensic-Semantic Mixture-of-Experts for AI | FUSED Forensic-Semantic MoE for AI Inpainting 稀疏门控 MoE 融合低层取 |
| R158 | 2608.28288 | GeoFF3D: Coordinate-Anchored Feed-Forward Reconstr | GeoFF3D Coordinate-Anchored Feed-Forward UAV Mapping 坐标锚定模型直 |
| K301 | 2608.28272 | Non-Uniform Quantisation for 3DGS Compression | 3DGS 非均匀量化方案，重要性加权量化和合并，MPEG 3DGS 标准化提案 3D/点云重建 |
| K302 | 2608.28240 | WilLaGS: Latent-Conditional 3D Appearance Fields f | WilLaGS Latent-Conditional 3D Gaussian Wild β-VAE 学全局外观流形，Tr |
| K303 | 2608.28218 | Focus Where It Counts: A Salience-Driven Vision-La | 低视力辅助 VLM，按人类感知重要性顺序描述场景元素， Salience COCO/Flickr/VizWiz 数据集  |
| K304 | 2608.28216 | WALDO: One-Shot Exemplar-Conditioned Object Detect | WALDO One-Shot Exemplar-Conditioned Detection 3.4M 参数检测头基于冻结 |
| K305 | 2608.28206 | NumBench: Diagnosing Counting Failures in Text-to- | NumBench Diagnosing Counting Failures T2I 64 万提示词 factorial  |
| K306 | 2608.28205 | Cut-ViT: Task-Specific Model Pruning via Gram Anch | Cut-ViT Task-Specific Pruning via Gram Subspace DINOv3 子空间 G |
| K307 | 2608.28195 | UniLipi: A Unified Multi-Script OCR for Historical | 单框架覆盖 13 种天城文手写体 OCR，脚本感知合成数据生成 + 跨非天城文（藏/拉丁/中文）零样本迁移 文档/OCR |
| K308 | 2608.28192 | Locate Anything in Videos: Rethinking Efficient Ge | Locate Anything in Videos Parallel Tube Decoding 并行管道解码（PTD） |
| K309 | 2608.28174 | Manifold4D: Denoising on Point Cloud Rendered Mani | Manifold4D Render Injected Noise for Video Re-shooting 将渲染注入 |
| K310 | 2608.28145 | Dual-Stream Semantic Guidance with Prototype Ancho | DSSG Dual-Stream Semantic Guidance SFF Adaptation 双语义漂移（静态+动 |
| K311 | 2608.28138 | Token-Budget Distillation: Transferring Full-Token | 固定 token 预算蒸馏（TBD），压缩学生模型保留 97% 精度（R=10%），LoRA 微调+双路径师生 KL 散 |
| K312 | 2608.28096 | Ex-Sim(3)-Reg: 2D-3D Correspondence Pruning via Ex | Ex-Sim(3)-Reg 2D-3D Correspondence Pruning 将 2D-3D 对应剪枝建模为扩展 |
| K313 | 2608.28080 | Cyc3D: Evaluating Cyclic Structural Stability and  | Cyc3D Evaluating Cyclic Structural Stability 跨视图对象一致性+表征质量二维 |
| K314 | 2608.28078 | Task-State Adaptation with Prototype Memory for Mu | MemMTL Task-State Prototype Memory Multi-Task 任务状态原型记忆+稀疏 to |
| K315 | 2608.28070 | CF-YOLO: Context-Aware Feature Refinement for Camo | CF-YOLO Context-Aware Micro-Defect Detection 大核+小核协同上下文感知聚合模 |
| K316 | 2608.28063 | A Controlled Audit of Architectural Complexity in  | Controlled Audit Uncertainty-Aware Ultrasound 六候选模型严格对照审计：简化 |
| K317 | 2608.28058 | Dynamic Alignment Compensation for Hallucination M | Dynamic Alignment Compensation Hallucination 训练无关推断方法检测跨层表征漂 |
| K318 | 2608.28033 | ZipMVS: Multi-View Stereo with Compressed Cost Vol | 新深度假设策略压缩代价体积，DTU 和 T&T 数据集精度与主流方法持平，GPU 内存大幅节省 3D/点云重建 |
| K319 | 2608.28020 | 3D-USE: From Image-Level to Scene-Level Underwater | 3D-USE Scene-Level Underwater Enhancement MediumRBF 介质感知高斯场景 |
| K320 | 2608.28008 | Visual Token Coding for Video Multimodal Large Lan | VTC 视觉 token 压缩范式，I/P 帧预测+残差估计 token 冗余；Qwen3-VL token 预算 50 |
| K321 | 2608.27997 | A-PAIR: A Benchmark and Identity-Consistent Ground | A-PAIR Air-Ground Cross-View Person Detection 首个空地跨视图指人检测基准（ |
| R159 | 2608.27989 | GAN-Based Semantic Communication for Image Transmi | GAN Semantic Communication IoV Image Transmission 金字塔注意力网络提取 |
| K322 | 2608.27971 | GAAT: Geometry-Aware Alignment Transformer for Mul | GAAT Geometry-Aware Alignment Transformer UAV 几何感知对齐变换器预训练，先 |
| K323 | 2608.27923 | PCBnet: A Dataset and Automatic Construction of SP | PCBnet Schematic to SPICE Netlist Pipeline 30 万张 PCB 原理图数据集（ |
| K324 | 2608.27922 | DensityKV: Density-Guided KV Cache Compression for | DensityKV: Density-Guided KV Cache Compression for Long Vide |
| K325 | 2608.27893 | CommerceVibe: Learning to Design E-Commerce Creati | CommerceVibe E-Commerce Visual Code Generation 将电商创意表示为可执行 H |
| K326 | 2608.27888 | Thread-Efficient Decoding for Neural Texture Compr | Thread-Efficient Decoding Neural Texture Compression 共享解码器 M |
| K327 | 2608.27881 | StreamEMS: Streaming Video Understanding with Self | StreamEMS Self-Evolving Memory Video Understanding 语义演进模块（从粗 |
| K328 | 2608.27877 | Relational Knowledge Distillation Brings DNN Repre | Relational KD Human-DNN Alignment Fine-Grained 无监督 GWOT 方法比较 |
| A153 | 2608.27871 | Temporal Tree of Thought: Reasoning-Guided Visual  | 训练无关层次时序树推理，自适应从时序区域→具体物体→视觉细节，Qwen2.5-VL-7B 在 VideoMME/Long |
| A154 | 2608.27866 | Iron: Intent-Aligned and Retrospective Dual Learni | Iron Intent-Aligned Retrospective Dual Learning GUI 步级循环一致性奖 |
| K329 | 2608.27860 | From Perspective to Fisheye Depth Estimation and O | DEX Fisheye Depth Estimation Open-Vocab Segmentation 可学习畸变扩展 |
| R160 | 2608.27795 | uScenes: A Multimodal RGB and 3D Sonar Dataset for | uScenes Multimodal RGB 3D Sonar Underwater 110 场景 9.5 万同步样本（ |
| K330 | 2608.27753 | What Can Low Resource Languages Learn From Each Ot | PSMC Pre-train Specialize Merge Co-train Low-Resource 低资源脚本  |
| K331 | 2608.27735 | ABCD: Alpha-Composited Block Coordinate Descent: C | 块坐标下降训练 3DGS，O(1) 峰值 VRAM（与场景规模无关），重建质量保留 95% 以上 3D/点云重建 |
| K332 | 2608.27633 | Depth-Aware Pothole Detection Using YOLO and RT-DE | Depth-Aware Pothole Detection Edge YOLO RT-DETR RGB-D 融合检测坑洞 |
| R161 | 2608.27610 | ShiftSplit-AD: Separating Domain Shift from Defect | ShiftSplit-AD Domain Shift vs Defects Anomaly DINOv2 残差低秩/行稀 |
| K333 | 2608.27073 | SpatialCrafter: Single Image World Modeling with G | SpatialCrafter Single Image 3D Proxies World Modeling 双阶段框架： |
| K334 | 2608.27954 | Not to Break, but to Attest: Adversarial Probes fo | 用对抗式探针放大 logit 漂移的 zk-SNARK 隐私保护审计框架，token 级探针黑盒最强，50 探针证明仅  |
| A155 | 2608.28497 | On the Maintenance and Co-evolution of Agent Plugi | 对 1926 仓库/8351 插件的实证研究：插件市场 6 个月提交增长 8.8x，技能目录内指令文件与脚本 78% 功 |
| A156 | 2608.28490 | LLM-Based Agents for Software and Systems Security | 2023-2026 系统综述：安全 Agent 已能行动但权限无界、行为不可审计，"有界权威+可审计"是核心未解问题 |
| S128 | 2608.28362 | Optimal Adversarial Testing: Extracting Honest Tes | 对抗性测试优化 用动态规划设计最优重测策略，在作弊者污染结果时仍可恢复真实测试成绩 |
| S129 | 2608.28327 | Layered LLM Defenses as an Ensemble: Access Tiers, | 防御栈=集成 用访问层级+成本模型度量七层 LLM 防御栈，15 对层间失败相关性全部为正（φ0.30-0.75），"失 |
| K335 | 2608.28147 | Post-Edit Re-Verification in Simulator-Backed Engi | 仿真 Agent 验证节奏 DWSIM 仿真器工程 Agent 对照实验：显式验证节奏引导使编辑后重验证 94/120  |
| S130 | 2608.28394 | BEACON: Behavior-Anchored Cross-Source Knowledge G | 以 ATT&CK 行为为锚的跨源 CTI 知识图谱构建，propose-then-verify 抑制幻觉+分层对齐合并， |
| K336 | 2608.27967 | DisCTI: Who Needs to Know Timely? Automated Sector | 把 CTI 到行业部门映射建模为多标签分类，BERT 在 872 事件数据集上宏 F1 0.89，解决 98% MISP |
| S131 | 2608.27782 | Memorization Is Not Extraction: Tight Differential | 记忆≠抽取 严格刻画 counterfactual memorization 与 adaptive extraction |
| S132 | 2608.28542 | Offline-Verifiable Accountability for Cross-Organi | 离线可验证问责 跨组织 Agent 消息的保留证据包+策略控制离线验证器，300 工作流负证据测试零误接受，为审计/争议 |
| S133 | 2608.28529 | Relaxed Sender Anonymity for CBDC Interbank Settle | 央行数字货币银行间结算放宽发送方匿名方案（Groth16+ECIES+NoteRegistry），5 节点 8-16s  |
| S134 | 2608.28502 | Recognition Without Enforcement: Configuration-Dep | 识别≠执行 揭示 LLM Agent 指令仲裁的识别-执行差距：模型能识别伪造权威却仍执行冲突工具调用，外部参考监视器可 |
| S135 | 2608.28480 | Quantum-Based Solutions for Security Enhancement i | O-RAN 量子安全综述：PQC/量子认证/量子增强检测融入零信任架构（持续验证+最小权限+微分割），面向 6G 路线图 |
| R162 | 2608.28412 | Exploiting Per-Core Leakage: Electromagnetic Side- | 逐核 EM 侧信道 首次演示多核架构逐核电磁泄漏利用，RF 前端+异构 SoC 原型在树莓派 4B（Cortex-A72 |
| K337 | 2608.28400 | When Verified Source Becomes Attack Input: Defendi | 多地址分离智能合约源码与运行时对抗 LLM 漏洞扫描，LLM 根因正确率 23.5%→6.6%，跨合约恢复仍是难点 |
| K338 | 2608.28351 | False-CSI Attacks in Power-Domain NOMA for 6G: A T | 6G 功率域 NOMA 虚假 CSI 攻击分类学（幅度×排序效应二维轴），主张假 CSI 是控制输入完整性问题而非估计误 |
| S136 | 2608.28124 | TagZilla: Automated Owner and Abuse Type Tagging f | LLM 自动给威胁报告 IoC 打归属/滥用类型标签，owner F1 0.94、abuse 0.93，标注 765 报 |
| K339 | 2608.28021 | Compared to What? A Human-Anchored Security Benchm | 首次带同规模人类基线的 IaC 安全基准：模型漏洞密度是人类的 3.21-3.87x，厂商 extended-think |
| K340 | 2608.28016 | The Impact of Magma: A Ground-Truth Fuzzing Benchm | ground-truth fuzzing 基准 Magma 的动机、设计、影响与扩展总结，统一模糊测试评估口径 |
| K341 | 2608.27994 | Moirae: A Multimodal Agent Collaborative Framework | 多模态 Agent 协作框架做动态安卓恶意软件检测：ReAct 专业 Agent 融合视觉欺骗线索+UI 状态+API  |
| K342 | 2608.27990 | CAITLYN: Can LLM Agents Autonomously Synthesize De | 双层防御中间件：规则/LLM 双层库即时防御+系统 II 自动合成并验证新注入防御，新兴攻击基准上显著降 ASR |
| K343 | 2608.27981 | CHISEL-ing Back Source Code with AI-enabled Iterat | 免测试套件的 LLM 迭代反编译：编译器静态分析+覆盖率引导 fuzzer 双反馈，96.1% 可重编译率/79.8%  |
| S137 | 2608.27928 | GraftyVul: Synthesising Insecure Programs Through  | 把真实漏洞嫁接进开源项目合成 212 个可复现可利用漏洞程序（5 语言 23 CWE），唯一兼具可复现性+广泛覆盖的数据 |
| K344 | 2608.27914 | A User-Centric Context-Aware Permission Governance | 权限治理框架 默认应用特征级授权 "Allow When Needed"+加权隐私影响评分，30 场景仿真平台+104  |
| K345 | 2608.27836 | FISGuard: Defending Against Membership Inference v | 用公开数据固定低维表示子空间限制梯度几何泄漏，ProjRes 成员推断 AUC 降至 0.5 随机水平且保下游任务性能 |
| S138 | 2608.27766 | Revisiting Continuous Noise Sampling for Multi-Par | 多方 DP 噪声采样 发现 sample-and-scale 连续噪声采样被缩放操作限制在稀疏值集导致近 100% 攻击 |
| R163 | 2608.27604 | FlyBlind: Cross-Slice Timeliness Attacks on UAV Si | 5G 切片软隔离下授权共租户竞争上行资源使 GCS 遥测老化 12s、位置偏差数十米，而链路指标全正常（"静默状态陈旧" |
| S139 | 2608.27531 | Fully Unleashing the Multimodal Attacker: Meta-Ada | 元层优化攻击者（策略提示+权重双层），GPT-4o/Gemini-3-Pro/Seed 2.0 上 ASR 78.9-8 |
| S140 | 2608.27511 | eBPF-Based Cybersecurity Mechanisms: A Systematic  | eBPF 安全机制 PRISMA 综述（54 研究 7 域）：中位 2.4% CPU 开销、94-99% 检出率，但 9 |
| S141 | 2608.27504 | Circuit Discovery Helps Detect LLM Jailbreaking: A | 机制可解释性定位 LLaMA-2 jailbreak 计算电路（attention heads+MLP 通路），首 to |
| S142 | 2608.28509 | Rethinking Vulnerability Remediation as a Capacity | 修复=容量分配 把漏洞修复重构成流控问题：Apache/Mozilla/Red Hat 队列 94-100% 达容量，严 |
| A157 | 2608.28498 | A System-of-Systems Case Study for the Verificatio | 数字孪生组合验证 温室 SoS 数字孪生 VDM-RT 案例研究：DT 质量属性操作化为可验证属性，揭示局部保证是组合推 |
| A158 | 2608.28403 | Recovering Software Architecture Intent from Histo | 架构意图恢复 LLM 五步流水线从 Azure DevOps 工作项恢复 C4 架构图，专家认可准确有用，实体稳定但关系 |
| K346 | 2608.28396 | Sustainability of Open-Source Machine Learning Rob | 鲁棒性工具可持续性 28 个开源 ML 鲁棒性评估工具仓库挖掘：仅 5 个活跃、22 个不活跃、1 个归档，维护投入高度 |
| K347 | 2608.28364 | Where Does Balance Break? Boundary Discovery for G | 把游戏平衡回归测试建模为有限仿真预算下的边界发现问题，多方向候选+两阶段筛选+自适应步长，低维强高维有效 |
| R164 | 2608.28230 | Adaptive Strategy Generation for Boundary Value Ex | 用 LLM Agent 自适应生成边界探索策略替代手工变异算子，首次覆盖非数值输入，QD 分数 11.7x、突变分数 8 |
| R165 | 2608.28156 | From Architecture to Binary: Ensuring Cross-Domain | 机载跨域一致性 仓库中心工具链保证机载软件系统/模型/嵌入式三域一致，CI 自动接口更新+差异通知+一致性检查，轻量适配 |
| K348 | 2608.28111 | CC4M: Code Clone Analysis and Visualization for Mi | 微服务感知代码克隆分析：检测跨服务边界克隆+共修改关系并可视化，优先排序高维护影响克隆 |
| K349 | 2608.27927 | Antipatterns in AI-assisted Qualitative Data Analy | AI 辅助定性数据分析反模式目录（危险驱动/操作失误/分析失败三层），为 SE 研究者与审稿人提供方法学护栏 |
| K350 | 2608.27889 | Decoupling is a Necessity: Transformation-Agnostic | 词法/句法/语义三层解耦的转换无关反编译恢复，语义失真数据库+控制流扁平化重构，8 万函数对 Top-5 检索 83% |
| S143 | 2608.27703 | Operationalizing Regulations into Code: A Model to | 三层 LLM 选型治理模型（法规要求/治理能力多准则决策/产出），K.O. 标准可排除技术强但合规风险不可接受的模型 |
| R166 | 2608.27621 | Predicting LLM Performance from Prompt Linguistic  | 30 个语言指标可预测 LLM prompt 性能（R2 0.38-0.42，需求工程二分类），句法特征主导，推理前低成 |
| K351 | 2608.27502 | Image Augmentation as Test Generation for Deep Lea | 图像增强=测试生成 50 种图像增强技术十类分类学+作为图像检索系统测试生成器的实证，天气模拟/SaSPA 不确定性最高 |
| K352 | 2608.28578 | Aero Hand Open: A Simulation-Ready Tendon-Driven H | 仿真就绪腱驱拟人手开源：线缆传动仿真模型+双向驱动映射+RL 训练包，纯仿真训练零微调零状态估计直接部署 |
| K353 | 2608.28305 | PanelShield: Verifiable Closed-Loop Safe Planning  | 工业面板操作可验证闭环规划：参数化动作原语+LTL/安全 FSM 双重形式验证，违例输出最早违例步反例，违例率降至 2. |
| K354 | 2608.28300 | MaCoPlanner: LLM-Assisted Manual-Compiled Task Pla | 手册编译为类型化中间表示+符号展开+状态约束检查，违例定位修复或拒绝，Level-2 成功率 62.8%→84.4% |
| A159 | 2608.28270 | Spatial-Semantic Reasoning using Large Language Mo | LLM 实时语义推理 UAV ObjectNav：对象检测+3D 映射+多项式样条轨迹，连续更新语义相关性，实测减少任务 |
| R167 | 2608.28246 | Training-free Suction Grasp Detection for Deformed | 免训练吸盘抓取 开放词汇 VLM 检测+SAM2 实例掩码+几何表面评分选吸点，变形利乐包单目标 88.2%、杂乱场景端 |
| R168 | 2608.28108 | DeicticVLA: Unifying Instruction Modes Based on La | 单一 VLA 统一语言/视觉语言/视觉指示三种指令模式（文本补全+指示手势接地），未见类别成功率 100% vs LI  |
| K355 | 2608.28570 | ChainSplat: A Physics-Inspired Screw-Theoretic Mod | 螺丝理论开链刚体+旋转关节表示 DLO，与高斯泼溅联合学习几何/外观/动力学，仅多视角 RGB 视频，实时状态与力估计 |
| A160 | 2608.28435 | Linear Temporal Logic Translation via Human-Inspir | 自约束 LTL 翻译 Self-Constrained Reasoning 把结构知识内化进 LLM 决策（而非外挂过滤 |
| K356 | 2608.28409 | Cooperative Risk-Aware Exploration in Heterogeneou | 算法利他探索 Hamilton 规则相关度权重的博弈论利他框架，低价值机器人主动承担风险惠及高价值队友，Social N |
| A161 | 2608.28279 | STEGNav: Spatio-Temporal Event Graph Reasoning for | 时空事件图扩展场景图：空间轴查询条件实例接地+可达性前沿，时间轴双窗口记忆，GOAT-Bench 66.3% SR |
| A162 | 2608.28266 | CoCoBench: A Cooperative Coordination Benchmark fo | 具身多智能体协调构造级基准（897 实例：任务分配/顺序/互斥/交接），11 个 MLLM 显示协调能力高度构造特定 |
| R169 | 2608.28213 | PAMoR: Parameterized Affective Motion Generation i | 把情感变为可测量控制参数：价-唤醒坐标由机器人运动学闭式计算，动作先验+双情感先验逐去噪步组合，29-DoF 实时生成 |
| A163 | 2608.28175 | Picking Bins Empty: A Hierarchical Hybrid Approach | 清空料箱抓取 四层混合分层 bin-picking：模型基骨干+无模型探索 Agent 解死锁+在线自学习抓取点（Wil |
| R170 | 2608.28154 | From Small Talk to Rapport: Exploring Robot Self-D | 机器人自我表露 N=50 用户研究：工业机械臂闲聊中低表露策略反而引发人类更多自我表露与更强团队感，高表露并不促进 ra |
| A164 | 2608.28140 | Contact-Guided Exploration for Non-Prehensile Loco | 接触引导强化学习 多 critic RL 中专用探索 critic 以密集接触奖励引导末端接触，权重渐进衰减，四足移动操 |
| K357 | 2608.28090 | Stay Seated: Learning Omnidirectional Humanoid Loc | 坐姿人形运动 被动移动椅上全向人形运动：无模仿奖励、actor 仅用本体感觉+速度指令，零样本 sim-to-real  |
| K358 | 2608.28075 | Plan Along the Way: Event-Triggered Foundation-Mod | 事件触发重规划：LLM/VLM 只见当前可见场景状态，对象发现视为独立重规划事件，6 种部分可观测操作任务验证 |
| R171 | 2608.27793 | CAVE-NAV: VLM-Based Autonomous 3D Navigation in Un | VLM+CoT 从光强梯度/通道形态/几何复杂度推理可航向，RGB+深度+声纳多模态，水下洞穴全穿越零碰撞 |
| A165 | 2608.27726 | Coordinated Motion Planning for Multi-Arm Systems  | 迭代 LQ 博弈多臂 迭代线性二次博弈多机械臂协调规划：Riccati 后向递推反馈 Nash 策略+可微自碰撞/臂间碰 |
| A166 | 2608.27685 | Distributed Model-Based Diffusion: Finite Horizon  | 分布式模型基扩散 分布式采样模型预测控制证明有界延迟下收缩性与抗延迟鲁棒性，circleswap makespan 提升 |
| R172 | 2608.27628 | One year in a forest: Analyzing the challenges of  | 森林全年部署报告 亚北极森林 64km 一年现场报告：9 种里程计/定位/建图方法季节性显著退化，视觉 SLAM 最脆弱 |
| K359 | 2608.27609 | PHR-VLA: Planning Horizon Reasoning for Vision-Lan | VLA 轻量未来头对齐特权潜在动力学，腕部相机 patch 级监督，LIBERO 84.1→88.4%、真实拆解 63. |
| K360 | 2608.27550 | Beyond Data Scaling: Representation-Centric Contin | 表示中心持续预训练：VLM 先验保持+多实体连续动作共监督+部分统一跨实体动作布局，20% 数据胜过 GR00T-N1. |
| A167 | 2608.27497 | Beyond Relative Geometry: Metric-Aware Geometry Pe | 度量尺度等变增强+灵活度量条件实现端到端度量几何重建，绝对误差 2.01m→0.07m，即插即用提升 LIBERO/Ro |
| K361 | 2608.27783 | SURE-Challenge: Evaluating Speech Evidence Before  | 定义SURE-Challenge基准，在LLM生成前评估语音是否受支持，Whisper规则优于原始Qwen2-Audio |
| R173 | 2608.28086 | Ada-TokenCom: Rate-Adaptive Token Communications v | Ada-TokenCom：LLM驱动token压缩+Lyapunov速率自适应，实现超低码率语义通信 |
| R174 | 2608.28469 | Distributed Cross-Layer Optimization for Covert Mu | 分布式PP-ADMM联合优化隐秘网络拥塞/路由/调度/功率，Q线性（指数）收敛 |
| R175 | 2608.28331 | Enhancing 3GPP Urban Channel Models For Terrestria | 3GPP城市场景NTN信道模型：终端高度+仰角函数化LOS概率/阴影衰落/clutter loss |
| R176 | 2608.28217 | Beam scheduling policy for communications and PNT  | LEO卫星波束功率预算模型：COM优先下PNT达95%可用性的beam-power分配策略 |
| R177 | 2608.28196 | CP-Aware OFDM-Based OOK Signaling | CP-aware OFDM-OOK波形：CP全时段生成OOK信号，干扰可控且检测性能显著提升 |
| R178 | 2608.28173 | Resource Allocation for Cloud Radar Networks with  | 云雷达网络资源分配：传感器本地频谱窗口化+两跳边缘服务器链，最小化CRLB |
| K362 | 2608.28162 | Fast Time-Domain MLE for Period Estimation of Puls | 稀疏矩阵优化脉冲周期MLE：相关+稀疏求和两步分离，内存/时间大幅降低 |
| R179 | 2608.28105 | Experimental and Signal Processing Techniques for  | 3kW小HAWT发电机故障诊断：风洞+试验台振动频谱，低频特征有效 |
| R180 | 2608.28085 | ODMA-based MIMO Massive Unsourced Random Access wi | ODMA框架MIMO大规模URA：三层pilot设计+MP模式检测+Polar码联合迭代译码 |
| R181 | 2608.27973 | Toward Secure Communications for a UAV Swarm with  | SAGIN无人机蜂群安全通信：可移动天线+卫星/空中/地面链路选择，CKM-MARL框架 |
| R182 | 2608.27838 | Observability Analysis for Fusion of Doppler Measu | 多基地雷达多普勒融合：Tx-Rx基线模糊区可观测性分析+ML初始化+EKF跟踪 |
| R183 | 2608.27837 | Enabling Secure Wireless Communications for FARIS- | FARIS辅助安全通信：流式有源RIS主动反射+端口动态选择，保密率最大化 |
| R184 | 2608.27835 | Robust Joint Beamforming and Configuration Design  | FARIS鲁棒波束成形：CSI误差建模+WMMSE交替优化，DoF+主动放大联合利用 |
| R185 | 2608.27759 | Fast Tri-Hybrid Beamforming via Deep Unfolding | Tri-hybrid波束成形Deep Unfolding：GNN保证置换等变性，推理速度提升10倍+ |
| R186 | 2608.27739 | Data-Aided Asynchronous OFDM Integrated Sensing an | 异步OFDM-ISAC变分贝叶斯：TO/CFO校正+检测数据辅助感知参数精化 |
| R187 | 2608.27693 | Secure Pseudonymetry with DSSS Watermarking for LE | LEO卫星DSSS水印：伪匿名ID+HMAC-SHA256认证，低功率抗共信道干扰透明方案 |
| K363 | 2608.27648 | Alias-Free Oscillator Synchronization via Additive | 加法合成无混叠振荡器同步：谱重采样变换+65nm ASIC，5采样周期完成 |
| K364 | 2608.27614 | Joint User Association and Pilot Assignment via Ph | 无蜂窝mMIMO联合用户关联+导频分配：相位偏移导频+0/1背包，容量翻倍 |
| R188 | 2608.27522 | PolyMap: A 64-Channel Polyphonic Guitar Pickup Sys | PolyMap：64通道吉他单弦多位置传感系统，MADI低延迟数字传输 |
| S144 | 2608.28533 | Targeted Power System Frequency Attack via the Sel | 电力系统频率攻击：选择最优恶意逆变器子集，MIQCP建模+启发式排序算法 |
| K365 | 2608.28532 | xTRUCE: A Provably Safe Arbiter for Multi-xApp Con | xTRUCE：O-RAN中LLM xApp冲突仲裁，三层约束层级+Near-RT安全保证 |
| K366 | 2608.28349 | Operator-Theoretic Stability and Observer Synthesi | 参数依赖Vlasov-Maxwell动力学：算子理论稳定性+观测器合成，算子微分LMI |
| K367 | 2608.28298 | Scalable Voltage-Stability Dataset Generation Via  | 电压稳定数据集生成：边界邻近指标聚类，CPF评估减少95.45% |
| K368 | 2608.28296 | Hierarchical Agglomerative Clustering for Efficien | 高RES系统年度电压安全评估：电压响应特征层次聚类，压缩99.66% |
| K369 | 2608.28194 | SafeLink-Agent: Agentic Maintenance for Adaptive B | **SafeLink-Agent: Agentic Maintenance for Adaptive Bitrate C |
| K370 | 2608.28180 | Distributed Model Predictive Control for Optimal C | 异构多智能体分布式MPC：同时优化控制序列+共识平衡，收敛性+递归可行性保证 |
| S145 | 2608.28093 | Managing Inherent Risk: On the Conceptualization o | 防御系统固有风险概念化：民用/军用风险框架对比，外部威胁纳入风险星座 |
| K371 | 2608.28056 | Anytime Primal--Dual Certification of the Maximum  | Anytime鲁棒MPC最大扰动半径证明：原对偶下界包络，2%容差下中位加速4.97倍 |
| K372 | 2608.28017 | Securing Cooperative Sensing in UAV Swarms Against | UAV蜂群拜占庭弹性感知：进化博弈+MAP估计，误信息超过半数才可淹没共识 |
| R189 | 2608.27916 | Backup Control Barrier Function Synthesis using Su | SOS反向可达集合Backup CBF合成：输入约束非线性系统安全集扩大 |
| K373 | 2608.27891 | AutoDRI: Bridging the Semantic Gap for Automated D | AutoDRI：多智能体自动化设计规则集成，CP-SAT标准单元合成，33/33正确 |
| A168 | 2608.27851 | Graphon Design for Human-Machine Coordination unde | 图上人机协调：随机块模型+水填充算法，有界理性下协调最优拓扑设计 |
| K374 | 2608.27659 | Horizon-Dependent Tube MPC for Elliptical-Orbit Re | 椭圆轨道会合管MPC：线性化误差 vs 扰动集比较，确定保证失效的距离范围 |
| R190 | 2608.27654 | Exact Decomposition of Value Functions for Two-Pla | 两人博弈HJ可达性价值函数精确分解：单调性假设下的推广证明 |
| K375 | 2608.26917 | Minimum Rate For Partially Observable Linear Syste | 部分可观测线性系统最小码率：侧信息下LQG+高斯马尔可夫源，凸优化 |
| S146 | 2608.28422 | Effects of HRTF Augmentation on Predicted Spatial  | HRTF增强空间线索：音乐中乐器分离度提升，听损模型下效果降低 |
| R191 | 2608.27695 | A Frequency-Domain Artificial Reverberator Plug-In | FDverb：频域人工混响器，STFT+噪声载波，开源JUCE插件 |
| R192 | 2608.27674 | Not all generalisation failures can be bought back | 情感音频模型泛化边界：corpus swap代价1/5，跨模态代价4/5，生理响应上限1/3 |
| K376 | 2608.28441 | Significance-Driven Semantic Communication | 显著性驱动语义通信：Meta-VIB超网络+MA-RMAB资源分配，语义频谱效率大幅提升 |
| K377 | 2608.28222 | Shortest self-orthogonal and LCD embeddings of lin | Fq+uFq上自正交/LCD嵌入最短长度精确公式，Witt理论构造 |
| R193 | 2608.28133 | Fine Difference Structure and Prime-Power Depth of | p元bent划分：K整除p^n，t≤⌊n/2⌋全局界，无条件证明，Lean4形式化 |
| K378 | 2608.28068 | Finite Sample Bounds for Composite Hypothesis Test | 复合假设检验有限样本界：Renyi投影+相变阈值，强逆+KL投影为最不利对 |
| R194 | 2608.27909 | Low-Altitude Fluid Antenna Network with Multi-Agen | 低空流体天线网络MARL：EM数字孪生+两阶段迁移学习，吞吐提升118.5% |
| R195 | 2608.27635 | Selective Interference Suppression of Siamese-Net  | Siamese-Net干扰抑制：孪生网络选择性抑制强干扰对，弱干扰对保留对齐 |
| S147 | 2608.28036 | Network Topologies for QKD Networks | QKD网络拓扑：图结构特性+成本函数+大规模图构造方法 |
| K379 | 2608.28160 | Gen-TAS: A Generative AI-Aided Hardware-Software T | Gen-TAS：FPGA-GPP异构任务分配LLM框架，CNN 2.45x/SDR 92.53x加速 |
| K380 | 2608.28048 | AI Hardware Accelerators for Large Language Models | LLM硬件加速器全景：GPU/TPU/ASIC/FPGA/PIM/神经形态/光子，内存墙是决定性瓶颈 |
| M130 | 2608.28521 | Modifying van der Waals Materials via Cavity Vacuu | 腔真空涨落调控范德华材料 |
| M131 | 2608.28353 | Crystal-phase quantum dots in AlGaAs nanowires | AlGaAs 纳米线晶相量子点 |
| M132 | 2608.28583 | Layer-Controlled Intermolecular Coupling and Many- | C60 层控分子间耦合与多体效应 |
| M133 | 2608.28546 | Switchable chiral antiferromagnetism through nonli | 非线性磁化率可切换手性反铁磁 |
| M134 | 2608.28492 | Wyckoff-Resolved Oxidation-State Atlas and Anion-C | Wyckoff 分辨氧化态图谱+阴离子条件先验 |
| M135 | 2608.28365 | Topological Signatures of Hardness and Structural  | 网络形成玻璃硬度/结构序拓扑签名 |
| M136 | 2608.28347 | Work Function and High-Coverage Adsorption Energy  | 功函数+高覆盖吸附能作析氢描述符 |
| M137 | 2608.28269 | Phenomenological Growth Regimes in Liquid-Precurso | 液态前驱体 CVD MoS2 现象学生长区 |
| M138 | 2608.28268 | Nanolamellar Hybrid High-Entropy Alloys with Super | 纳米层状混合高熵合金优异微机械性能 |
| M139 | 2608.28238 | Interplay between crystal structure and magnetism  | CeCrB4 晶体结构与磁性相互作用 |
| M140 | 2608.28231 | Quantum Geometric Origin of Nonlinear Current Indu | 非线性电流诱导轨道磁化量子几何起源 |
| M141 | 2608.28143 | Light-induced atomic motion in ionic crystals | 离子晶体光致原子运动 |
| M142 | 2608.28104 | Band-like Carriers in a Soft, Anharmonic Lattice:  | 软非谐晶格铅卤钙钛矿类带载流子 |
| M143 | 2608.27930 | Steady shear rheology of a granular crystal contai | 含单错位颗粒晶体稳态剪切流变 |
| M144 | 2608.27890 | Ionization Energies, Electron Affinities, Bandgaps | 电离能/电子亲和/带隙/激子结合能基准 |
| M145 | 2608.27747 | Electronic structure, magnetic interactions, and m | 2D 三氯化物电子结构/磁性/磁振子 |
| M146 | 2608.27645 | First-Principles DFT Study of Ferroelectric-to-Ant | 铁电到反铁电相变第一性原理 |
| M147 | 2608.27589 | Atomistic Indicators of the Ductile-to-Brittle Tra | 多晶钨延脆转变原子级指示 |
| M148 | 2608.27519 | Exact branch-transfer criterion for common-mode Th | 共模汤姆森热消除精确分支转移判据 |
| M149 | 2608.28554 | Machine learned designs of functional colloidal fo | 机器学习设计功能胶体折叠体 |
| M150 | 2608.28527 | Hierarchical organization governs nonlinear mechan | 层级组织调控 ι-角叉菜胶非线性机械可逆性 |
| M151 | 2608.28055 | Weakly non-linear creep of amorphous polymers near | 非晶聚合物玻璃转变附近弱非线性蠕变 |
| M152 | 2608.25242 | Dynamical and conformational behavior of a polymer | 拥挤溶液聚合物动力学与构象 |
| K381 | 2608.28366 | Real-Time Monitoring of MHD Liquid Metal Flows wit | 浅循环解码器实时监测 MHD 液态金属流 |
| K382 | 2608.27936 | Accelerated S-NFC for Million-Chaff RCS Computatio | 低秩压缩加速百万级 RCS 计算 |
| K383 | 2608.27861 | Vectorized Symmetric and Fermionic Tensor Network  | GPU 矢量化对称/费米张量网络 |
| R196 | 2608.28275 | Full-field fluorescence computed tomography (F3CT) | 标定虚拟源全视场荧光 CT |
| R197 | 2608.27528 | Compact Modeling of Oxide-Semiconductor, 2D Materi | 氧化物半导体/2D/CNT 紧凑建模 |
| K384 | 2608.28466 | Synergy between laser linewidth and frequency chir | 中层磁强计激光线宽与啁啾协同 |
| R198 | 2608.28130 | Beating the nonreciprocal isolation limit of integ | Floquet 工程突破集成环形器非互易隔离极限 |
| R199 | 2608.27858 | Extending the operating window of scanning electro | 图像增强扩展扫描电镜工作窗口 |
| R200 | 2608.27765 | Frequency Synchronization Circuit Model for Analog | 模拟向量矩阵乘频率同步电路模型 |
| R201 | 2608.28356 | Development of a high-granularity, high-precision  | 高粒度高精度定时读出电子学 |
| R202 | 2608.27814 | Migration of Belle II TOP Feature Extraction from  | Belle II TOP 特征提取 Zynq 迁移 |
| R203 | 2608.27556 | A microwave SQUID multiplexing concept for macro-c | 宏低温量热阵列微波 SQUID 多路复用 |
| K385 | 2608.28483 | Modelling platelet dynamics in blood flow: an unre | 血流血小板动力学未解 DEM |
| K386 | 2608.28193 | Editorial: Promoting Green Computing in High Energ | 高能物理/天体物理绿色计算倡议 |
| K387 | 2608.28101 | A Synthetic Iterative Scheme for Non-Gray Phonon B | 非灰声子玻尔兹曼输运方程合成迭代 |
| K388 | 2608.27918 | Higher-Order Topological Phase in the Two-Dimensio | 2D IV 型磁体高阶拓扑相 |
| K389 | 2608.28513 | Machine-learning-assisted multiscale topology opti | ML 辅助多尺度功能梯度拓扑优化 |
| R204 | 2608.28060 | A Compact Selective State-Space Model for Cross-Se | 紧凑选择性状态空间模型股票收益排序 |
| K390 | 2608.27778 | Investigating Forecast Proficiency of Hurricane-In | 飓风诱导复合洪水预报 |
| K391 | 2608.27639 | Dimension Bridging for 3D RANS with Neural Network | 神经网络加速高斯函数 3D RANS 维度桥接 |
| K392 | 2608.22070 | Catellect-VL-2B: A Vision-Language Model for Edge- | 边缘猫咪行为理解视觉语言模型 |
| K393 | 2608.28576 | Learning a Size-Weight Frontier for Synthetic-Augm | 合成增强推断尺寸-权重前沿 |
| K394 | 2608.28566 | On two proofs of $d^2$ mixing of weighted Dikin wa | On two proofs of $d^2$ mixing of weighted Dikin walks |
| R205 | 2608.28137 | CheXtriev: Anatomy-Centered Representation for Cas | 解剖中心胸部 X 光案例检索 |
| K395 | 2608.27826 | Personalized and Multi-View Representation for Fed | Personalized and Multi-View Representation for Federated Col |
| A169 | 2608.27817 | Auditing Generative Audio Calls for Known-Task Aud | Auditing Generative Audio Calls for Known-Task Audio-LLM Eva |
| K396 | 2608.28183 | Memory-efficient GPU pipelines for real-time non-l | 内存高效 GPU 实时非视距重建 |
| K397 | 2608.28102 | What Will This Copper Look Like Later? Forecasting | What Will This Copper Look Like Later? Forecasting Surface A |
| S148 | 2608.27819 | ANCHOR: A Vision for Secure Persistent Key-Value S | 分解数据中心安全持久键值存储 |
| K398 | 2608.27822 | DBRepro: Automated Database Synthesis via a Hybrid | 混合约束求解自动化数据库合成 |
| K399 | 2608.27606 | Robust model-based clustering via mixtures of mult | 多元伪 Voigt 混合鲁棒聚类 |
| K400 | 2608.26610 | On efficiency gains via augmenting a tiny sample w | On efficiency gains via augmenting a tiny sample with a mass |
| R206 | 2608.28001 | FocusGen: Expanding Visual Design Exploration with | FocusGen: Expanding Visual Design Exploration with a Simulat |
| A170 | 2608.27723 | Horizon-Independent Contraction for Continuous-Tim | Horizon-Independent Contraction for Continuous-Time Discount |
| R207 | 2608.28493 | Low-Power End-to-End Cochlear Implant Speech Denoi | 低功耗尖峰神经网络人工耳蜗语音去噪 |
| K401 | 2608.28127 | Exploring the Design Space of Representation Learn | 音频变换表示学习设计空间 |
| K402 | 2608.27724 | A Mixed-Behavior Vote Model for Multimedia Subject | A Mixed-Behavior Vote Model for Multimedia Subjective Qualit |
| K403 | 2608.28097 | Great Expectations: Benchmarking the Real-World Pe | HPC 中 RVV 1.0 真实性能基准 |
| A171 | 2608.27777 | Optimal exponential memory for sequential Euclidea | Optimal exponential memory for sequential Euclidean connecti |
| R208 | 2608.28287 | Development, Configuration and Performance Charact | 可扩展 BETA 阵列开发配置与性能表征 |
| R209 | 2608.15989 | Exact spherical-wave forward model for radio refle | 分层介质无线电反射精确球面波前向模型 |
| R210 | 2608.27622 | Game of Life on Archimedean Lattices: Glider Guns  | Game of Life on Archimedean Lattices: Glider Guns and Phase  |
| R211 | 2608.28304 | Correction of the influence of rolling shutter det | Correction of the influence of rolling shutter detectors on  |
| R212 | 2608.28159 | The Canadian Galactic Emission Mapper: A New 8-10  | 8-10 GHz 银河发射测绘望远镜（极化） |
| R213 | 2608.28098 | Broadband heterodyne interferometry with a chirped | 啁啾飞秒激光宽带外差干涉 H 波段 |
| K404 | 2608.27786 | JUG: JAX-based Unified pulsar timinG | JAX 统一脉冲星计时 |
| R214 | 2608.27775 | PolPy: A universal tool for X-ray/gamma-ray polari | PolPy: A universal tool for X-ray/gamma-ray polarimetry usin |
| K405 | 2608.27637 | Toward a realistic test of black-hole movie correl | 黑洞电影关联作为极端透镜探针 |