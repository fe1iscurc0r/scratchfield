# scratchpad 知识底座整合执行计划

> 依据：`TRAE_PROMPT.md`（2026-08-13 最新版） · 许可策略已按新推送确认
> 主仓：scratchpad（AGPL v3，个人 AI 助手 monorepo）· 本仓库：scratchpad-knowledge（知识底座源码归档）
> 状态：预处理完成，待按阶段合入 scratchpad 主仓

---

## 一、许可策略（已确认）

- 有许可证（含 SSPL 等非标准开源）的项目 → **全按开源处理**，正常进入融合评估。
- 无 LICENSE 的项目 → **一律暂缓**，标"暂缓：无许可"，不进入融合评估。

| 项目 | 许可 | 处理 |
|------|------|------|
| FalkorDB | SSPL | 按开源处理，可评估；仅后期开源发布时单独评估 SSPL 传染 |
| corese-core | 无 LICENSE | **暂缓：无许可**，不参与融合 |

---

## 二、融合层级总览（36 项）

**耦合（完整源码合入 scratchpad 子项目）— 12 项**
thermo、pycalphad、CoolProp、PyXtal、gemmi、ChemFormula、Pynite、AffineGaps、rdflib、business_rules_reasoning、llm-graph-builder、sift

**Skill（写成 .md 技能文件进 skills/）— 2 项**
obsidian-skills、OpenReason

**融合参考（提炼可借鉴设计，不合入）— 14 项**
tespy、Clapeyron.jl、SLICES、WaveBench、rp2daq、hololinked、FEMcy、graphrag、LightRAG、neosemantics、trustgraph、Nucleoid、kb-arena、quartz

**基础设施（独立部署 DB/服务，不进主仓）— 7 项**
hyalite、FalkorDB、oxigraph、terminusdb、second-brain、khoj、siyuan

**暂缓（无 LICENSE）— 1 项**
corese-core

---

## 三、分阶段执行计划（按 TRAE_PROMPT 五个重点方向优先级）

### 阶段一：语义网补层（确定性知识，最高优先级）
| 项目 | 层级 | 落地动作 |
|------|------|----------|
| rdflib | 耦合 | 合入 src/ 子项目，作为 RDF/SPARQL 基础层 |
| oxigraph | 基础设施 | 独立服务，RocksDB 持久化 + SPARQL 协议 |
| trustgraph | 融合参考 | 提炼 OntologyRAG 语义过滤 + provenance 溯源设计 |
| neosemantics | 融合参考 | 提炼 RDF↔LPG 无损映射 + SHACL 校验 |
| terminusdb | 基础设施 | 评估 datalog 引擎 + git 式版本化 |
| corese-core | 暂缓 | 不动作 |

### 阶段二：逻辑引擎（LLM 之外的第二条推理线）
| 项目 | 层级 | 落地动作 |
|------|------|----------|
| business_rules_reasoning | 耦合 | 合入作为 Horn 规则引擎，LLM 仅作文本事实抽取 |
| Nucleoid | 融合参考 | 提炼"赋值即依赖"符号世界模型设计 |
| OpenReason | Skill | 写 skills/ 五阶段 LLM 推理工作流技能 |

### 阶段三：混合检索（跳出纯向量，BM25+重排）
| 项目 | 层级 | 落地动作 |
|------|------|----------|
| sift | 耦合 | 合入混合检索内核（BM25+向量+RRF+重排） |
| second-brain | 基础设施 | 参照其 MCP 暴露 + token 预算 recall 模式 |
| kb-arena | 融合参考 | 提炼策略目录 + 检索选型评估方法论 |

### 阶段四：Obsidian 桥接（agent 直接读写笔记库）
| 项目 | 层级 | 落地动作 |
|------|------|----------|
| obsidian-skills | Skill | 写 skills/，直接复用 SKILL.md 集合 |
| siyuan | 基础设施 | 参照其内建 MCP server 暴露笔记库范式 |
| khoj | 基础设施 | 参照 bi-encoder+cross-encoder 语义检索管道 |
| quartz | 融合参考 | 提炼 OFM 解析 + 插件流水线 |

### 阶段五：热力学/材料（Lumo 材料库地基）
| 项目 | 层级 | 落地动作 |
|------|------|----------|
| thermo / pycalphad / CoolProp | 耦合 | 合入物性 + 相平衡 + EOS 基础层 |
| PyXtal / gemmi / ChemFormula | 耦合 | 合入晶体结构 + 晶体学 + 分子式解析 |
| Pynite / AffineGaps | 耦合 | 合入结构有限元 + 序列比对小工具 |
| SLICES / FEMcy / tespy / Clapeyron.jl / hololinked / rp2daq / WaveBench | 融合参考 | 提炼编码/并行求解/建模抽象 |
| hyalite | 基础设施 | 独立，SIMD 序列比对服务 |

### GraphRAG 对照（不直接合入，供设计参考）
graphrag（融合参考）、LightRAG（融合参考）、llm-graph-builder（耦合）、FalkorDB（基础设施）

---

## 四、各项目详细评估

### academic/（热力学）
#### thermo
- 定位：Python 化工物性库——化学品常数检索 + 温压物性（热/输运）+ 混合物相平衡 flash。
- 融合层级：耦合
- 运行依赖：无（纯 Python/numpy，可选 numba）
- 价值判断：物性常数获取 + 闪蒸/相平衡，Lumo 材料库物性层现成地基。
- 可借鉴点：ChemicalConstantsPackage 数据包封装；flash 按复杂度分层（vl/vln/vls）；参数库 JSON/TSV 组织。

#### tespy
- 定位：热力装置/循环系统稳态网络仿真，oemof 生态。
- 融合层级：融合参考
- 运行依赖：无（Python，自身依赖 CoolProp）
- 价值判断：独立应用，与材料库地基关联弱，偏参考。
- 可借鉴点：component/connection/network 三层抽象；on/off-design 特性曲线；物性接口与库解耦。

#### pycalphad
- 定位：CALPHAD 相图计算库——读 TDB、多元多相 Gibbs 能量最小化求相平衡。
- 融合层级：耦合
- 运行依赖：无（Python + Cython）
- 价值判断：材料相图/相平衡计算，可作相平衡层复用。
- 可借鉴点：io/tdb.py TDB 解析器；codegen 编译符号模型成 Cole 码加速；mapping/strategy 策略扫相图。

#### Clapeyron.jl
- 定位：Julia 物态方程(EOS)库，覆盖 SAFT/cubic/活度系数/电解质。
- 融合层级：融合参考
- 运行依赖：无（Julia 1.10+，非 GPU/付费）
- 价值判断：无法合入 Python monorepo，但 EOS 框架设计是顶级参考。
- 可借鉴点：ThermodynamicMethod 可插拔抽象；SingleParam/PairParam/GroupParam 参数体系；ForwardDiff 隐式求导。

#### CoolProp
- 定位：跨语言高精度流体物性库（Helmholtz EOS），REFPROP 开源替代。
- 融合层级：耦合
- 运行依赖：无（C++ 编译，Python/Julia/MATLAB 绑定）
- 价值判断：高精度物性与标准 EOS，全行业物性基石。
- 可借鉴点：AbstractState 统一接口 + 多后端；流体参数 JSON 数据驱动；SVD/TTSE 表查加速。

### academic/（晶体/材料/化学）
#### PyXtal
- 定位：Python 对称性约束生成 0-3D 晶体结构，支持对称分析、XRD 模拟、结构优化。
- 融合层级：耦合
- 运行依赖：无（可选 Julia/GPU）
- 价值判断：给定化学计量比+空间群下对称放原子的算法难题。
- 可借鉴点：Wyckoff 位置枚举；群论对称操作；多外部 DFT 力场接口。

#### SLICES
- 定位：可逆不等的晶体结构序列编码 + MatterGPT Transformer 反向设计。
- 融合层级：融合参考
- 运行依赖：GPU 推荐；可选 Materials Project API（付费新颖性检查）
- 价值判断：晶体结构→一维序列不可逆/不等价编码，让生成式 LLM 可用于固体设计。
- 可借鉴点：结构线性化编码；Wyckoff 对称处理；数据增强。

#### gemmi
- 定位：C++ 库（带 Python 绑定），大分子晶体学数据（CIF/STAR/PDB/MTZ 读写、对称、电子密度）。
- 融合层级：耦合
- 运行依赖：无
- 价值判断：统一的晶体学基础设施。
- 可借鉴点：C++/Python 混合编译最佳实践；稳健 CIF/STAR 解析；对称性/空间群数据结构。

#### ChemFormula
- 定位：轻量 Python 库，解析/格式化化学分子式，支持计量运算与分子量。
- 融合层级：耦合
- 运行依赖：无
- 价值判断：分子式解析与格式转换（LaTeX/HTML/Unicode）。
- 可借鉴点：希尔排序(Hill notation)；分子式算术设计；IUPAC 原子量整合。

#### hyalite
- 定位：纯 Rust SIMD 加速的精确 DNA/蛋白序列比对库，多模式 + 确定性保证。
- 融合层级：基础设施
- 运行依赖：无（CPU SIMD，非 GPU）
- 价值判断：批量序列比对精确可重复前提下大幅提速。
- 可借鉴点：Rognes 多序列 SIMD 并行；运行时 CPU 特征分发；比特级确定性保证。

### academic/（仪器/有限元/序列）
#### WaveBench
- 定位：Python 实验室自动测量台，把信号源/示波器/电源/万用表编排成可复现 run plan 并出离线报告。
- 融合层级：融合参考（自带只读 MCP 入口，但绑真实仪器）
- 运行依赖：真实仪器（R&S/RIGOL，pyvisa/serial）；`--fake` 可离线
- 价值判断：实验流程不可复现、证据难追溯。
- 可借鉴点：run plan 三段式 check→verify→plan 安全闸门；case_id 采集证据链；MCP 只读/disabled 权限模型。

#### rp2daq
- 定位：Raspberry Pi Pico 数据采集/步进电机/数字 IO 的 Python 控制 + 预编译 C 固件。
- 融合层级：融合参考（需 Pico 硬件 + 刷固件）
- 运行依赖：特定硬件（RP2040 + .uf2 固件），无 GPU/付费
- 价值判断：MCU 编程门槛与调试。
- 可借鉴点：Python 解析 C 源码动态生成命令接口；异步命令+回调；大块数据分 report 流式回传。

#### hololinked
- 定位：Python 仪器控制/数据采集框架，遵循 W3C Web of Things，一个 Thing 类即网络设备。
- 融合层级：融合参考
- 运行依赖：无（纯 Python；MQTT 需 broker）
- 价值判断：硬件对象跨网络暴露、多协议接入。
- 可借鉴点：Property/Action/Event 三分模型；W3C Thing Description 自动生成；多协议并发 + 状态持久化。

#### Pynite
- 定位：纯 Python 三维弹性结构有限元库，聚焦易用/准确/可维护。
- 融合层级：耦合
- 运行依赖：无（NumPy/SciPy；VTK/pyvista 可选）
- 价值判断：易用开源的结构有限元能力。
- 可借鉴点：刚度/质量矩阵分块向量化写入提速 15-30%；DKMQ 板单元；P-Δ 几何刚度矩阵免迭代。

#### FEMcy
- 定位：Taichi 并行（CPU/GPU）有限元求解器，读 Abaqus .inp，支持几何/材料非线性。
- 融合层级：融合参考
- 运行依赖：GPU 可选（Taichi；C3D10 编译需 5 分钟）
- 价值判断：可定制的 GPU 并行有限元求解器。
- 可借鉴点：element_zoo/material_zoo 工厂模式；复用 Abaqus 前处理生态；自适应步长 Newton 法 + 预处理 CG。

#### AffineGaps
- 定位：单文件 Numba 加速的 Gotoh 仿射空位序列比对，修正论文/教科书初始化 bug。
- 融合层级：耦合（单文件小工具）
- 运行依赖：无（Numba 可选 JIT）
- 价值判断：常见比对实现初始化错误。
- 可借鉴点：无依赖即跑/有则加速双模式；用 int 规避长序列数值不稳定；严谨 DP 边界处理。

### knowledge/（GraphRAG 对照）
#### graphrag（Microsoft）
- 定位：微软官方 GraphRAG 管道，LLM 抽取实体/关系建图，社区摘要支撑全局/局部/drift 检索。
- 融合层级：融合参考
- 运行依赖：付费 LLM API（OpenAI 为主，索引调用量大）
- 价值判断：跨文档全局主题/关系推理，但索引贵、延迟高。
- 可借鉴点：hierarchical-leiden 社区聚类 + 社区报告摘要；模块化 pipeline；drift search。

#### LightRAG
- 定位：轻量图 RAG，KG + 向量双检索，GraphRAG 高效简化替代，自带 REST + WebUI。
- 融合层级：融合参考
- 运行依赖：LLM（OpenAI 付费或 ollama/vllm/hf 本地）；无 GPU 硬需
- 价值判断：解决 GraphRAG 索引贵、响应慢、增量更新难。
- 可借鉴点：local/global/hybrid/mix 双级检索；KV/vector/graph/doc_status 四类存储抽象；增量更新+选择性删除。

#### llm-graph-builder（neo4j-labs）
- 定位：Neo4j 官方全栈应用（FastAPI+React），多源数据经 LLM 抽取入 Neo4j + 多模式对话。
- 融合层级：耦合
- 运行依赖：Neo4j 5.23+（付费或自建）+ 付费 LLM 与 Diffbot
- 价值判断：整套产品化流程，但强绑定 Neo4j，仅提炼设计。
- 可借鉴点：多数据源接入抽象；图 schema 定义 + 实体合并去重；vector/graph/fulltext 多查询模式。

#### FalkorDB
- 定位：稀疏矩阵+线性代数的属性图数据库（OpenCypher），面向 LLM 图谱与 Agent 记忆，Rust 重写。
- 融合层级：基础设施
- 运行依赖：独立部署（Docker）；许可 SSPL（按开源处理）
- 价值判断：高性能图存储/图算法，后期开源发布时单独评估 SSPL。
- 可借鉴点：稀疏矩阵邻接 + 线性代数执行查询；节点/边向量索引；内置图算法过程。

### knowledge/（语义网/本体论）
#### rdflib
- 定位：Pure Python RDF 图库，Graph 接口 + SPARQL 1.1 + 全格式解析/序列化，确定性知识底层。
- 融合层级：耦合
- 运行依赖：无（BerkeleyDB/networkx 可选）
- 价值判断：三元组怎么建/查/存的最底层痛点，语义推理基础。
- 可借鉴点：插件式 Store 抽象可热切换；term.py 词项类型系统；内置 namespace 词汇表；SPARQL 处理器扩展。

#### oxigraph
- 定位：Rust 图数据库 + RDF/SPARQL 工具链，RocksDB 存储，可起 SPARQL 协议服务器。
- 融合层级：基础设施
- 运行依赖：Rust + RocksDB；有 Docker/pyoxigraph 绑定；无 GPU/付费
- 价值判断：确定性知识的大规模持久化与标准 SPARQL 查询。
- 可借鉴点：oxrdf/oxrdfio/spargebra/sparopt 分层 crate；sparopt 查询优化器；RDF 数据集规范化。

#### terminusdb
- 定位：分布式图数据库，"git for data"，WOQL(datalog)+GraphQL+文档 API，时间旅行与分支协作。
- 融合层级：基础设施
- 运行依赖：SWI-Prolog + Rust + Docker/Snap；无 GPU/付费
- 价值判断：知识版本化/协作/时态推理，datalog 统一引擎。
- 可借鉴点：document instance/schema 双层建模；git 式版本控制与 push/pull/clone；rust 层 datalog 引擎。

#### neosemantics
- 定位：Neo4j 的 RDF 插件（.jar），属性图无损存取 RDF、SHACL 校验、OWL/RDFS/SKOS 导入。
- 融合层级：融合参考
- 运行依赖：需 Neo4j + Java/JVM
- 价值判断：RDF↔属性图双向映射与本体导入，但强绑 Neo4j。
- 可借鉴点：RDFToLPGStatementProcessor 无损映射；SHACL 校验器；本体导入管线。

#### trustgraph
- 定位：holonic context graph 平台，完整 agentic GraphRAG/OntologyRAG 上下文工程基础设施。
- 融合层级：融合参考
- 运行依赖：Cassandra/Qdrant/Garage/Pulsar 多服务；可选付费 LLM 或本地 vLLM/Ollama
- 价值判断：最贴近"GRAG 缺语义推理"痛点的完整实现（符号图+语义检索+全量溯源），但太重。
- 可借鉴点：OntologyRAG/GraphRAG 语义过滤策略；provenance 溯源设计；Workspace/Collection/Flow 三层隔离。

#### corese-core
- 定位：Java 语义网库，RDF+SPARQL 1.1+RDFS/OWL RL 推理+SHACL+STTL+规则引擎。
- 融合层级：暂缓（无 LICENSE）
- 运行依赖：Java/JVM
- 价值判断：**暂缓：无许可**，不进入融合评估。
- 可借鉴点：（暂缓，仅留档）logic/ 推理闭包 + rule/ 规则引擎 + sparql/ 编译器。

### knowledge/（逻辑推理引擎）
#### Nucleoid
- 定位：Rust 声明式逻辑编程运行时，把赋值语句作"关系"入依赖图自动传播更新，可查 why/affects。
- 融合层级：融合参考
- 运行依赖：无（纯 Rust）
- 价值判断：把隐式世界模型外化为可检查、可一致的显式逻辑图，合"第二条符号推理线"。
- 可借鉴点：graph.rs NodeKey 单点归一化；transaction.rs 事务回滚防漂移；声明式"赋值即依赖"状态传播。

#### OpenReason
- 定位：TypeScript 的 LLM 推理编排层，classify→skeleton→solve→verify→finalize 分阶段驱动多模型。
- 融合层级：Skill
- 运行依赖：付费 LLM API（OpenAI/Anthropic/Gemini/xAI）+ npm；非独立引擎
- 价值判断：结构化分步+验证修复解决 LLM 推理不可靠，但依赖付费 API，非独立符号推理。
- 可借鉴点：五阶段流水线；verification 层（math/logic 检查+critic+repair）；simple/complex 模型混用降本。

#### business_rules_reasoning
- 定位：Python Horn 子句业务规则推理引擎（deduction/hypothesis），可选 LLM 编排。
- 融合层级：耦合
- 运行依赖：无（引擎纯 Python；LLM 编排可选需 HF）
- 价值判断：规则引擎保证决策可追溯，LLM 只作文本事实抽取，可落地性高。
- 可借鉴点：deductive/ 纯规则引擎 + 全 JSON 序列化状态；决策表/树转换；orchestrator 将 LLM 限定为"事实检索代理"。

### knowledge/（混合检索）
#### sift
- 定位：Rust 本地优先混合检索 CLI+库，单二进制跑通"扩展→多路召回→融合→重排"流水线，支持 agentic 规划搜索。
- 融合层级：耦合
- 运行依赖：无强依赖（CPU-first，CUDA 可选；LLM 本地可选，无付费必需）
- 价值判断：跳过基础设施税、开箱即用的混合检索（BM25+向量+RRF+位置重排）。
- 可借鉴点：SearchPlan 的 Expansion/Retriever/Fusion/Reranking 分层抽象；sector 缓存+CAS+mmap+SIMD 索引；内置 eval/optimize。

#### second-brain
- 定位：个人知识库+实体图谱（GraphRAG），Postgres/pgvector 混合检索，对外 CLI、`brain-mcp` MCP server、web UI、Quartz wiki。
- 融合层级：基础设施
- 运行依赖：Docker/Postgres 必需；Ollama 本地可选；无付费/GPU 必需
- 价值判断：个人语料散落、agent 重复贴上下文，token 预算打包省 4-15×。
- 可借鉴点：RRF+新近度加权融合；token_budget/recall 打包+引用模式；sensitivity 出站控制。

#### kb-arena
- 定位：Python 检索架构评估框架，同一语料/问题集上跑 lexical/dense/graph/hybrid 等策略并记录质量/延迟/成本，配 Next.js 看板。
- 融合层级：融合参考（评估实验室，非运行时检索库）
- 运行依赖：Ollama 本地或付费 API 按需；graph 策略需 Neo4j；demo 零依赖
- 价值判断：用证据支撑检索架构选型，可作回归实验室。
- 可借鉴点：策略目录+插件化 base 接口；retriever-lab 隔离"检索-only"评估；dev/holdout 双 split 防过拟合。

### knowledge/（Obsidian 生态）
#### obsidian-skills
- 定位：kepano 的 Obsidian Agent Skills 集合，把笔记读写语法打包成标准 SKILL.md 供 Claude Code/Codex 调用。
- 融合层级：Skill
- 运行依赖：无（obsidian-cli 需本机 Obsidian 已打开）
- 价值判断：agent 读写笔记库，不写代码靠技能文件掌握 wikilink/callout/frontmatter。
- 可借鉴点：SKILL.md + references/ 拆分结构；obsidian-cli 最小命令面（read/create/append/search/tasks/backlinks）；写后验证渲染。

#### khoj
- 定位：AI 第二大脑（Python），本地文档语义索引后提供 chat/search/agent/automation，可自托管。
- 融合层级：基础设施
- 运行依赖：付费 API 或 ollama 本地；非 GPU 必需
- 价值判断：自带 Obsidian/Emacs/手机/WhatsApp 客户端，Obsidian 桥接完整产品化参照。
- 可借鉴点：bi-encoder 检索 + cross-encoder 重排；已有 MCP 模块；多源数据接入 + Obsidian 插件客户端。

#### quartz
- 定位：Hugo + TypeScript 把 Markdown 数字花园生成静态网站。
- 融合层级：融合参考
- 运行依赖：无
- 价值判断：纯参考（方向是发布非读写），OFM 兼容解析与插件体系可借鉴。
- 可借鉴点：transformers/emitters/filters 插件流水线；Obsidian Flavored Markdown 解析；full-text search + graph view。

#### siyuan
- 定位：思源笔记，Go 内核 + Electron 前端，隐私优先、块级引用、所见即所得本地知识库（AGPL-3.0）。
- 融合层级：基础设施
- 运行依赖：无（AI 功能可选填 API；自带内建 MCP server）
- 价值判断：价值在其"笔记应用内建 MCP server"的桥接范式，不依赖 Obsidian。
- 可借鉴点：kernel/mcp/server.go 用 go-sdk 暴露 /mcp 端点；块级索引/引用；import_obsidian.go 已有导入能力。注意 AGPL 传染。

---

## 五、执行边界与依赖

- **本仓库（scratchpad-knowledge）**：仅做源码归档 + 融合评估（本文档为交付物）。
- **真正合入**发生在 scratchpad 主仓（mcpserver/、skills/、src/ 子项目），需主仓访问。
- **基础设施类**（oxigraph/terminusdb/FalkorDB/second-brain/khoj/siyuan/hyalite）不进主仓，独立部署。
- **Skill 类**（obsidian-skills/OpenReason）首批落地为 skills/*.md，可在本仓库先行起草。
- **许可黑名单**：corese-core 暂缓，不参与。