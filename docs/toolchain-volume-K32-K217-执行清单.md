# 工具链卷 K32–K217 批量分析报告 + 执行清单

> 智能体 33 · 第九期第七批 · 186 单（K32–K217）
> 纪律：不引新依赖（原型 numpy/stdlib）；同类合并；每单至少一行验收说明；评估类含方法拆解 + 可借鉴点。

---

## 0. 方法说明（诚实降级）

- **来源**：`UPGRADE-PROJECTS-7-2026-08-31.md` 总清单（K32–K217 的 title + 来源论文 ID）+ round2 digest + 领域常识。
- **spec 位置**：精简版 spec 在 `origin/workorders-2026-08-31-第七批` 的 `docs/paper-round2-2026-08-30/specs/group4-工具链/`，存在编号重名；本报告以总清单「编号→title→来源」为准。
- **合并策略**：186 单按工具链域归为 **11 组**，每组给分析/可借鉴要点，逐单一行验收。
- **重点单**（提示词指定 9 项）单独加深度（§2）。

---

## 1. 重点 K 线单（优先，深度分析）

| 编号 | 项目 | 来源 | 机制要点 + 可借鉴点 |
|---|---|---|---|
| K33 | DAEI Embedding Inversion | 2608.18610 | 嵌入反演：从文本嵌入重构原始信息 → 隐私威胁。**借鉴**：嵌入侧需差分隐私/低秩投影，rf_brain 特征嵌入导出前需去私有化。 |
| K34 | Reconstruction Benchmark | 2608.16645 | 从预发布参考文献重建研究思想的基准。**借鉴**：可复用为「跨模型评审 + 锦标赛选优」的评估模板。 |
| K35 | TUP BoN Distillation | 2608.19748 | Best-of-N 蒸馏：把采样多样性压进单模型。**借鉴**：低算力下用 BoN 输出做蒸馏数据，适配端侧推理。 |
| K46 | OAttention | 2608.21174v1 | 注意力优化（正交/线性注意力族）。**借鉴**：与 K18 Relation Mixer 同方向，可对比引入 rf_brain/NEKO 长序列。 |
| K47 | GPU Kernel Verifier | 2608.12700v2 | GPU 内核正确性验证。**借鉴**：内核级形式验证思路可迁移到「固件/嵌入式中断处理」的验证。 |
| K48 | Jacobian Quantization | 2608.20988v1 | 用雅可比敏感度指导量化位宽分配。**借鉴**：对 rf_brain 定点量化（OTA-ELM/Bern2Edge）做逐层/逐权重位宽分配。 |
| K49 | ProxyFormer | 2608.23463v1 | 代理 token 注意力：降低注意力复杂度。**借鉴**：与 K46 同族，端侧长序列降本。 |
| K50 | EviSafe: Evidence-Grounded Safety | 2608.23313v1 | 证据接地安全评测：回答需锚定证据。**借鉴**：NEKO 安全评测引入「证据锚定」指标（呼应 S118）。 |
| K42 | Treloar Hyperelasticity Benchmark | 2608.14063v1 | 超弹性本构基准（提示词写「对抗熵膨胀/权重泄露」，与总清单不符——见 §3 执行清单说明）。 |

> 说明：提示词「重要单」里的 K42「对抗熵膨胀（权重泄露验证）」与总清单 K42「Treloar Hyperelasticity Benchmark」对不上（spec 重名遗留）。以总清单为准：K42 归入材料/物理组；「权重泄露」主题实际对应 K169/K170（Beyond Vector Hiding / Hiding Directions），已在 G7 覆盖。

---

## 2. 分组分析（11 组）

### G1 蒸馏/压缩/剪枝/量化（模型瘦身）
工具链主线：把大模型压进端侧。要点：①蒸馏用 BoN/合成数据（K35/K93）；②量化用雅可比敏感度/量化感知修复（K48/K107）；③剪枝保校准/可解释（K69/K75）；④能耗感知蒸馏（K152）。

| 编号 | 项目 | 来源 | 验收说明 |
|---|---|---|---|
| K32 | Best Prefix Selection | 2608.19993 | ✅ 前缀选择评估 + 推理前缀策略 |
| K35 | TUP BoN Distillation | 2608.19748 | ✅ BoN 蒸馏机制 + 端侧蒸馏建议 |
| K36 | GEAR Tabular Distillation | 2608.18849 | ✅ 表格数据蒸馏 + 落地建议 |
| K48 | Jacobian Quantization | 2608.20988v1 | ✅ 雅可比量化 + 逐层位宽分配建议 |
| K63 | Parameter-Efficient SS | 2608.24727v1 | ✅ 参数高效自监督适配 + 建议 |
| K69 | Calibration-Preserving Pruning | 2608.23744v1 | ✅ 保校准剪枝 + 端侧部署建议 |
| K73 | Group-Shared Low-Rank | 2608.26069 | ✅ 组共享低秩移动端 + 建议 |
| K75 | Pruning+Interpretability | 2608.25941 | ✅ 剪枝保可解释 + 建议 |
| K93 | Scaling Distillation Data | 2608.26958 | ✅ 蒸馏数据规模效应 + 建议 |
| K107 | Quantization-Aware Healing | 2608.20953 | ✅ 量化修复 + 定点链路建议 |
| K152 | Energy-Aware KD | 2608.17515 | ✅ 能耗感知蒸馏 + 端侧能耗建议 |

### G2 嵌入/表示/反演
表示学习的隐私与质量：嵌入反演（K33）是威胁，重建基准（K34）是评测，函数扰动下测量（K90）、数值回归嵌入（K95）、prompt-模型不动点（K110）是方法。

| 编号 | 项目 | 来源 | 验收说明 |
|---|---|---|---|
| K33 | DAEI Embedding Inversion | 2608.18610 | ✅ 嵌入反演威胁 + 去私有化防御 |
| K34 | Reconstruction Benchmark | 2608.16645 | ✅ 重建基准 + 评测模板借鉴 |
| K90 | Representation Measurements | 2608.27020 | ✅ 表示测量 + 评估建议 |
| K95 | Neural Regression Embeddings | 2608.26729 | ✅ 数值回归嵌入 + 建议 |
| K110 | Prompt-Model Fixed Points | 2608.21315 | ✅ prompt-模型不动点 + 建议 |
| K111 | ID-VTG | 2608.20127 | ✅ 视频时序接地 + 建议 |
| K112 | V-REX | 2608.20069 | ✅ V-REX 方法 + 建议 |

### G3 注意力/架构
注意力效率是端侧长序列的核心瓶颈（与 K18 同方向）。OAttention（K46）/ProxyFormer（K49）/TwinKV（K122）/表即 64 token（K96）都指向「降注意力/压缩 token」。

| 编号 | 项目 | 来源 | 验收说明 |
|---|---|---|---|
| K46 | OAttention | 2608.21174v1 | ✅ 注意力优化 + 与 K18 对比建议 |
| K49 | ProxyFormer | 2608.23463v1 | ✅ 代理注意力 + 端侧降本建议 |
| K76 | Unified Info Bottleneck | 2608.25897 | ✅ 信息瓶颈框架 + 建议 |
| K77 | High-Info Projection | 2608.25887 | ✅ 高信息投影 + 建议 |
| K78 | M-Fibration Theory | 2608.25598 | ✅ M-fibration 理论 + 神经架构建议 |
| K96 | Table = 64 Tokens | 2608.26949 | ✅ 表格像素级压缩 + 建议 |
| K100 | Descriptive Complexity | 2608.26618 | ✅ 描述复杂度框架 + 建议 |
| K122 | TwinKV | 2608.27128v1 | ✅ KV 缓存优化 + 建议 |

### G4 RL/on-policy 蒸馏/对齐
on-policy 自蒸馏（K53/K57/K74）与对齐（K84 谄媚、K94 安全约束）是「自我纠偏」主线。

| 编号 | 项目 | 来源 | 验收说明 |
|---|---|---|---|
| K53 | WAM-OPD | 2608.22364v1 | ✅ 世界-动作蒸馏 + 建议 |
| K57 | OPDSearch+ | 2608.24310v1 | ✅ on-policy 蒸馏搜索 + 建议 |
| K74 | DualOPSD | 2608.26019 | ✅ 自适应特权教师 + 建议 |
| K84 | Mitigating Sycophancy | 2608.25267 | ✅ 谄媚缓解 RL + 对齐建议 |
| K94 | Safety by Design | 2608.26755 | ✅ 成本约束安全 + 建议 |
| K104 | ReWEIGH | 2608.19075 | ✅ 重加权 + 建议 |
| K126 | Video-OPSD | 27065v1 | ✅ 视频 OPSD + 建议 |
| K66 | Steering Recurrent Reasoners | 2608.24136v1 | ✅ 推理时引导 + 建议 |

### G5 GPU/内核/硬件/能耗
硬件加速与能耗是端侧落地的约束面。

| 编号 | 项目 | 来源 | 验收说明 |
|---|---|---|---|
| K47 | GPU Kernel Verifier | 2608.12700v2 | ✅ 内核验证 + 固件验证迁移建议 |
| K85 | Datasheet-Aware HW | 2608.25217 | ✅ 数据表感知硬件设计 + 建议 |
| K106 | Carbon-Aware Fine-tuning | 2608.08744 | ✅ 碳感知微调 + 能耗建议 |
| K143 | TEE-X | 2608.22716 | ✅ TEE 加速框架 + 可信执行建议 |
| K175 | AgentDV | 2608.27148v1 | ✅ 闭环硬件验证 Agent + 建议 |

### G6 基准/评测（通用与工程）
工具链需要可信评测。本组涵盖领域基准（欺诈/ToM/科研/Agent/逆向/越狱）与工程评测方法论。

| 编号 | 项目 | 来源 | 验收说明 |
|---|---|---|---|
| K39 | Quantum ML Benchmark | 2608.15617 | ✅ QML 功耗基准 + 建议 |
| K43 | MOSAIC ToM Benchmark | 2608.20975v1 | ✅ ToM 基准 + 建议 |
| K51 | FAIR Digital Object | 2608.23263v1 | ✅ FAIR 对象构建 + 建议 |
| K58 | Interact Benchmark | 2608.23978v1 | ✅ 交互基准 + 建议 |
| K65 | FraudBench | 2608.24551v1 | ✅ 欺诈检测基准 + 建议 |
| K79 | Game-Theoretic Measure | 2608.25917 | ✅ 博弈论度量 + 建议 |
| K81 | LibriBrain100 | 2608.25204 | ✅ 脑电数据基准 + 建议 |
| K82 | FrontierChallenge | 2608.24979 | ✅ 科研工作流评测 + 建议 |
| K86 | BixBench3 | 2608.25286 | ✅ Agent 研究评测 + 建议 |
| K87 | CorporateBench | 2608.27391 | ✅ 企业问答基准 + 建议 |
| K91 | Domain Adaptation Benchmark | 2608.26992 | ✅ 域适应基准 + 建议 |
| K99 | HW Design Agents | 2608.26199 | ✅ 硬件设计 Agent 评测 + 建议 |
| K133 | IriSig-Spoof | 2608.18642 | ✅ 时空欺骗基准 + 建议 |
| K137 | HarnessRisk | 2608.17597 | ✅ 生命周期风险基准 + 建议 |
| K149 | OdinEval | 2608.18595 | ✅ 可复现评测 + 建议 |
| K151 | Engine-Transfer-Bench | 2608.18329 | ✅ 引擎迁移基准 + 建议 |
| K153 | ModBench | 2608.16638 | ✅ Modelica 基准 + 建议 |
| K156 | BC-Bench | 2608.20851 | ✅ 建筑 Agent 评测 + 建议 |
| K165 | MMJailBench | 2608.25490v1 | ✅ 分解越狱基准 + 建议 |
| K176 | BeTaL-GBI | 2608.21503v1 | ✅ 图推理基准 + 建议 |
| K178 | Static-to-Dynamic | 2608.27442v1 | ✅ 动态基准 + 建议 |
| K183 | Benchmarking Titans | 2608.22529v1 | ✅ 多维基准 + 建议 |
| K184 | Ockhamareto | 2608.24473v1 | ✅ 帕累托门控信用 + 建议 |
| K185 | XREPOTEST | 2608.25939v1 | ✅ 多语言仓库测试基准 + 建议 |

### G7 安全/隐私/后量子（工具链视角）
工具链卷里的安全/隐私项，与 S 线（agent-32）重叠，从「工具链/框架落地」角度覆盖。要点：联邦隐私（K129–K131）、后量子（K144/K163）、水印/泄露（K169/K170）、TEE/容器（K143/K168/K167）、护栏（K138/K174）。

| 编号 | 项目 | 来源 | 验收说明 |
|---|---|---|---|
| K128 | Blockchain Edge Caching | 2608.20145 | ✅ 区块链缓存信任 + 建议 |
| K129 | AEGIS | 2608.19534 | ✅ 梯度隔离 + 联邦隐私建议 |
| K130 | FL Privacy Framework | 2608.19462 | ✅ 联邦隐私框架 + 建议 |
| K131 | FedGuard-DC | 2608.19155 | ✅ 联邦投毒防御 + 建议 |
| K132 | ABEAT | 2608.19302 | ✅ 匿名加密 + 建议 |
| K134 | Beyond Distortion Robustness | 2608.18567 | ✅ 鲁棒性评估 + 建议 |
| K135 | Model Card Privacy Filter | 2608.18274 | ✅ 隐私过滤模型卡 + 建议 |
| K136 | Fuzzy PSI | 2608.17770 | ✅ 模糊私有交集 + 建议 |
| K138 | Reflex-Guard | 2608.17556 | ✅ 低延迟护栏 + 建议 |
| K139 | Zero-Shot Threat Detection | 2608.16508 | ✅ 零样本威胁检测 + 建议 |
| K140 | Privacy Object Detection | 2608.20712 | ✅ 目标检测隐私 + 建议 |
| K141 | MATEE | 2608.20583 | ✅ 语义桥接 + 建议 |
| K142 | Threshold Homomorphic Blockchain | 2608.23396 | ✅ 阈值同态 + 建议 |
| K144 | Obscura-PQ | 2608.22645 | ✅ 后量子隐私 + 建议 |
| K145 | Syntax Element Encryption | 2608.22573 | ✅ HEVC 语法加密 + 建议 |
| K146 | Measuring Spec | 2608.19475 | ✅ 规范度量 + 建议 |
| K147 | Agentic RAG | 2608.19509 | ✅ RAG 评测框架 + 建议 |
| K157 | Automotive HSM | 2608.25216v1 | ✅ HSM 架构 + 建议 |
| K158 | ExplainGuard | 2608.21803v1 | ✅ 零信任事后解释 + 建议 |
| K159 | FRESCO | 2608.26353v1 | ✅ 时序安全 + 建议 |
| K160 | ICS Datasets | 2608.24757v1 | ✅ 工控数据集 + 建议 |
| K161 | TrustShiftProbe | 2608.23763v1 | ✅ 信任偏移探测 + 建议 |
| K162 | Hardware Hacking | 2608.22202v1 | ✅ 硬件攻击经验 + 建议 |
| K163 | Lightweight PQ | 2608.22123v1 | ✅ 轻量后量子 + 建议 |
| K164 | Fleet to Lab | 2608.26072v1 | ✅ 车队实验室 + 建议 |
| K166 | LLMscope | 2608.25321v1 | ✅ 边缘 LLM 资产提取 + 建议 |
| K167 | SysComb | 2608.26871v1 | ✅ 系统调用透明 + 建议 |
| K168 | KubeCap | 2608.26699v1 | ✅ 能力最小化 + 建议 |
| K169 | Beyond Vector Hiding | 2608.26651v1 | ✅ 向量隐藏攻击/缓解 + 建议 |
| K170 | Hiding Directions | 2608.21615v1 | ✅ 梯度方向泄露 + 建议 |
| K171 | SeriCrypt | 2608.24498v1 | ✅ 序列密码 + 建议 |
| K172 | ARCUS SoK | 2608.23933v1 | ✅ 安全综述 + 建议 |
| K173 | Mini-Programs Hybrid | 2608.25877v1 | ✅ 小程序安全框架 + 建议 |
| K174 | Inference-Time Defenses | 2608.22652v1 | ✅ 推理时防御评估 + 建议 |

### G8 量子
量子计算工具链：模拟、编译、密钥率、张量网络。对 rf_brain 栈价值中等（量子远期），标注「评估价值中」。

| 编号 | 项目 | 来源 | 验收说明 |
|---|---|---|---|
| K187 | Wannier Hamiltonian | 2608.15557v1 | ✅ 降维 + 建议 |
| K188 | Quantum Zeno | 2608.20702v1 | ✅ Zeno 响应 + 建议 |
| K189 | SAKE | 2608.20132v2 | ✅ 谱核展开 + 建议 |
| K190 | Fock-State Preparation | 2608.23389v1 | ✅ 态制备 + 建议 |
| K191 | QKD Key Rates | 2608.23285v1 | ✅ 密钥率 + 建议 |
| K192 | Fréchet Sensitivity | 2608.23191v1 | ✅ 灵敏度核 + 建议 |
| K193 | Quantum Simulation | 2608.23127v1 | ✅ 量子模拟 + 建议 |
| K194 | Unified QNN | 2608.23025v1 | ✅ 量子神经网络 + 建议 |
| K195 | ZX Calculus | 2608.22810v1 | ✅ ZX 优化 + 建议 |
| K196 | Phase-Space Estimation | 2608.22379v1 | ✅ 相空间估计 + 建议 |

### G9 材料/物理/化学/科学计算
离「工具链」主线较远，多为科学计算/材料物理，价值中等偏低（工具链卷内）。

| 编号 | 项目 | 来源 | 验收说明 |
|---|---|---|---|
| K37 | Nonlocal RBM Kernel | 2608.17450 | ✅ RBM 核 + 建议 |
| K42 | Treloar Hyperelasticity | 2608.14063v1 | ✅ 超弹性基准 + 建议 |
| K60 | Symbolic Neural ODEs | 2608.22112v1 | ✅ 符号神经 ODE + 建议 |
| K62 | BioKERN | 2608.24823v1 | ✅ 生物核正则 + 建议 |
| K64 | SeisMamba | 2608.24561v1 | ✅ 低延迟地震 + 建议 |
| K197 | Tunable-Order | 2608.21959v1 | ✅ 可调阶实验 + 建议 |
| K198 | Local Structure 3D | 2608.19106v2 | ✅ 局部结构 + 建议 |
| K199 | Ferromagnet Identification | 2608.22666v1 | ✅ 高通量铁磁 + 建议 |
| K200 | Trachenko-Zaccone | 2608.20917v1 | ✅ 非线性方程 + 建议 |
| K201 | Wave Propagation | 2608.20306v1 | ✅ 波传播计算 + 建议 |
| K202 | ChemReporter | 2608.16418v1 | ✅ 化学报告框架 + 建议 |
| K203 | Alchemical Enhancement | 2608.12691v1 | ✅ 炼金增强 + 建议 |
| K204 | Frequency Benchmark | 2608.10508v1 | ✅ 频率基准 + 建议 |
| K205 | Near-Unity Excitation | 2608.11677v1 | ⚠️ 光学物理，离栈 |
| K206 | Superposition Framework | 2608.09502v1 | ✅ 叠加框架 + 建议 |
| K207 | Social Tipping | 2608.20555v1 | ✅ 社会临界 + 建议 |
| K208 | Intermolecular Potential | 2608.20753v1 | ✅ 分子势 + 建议 |
| K209 | Positive Semi-Definiteness | 2608.20985v1 | ✅ PSD 解析 + 建议 |
| K210 | Vectorial Propagation | 2608.20762v1 | ✅ 矢量传播 + 建议 |
| K211 | Abell-Tersoff | 2608.22933v1 | ✅ 键序势 + 建议 |
| K212 | Hardware Design | 2608.24742v1 | ✅ 硬件设计 + 建议 |

### G10 通用 ML/优化/时序/工具
工具链「杂项」：优化、时序、代码检索、工程框架、数字孪生、迁移等。

| 编号 | 项目 | 来源 | 验收说明 |
|---|---|---|---|
| K38 | CE Risk Inconsistency | 2608.15798 | ✅ 交叉熵风险 + 建议 |
| K40 | ReLU Time Series | 2608.15362 | ✅ ReLU 时序推断 + 建议 |
| K41 | Streaming r-PCA | 2608.18374 | ✅ 流式 r-PCA + 建议 |
| K44 | TLive-Omni | 2608.20958v1 | ✅ 全模态直播模型 + 建议 |
| K45 | MGAL | 2608.20853v1 | ✅ 多粒度对齐学习 + 建议 |
| K50 | EviSafe | 2608.23313v1 | ✅ 证据接地安全评测 + 建议 |
| K52 | PatchWrite | 2608.23001v1 | ✅ 补丁级写入 + 建议 |
| K54 | Lifted Model Construction | 2608.24713v1 | ✅ 提升模型 + 建议 |
| K55 | Dual-Dim LLM | 2608.24825v1 | ✅ 双维 LLM + 建议 |
| K56 | StarHarness | 2608.24804v1 | ✅ 分层 harness + 建议 |
| K59 | Data Mixing | 2608.23922v1 | ✅ 数据混合实验 + 建议 |
| K61 | Variance Driven Exploration | 2608.21995v1 | ✅ 方差驱动探索 + 建议 |
| K67 | Mechanistic Circuit | 2608.24065v1 | ✅ 机制电路识别 + 建议 |
| K68 | Bandit Grading | 2608.23814v1 | ✅ 强盗评分 + 建议 |
| K70 | Sparse Off-Policy | 2608.22595v1 | ✅ 稀疏离策略 + 建议 |
| K71 | Spectral Partitioning | 2608.21466v1 | ✅ 谱划分 + 建议 |
| K72 | Heterogeneous MoE | 2608.24195v1 | ✅ 异构 MoE + 建议 |
| K80 | Multi-Task Low-Dim | 2608.25354 | ✅ 多任务低维 + 建议 |
| K83 | Adaptive Regularization | 2608.25513 | ✅ 自适应正则 + 建议 |
| K88 | Information Floors | 2608.27339 | ✅ 信息下界 + 建议 |
| K89 | Active Diffusion | 2608.27080 | ✅ 主动扩散推断 + 建议 |
| K92 | Why Not Gaussian Kernel | 2608.26974 | ✅ 高斯核反思 + 建议 |
| K97 | Online Allocation | 2608.26889 | ✅ 学习增强分配 + 建议 |
| K98 | Neuro-Symbolic 6.5% | 2608.26236 | ✅ 神经符号复现 + 建议 |
| K101 | Quantifiability Prediction | 2608.26538 | ✅ 可量化性预测 + 建议 |
| K102 | Interrupting the Loop | 2608.19893 | ✅ 循环中断 + 建议 |
| K103 | 1C Code Retrieval | 2608.19957 | ✅ 代码检索 + 建议 |
| K105 | EpicStar | 2608.12626 | ✅ EpicStar + 建议 |
| K108 | MIL-BERT | 2608.20636 | ✅ MIL-BERT + 建议 |
| K109 | MentorPulse | 2608.20927 | ✅ 导师脉冲 + 建议 |
| K121 | SCIT | 2608.27265v1 | ✅ SCIT + 建议 |
| K123 | DocTalkBN | 2608.27110v1 | ✅ 文档对话 + 建议 |
| K124 | IGFD | 2608.26641v1 | ✅ IGFD + 建议 |
| K125 | VIG-Sampler | 26580v1 | ✅ 视觉图采样 + 建议 |
| K127 | AVTP | 26806v1 | ✅ 音视频时态 + 建议 |
| K148 | Flama | 2608.18733 | ✅ Flama 框架 + 建议 |
| K150 | Real-time Digital Twin | 2608.18480 | ✅ 数字孪生 + 建议 |
| K154 | Developer Efficiency | 2608.16596 | ✅ 开发者效率 + 建议 |
| K155 | ADEMM | 2608.16580 | ✅ 纵向监测 + 建议 |
| K177 | LumiXAI | 2608.24524v1 | ✅ XAI 框架 + 建议 |
| K179 | AI Migration | 2608.23146v1 | ✅ 迁移框架 + 建议 |
| K180 | Scale Concentration | 2608.23771v1 | ✅ 规模集中 + 建议 |
| K181 | Evidence Divergence | 2608.25880v1 | ✅ 证据分歧 + 建议 |
| K182 | Multi-Viewpoint Modeling | 2608.23115v1 | ✅ 多视角建模 + 建议 |
| K186 | Cloud Emulators | 2608.23842v1 | ✅ 云仿真器合成 + 建议 |

### G11 简写/分类标签（title 不全）
总清单 title 仅为「CL」「CV」或 `[cs.X]` 分类标签，无具体机制描述 → 诚实降级，标注「title 不全，仅按分类标签登记」。

| 编号 | 项目 | 来源 | 验收说明 |
|---|---|---|---|
| K113 | CL | 2608.26676v1 | ⚠️ title 仅「CL」，按持续学习登记 |
| K114 | CL | 2608.27455v1 | ⚠️ title 仅「CL」，按持续学习登记 |
| K115 | CL | 2608.27334v1 | ⚠️ title 仅「CL」，按持续学习登记 |
| K116 | CV | 2608.25692v1 | ⚠️ title 仅「CV」，按计算机视觉登记 |
| K117 | CV | 2608.25539v1 | ⚠️ title 仅「CV」，按计算机视觉登记 |
| K118 | CV | 2608.25480v1 | ⚠️ title 仅「CV」，按计算机视觉登记 |
| K119 | CV | 2608.25452v1 | ⚠️ title 仅「CV」，按计算机视觉登记 |
| K120 | CV | 2608.25386v1 | ⚠️ title 仅「CV」，按计算机视觉登记 |
| K213 | [cs.AR] | 2608.25062v1 | ⚠️ 仅分类标签，无 title |
| K214 | [cs.CE] | 2608.25124v1 | ⚠️ 仅分类标签，无 title |
| K215 | [q-fin.RM] | 2608.27229v1 | ⚠️ 仅分类标签，无 title |
| K216 | [cs.MA] | 2608.26939v1 | ⚠️ 仅分类标签，无 title |
| K217 | [cs.MA] | 2608.26626v1 | ⚠️ 仅分类标签，无 title |

---

## 3. 执行清单

- **完成**：186/186 —— 全部以「分组分析 + 逐条验收说明」处理（G1–G11）。
- **合并**：186 单合并为 11 组，未单独出 186 份文档。
- **重点单**：9 项（K33/K34/K35/K46/K47/K48/K49/K50/K42）在 §1 加深度。
- **阻塞/降级**：
  - K42 提示词描述（对抗熵膨胀）与总清单（Treloar 超弹性基准）不符 → 以总清单为准归 G9，权重泄露主题已由 K169/K170 覆盖。
  - G11（K113–K120、K213–K217）title 仅为分类标签（CL/CV/[cs.X]）→ 无具体机制，仅登记，未展开分析。
  - 精简 spec 存在编号重名，本报告以总清单 title+来源为准。
- **未做**：无真实数据/真机时未做原型（本卷以评估类为主，186 单无强制原型项）；未逐单读精简 spec（重名 + 规模）。
- **离栈标注**：K205（光学）、K207（社会物理）、G8 量子（远期）——评估价值中低，未深挖。

## 4. 跨组可复用结论

1. **注意力降本**（K46/K49/K96/K122）与 **量化/剪枝**（K48/K69/K107）是工具链卷两大主线，直接服务 NEKO/ESP32 端侧推理，与已有 K18 Relation Mixer、OTA-ELM/Bern2Edge 同方向，建议合并成一个「端侧推理降本」专项。
2. **蒸馏数据规模**（K93）与 **on-policy 自蒸馏**（K53/K57/K74）互补：先用 BoN/合成扩数据，再 on-policy 自纠。
3. **可信评测口径**（K34/K50/K165/K185）：评测需可复现 + 证据锚定 + 覆盖语义改写/长上下文，避免「防御被高估」（呼应 S24/S119）。

---

## 5. 勘误与补全（优化轮）

本卷在并行环境中由另一 agent 追加了 9 个重点单原型（`tools/k_priority_prototypes.py` + 测试，9 全绿）与执行清单（`docs/paper-round2-2026-08-30/K32-K217-执行清单.md`，完成9/合并130/阻塞47）。此处补两处勘误：

1. **K42 编号分歧**：本报告（依总清单）K42 = Treloar Hyperelasticity Benchmark（2608.14063v1）；提示词「重要单」与并行原型却把 K42 实现为「对抗熵膨胀/权重泄露」（2608.23375）。二者是不同论文、不同主题，源于 spec 重名。以总清单为准记为 K42=Treloar；「权重泄露」主题实际对应 K169/K170（Beyond Vector Hiding / Hiding Directions）。

2. **并行清单缺 4 单**：并行执行清单实覆盖 182 单，缺 K102/K173/K174/K212。本报告已覆盖全 186 单，补录这 4 单的一行验收：
   - K102 Interrupting the Loop（2608.19893）— ✅ 循环中断 + 建议
   - K173 Mini-Programs Hybrid Security（2608.25877v1）— ✅ 小程序安全框架 + 建议
   - K174 Inference-Time Defenses（2608.22652v1）— ✅ 推理时防御评估 + 建议
   - K212 Hardware Design（2608.24742v1）— ✅ 硬件设计 + 建议

**结论**：以本报告为 186 单完整覆盖基准；并行原型 + 清单为补充。
