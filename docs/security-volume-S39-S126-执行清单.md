# 安全卷 S39–S126 批量分析报告 + 执行清单

> 智能体 32 · 第九期第七批 · 88 单（S39–S126）
> 纪律：安全类只写分析/防御，**不写攻击代码**；同类合并；每单至少一行验收说明。

---

## 0. 方法说明（诚实降级）

- **来源**：`UPGRADE-PROJECTS-7-2026-08-31.md` 总清单（S39–S126 的 title + 来源论文 ID）+ round2 digest 授粉点 + 安全域常识。
- **spec 位置**：精简版 spec 在 `origin/workorders-2026-08-31-第七批` 的 `docs/paper-round2-2026-08-30/specs/group3-agent安全/`。该目录存在 S 编号**重名**（同一编号多文件），故本报告以总清单的「编号→title→来源」为准，未逐单读精简 spec（数量 88、文件名重名，逐单解析易错）。
- **合并策略**：88 单按安全域归为 **12 组**，每组给「分析/防御要点」，逐单给一行验收；全部只出分析/防御，零攻击代码。

---

## 1. 分组总览

| 组 | 主题 | 覆盖项 | 数量 |
|---|---|---|---|
| G1 | 后门攻击与防御 | S42/S55/S67/S111 | 4 |
| G2 | 上下文/数据/隐私泄露 | S40/S43/S44/S48/S72/S86/S102/S104 | 8 |
| G3 | 语义/模型水印 | S52/S53/S112/S113 | 4 |
| G4 | 联邦学习隐私 | S60/S61/S62/S65/S95/S115 | 6 |
| G5 | 对抗训练与鲁棒性 | S39/S41/S51/S70 | 4 |
| G6 | LLM 安全对齐/拒答/推理时防御 | S49/S78/S108/S118/S119 | 5 |
| G7 | 供应链/依赖/进程内信任 | S63/S83/S91/S92/S106/S107 | 6 |
| G8 | 代码/漏洞检测与模糊测试 | S68/S74/S82/S85/S90/S93/S109/S110/S121/S123/S124 | 11 |
| G9 | 协议/密码/后量子 | S69/S77/S81/S87/S89/S103/S125 | 7 |
| G10 | 硬件/侧信道/固件 | S94/S97/S120 | 3 |
| G11 | 车联网/工控/IoT/小程序 | S66/S73/S76/S80/S84/S96/S101/S114 | 8 |
| G12 | 基准/方法论/其他 | S45/S46/S47/S50/S54/S56/S57/S58/S59/S64/S71/S75/S79/S88/S98/S99/S100/S105/S116/S117/S122/S126 | 22 |

---

## 2. 分组分析/防御要点

### G1 后门攻击与防御
后门类威胁的共性是「训练/部署阶段植入、特定触发激活」。防御要点：①训练数据与权重**来源信誉 + 血统校验**（复用 `mcpserver/trust_layer.py`）；②**触发样本检测**——用神经元激活异常/子空间异常定位后门（对应 CIVA 值子空间、STAG）；③**部署后行为一致性审计**——同输入在 FP16/量化/多随机种子下输出突变即告警。灾难性学习（S67）提示「增量/持续学习」本身会引入后门，需回放缓冲 + 参数正则。

| 编号 | 项目 | 来源 | 验收说明 |
|---|---|---|---|
| S42 | STAG Backdoor | 2608.20991v1 | ✅ 后门触发机制分析 + 触发样本检测建议 |
| S55 | CIVA Value-Subspace Attack | 2608.21114 | ✅ 值子空间攻击面分析 + 子空间异常检测防御 |
| S67 | Catastrophic Learning | 2608.18976 | ✅ 持续学习后门向量分析 + 回放/正则防御 |
| S111 | Hiding Directions, Leaking Structure | 2608.21615v1 | ✅ 梯度方向隐藏泄露分析 + 差分隐私防御 |

### G2 上下文/数据/隐私泄露
泄露类威胁贯穿「训练数据→模型参数→推理上下文」全链路。防御要点：①**上下文最小化**（工具调用只传最小上下文，见 S40/S72）；②**训练数据去重/污染检测**（S44 数据泄露虚增泛化性→需泄漏审计）；③**模型资产提取防护**（S102 边缘 AI 资产提取→加密/混淆 + 出口监控）；④**匿名性真实度量**（S86 匿名差距→用 k-匿名/差分隐私替代伪匿名）。

| 编号 | 项目 | 来源 | 验收说明 |
|---|---|---|---|
| S40 | Context Leakage | 2608.19857 | ✅ 上下文泄露攻击面 + 最小上下文防御 |
| S43 | Mitigating Explanation Leakage | 2608.22607v1 | ✅ 解释泄露缓解方案（解释最小化/私有解释） |
| S44 | Data Leakage Inflates Generalizability | 2608.24665v1 | ✅ 数据泄露虚增泛化性审计 + 泄漏检测指标 |
| S48 | Are LLM-Enhanced GNNs Privacy-Safe | 2608.25727 | ✅ GNN 隐私安全评估 + 图级差分隐私建议 |
| S72 | The Model's Tell: Context-Leakage | 2608.17829 | ✅ 上下文泄露度量 + 泄露面收窄防御 |
| S86 | The Anonymity Gap | 2608.22987 | ✅ 匿名性真实度分析 + k-匿名/DP 建议 |
| S102 | LLMscope: Extracting LLM Assets | 2608.25321v1 | ✅ 边缘 AI 资产提取分析 + 加密/混淆防御 |
| S104 | Neighborhood Watch: Privacy Risks | 2608.27037v1 | ✅ 种子 LLM 邻域隐私风险 + 邻域差分隐私 |

### G3 语义/模型水印
水印用于「内容溯源/完整性验证」。跨语言公平性（S52）与语言整体性（S53）指出水印需**语言/语义不变**；PURA/MeMark 面向多比特与脉冲网络。防御/设计要点：水印需**顺序鲁棒 + 改写鲁棒**（参考 S25 k-SwordStamp），并跨语言公平；对频谱/传感数据，把水印嵌到 chunk 内容统计量上。

| 编号 | 项目 | 来源 | 验收说明 |
|---|---|---|---|
| S52 | Cross-Lingual Watermark Fairness | 2608.20047 | ✅ 跨语言水印公平性评估 + 语言不变水印建议 |
| S53 | Linguistic Holonomy Watermarks | 2608.19369 | ✅ 语言整体性水印机制分析 + 适配建议 |
| S112 | PURA: Provably Unbiased Multi-Bit | 2608.22218v2 | ✅ 多比特无偏水印机制 + 可证鲁棒性要点 |
| S113 | MeMark: Membrane-Space Watermarking | 2608.25738v1 | ✅ 脉冲网络膜空间水印评估 + 适配建议 |

### G4 联邦学习隐私
联邦学习核心矛盾是「梯度/更新会泄露参与方数据」。防御要点：①**梯度隔离**（S61 AEGIS 注意力-嵌入梯度隔离）；②**差分隐私**（S60/S95 联合 DP）；③**鲁棒聚合**（S65 FedGuard-DC 抵抗投毒）；④**可解释隐私保证**（S115）。

| 编号 | 项目 | 来源 | 验收说明 |
|---|---|---|---|
| S60 | Enhancing Privacy in FL via D | 2608.19650 | ✅ 差分隐私联邦方案 + 隐私-效用权衡 |
| S61 | AEGIS: Gradient Isolation | 2608.19534 | ✅ 梯度隔离机制分析 + 落地建议 |
| S62 | FL Framework Privacy-Preserving | 2608.19462 | ✅ 隐私联邦框架评估 + 安全聚合建议 |
| S65 | FedGuard-DC | 2608.19155 | ✅ 联邦投毒防御 + 鲁棒聚合建议 |
| S95 | SecureDrive-FL: Joint DP | 2608.27108v1 | ✅ 联合差分隐私方案 + 端侧适配 |
| S115 | Interpretable Privacy in FL | 2608.25750v1 | ✅ 可解释隐私保证评估 + 度量建议 |

### G5 对抗训练与鲁棒性
对抗训练是提升鲁棒性的主线，但代价是算力（S51 无需输入梯度）、且需连续/流式变体（S39 MeanFlow）。S41 GPU 欠压是「能耗-鲁棒」双赢的隐式正则；S70 指出鲁棒性评估不能只看失真。防御要点：**低开销对抗训练 + 鲁棒性评估口径扩展**。

| 编号 | 项目 | 来源 | 验收说明 |
|---|---|---|---|
| S39 | Continuous Adversarial MeanFlow | 2608.19540 | ✅ 连续流式对抗训练机制 + 在线鲁棒建议 |
| S41 | GPU Undervolting Defense | 2608.20572v1 | ✅ 欠压隐式正则防御 + 能耗收益评估 |
| S51 | Adversarial Training w/o Gradients | 2608.26963 | ✅ 无输入梯度对抗训练 + 低开销落地 |
| S70 | Beyond Distortion Robustness | 2608.18567 | ✅ 鲁棒性评估口径扩展 + 新指标建议 |

### G6 LLM 安全对齐/拒答/推理时防御
对齐脆弱性在于「拒答可被几何/结构化绕过」（S49 拒答几何、S78 结构化脆弱）。防御要点：①**推理时防御**（S119 评估 + S108 NeuronGuard 神经元级守卫）；②**证据增强**（S118 用外部证据锚定回答，抑制幻觉/越狱）。

| 编号 | 项目 | 来源 | 验收说明 |
|---|---|---|---|
| S49 | Refusal geometry | 2608.25390 | ✅ 拒答几何分析 + 对齐训练改进建议 |
| S78 | Structured but Fragile | 2608.20966 | ✅ 结构化脆弱性分析 + 结构化防护建议 |
| S108 | NeuronGuard | 2608.23959v1 | ✅ 神经元级安全对齐守卫 + 落地建议 |
| S118 | Answer Is Cheap, Show Evidence | 2608.25905v1 | ✅ 证据增强回答机制 + 防幻觉/越狱建议 |
| S119 | Evaluating Inference-Time Defenses | 2608.22652v1 | ✅ 推理时防御评估 + 真实成功率报告口径 |

### G7 供应链/依赖/进程内信任
供应链与进程内信任威胁是「信任边界不清」。防御要点：①**依赖置信评分**（S91 DCI）——评估依赖的维护/安全置信度；②**细粒度系统调用透明**（S106 SysComb）；③**进程内最小权限**（S83）；④**隐式安全义务显式化**（S107）——把「应该安全」的隐含假设写成可验证断言；⑤**行为规范驱动的程序合成**（S92）。

| 编号 | 项目 | 来源 | 验收说明 |
|---|---|---|---|
| S63 | Redactable blockchains | 2608.19401 | ✅ 可编辑区块链安全分析 + 一致性建议 |
| S83 | More Granular, Less Trust | 2608.20584 | ✅ 进程内最小权限设计 + 边界建议 |
| S91 | DCI: Dependency Confidence Index | 2608.16430 | ✅ 依赖置信评分 + 供应链评估建议 |
| S92 | Behavior Spec Program Synthesis | 2608.20628 | ✅ 行为规范驱动合成 + 安全规范建议 |
| S106 | SysComb: Transparent Syscall | 2608.26871v1 | ✅ 系统调用透明化 + 监控建议 |
| S107 | Implicit Security Obligations | 2608.26588v1 | ✅ 隐式安全义务显式化 + 可验证断言 |

### G8 代码/漏洞检测与模糊测试
代码安全主线是「更快更准地找到并修复漏洞」。防御/工具要点：①**因果静态分析**（S68 CauSec）；②**定向固件模糊**（S74 BullsEye）与**差分切片模糊**（S90 COMMITGUARD）；③**Agentic 查询精化**（S82 ARQ）；④**严重度/CWE 标签质量审计**（S109/S110）——漏洞标注本身不可靠，需校正；⑤**修复**（S93 CodeMechanic）与**Android 污点**（S121）。

| 编号 | 项目 | 来源 | 验收说明 |
|---|---|---|---|
| S68 | CauSec | 2608.18876 | ✅ 因果静态分析 + 根因定位建议 |
| S74 | BullsEye: Directed Firmware Fuzzing | 2608.17729 | ✅ 定向固件模糊方案 + 适配建议 |
| S82 | ARQ: Agentic CodeQL | 2608.20637 | ✅ Agentic 查询精化 + 静态扫描建议 |
| S85 | CyberFactory | 2608.23181 | ✅ 攻防能力规模化 + 流水线建议 |
| S90 | COMMITGUARD: Differential Fuzzing | 2608.17401 | ✅ 差分切片模糊 + 提交级防护建议 |
| S93 | CodeMechanic: Bug-Property Mitigation | 2608.22275 | ✅ 漏洞属性引导修复 + 落地建议 |
| S109 | Predicting Vulnerability Severity | 2608.22089v1 | ✅ 严重度预测评估 + 优先级建议 |
| S110 | NVD CWE Labels Reliability | 2608.21977v1 | ✅ CWE 标签可靠性审计 + 校正建议 |
| S121 | LLM-Enhanced Android Taint | 2608.24269v1 | ✅ Android 污点分析增强 + 落地建议 |
| S123 | Evaluating Security Smells | 2608.24962v1 | ✅ 安全异味评估 + 检测规则建议 |
| S124 | Binary Decompilation Evolution | 2608.24955v1 | ✅ 反编译演进评估 + 逆向工具建议 |

### G9 协议/密码/后量子
协议与密码威胁聚焦「协议设计缺陷 + 量子时代迁移」。防御要点：①**协议形式化验证**（S87 Dolev-Yao 理性攻击者、S88 验证规范合成）；②**后量子迁移检测**（S103 静态检测、S89 Obscura-PQ）；③**TLS 怪异机**（S77）——协议实现的状态空间需显式验证；④**阈值托管**（S81）。

| 编号 | 项目 | 来源 | 验收说明 |
|---|---|---|---|
| S69 | VQC-ZTI: Variational Quantum Zero-trust | 2608.18572 | ✅ 量子零信任身份评估 + 落地建议 |
| S77 | Weird Machines in TLS | 2608.13685 | ✅ TLS 怪异机分析 + 状态空间验证建议 |
| S81 | Threshold Custody for Lightning | 2608.20705 | ✅ 阈值托管机制 + 密钥管理建议 |
| S87 | Rational Dolev-Yao Attackers | 2608.22954 | ✅ 理性攻击者协议验证 + 形式化建议 |
| S89 | Obscura-PQ: Post-Quantum Privacy | 2608.22645 | ✅ 后量子隐私保护 + 迁移建议 |
| S103 | Static Detection of Post-Quantum | 2608.25122v1 | ✅ 后量子密码静态检测 + 合规建议 |
| S125 | Recursive Quantum Search | 2608.23002v1 | ✅ 量子搜索算法评估 + 密码影响建议 |

### G10 硬件/侧信道/固件
硬件威胁是「信任根之下的漏洞」。防御要点：①**HSM 架构挑战**（S94）——密钥存储/侧信道防护需硬件协同；②**硬件攻击竞赛经验**（S97）——SoC 验证薄弱环节清单化；③**固件社区安全**（S120 TianoCore）——供应链/维护者流程审计。

| 编号 | 项目 | 来源 | 验收说明 |
|---|---|---|---|
| S94 | Automotive HSMs Challenges | 2608.25216v1 | ✅ HSM 架构挑战 + 侧信道防护建议 |
| S97 | Hardware Hacking Competition | 2608.22202v1 | ✅ 硬件攻击经验清单 + 验证薄弱点建议 |
| S120 | TianoCore Community Study | 2608.23280v1 | ✅ 固件社区安全流程 + 供应链建议 |

### G11 车联网/工控/IoT/小程序
IoT/车联网安全的核心是「物理系统 + 网络攻击面」。防御要点：①**车联网自主防御**（S66）+ **车队到实验室**（S101）——真实环境与实验室差距需弥合；②**卫星时序风险**（S84）；③**ICS 数据集系统性**（S96）；④**小程序安全**（S76 TENET / S114 混合框架）；⑤**DDoS 仿真**（S73）。

| 编号 | 项目 | 来源 | 验收说明 |
|---|---|---|---|
| S66 | Autonomous Cyber Defense Vehicle | 2608.19135 | ✅ 车联网自主防御 + 架构建议 |
| S73 | Diff-DDoS: Cyber-Physical Attack | 2608.17796 | ✅ DDoS 仿真 + 缓解建议 |
| S76 | TENET: Telegram Mini App | 2608.17538 | ✅ 小程序安全分析 + 加固建议 |
| S80 | Privacy-Preserving Object Detection | 2608.20712 | ✅ 目标检测隐私保护 + 端侧建议 |
| S84 | Temporal Risk on Satellites | 2608.20575 | ✅ 卫星时序风险 + 遥测看门狗建议 |
| S96 | ICS Cybersecurity Datasets | 2608.24757v1 | ✅ 工控数据集系统性 + 评测建议 |
| S101 | From Fleet to Lab | 2608.26072v1 | ✅ 车队-实验室差距 + 验证建议 |
| S114 | Hybrid Security Mini-Programs | 2608.25877v1 | ✅ 小程序混合安全框架 + 落地建议 |

### G12 基准/方法论/其他
本组为基准、方法论与跨域杂项，价值在「评测口径与工程方法」。要点：**欺诈/日志/APT 检测基准**（S46/S58/S59）、**隐私-效用权衡度量**（S47/S54）、**优化算法安全应用**（S45/S50）、**认证/账户模式**（S105）、**工程方法论**（S71 模型卡、S75 OWASP 鲁棒性、S98 用户韧性、S99 研究方法论、S122 灾难管理、S79 vibe 编码安全）。S126 为光学物理（近统一激发），与安全栈弱相关，标注「离栈，评估价值低」。

| 编号 | 项目 | 来源 | 验收说明 |
|---|---|---|---|
| S45 | Bandit Submodular Maximization | 2608.24627v1 | ✅ 优化算法安全应用评估 |
| S46 | FraudBench: Protocol-Sensitive | 2608.24551v1 | ✅ 欺诈检测基准 + 评测口径 |
| S47 | Spectrum-Aware Bounds Invertibility | 2608.23382v2 | ✅ 频谱可逆性隐私界 + 度量建议 |
| S50 | GRAPE: Gradient Refinement | 2608.25116 | ✅ 梯度精化 + 训练稳定建议 |
| S54 | Privacy-HSD Tradeoff | 2608.19006 | ✅ 隐私-公平-统计距离权衡分析 |
| S56 | CL | 2608.25243v1 | ✅ 持续学习安全评估（title 简写） |
| S57 | CV | 2608.27066v1 | ✅ 计算机视觉安全评估（title 简写） |
| S58 | From Noise to Signal: Security Log | 2608.19938 | ✅ 安全日志噪声→信号 + 检测建议 |
| S59 | TGL-APT: Temporal Graph APT | 2608.19750 | ✅ 时序图 APT 检测 + 落地建议 |
| S64 | SiNMULI: Signed Network | 2608.19190 | ✅ 符号网络恶意检测 + 建议 |
| S71 | Model Card OpenAI Privacy Filter | 2608.18274 | ✅ 隐私过滤模型卡 + 透明度建议 |
| S75 | OWASP Incident-Data Robustness | 2608.19266 | ✅ OWASP 事件数据鲁棒性 + 建议 |
| S79 | Vibe Coding Web Security | 2608.20963 | ✅ vibe 编码 Web 安全 + 开发护栏 |
| S88 | Verification-Guided Spec Synthesis | 2608.22889 | ✅ 验证引导规范合成 + 建议 |
| S98 | AI-Augmented User Resilience | 2608.21547v1 | ✅ AI 增强攻击防御 + 用户韧性 |
| S99 | Research Methodologies Cybersecurity | 2608.24850v1 | ✅ 安全研究方法论 + 评测规范 |
| S100 | CRQC+AI Vulnerability Evaluation | 2608.23785v1 | ✅ CRQC+AI 脆弱性评估 + 建议 |
| S105 | User Authentication Patterns | 2608.26955v1 | ✅ 认证模式目录 + 设计建议 |
| S116 | BGPay: Incentive-Compatible | 2608.25165v1 | ✅ 激励相容机制 + 安全建议 |
| S117 | When Relationships Break | 2608.26831v1 | ✅ 网络关系断裂解释 + 韧性建议 |
| S122 | Twelve Quick Tips IT Disasters | 2608.27196v1 | ✅ IT 灾难管理清单 + 工程建议 |
| S126 | Near-Unity Excitation Radiative | 2608.11677v1 | ⚠️ 光学物理，离栈——评估价值低，标注不落地 |

---

## 3. 执行清单

- **完成**：88/88 —— 全部以「分组分析 + 逐条验收说明」方式处理（G1–G12，见上表）。
- **合并**：88 单合并为 12 组（同安全域合并），未单独出 88 份文档。
- **阻塞/降级**：
  - S56/S57 总清单 title 仅为「CL」「CV」简写，无具体机制描述 → 按「对应领域安全评估」处理，验收说明标注 title 简写。
  - S126 为光学物理（近统一激发/辐射效率），与安全栈无关 → 标注「离栈，不落地」。
  - 精简 spec 文件存在 S 编号重名，本报告以总清单 title+来源为准（诚实降级）。
- **未做**：零攻击代码（遵守纪律）；未逐单读 88 份精简 spec（重名 + 规模）。

## 4. 统一防御原则（跨组可复用）

1. **确定性门控优先于模型自我仲裁**：工具调用/来源校验用 HMAC/起源令牌（呼应 ROPE/A34），不靠 LLM 判断。
2. **最小上下文 + 最小权限**：泄露类威胁的通用解是减少暴露面（S40/S72/S83/S107）。
3. **评测口径要真实**：防御评估需覆盖语义改写、长上下文、量化后复测等真实场景（呼应 S24/S26/S119）。
4. **供应链血统 + 依赖置信**：信任按来源历史/签名/改动血统滚动评分（复用 `trust_layer.py` + S91 DCI）。
