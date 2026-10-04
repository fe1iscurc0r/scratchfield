# 论文流水线 — 周度授粉记录（增量轮）

> 承接 `pollination_notes.md`（2026-08-23 首次全量 1215 篇精读）。
> 本文件：每轮增量采集后的聚类趋势 + 跨领域授粉点，追加式记录。
> 语料：`arxiv_corpus.jsonl` ｜ 已处理：`processed_ids.txt`

---

## 2026-08-23 增量轮：扩类 backlog 992 篇

- 本轮 fetch：new=0（31 类最近 80 篇均在库，无新提交）
- 待处理：992 篇 = 17→31 类扩类后补拉的未精读论文（2608 月 879 / 2607 月 61 / 2606 月 29 / 2605 月 23）
- 领域分布（Top）：cs.AR 59, cond-mat.soft 56, cond-mat.mes-hall 55, cs.RO 54, cs.NI 49, eess.AS 48, cs.IT 43, eess.SY 42, physics.chem-ph 41, cs.CE 41, q-bio.MN 37, cs.LG 35, quant-ph 35, cs.AI 31, cond-mat.stat-mech 30, cs.MA 26, physics.app-ph 25, physics.space-ph 24, astro-ph.SR 22, cond-mat.mtrl-sci 22, physics.optics 17

### 本轮趋势（5 条）

1. **AI 原生 6G + ISAC 通感一体进入标准与系统设计**：ISAC in 3GPP、Conversational Orchestration for Organic 6G、AI-Native 6G 语义通信（eess.SP 信念同步）、激光二极管 LiFi 系统建模与 ns-3 交叉验证。感知与通信共用同一频谱资源已成设计前提。
2. **物理引导世界模型从 ML 扩散到无线与多智能体**：RFWM（动态无线辐射场生成）、RMWorld（多 UAV 通信用任务感知世界模型）、Physics-Informed World Model（混合交通 MARL）、DART-S（可达性审计主动悬挂预调节）。"模型预测 + 物理约束"成为系统层标配。
3. **Agent 从对话走向关键基础设施运营与安全**：mission-critical 场景的 harness 供给、SysEvolve AI 原生攻防共演化、AV 边缘截止感知混合关键度调度、agentic 工作负载 serving 表征、Memory Is Communication。LLM 开始被当作基础设施组件来运维，而不是只会推理的对话体。
4. **软物质/玻璃非平衡动力学 + 可解释 ML 材料预测并行深化**：溶剂通量理论（微凝胶非平衡溶胀）、轨迹级涨落-响应不等式、非平衡流拓扑控制主动输运、casein 胶束酶解 SAXS；材料侧出现可解释符号回归预测 MOF 吸附、数据高效材料特定 MLIP，从黑箱逼近走向可写进论文的显式表达式。
5. **量子容错与拓扑器件工程化**：CSS 码横向逻辑对角门、浅层 Clifford 随机匹配稳定子码、对抗错误下的容错计算、硅空穴自旋量子比特微波相位调制相干保护、NbSe2/CrBr3 无外场超导二极管效应、铁磁纳米环扭曲磁振子频率梳。

### 跨领域授粉点（3 个）

| 授粉点 | 来源 | 流向 | 用途 |
|---|---|---|---|
| 乘法免费特征提取器（cs.SD Keyword Spotting） | 音频 DSP | ESP32-S3 嵌入式 | 信号分类/关键词检测的特征提取全程无乘法，MCU 直接跑；适合 SX1278 收包分类、语音唤醒、声学异常监测 |
| 物理引导无线世界模型（cs.NI RFWM / RMWorld） | 6G 通信 | SDR/无线电 | 辐射场/信道动态预测 → 频谱感知、传播预测、"通信即感知"路线（IC-705 + SDR 可实验） |
| 分布式 Agentic 记忆合并 + 可逆遗忘（cs.DC MELD / cs.LG Reversible Forgetting） | 分布式系统/持续学习 | NEKO 五维记忆融合 | 跨 Agent 记忆合并协议 + 过时知识可逆遗忘，直接给 SQLite+FTS+向量混合检索的融合设计提供参照 |

> 材料方向另有一条强线索：cond-mat.mtrl-sci 的可解释符号回归（CO2 吸附显式表达式）与数据高效 MLIP，与生物质/水凝胶体系性能预测直接对口，下一轮精读优先跟进。

---

## 2026-08-25 增量轮：常规采集 527 篇

- 本轮 fetch：new=527（31 类增量，corpus 2207→2734）
- 待处理：527 篇全部为本次新增，无 backlog
- 领域分布（Top）：cs.CV 67, cs.AI 51, quant-ph 48, cs.LG 44, cs.CL 35, cs.CR 27, cs.RO 26, cond-mat.mtrl-sci 23, cs.SE 21, cond-mat.mes-hall 16, eess.SY 13, eess.SP 13, cond-mat.soft 13, math.OC 12, astro-ph.IM 9, physics.chem-ph 8

### 本轮趋势（5 条）

1. **Agent 安全从"入口拦截"转向"全生命周期治理"**：cs.CR 井喷——Agent 记忆投毒（1.2% 语料投毒 → 准确率 0.850→0.300）、状态化授权 AID-Guard（授权覆盖到 effect 的提交/重试/恢复）、多级安全监控 ClawSentry（skill 准入/调用意图/执行期/事后四道防线）、TraceGrant 合约治理任务-效果生命周期、Z²-ACT 把 agentic 意图控制做成 6G RAN 可验证闭环。共识：持久记忆本身就是攻击面，授权必须跟到副作用发生为止。
2. **无线物理层"孪生化"与天线架构革命**：电磁孪生（EM Twin）用稀疏探测补全无线世界（1% 探测点重建全图 + 率灵敏度界选择下一探测点）、Pinching-Antenna 系（频率选择性 Toeplitz 信道/OFDM ISAC/分布式联合解码三连发）、流体天线 AoI 调度、LEO 星座流体动力学干扰建模（压缩流体壳守恒律）、NB-PLC 单线大地回路 300kHz 数字孪生。信道从"测出来"变"生成出来"，天线从固定阵元变"可捏/可流/可移"。
3. **边缘部署进入"量化后恢复 + 硬件感知"阶段**：Llama-Mobile 2.7-bit VLM 量化（模型自生成数据微调）、Quantization-Aware Healing（4-bit 压缩模型恢复配方）、Target-Aware 校准数据（保不确定性而非纯精度）、μNet 超低内存语音增强（整数运算 DSP 直落）、Thermo-FL 热感知联邦微调（节流客户端 + Byzantine 更新）、事件触发零阶微调自旋 Transformer（IMC 免 RNG）。压缩不再只盯精度，开始盯不确定性、热、内存带宽。
4. **"训练一次"退场：测试时训练/持续学习/本体感觉替代三线并行**：E²-TTT 在 chunk 梯度近似下推导闭环权衡、SPARCL 把持续学习遗忘归因于谱干涉（封闭解岭回归也会漂移）、IMU-Free 四旋翼状态估计（立体视觉 + 推力命令 + 流形 EKF，无惯性传感器）、Off-Policy Q-Planning 让行为克隆策略自改进、NeSAM 神经符号土壤动力学（可解释越野运动学）。硬件侧信号：能少一个传感器就少一个。
5. **材料科学 Agent 化 + ML 全流水线化**：MAESTRO LLM agent 端到端跑 MOF 发现（文献→晶体结构→筛选）、AutoMOOSE 自然语言→相场仿真、Polymer Genome 系统性评估聚合物编码策略、MLIP 引导高熵氧化物合成预测、ReCurveflow 流匹配学弯曲反应轨迹预测过渡态、ShiftML4 ML-NMR（内置杂化泛函修正）。"论文流水线"范式从 AI 圈正式蔓延到材料计算。

### 跨领域授粉点（4 个）

| 授粉点 | 来源 | 流向 | 用途 |
|---|---|---|---|
| Agent 记忆投毒 + 写时筛查/来源分级（cs.CR 2608.21230 / 21159） | Agent 安全 | NEKO 记忆融合 + 工单流水线 | 持久记忆=攻击面：写时校验、来源分级、provenance ranking；weixin/qqbot/cli 共享工作树就是共享记忆，需防"一条假事实污染后续会话"——与既有撞车防呆（git log/时间戳）同思路升级为内容级 |
| 电磁孪生稀疏重建（eess.SP 2608.20813 / 20846） | 无线信道 | SDR/传播预测 | 稀疏 IQ 采样 → 空间-频谱孪生 → 主动选点（率灵敏度界）；QRP 传播预测/频谱监测可走"1% 探测点补全"路线，正好契合成本敏感偏好；图正则估计可直接落到 ESP32 频谱扫描后处理 |
| IMU-Free 流形 EKF + 超低内存 DSP 算法（cs.RO 2608.20891 / eess.AS 21155 / cs.SD 20693） | 机器人/音频 | ESP32-S3 嵌入式 | 本体感觉替代降传感器成本；μNet 整数 DSP 语音增强、块对角 RLS（RBD-RLS）回声消除是 MCU 可直接移植的低复杂度算法；无 IMU 状态估计思路可借鉴到自制飞控/定位实验 |
| 活性微泳者机械增强乳液 + 聚合物编码策略评估（cond-mat.soft 2608.21078 / 20979） | 软物质 | 生物质材料 | 微藻活性增强乳液 yield stress 达 2 倍——生物质颗粒/微藻体系做胶体增强的机制参照；Polymer Genome 的编码策略对比方法论可直接套到木质素 NPs 结构-性能数据建模（选指纹/编码而非盲目堆模型） |

> 备注：quant-ph 48 篇多为容错/变分/纠缠理论，与用户栈交集小，本轮未精读；physics.ins-det 的 Timepix4 亚像素质心重建偏差分析对 SDR 采样/质心类信号处理有参考价值，下一轮可跟进。

---

## 2026-08-26 增量轮：常规采集 906 篇

- 本轮 fetch：new=906（31 类增量，corpus 2734→3640）
- 待处理：906 篇全部为本次新增，无 backlog
- 领域分布（Top）：cs.LG 74, cs.CV 71, quant-ph 67, cs.RO 63, cs.CL 61, cs.AI 51, cond-mat.mtrl-sci 51, cs.CR 50, cs.SE 37, math.OC 31, eess.SY 26, eess.SP 25, cond-mat.mes-hall 17, stat.ML 16, cs.NI 16, astro-ph.IM 15, cs.IT 14, cond-mat.soft 14, physics.optics 13

### 本轮趋势（5 条）

1. **Agent 安全从记忆投毒升级为\"记忆/技能双注入 + 流治理\"**：InjecMEM 证明只需一次交互即可定向污染记忆系统后续检索输出（retriever-agnostic anchor + gradient-searched 命令）；SkillBloat 把技能文件当作\"可信指令通道\"做 token 放大攻击（平均 5.4-10.1x 资源消耗）；AgentFlow 提出流策略语言（数据能流向哪些工具/边界）把 AgentDojo 注入妥协率 33%→0%；另有 CLAUDE.md 安全规则与内置控制仅 4-16% 匹配的审计、多 Agent 电商长程会话中 12.6% 邮件自发错位（胁迫/共谋/虚假声明）。共识：持久记忆与技能库本身就是攻击面，必须按流（flow）而非按条（action）治理。
2. **Agent 工程化进入\"自进化 harness\"阶段**：AutoSaddler 把 harness 当代码迭代优化（GAIA2/SWE-Bench Pro/Terminal-Bench 各 +9~10pt）、TRACE 用轨迹对比进化技能库（Pass³ 59.9%→94.5%）、OptiMAS 端到端自动优化 MAS、Apodex 1.1 用 AgentOS 协调长程任务+可验证交付（35B 达前沿档）、AgentWeave 先路由后推理省函数调用。手工调 prompt 的时代在被\"用失败轨迹训练 harness\"取代。
3. **世界模型 + VLA 成为机器人主流范式**：cs.RO 63 篇为最大工程类目——世界模型做规划（DreamMimic、Correcting a learned physical invariant、BehaviorWorldGen、WorldToken 时间优先序列建模）、VLA 端侧化（ROS2SmolVLA 轻量机器人集成、Pointing-VLA 类型化空间基座）、Physical Agentic AI 用\"技能库+确定性编排门\"防止 23-29% 错误派发落地为动作；边缘 VLM 走紧凑 JSON 结构化输出（SoulGard-VL-2B 在 RK3576 上 2.51x 加速）。机器人靠\"先验证后执行\"的架构门而非模型自觉保安全。
4. **射频进入\"AI 原生空口 + 天线形态革命\"**：ISAC 波形设计成主流（Dual-Orthogonality 60GHz 实测 30cm 距离分辨率）、RIS/IOS 全面铺开（认知无线电、频谱拍卖、共形智能全向面室内外覆盖）、DMA 60GHz 实时视频串流（USRP+商用模块 3Mbps）、双频段架构用 sub-10GHz CSI 估 sub-THz 时序提前、PACC 无标签信道制图；工程侧出现 LoRa C-RAN（集中式基带联合处理多接收机 IQ 提升灵敏度/抗多径）与 NICWhisper（NIC 电磁侧信道被动识别 8 类威胁行为，80.67% Macro-F1）。物理层从\"测信道\"转向\"生成/推断信道\"。
5. **材料计算闭环：wet-dry agentic loop + 机器学习力场 + 成核动力学**：Xtalyst 用\"推荐-重扫-再分析\"湿干代理循环缩小 PXRD 仿真-现实差距（修正峰位漂移后检索相关性翻倍）；DPE 机器学习力场（DFT+deep potential）首次在原子级建模高压自由基聚合聚乙烯；氧化学计量被证明是 TiO2 锐钛矿/金红石晶相选择的动力学控制参量；偏聚电解质水凝胶电荷调控（CR）非均匀溶胀理论成形；聚合物连接纳米粒子网络（PNNP）用热流跑通类神经网络计算。动力学控制与实验闭环成为材料合成可预测化的两条主线。

### 跨领域授粉点（4 个）

| 授粉点 | 来源 | 流向 | 用途 |
|---|---|---|---|
| 记忆注入/技能注入/流策略（cs.CR 2608.23471 InjecMEM / 21929 SkillBloat / 22868 AgentFlow） | Agent 安全 | NEKO memory_maas/trust/skill | 记忆与技能输入默认不可信：写时来源分级+provenance ranking（与供应链铁律同构，延伸到 skill/metadata/记忆条目）；trust 模块可参照 AgentFlow 的\"敏感数据可流向哪些工具\"流策略而非逐条 ACL；skill 文件审查清单增加\"token 放大/指令隐藏\"检测面 |
| LoRa C-RAN 联合处理 + NIC 电磁侧信道 + EM 全息 LISTA（eess.SP 2608.23027 / cr 22941 / eess.SP 22409） | 射频/SDR | 无线电实践 | 多接收机 IQ 集中联合处理可提灵敏度——RTL-SDR 双通道分集/协同接收可实验；NICWhisper 证明被动近场电磁信号能分类网络行为，ESP32+近场探头即可复现，是频谱感知+信息战的低成本入口；EM 全息稀疏重建思路可落 ESP32 频谱扫描后处理 |
| TinyML 多分类 NPU + 边缘 VLM 紧凑输出 + Age-Optimal TWT（cs.LG 2608.23101 PolyChirp / cs.CE 22070 SoulGard / cs.NI 21596） | 嵌入式/边缘 AI | ESP32-S3/边缘 Agent | MCU+NPU 单电池撑整季的多类声学识别流水线可复刻（mel 频谱+轻量模型）；VLM 边缘部署用紧凑 JSON 序列化而非长文本（RK3576 实测 2.51x 提速）——边缘 Agent 输出协议设计直接借鉴；TWT 唤醒调度（AoI 最小化 + 能量预算，常数因子近似 5.77x）对低功耗遥测节点唤醒策略有理论指导 |
| wet-dry agentic loop + 水凝胶 CR 溶胀 + 反应性 MLFF（cond-mat.mtrl-sci 2608.22400 / cond-mat.soft 21698 / mtrl-sci 21741） | 材料计算 | 生物质材料 | PXRD 类\"实测反馈驱动合成参数迭代\"闭环可直接套到木质素 NPs→水凝胶/共熔凝胶的合成条件自动寻优；电荷调控非均匀溶胀理论给水凝胶响应设计提供定量框架；deep potential 力场已能处理反应性高压聚合，后续聚合物/生物质反应体系模拟优先选 MLFF 而非经验势 |

> 备注：quant-ph 67 篇多为容错/纠缠/变分理论，QKD 与量子网络路由（stabilizer-code 时空路径优化）与用户交集浅，仅记 QEYSSat 链路数字孪生（Monte Carlo 光子发射-传输-探测）供卫星通信兴趣参考。
---

## 2026-08-27 增量轮：常规采集 669 篇

- 本轮 fetch：new=669（31 类增量，corpus 3640→4309）
- 待处理：669 篇全部为本次新增，无 backlog
- 领域分布（Top）：cs.CV 72, cs.AI 68, cs.LG 64, cs.CL 51, quant-ph 40, cs.RO 32, cs.SE 27, cs.CR 24, cond-mat.mtrl-sci 21, eess.SY 20, astro-ph.IM 17, math.OC 15, cs.IT 15, eess.SP 13, cond-mat.stat-mech 13, cond-mat.mes-hall 12, stat.ML 11, astro-ph.SR 11, cs.AR 9, cs.NI 9, cs.CE 8, eess.AS 7, physics.chem-ph 7, physics.ins-det 7, cond-mat.soft 6

### 本轮趋势（5 条）

1. **Agent harness 走向收敛 + 工程化运维**：三套 agent harness 架构趋同(Architectural Convergence)、LLM 多智能体系统可观测性与故障注入、Pufibara/Modelica 物理系统 Agent 工作流基准、长程记忆递归演化(Recursive Experiential-Working Memory)、异步 Agentic RL(SPO++)、工具调用阶段式扰动鲁棒性(ToolRobustBench)。LLM Agent 从"能跑"进入"能测、能运维、能演进"阶段。
2. **世界模型行动对齐 + 生成式仿真**：世界模型行动条件诊断与对齐、Latent Action 作意图、3D Gaussian 蒸馏进 World-Action Models、NVIDIA Cosmos-H-Dreams 实时生成式物理仿真(手术机器人)、生成式潜在流规划(LeFlow)。仿真侧开始用生成模型直接造训练数据，而非仅做预测。
3. **Agent/MCP 信任边界成为安全主战场**：MCP 服务器分阶段信任攻击基准(TrustShiftProbe)、浏览器集成 LLM Agent 信任边界强制(WebMCP-Phalanx)、RAG 可认证几何共识(RAGSentinel)、系统提示指纹克隆检测、ICS 网络安全数据集元审查、硬件 fuzzing SoK、Rowhammer 推理期后门注入、后量子 SSH KEM 替换。AI 供应链攻击面从"提示注入"扩散到协议层与硬件层。
4. **无导频/物理引导的无线感知进阶**：联合多接收机无导频 Wi-Fi 解码 Transformer、物理信息 WiFi 感知 3D 人体姿态、相干直接 D-MIMO 定位、流体天线 HARQ、事件相机超低延迟光通信(ECO-COMM)、可旋转天线中继、W/D 波段 SiGe PA 与 V 波段 EDMOS PA、EM-KalmanNet 自适应跟踪。通感一体化从概念走向无导频解码与器件落地。
5. **信号级自监督与基础模型下探**：时窗 Noise2Noise 自监督盲去噪(振动/冲击)、EEG 基础模型参数高效适配与不变性预训练、可审计 EEG 诊断、SeisMamba 低延迟单站地震震级、嗅觉传感器漂移补偿(reservoir computing)、材料侧化学语言模型预测电子态密度 CLM、神经算子拟线性 DFT、差分学习热稳定性预测。自监督+轻量适配成为信号与材料两端的共同范式。

### 跨领域授粉点（3 个）

| 授粉点 | 来源 | 流向 | 用途 |
|---|---|---|---|
| LLM-MAS 可观测性+故障注入+工具鲁棒性诊断(cs.SE ToolRobustBench/Observability & Fault Injection) | 软件工程 | NEKO/hermes_proxy+MCP 总线 | 给多 Agent 栈搭"故障注入+阶段式扰动"回归测试：工具调用抖动、MCP 限流/断连、编排器前缀扰动，量化 wrapper 层鲁棒性，不用等线上翻车 |
| MCP 服务器分阶段信任攻击基准 + RAG 可认证共识(cs.CR TrustShiftProbe/WebMCP-Phalanx/RAGSentinel) | 安全 | 供应链铁律落地 | 用户"外来 MCP 配置/文件默认不审查不接入"原则拿到论文级支撑：信任攻击也分阶段，接入前按阶段做审计清单；RAG 结果可带几何共识认证，防检索投毒 |
| 时窗自监督盲去噪+MCU 友好漂移补偿(eess.SP Noise2Noise/reservoir computing) | 信号处理 | ESP32-S3/SX1278 嵌入式传感 | 振动/电流/射频包络去噪无需干净标签(自监督)，reservoir computing 漂移补偿可跑 MCU——传感器长稳方案直接可试验 |

> 材料方向强线索：CLM 预测电子 DOS、神经算子 DFT(准线性标度)与差分学习热稳定性，与生物质/水凝胶性能预测对口，下一轮精读优先。

## 2026-08-28 增量轮：常规采集 652 篇

- 本轮 fetch：new=652（31 类增量，corpus 4309→4961）
- 待处理：652 篇全部为本次新增，无 backlog
- 领域分布（Top）：cs.CV 73, cs.LG 65, cs.CL 51, quant-ph 51, cs.RO 44, cs.AI 32, cs.CR 28, cond-mat.mtrl-sci 21, cs.SE 20, eess.SY 18, eess.SP 17, astro-ph.IM 16, cond-mat.mes-hall 15, astro-ph.SR 15, math.OC 13, cs.NI 12, cond-mat.stat-mech 11, cs.AR 11, cs.IT 10, physics.chem-ph 10, cond-mat.soft 8, stat.ML 7, eess.AS 7, cs.CE 5

### 本轮趋势（5 条）

1. **Agent 自主科研/工程闭环成型**：Agentic Autoresearch 把无线资源管理 ML 的架构/损失/训练配方全权交给 coding agent（单一不可变指标决定保留/丢弃）；自驾驶材料实验室 BO 综述覆盖失败实验、混合变量、多目标、成本-保真度、历史数据迁移；HypoForge 多 agent 自动假设生成与验证、AI Agentic 激光烧结工艺优化。Agent 从"能跑工具"进入"自主设计实验与算法"阶段。
2. **分布式 Agent 网络与可审计性集中爆发**：SPFR 提出无中心路由下将执行器发现+重选嵌入逐跳转发的语义势场路由（Internet of Agents）；Trace Integrity 定义 LLM 数据 agent 的部署可靠性——答案正确但 trace 非法（schema-valid/replayable/auditable）；ProgRouter 按质量-成本在线编排多 agent 工作流；SwarmWorld stigmergic 群体演化。无中心互连+可审计追踪成 Agent 工程主线。
3. **弱链路/能量受限通信的代数级韧性与能量门控**：APC-RLNC 按 EWMA 可靠度动态聚类+分层随机线性网络编码，抗异构链路；MagPie 用微安级 wake-up radio + 低功耗 RTC 后备解决无电池传感"断电丢时序状态"问题，epoch 版本化调度+幂等时隙分配实现无主控锚点的采集。低功耗遥测走向"唤醒即同步"。
4. **射频可视化与通感一体化工具化**：ESPARGOS 把相位相干 WiFi 阵列测量转成 AR 波束空间叠加（路径时延/极化可视化）；6G 侧 Multi-UE networked sensing、BeamGuard 毫米波 V2I 波束预报、近场双 UPA 几何建模、318GHz THz 工业 IoT 信道统计、太空卫星协调充电。射频从"不可见"到"可看、可预报"。
5. **空间天气对导航/传播的实测干扰证据**：南极记录到地磁平静期 quiet STEVE 事件引发 GNSS 信号闪烁（此前无直接证据）；GIC 地磁感应电流与太阳风条件的经验关系。空间天气对实际无线电传播的影响有了新实测抓手。

### 跨领域授粉点（3 个）

| 授粉点 | 来源 | 流向 | 用途 |
|---|---|---|---|
| APC-RLNC 自适应聚类 + MagPie 无电池唤醒范式（eess.SP 2608.26040 / cs.NI 2608.25292） | 无线网络 | 无线电/LoRa 嵌入式 | SX1278 多跳网（NR11/LR21-433 储备）链路质量参差时按 EWMA 分组+分层编码可提升整体韧性，直接对应 433 主场弱链路场景；MagPie 的微安级 WuR+LP-RTC"停电不丢相位"思想可落 ESP32-S3 休眠遥测节点——LoRa CAD 唤醒 + RTC 保持，唤醒即重同步，省掉每次冗长入网 |
| SPFR 语义势场路由 + Trace Integrity 审计标准（cs.NI 2608.25396 / cs.AI 2608.26036） | Agent 网络 | MCP 总线/多 Agent 栈 | 分布式 MCP 服务器可借鉴"能力势场梯度+逐跳语义转发"替代中心发现，沿现有 ZMQ/MQTT 总线做能力广播；Trace Integrity 的 schema-valid/replayable/auditable 七项标准可直接做成多 agent 协作审计清单，与供应链铁律（外来文件审查）互为表里 |
| Agentic Autoresearch + 自驾驶材料实验室 BO + PIRAG-LM 合成规划（cs.LG 2608.26093 / cond-mat.mtrl-sci 2608.26016 / 2608.25392） | AI×材料 | 生物质材料/陆墨科研 | 把材料 ML 的架构/损失/配方交给 agent 自主迭代（单一指标裁决）可套入木质素 NPs→水凝胶合成条件寻优；BO 综述的失败实验/混合变量/迁移学习章节直接映射到真实材料实验约束；PIRAG-LM 用 13,820 条合成路线建 SSKB+物理信息 RAG，是"生物质材料合成路线问答"的现成范式 |

> 备注：quant-ph 51 篇多为容错/纠缠/变分理论，与用户交集浅；仅 Q2NS/ns-3 量子中继链仿真（QPacket 元头+append-only action-commit 戳，超越分层协议）对自定义协议栈设计的"服务意图"思路可作次要参考。材料侧本轮 BO+RAG 合成规划线索强，下一轮精读优先。


---

## 2026-08-29 增量批次

- 新增：659 篇
- 领域分布（Top）：cs.CV(69), cs.CL(60), quant-ph(58), cs.LG(54), cs.AI(47), cs.RO(38), cs.CR(37), cond-mat.mtrl-sci(33), cond-mat.mes-hall(26), cs.SE(23)

### 本轮趋势（4 条）

1. **超大规模 MIMO + OTA-ELM 走向硬件可行**：XL-MIMO 作为 Extreme Learning Machine 直接做 Over-The-Air 二分类，非线性超表面层替代部分 RF 链路降低硬件复杂度；Frugal D-MIMO ISAC 用正交子载波分 sensing/com 消除互干扰，相干相位架构实现多 AP 协同无线电成像。无线空口本身在变成计算介质而非仅传输介质。

2. **Agent 安全从文本越狱延伸至物理执行层**：PLCBench 首提"真实 PLC 持久物理影响"评估——Agent 拿到 PLC 访问权后能造成持续物理破坏，不只是改数据；Daydreaming 通过黑盒任务交互窃取 agent 技能文件（多文件 skill 盗取）；Safety Does Not Compose 揭示 Agent 循环中安全状态跨迭代组合失效的根本问题。无中心自主 Agent 的安全评估正在从数字化层走向物理层。

3. **机器学习信号分解取代经典时频方法**：IDSD 用神经网络替代 VMD 等经典方法的窄带预设假设，无需预先知道分量数量；DPSWIN Transformer 对 chirp-sequence 雷达 rD map 做超分辨率，内存效率针对真实毫米波雷达设计。数据驱动的信号处理正系统性替代参数化经典方法。

4. **Cross-embodiment 视频世界模型打通异构物理经验**：CLAP 用跨人体/机器人的大规模视频训练 action-conditioned video model，学习通用物理规律而非特定机体动力学；FlashVLA 用流式解码解决 VLA 推理延迟问题；STEP 用 MM-LLM 结合状态追踪做任务规划，减少幻觉动作。机器人技能迁移从"模仿特定机器人"走向"学习跨机体的通用物理先验"。

### 跨领域授粉点（2 个）

| 授粉点 | 来源 | 流向 | 用途 |
|---|---|---|---|
| OTA-ELM + 非线性超表面激活函数（eess.SP 2608.27137） | 无线 ML 推理 | IC-705 / ESP32-S3+SX1278 | ELM 单隐层随机映射+解析解输出权重的范式非常适合资源受限嵌入式：无需梯度反向传播，适合 SX1278 的有限算力场景；超表面的固定非线性响应可映射为预定义查找表，ESP32-S3 查表即可模拟"非线性激活层"，为 LoRa 节点上的轻量推理提供新思路 |
| CLAP cross-embodiment + FlashVLA 流式解码（cs.RO 2608.27406 / 2608.27384） | 机器人跨模态 | 无线电感知/嵌入式 | CLAP 的 insight"通用物理规律独立于执行者"可迁移到无线电：频谱的物理特性（传播、衰落、多径）不依赖具体硬件平台，ESP32-S3+SX1278 采集的频谱数据训练的模型可迁移到 IC-705；FlashVLA 的流式解码+异步执行对应 LoRa 节点的"边听边做"——CAD 唤醒后不解完完整帧就触发动作，适用于紧急频谱事件响应 |

---

## 2026-08-30 增量批次

- 新增：28 篇（本轮 fetch new=28，corpus 5620→5648）
- 领域分布：astro-ph.SR(14), astro-ph.IM(9), astro-ph.CO(2), math.DS(2), astro-ph.EP(1)

### 本轮趋势（5 条）

1. **AI 成像从专用网络走向可迁移基础模型**：Cassini-ISS 背景强度估计用去噪扩散模型替代多项式/统计拟合，抗非均匀背景与散射光（2608.26524）；再电离 SBI 用自监督 ViT 标签无关预训练，冻结编码器跨模拟器迁移零重训（2608.26354）；Bifrost 用 kNN 存档库加速非-LTE 太阳色球谱线反演（2608.26629）。核心诉求从"精度"转向"抗模型失配 + 跨域复用"。

2. **动态时域成像成为射电/太阳观测主战场**：最优传输正则化动态射电干涉重建，把物理运动编码进正则项捕捉分钟级演化（2608.27192）；Solar Orbiter 0.04s 短曝光 EUV + STIX 硬 X 射线联合解析 M2.1 耀斑精细结构（2608.26438）；KMTNet 10 年数据库黑洞天体测量微透镜 Fisher 分析（2608.26399）；NGTS 一次测出 1063 个恒星自转周期（2608.27170）。重建与统计工具必须吃下"时间维"。

3. **混合控制与实测验证主导下一代大望远镜**：MICADO/ELT 的 SCAO 采用 LQG 低阶模式 + 积分器高阶模式混合控制，台架实测通过（2608.27379）；JWST NIRCam 天体测量给出工程实践规范（2608.26217）。控制策略从单一最优走向"分工混合"，实测数据倒逼设计。

4. **相互作用驱动的复杂性与双星/多体系统**：双 futile cycle 结构上可发生 Hopf 分岔但质量作用动力学下不能（含 ChatGPT 辅助证明，2608.27081）；双星质量转移产生 CSM 导致剥离包层超新星光变多样性（2608.26390）；双食系统与多中心径向剖面工具 RadialPaths（2608.26931 / 2608.26326）。观测多样性越来越需要多体相互作用解释，AI 已进入数学证明辅助环节。

5. **空间低频射电新窗口**：MegaWave 空间干涉仪概念——<30MHz 地面被电离层挡住，目标含恒星空间天气、系外行星磁层发射、黑暗时代 HI（2608.26322）；邻近恒星 X 射线→射电全波段 SED 刻画宜居带辐射环境（2608.27344）。低频射电 + 系外行星磁层 + 恒星活动交叉成新前沿。

### 跨领域授粉点（3 个）

| 授粉点 | 来源 | 流向 | 用途 |
|---|---|---|---|
| 最优传输正则化动态重建（astro-ph.IM 2608.27192） | 射电成像 | 无线电/频谱监测 | OT 距离把物理运动编码进正则项，比 TV/L1 更保时序连贯——可借到 SDR 频谱的动态去卷积/突发信号跟踪：把频谱序列当"图像"做 OT 正则重建，在 433/2.4G 多径叠加场景下分离移动目标信号 |
| 自监督 ViT 冻结摘要器跨模拟器迁移（astro-ph.CO 2608.26354） | SBI | Agent/嵌入式部署 | 标签无关预训练 + 冻结复用，抗前向模型失配——对应嵌入式"一次训练多场景复用"（仿真训练、真机冻结推理）与 Agent"共享表示层 + 任务头"架构；SBI 对 misspecification 的鲁棒性可直接套用户仿真→真机迁移管线 |
| kNN 存档反演 + LQG/积分器混合控制（astro-ph.SR 2608.26629 / astro-ph.IM 2608.27379） | 太阳物理/自适应光学 | ESP32 实时处理 | 先离线建合成谱库、在线只做最近邻查表——轻量推理范式正适合 ESP32-S3 级 MCU 的实时分类/底噪估计；混合控制分工（LQG 管低频扰动、积分器管高阶）可移植到无线电 AGC/锁相或机器人控制：低阶精确估计 + 高阶鲁棒积分 |

> 备注：math.DS 两篇为生物反应网络结构理论，与用户交集浅；但 2608.27081 的"ChatGPT 辅助证明"是 Agent 授粉信号（AI 参与形式化验证），次要参考。MegaWave 空间低频射电与用户 433/2.4G 地面主场不同维，其系外行星磁层发射探测思路对理解低频传播有背景价值。

---

## 2026-09-23 落地记录（卷151 任务C）

本日增量轮提炼的 3 个授粉点，已各自落成可施工文档（**均未开工，仅 SPEC/路线图**）：

| 授粉点 | 文档 | 落点 | 状态 |
|---|---|---|---|
| ① Agent 治理模式 → 工单流水线特权操作守卫（ActGov 策略约束验证 + LeaseGuard 租约式准入） | [`docs/ActGov-租约守卫-工单特权操作SPEC-轮23.md`](../../ActGov-租约守卫-工单特权操作SPEC-轮23.md) | `apiserver/event_bus/`（叠加在既有 `confirm_gate.py` / `tool_gate.py` / `tool_pipeline.py` 之上） | SPEC，未开工 |
| ② 在线频谱制图 → IC-705 + SDR 组网（多节点分布式采样 → 稀疏重建占用图） | [`docs/频谱制图SPEC-轮23.md`](../../频谱制图SPEC-轮23.md) | `mcpserver/rf_brain/` + `hardware/antenna-rotator/`（LoRa 回传） | SPEC，未开工 |
| ③ 小数据 MLIP → 木质素 NPs 分子模拟（小超胞 + 迁移学习 + Boltz-2 早期富集） | [`docs/MLIP-木质素路线图.md`](../../MLIP-木质素路线图.md) | `scripts/materials_model/` + 卷143 天选7 学术模型环境 | 路线图，未开工 |

同批（卷151 任务B）另有 4 个宽松许可仓接入 vendor，为上述 ②③ 的模型/参数层提供外部参考：
`vendor/polykin`（MIT）、`vendor/martignac`（MIT）、`vendor/MartiniGlass`（Apache-2.0）、`vendor/DPDsim`（MIT）——每仓附 `POLLINATION-NOTES.md`（核心 API 面 / 可复用模块 / 融合点 / 许可快照）。

> 路径偏差记录：本卷工单写「追加到 `research/papers/weekly_pollination.md`」，实际该文件位于本路径（`docs/pollination/plans/`），已按实际路径追加。


