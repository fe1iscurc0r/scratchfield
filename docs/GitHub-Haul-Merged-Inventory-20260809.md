# GitHub 扫货 — 三轮合并清单

> 轮1 (久): 52包已clone → /home/ubuntu/github_haul/
> 轮2 (今日cron): 15候选
> 轮3 (今日手动): 35候选
> 去重合并: 82 个项目

---

## 融合模式说明

| 模式 | 含义 | 预处理？ |
|------|------|---------|
| **MCP** | 独立进程，MCP协议接入 mcpserver/ | ✅ 可预处理 |
| **Skill** | .md工作流，Hermes直接执行 | ✅ 可预处理 |
| **内嵌** | 源码合入 scratchpad，作为项目一部分 | ❌ 需人工审查 |
| **融合参考** | 不接入，架构/设计学习 | ❌ |
| **基础设施** | 独立部署（DB/MQ/Broker） | ❌ |
| **学术** | 材料/化学知识提取，给模型当弹药 | ❌ |

---

## 一、MCP Server（可预处理）

| # | 项目 | ⭐ | 许可 | 状态 | 说明 |
|---|------|-----|------|------|------|
| 1 | headroomlabs-ai/headroom | 65k | Apache-2.0 | 🆕 | LLM上下文压缩，JSON省95% token |
| 2 | rtk-ai/rtk | 待确认 | 待确认 | 🆕 | Token压缩60-90%，Rust单二进制 |
| 3 | caura-ai/caura-memclaw | 420 | Apache-2.0 | 🆕 | 多Agent共享记忆MCP |
| 4 | mnemon-dev/mnemon | 398 | Apache-2.0 | 🆕 | 图基跨会话记忆 |
| 5 | Panniantong/Agent-Reach | 待确认 | 待确认 | 🆕 | 多平台信息获取(含B站) |
| 6 | 0xSteph/pentest-ai | 1.5k | MIT | 🆕 | 渗透测试205工具+17Agent |
| 7 | heizaheiza/Charles-mcp | 293 | MIT | 🆕 | Charles Proxy抓包MCP |
| 8 | vercel-labs/agent-browser | 待确认 | 待确认 | 🆕 | 浏览器自动化CLI(Rust) |
| 9 | HKUDS/CLI-Anything | 待确认 | 待确认 | 🆕 | 让所有软件Agent-Native |
| 10 | browser-use | - | 已确认 | 📦 | 浏览器自动化 |
| 11 | nuclei | - | 已确认 | 📦 | 漏洞扫描 |
| 12 | trivy | - | 已确认 | 📦 | 容器扫描 |
| 13 | syft | - | 已确认 | 📦 | SBOM生成 |
| 14 | strix | - | 已确认 | 📦 | API安全测试 |
| 15 | falco | - | 已确认 | 📦 | 运行时安全 |
| 16 | coraza | - | 已确认 | 📦 | WAF |
| 17 | cosign | - | 已确认 | 📦 | 签名验证 |
| 18 | sherlock | - | 已确认 | 📦 | 用户名搜索 |
| 19 | frida | - | 已确认 | 📦 | 动态插桩 |
| 20 | jadx | - | 已确认 | 📦 | Dex反编译 |
| 21 | nanobrowser | - | 已确认 | 📦 | 轻量浏览器Agent |
| 22 | pentagi | - | 已确认 | 📦 | 渗透测试Agent |
| 23 | LLM4Decompile | - | 已确认 | 📦 | LLM反编译 |

---

## 二、Skill（可预处理）

| # | 项目 | ⭐ | 许可 | 状态 | 说明 |
|---|------|-----|------|------|------|
| 1 | K-Dense-AI/scientific-agent-skills | 33k | MIT | 🆕 | 158科学Agent Skills |
| 2 | NirDiamant/Agent_Memory_Techniques | 850 | Apache-2.0 | 🆕 | 30个记忆技术Notebook |
| 3 | mattpocock/skills | 210k | MIT | 🆕 | Agent Skills集合 |
| 4 | garrytan/gstack | 127k | MIT | 🆕 | 23个Claude Code工具 |
| 5 | obra/superpowers | 待确认 | 待确认 | 🆕 | Agent Skills框架+方法论 |
| 6 | mvanhorn/last30days-skill | 待确认 | 待确认 | 🆕 | 多平台研究Skill |
| 7 | multica-ai/andrej-karpathy-skills | 待确认 | 待确认 | 🆕 | Karpathy的CLAUDE.md |
| 8 | JuliusBrussee/caveman | 96k | MIT | 🆕 | Token压缩65% |
| 9 | DietrichGebert/ponytail | 98k | MIT | 🆕 | 让Agent像最懒senior dev |
| 10 | baoyu-skills | - | 已确认 | 📦 | 宝玉Skills |
| 11 | AI-Animation-Skill | - | 已确认 | 📦 | AI动画Skill |

---

## 三、内嵌（需合入 scratchpad 源码）

| # | 项目 | ⭐ | 许可 | 状态 | 嵌入位置 | 说明 |
|---|------|-----|------|------|---------|------|
| 1 | chyinan/Kokoro-Engine | 111 | MIT | 🆕 | NEKO/参考 | Live2D+LLM+TTS+MCP五合一 |
| 2 | jamiepine/voicebox | 待确认 | 待确认 | 🆕 | NEKO/voice/ | AI语音克隆工作室 |
| 3 | diegosouzapw/OmniRoute | 待确认 | 待确认 | 🆕 | apiserver/网关 | 290+provider统一网关 |
| 4 | Graphify-Labs/graphify | 104k | Apache-2.0 | 🆕 | mcpserver/ | 代码→知识图谱 |
| 5 | Egonex-AI/Understand-Anything | 待确认 | 待确认 | 🆕 | mcpserver/ | 交互式知识图谱 |
| 6 | affaan-m/ECC | 238k | MIT | 🆕 | Hermes/ | Agent harness优化 |
| 7 | HKUDS/nanobot | 46k | MIT | 🆕 | 参考 | 轻量Agent框架 |
| 8 | paperclipai/paperclip | 待确认 | 待确认 | 🆕 | 参考 | Agent工作管理 |
| 9 | stablyai/orca | 待确认 | 待确认 | 🆕 | 参考 | 并行Agent舰队 |
| 10 | tinyhumansai/openhuman | 待确认 | 待确认 | 🆕 | 参考 | 个人AI超级智能 |
| 11 | zeroclaw-labs/zeroclaw | 待确认 | 待确认 | 🆕 | 参考 | Rust AI助手基础设施 |
| 12 | x380kkm/Live2DPet | 76 | MIT | 🆕/📦 | NEKO/参考 | Live2D桌宠（之前已拉） |
| 13 | kiyotakali/Miru | 59 | Apache-2.0 | 🆕 | NEKO/参考 | AI伴侣+长期记忆 |
| 14 | neko_src_v0.8.3 | - | Apache-2.0 | 📦 | NEKO/ | NEKO后端源码 |
| 15 | code-yeongyu/oh-my-openagent | 待确认 | 待确认 | 🆕 | 参考 | Codex harness |
| 16 | Hmbown/CodeWhale | 待确认 | 待确认 | 🆕 | 参考 | Agent harness |
| 17 | BigPizzaV3/CodexPlusPlus | 待确认 | 待确认 | 🆕 | 参考 | Codex增强工具 |

---

## 四、融合参考（只看不接入）

| # | 项目 | ⭐ | 许可 | 状态 | 学什么 |
|---|------|-----|------|------|--------|
| 1 | Open-LLM-VTuber | 10k+ | MIT | 🆕 | 语音打断状态机、Live2D表情映射 |
| 2 | Soul-of-Waifu | 高 | GPL-3.0⚠️ | 🆕 | 四层认知记忆架构 |
| 3 | OpenBMB/MiniCPM-Desk-Pet | 419 | AGPL-3.0⚠️ | 🆕 | Electron+llama.cpp sidecar |
| 4 | nexu-io/open-design | 待确认 | 待确认 | 🆕 | Agent驱动设计管线 |
| 5 | karpathy/autoresearch | 待确认 | 待确认 | 🆕 | AI自动做研究 |
| 6 | xai-org/x-algorithm | 待确认 | 待确认 | 🆕 | 推荐算法→RAG重排 |
| 7 | chenglou/pretext | 待确认 | 待确认 | 🆕 | 文本精确测量→Live2D气泡 |
| 8 | AlexsJones/llmfit | 待确认 | 待确认 | 🆕 | 模型×硬件适配矩阵 |
| 9 | MemPalace/mempalace | 待确认 | 待确认 | 🆕 | AI记忆基准测试 |
| 10 | crewAI | - | 已确认 | 📦 | 多Agent编排 |
| 11 | LightRAG | - | 已确认 | 📦 | 轻量RAG |
| 12 | graphiti | - | 已确认 | 📦 | 时序知识图谱 |
| 13 | dify | - | 已确认 | 📦 | LLM应用平台 |
| 14 | Flowise | - | 已确认 | 📦 | 低代码LLM |
| 15 | anything-llm | - | 已确认 | 📦 | 多源RAG |
| 16 | mastra | - | 已确认 | 📦 | TS Agent框架 |
| 17 | agent-memory | - | 已确认 | 📦 | Agent记忆 |
| 18 | pentest-agents | - | 已确认 | 📦 | 渗透测试Agent |
| 19 | OpenBMB/VoxCPM | 35k | Apache-2.0 | 🆕 | 多语言TTS |
| 20 | soniqo/speech-studio | 49 | Apache-2.0 | 🆕 | 桌面TTS工作台 |
| 21 | koala73/worldmonitor | 待确认 | 待确认 | 🆕 | 全球情报仪表盘 |
| 22 | odysseus-dev/odysseus | 84k | AGPL-3.0⚠️ | 🆕 | 自托管AI工作空间 |

---

## 五、基础设施（独立部署）

| # | 项目 | ⭐ | 许可 | 状态 | 说明 |
|---|------|-----|------|------|------|
| 1 | emqx | - | 已确认 | 📦 | MQTT Broker |
| 2 | EmbeddedMqttBroker | - | 已确认 | 📦 | 嵌入式MQTT |

---

## 六、学术（材料/化学知识提取）

| # | 项目 | ⭐ | 许可 | 状态 | 说明 |
|---|------|-----|------|------|------|
| 1 | pymatgen | - | 已确认 | 📦 | 材料基因组 |
| 2 | ase | - | 已确认 | 📦 | 原子模拟环境 |
| 3 | cantera | - | 已确认 | 📦 | 化学动力学 |
| 4 | biosteam | - | 已确认 | 📦 | 生物精炼模拟 |
| 5 | biosteam_lca | - | 已确认 | 📦 | 生命周期评估 |
| 6 | matbench | - | 已确认 | 📦 | 材料ML基准 |
| 7 | foundry | - | 已确认 | 📦 | 材料数据平台 |
| 8 | gasification | - | 已确认 | 📦 | 气化模拟 |
| 9 | data-resources-for-materials-science | - | 已确认 | 📦 | 材料数据资源 |
| 10 | NVIDIA/nvalchemi-toolkit | 127 | Apache-2.0 | 🆕 | 化学AI加速 |
| 11 | deepchem/deepchem | 6.9k | MIT | 🆕 | 药物/材料ML全栈 |
| 12 | ZhuLinsen/daily_stock_analysis | 待确认 | 待确认 | 🆕 | LLM股票分析（学术：金融ML参考） |

---

## 七、WT 插件（已拉取，给 QClaw 当样本）

| # | 项目 | 说明 |
|---|------|------|
| 1-13 | wt-tools, WTRTI, WTDashboard, wthud2, wtmap, wtac, WTDeck, WT-8111-Neo, WarThunder8111, WarThunder-Vehicles-API, WarThunder-localhost-documentation, Artillery-Calculator-War-Thunder, AdvancedMapWarthunder | WT火控/仪表/地图/API插件 |

---

## 统计

| 分类 | 旧 | 新 | 合计 | 可预处理 |
|------|-----|-----|------|---------|
| MCP Server | 14 | 9 | **23** | ✅ 全部 |
| Skill | 2 | 9 | **11** | ✅ 全部 |
| 内嵌 | 2 | 15 | **17** | ❌ |
| 融合参考 | 9 | 13 | **22** | ❌ |
| 基础设施 | 2 | 0 | **2** | — |
| 学术 | 9 | 3 | **12** | ❌ |
| WT插件 | 13 | 0 | **13** | — |
| **合计** | **51** | **49** | **100** | **34** |

---

## 预处理优先级（Top 10）

| 优先级 | 项目 | 模式 | 理由 |
|--------|------|------|------|
| P0 | headroom | MCP | 立即可用，省token，已确认Apache-2.0 |
| P0 | scientific-agent-skills | Skill | 158现成Skill，33k⭐，MIT |
| P1 | caura-memclaw | MCP | NEKO+Lumo共享记忆总线 |
| P1 | Agent-Reach | MCP | 支持B站，陆墨的"外部感官" |
| P2 | caveman + ponytail | Skill | Token压缩双刀流，MIT |
| P2 | rtk-ai/rtk | MCP | 旁路token压缩 |
| P3 | agent-browser | MCP | Vercel出品，浏览器自动化 |
| P3 | Charles-mcp | MCP | 网络抓包感知 |
| P3 | pentest-ai | MCP | 安全审计能力 |
