# GitHub 扫货 — 终版合并清单

> 轮1(久): 52包 | 轮2(今日cron): 15 | 轮3(今日手动): 35 | Uncle城: +3
> 去重后: 104 项目 | 标注: ✓已有基础 / 🆕缺失 / ⚡竞品参考

---

## 一、MCP Server

| # | 项目 | ⭐ | 许可 | 状态 | 融合模式 | 说明 |
|---|------|-----|------|------|---------|------|
| 1 | headroomlabs-ai/headroom | 65k | Apache-2.0 | 🆕 | MCP | LLM上下文压缩(JSON省95%) |
| 2 | rtk-ai/rtk | - | 待确认 | 🆕 | MCP | Token压缩60-90%(Rust) |
| 3 | caura-ai/caura-memclaw | 420 | Apache-2.0 | 🆕 | MCP | 多Agent共享记忆总线 |
| 4 | mnemon-dev/mnemon | 398 | Apache-2.0 | 🆕 | MCP | 图基跨会话记忆 |
| 5 | Panniantong/Agent-Reach | - | 待确认 | 🆕 | MCP | 多平台信息获取(含B站) |
| 6 | 0xSteph/pentest-ai | 1.5k | MIT | 🆕 | MCP | 渗透测试205工具 |
| 7 | heizaheiza/Charles-mcp | 293 | MIT | 🆕 | MCP | Charles抓包MCP |
| 8 | vercel-labs/agent-browser | - | 待确认 | 🆕 | MCP | 浏览器自动化(Rust) |
| 9 | HKUDS/CLI-Anything | - | 待确认 | 🆕 | MCP | 软件Agent-Native化 |
| 10 | Unclecheng-li/DeepSec | - | MIT | 🆕 | MCP | AI安全攻防VS Code+MCP |
| 11 | Unclecheng-li/VulnClaw | - | MIT | 🆕 | MCP | AI Agent MCP漏洞挖掘 |
| 12-24 | nuclei/trivy/syft/strix/falco/coraza/cosign/sherlock/frida/jadx/nanobrowser/pentagi/LLM4Decompile/browser-use | - | 已确认 | 📦 | MCP | 安全/逆向工具线 |

---

## 二、Skill

| # | 项目 | ⭐ | 许可 | 状态 | 融合模式 | 说明 |
|---|------|-----|------|------|---------|------|
| 1 | K-Dense-AI/scientific-agent-skills | 33k | MIT | 🆕 | Skill | 158科学Agent Skills |
| 2 | NirDiamant/Agent_Memory_Techniques | 850 | Apache-2.0 | 🆕 | Skill | 30个记忆技术Notebook |
| 3 | mattpocock/skills | 210k | MIT | 🆕 | Skill | Agent Skills集合 |
| 4 | garrytan/gstack | 127k | MIT | 🆕 | Skill | 23 Claude Code工具 |
| 5 | obra/superpowers | - | 待确认 | ⚡ | Skill | Skills框架(已有baoyu) |
| 6 | mvanhorn/last30days-skill | - | 待确认 | 🆕 | Skill | 多平台研究Skill |
| 7 | multica-ai/andrej-karpathy-skills | - | 待确认 | 🆕 | Skill | Karpathy的CLAUDE.md |
| 8 | JuliusBrussee/caveman | 96k | MIT | 🆕 | Skill | Token压缩65% |
| 9 | DietrichGebert/ponytail | 98k | MIT | 🆕 | Skill | 最懒senior dev策略 |
| 10-11 | baoyu-skills / AI-Animation-Skill | - | 已确认 | ✓ | Skill | 已有 |

---

## 三、内嵌

| # | 项目 | ⭐ | 许可 | 状态 | 嵌入位置 | 说明 |
|---|------|-----|------|------|---------|------|
| 1 | chyinan/Kokoro-Engine | 111 | MIT | ⚡ | NEKO/参考 | Live2D+LLM+TTS+MCP |
| 2 | jamiepine/voicebox | - | 待确认 | 🆕 | voice/ | AI语音克隆(现有TTS无克隆) |
| 3 | diegosouzapw/OmniRoute | - | 待确认 | ⚡ | apiserver/ | 290+provider网关(llm_service已有基础) |
| 4 | Graphify-Labs/graphify | 104k | Apache-2.0 | 🆕 | mcpserver/ | 代码→知识图谱 |
| 5 | Egonex-AI/Understand-Anything | - | 待确认 | 🆕 | mcpserver/ | 交互式知识图谱 |
| 6 | affaan-m/ECC | 238k | MIT | ⚡ | Hermes/ | Agent harness(Hermes已有) |
| 7 | HKUDS/nanobot | 46k | MIT | ⚡ | 参考 | 轻量Agent框架 |
| 8 | paperclipai/paperclip | - | 待确认 | 🆕 | 参考 | Agent工作管理 |
| 9 | stablyai/orca | - | 待确认 | 🆕 | 参考 | 并行Agent舰队 |
| 10 | tinyhumansai/openhuman | - | 待确认 | ⚡ | 参考 | 个人AI(与Hermes+Lumo重叠) |
| 11 | zeroclaw-labs/zeroclaw | - | 待确认 | ⚡ | 参考 | Rust AI助手 |
| 12 | x380kkm/Live2DPet | 76 | MIT | ⚡ | NEKO/参考 | Live2D桌宠(已有NEKO) |
| 13 | kiyotakali/Miru | 59 | Apache-2.0 | ⚡ | NEKO/参考 | AI伴侣(已有Lumo) |
| 14 | neko_src_v0.8.3 | - | Apache-2.0 | ✓ | NEKO/ | NEKO后端源码 |
| 15-17 | oh-my-openagent/CodeWhale/CodexPlusPlus | - | 待确认 | ⚡ | 参考 | Agent harness(与Hermes重叠) |

---

## 四、融合参考

| # | 项目 | ⭐ | 许可 | 状态 | 学什么 |
|---|------|-----|------|------|--------|
| 1 | Open-LLM-VTuber | 10k+ | MIT | ⚡ | 语音打断状态机(Lumo缺) |
| 2 | Soul-of-Waifu | 高 | GPL-3.0⚠️ | ⚡ | 四层认知记忆(GRAG可借鉴) |
| 3 | OpenBMB/MiniCPM-Desk-Pet | 419 | AGPL-3.0⚠️ | ⚡ | Electron+llama.cpp sidecar |
| 4 | nexu-io/open-design | - | 待确认 | 🆕 | Agent驱动设计→HTML/PDF |
| 5 | karpathy/autoresearch | - | 待确认 | 🆕 | AI自动做研究 |
| 6 | xai-org/x-algorithm | - | 待确认 | 🆕 | 推荐→RAG重排 |
| 7 | chenglou/pretext | - | 待确认 | 🆕 | 文本测量→Live2D气泡 |
| 8 | AlexsJones/llmfit | - | 待确认 | 🆕 | 模型×硬件适配 |
| 9 | MemPalace/mempalace | - | 待确认 | 🆕 | 记忆基准测试 |
| 10 | koala73/worldmonitor | - | 待确认 | 🆕 | 情报聚合→RSS管道 |
| 11 | odysseus-dev/odysseus | 84k | AGPL-3.0⚠️ | ⚡ | 自托管AI工作空间 |
| 12 | OpenBMB/VoxCPM | 35k | Apache-2.0 | 🆕 | 多语言TTS(现有Edge TTS) |
| 13 | soniqo/speech-studio | 49 | Apache-2.0 | 🆕 | Tauri桌面TTS |
| 14-21 | crewAI/LightRAG/graphiti/dify/Flowise/anything-llm/mastra/agent-memory/pentest-agents | - | 已确认 | 📦 | 已有 |

---

## 五、学术 / 安全 / 基础设施 / WT

| # | 分类 | 项目 | 说明 |
|---|------|------|------|
| 1 | 学术 | pymatgen/ase/cantera/biosteam/matbench/foundry/gasification/data-resources-materials | 材料科学计算(9个已有📦) |
| 2 | 学术 | NVIDIA/nvalchemi-toolkit | GPU化学AI加速 🆕 |
| 3 | 学术 | deepchem/deepchem | 药物/材料ML全栈 🆕 |
| 4 | 安全 | Unclecheng-li/poc-lab | 25+ CVE PoC 🆕 |
| 5 | 基础设施 | emqx/EmbeddedMqttBroker | MQTT(已有📦) |
| 6 | WT插件 | 13个 | 火控/仪表/地图(已有📦) |

---

## 统计

| 分类 | 已有✓ | 缺失🆕 | 竞品⚡ | 合计 |
|------|--------|--------|--------|------|
| MCP Server | 14 | 10 | 0 | 24 |
| Skill | 2 | 7 | 2 | 11 |
| 内嵌 | 1 | 6 | 10 | 17 |
| 融合参考 | 9 | 10 | 3 | 22 |
| 学术 | 9 | 3 | 0 | 12 |
| 安全 | 0 | 1 | 0 | 1 |
| 基础设施 | 2 | 0 | 0 | 2 |
| WT | 13 | 0 | 0 | 13 |
| **合计** | **50** | **37** | **15** | **104** |

---

## 可预处理优先级

| 优先级 | 项目 | 模式 | 理由 |
|--------|------|------|------|
| **P0** | headroom | MCP | 立即可用，省95%JSON token |
| **P0** | scientific-agent-skills | Skill | 158现成Skill，33k⭐ |
| **P0** | VulnClaw | MCP | AI漏洞挖掘，MIT，Uncle城出品 |
| **P1** | caura-memclaw | MCP | 多Agent共享记忆总线 |
| **P1** | Agent-Reach | MCP | 支持B站，陆墨外部感官 |
| **P1** | DeepSec | MCP | AI安全攻防，MIT |
| **P2** | caveman + ponytail | Skill | Token省65% |
| **P2** | graphify | 内嵌 | 代码→知识图谱，Apache-2.0 |
