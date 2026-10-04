# 扫货 HackerNews 热点 — 2026-09-02

> 数据源: hn.algolia.com API (近7天, 2026-08-26 ~ 09-02, tags=story, points>=3)
> 目的: 找值得立项的 AI Agent / MCP / 无线电 / 知识库方向新项目或趋势
> 纪律: 已立项/已有 51 项不重复收集（xiaozhi/腾讯记忆/darknet-mcp/robin/AutoProber/neo4j图记忆/easyeda对照/cti-expert/avogadro/GitNexus/latticedb/OpenKB/BiliSum/rag-skill/ground-station/ai-engineer-notebooks/rtl-ml/AntiHunter/meshpoint/drawio-skill/codebase-memory-mcp/worldmonitor/oh-my-openagent/QwenPaw/granite-biomass/Supertonic-TTS/esp32-tinylm/radio-modulation/KWS/RS41ng/painlessMesh/meshtastic_sdr/bluepad32/gnss-sdr/gr-leo/theseus-cores/lorhammer/gr-lora_sdr/x-qsl/OpenRTX/lorawan-server/satellite.js/mcp-proxy/lora-packet/pmcp/adk-agent/cortex-memory/agdb/desperado/peat-mesh/Graphiti）

## 候选清单 (12 项)

| 标题 | 分数 | 评论 | 描述 | 贴栈理由 | 立项建议 |
|------|------|------|------|----------|----------|
| Agent memory as a file format | 190 | 93 | calpaterson.com/memoryfields.html — 提出把 agent 记忆做成一种文件格式（memoryfields），人/程序/agent 三方都能读写 | 直接命中知识库/记忆栈（对照 cortex-memory/agdb/Graphiti） | 立项调研：研读 memoryfields 规范，评估能否作为自家记忆层的"文件即记忆"标准化底座；产出格式对照表 |
| Serve Markdown to AI Agents with Accept Headers | 176 | 108 | acceptmarkdown.com — 用 HTTP Accept: text/markdown 给 agent 提供 Markdown 版页面，agent 友好 Web 协议 | 命中 MCP/Agent 生态协议趋势，可落地方向多 | 立项：给自家知识库/文档站启用 accept-markdown 网关（中间件），让 agent 直接抓 markdown 源；对照 mcp-proxy |
| VMs won't contain cyber-capable agents | 192 | 147 | Trail of Bits — 论证 VM 无法真正隔离有网络能力的 agent，分析逃逸/检测路径 | 命中 Agent 安全趋势，与现有 agent 沙箱/安全层对照 | 立项：研究 VM 检测与隔离边界，对照现有 agent 沙箱写评估报告，补 agent 权限/沙箱缺口 |
| The smallest dual-band aircraft tracker | 93 | 23 | pantsforbirds.com — 世界最小双频 ADS-B 接收模块（硬件 Show HN） | 命中无线电/地面站栈（对照 ground-station） | 立项：对照 ground-station 评估此 ADS-B 硬件模块方案，纳入飞机追踪/ADS-B 数据链 |
| RotaryCell: rotary phone over LTE with ESP32-S3 | 147 | 51 | github.com/fregacmols/RotaryCell — 用 ESP32-S3 让老式旋转电话跑在 LTE 上 | 命中 ESP32/嵌入式/无线电硬件栈 | 立项：复用其 ESP32-S3 电话/音频处理思路，评估接入 phone-mobile-hub/IC-705 移动核心 |
| The load-bearing vocabulary of Claude | 701 | 326 | louisabraham.github.io/load-bearing — 分析 Claude 的"承重词汇"，哪些词删掉会让模型崩掉 | 高分分析文章，agent 提示词/词汇研究视角 | 立项：复现"承重词汇"分析工具，建自家 agent 提示词词汇资产库（对照组词表） |
| I accidentally turned LLM memory into program analysis | 302 | 85 | pwning.systems — 把 LLM 记忆当程序分析做，发现记忆可以被当作代码来审 | 命中 Agent 记忆安全/知识库栈 | 立项：把"记忆=可分析程序"思路用于自家记忆审计，写记忆污染检测 PoC |
| Is MCP Good Yet? | 27 | 1 | ismcpgoodyet.com — MCP 生态成熟度追踪站（谁支持/谁不支持） | 命中 MCP 栈，生态监测角度 | 立项：做常驻 MCP 生态监测（定期快照 mcp 生态成熟度），或并入既有 worldmonitor |
| Conduct – open-source guardrails for LLM and MCP tool calls | 22 | 4 | github.com/sseshachala/conductai — MCP/LLM 工具调用护栏（开源） | 命中 MCP 工具安全 | 立项：评估接入 pmcp/mcp-proxy 做工具调用护栏（白名单/参数校验/风控） |
| Talos – AI agent with a permission kernel between model and shell | 14 | 10 | talos-agent.ch — 在模型和 shell 之间加权限内核的 agent | 命中 Agent 安全/权限模型 | 立项：对照其权限内核设计，评估引入自家 agent 的权限最小化层 |
| AC2 Protocol: missing security layer for AI agents | 17 | 16 | ac2protocol.org — 提议给 AI agent 补安全协议层 | 命中 Agent 安全协议趋势 | 立项：研读 AC2 协议，评估与 mcp-proxy/pmcp 的安全层集成 |
| Previewing the Model Hardware Standard (MHS) | 136 | 62 | anthropic.com — Anthropic 提出模型硬件接口标准（推理硬件标准） | 命中嵌入式/无线电/AI 硬件方向 | 立项：跟踪 MHS 规范，评估对 esp32-tinylm/嵌入式推理硬件的适配影响 |

## 备选 (未入主表但值得关注)

| 标题 | 分数 | 评论 | 描述 | 备注 |
|------|------|------|------|------|
| The Rise and Fall of Agent Civilizations | 271 | 194 | Dwarkesh 长文 — agent 生态/文明兴衰分析 | 趋势参考：agent 生态演进 |
| Small Models Have Arrived | 799 | 348 | calv.info — 小模型时代到来 | 趋势：与 esp32-tinylm/本地推理相关 |
| We built open OpenRouter (experiential) | 220 | 47 | 开源 OpenRouter，把使用量回馈为更好模型 | 对照 oh-my-openagent/开源网关 |
| DoltLite: SQLite fork + Git 版本控制 (2k agent PRs) | 61 | 52 | SQLite 分支带 Git 式版本控制，全 agent 构建 | 对照 latticedb/agdb，数据版本化 |
| Warp builds self-improving agents on Claude | 58 | 59 | Warp 在 Claude 上做自我改进 agent 闭环 | 自改进趋势 |
| Terminal-Bench-Science | 117 | 36 | 科学科研工作流 agent 评测基准 | 评测方向，对照 ai-engineer-notebooks |
| Autonomous Mathematical Discovery (multi-agent) | 121 | 40 | arXiv 2608.23691 开放世界多智能体数学发现 | 科研 agent 方向 |
| Domain-Driven Agents | 96 | 21 | coldtake.dev — 领域驱动 agent 方法论 | 方法论参考 |
| Aetheryte Radio | 80 | 16 | haz.ee — 手搓无线电项目 | 无线电灵感 |
| AI Agents for Osint/Sigint (makralabs) | 13 | 2 | OSINT/SIGINT agent 平台 | 无线电/情报栈 |
| KHMS – file-based long-term memory agent 自装 | 11 | 0 | 文件式长期记忆 | 对照 memory 栈 |
| Hillock – neuro-symbolic memory engine <1.2GB VRAM | 12 | 3 | 本地神经符号记忆引擎 | 对照 cortex-memory |
| Saccade – live semantic browser truth for agents | 5 | 0 | agent 浏览器语义真值 | 浏览器 agent 方向 |
| AgentConnect – shared agents with separate permissions | 5-6 | 1-3 | 多 agent 权限分离模型 | 权限模型 |
| FnScribe – offline dictation for macOS | 36 | 25 | 本地离线听写 | 语音栈参考 |

## Top 5 推荐立项

1. **Agent memory as a file format** (190p/93c) — 记忆文件格式，直接对接知识库/记忆栈
2. **Serve Markdown to AI Agents with Accept Headers** (176p/108c) — agent 友好 Web 协议，可落地自家站点
3. **VMs won't contain cyber-capable agents** (192p/147c) — agent 安全边界研究（Trail of Bits）
4. **The smallest dual-band aircraft tracker** (93p/23c) — ADS-B 硬件模块，对接无线电/地面站栈
5. **The load-bearing vocabulary of Claude** (701p/326c) — 高分词汇分析，agent 提示词资产库

## 扫描元信息

- 关键词批次1: mcp/agent/sdr/lora/knowledge graph/radio/satellite/embedded/LLM memory/meshtastic/mesh network/RAG/vector database/AI agent → 166 唯一命中
- 关键词批次2: agent security/ADS-B/on-device/computer use/self-improving/browser agent/permission/guardrails/long-term memory/open source model/LoRa/mesh/hardware/ESP32/satellite internet + 全站 Top40 → ~80 额外命中
- 全站热点: Nvidia 收购 HF ($13B)、Claude Fable/Mythos 5.1、GLM-5.3 open-weight、Small Models Have Arrived(799p)、Cursor 被 SpaceX 收购等（大事件级，非项目立项类）
