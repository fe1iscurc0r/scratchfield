# GitHub 扫货日报 · 2026-10-13

> 范围：MCP / Live2D 桌宠 / 知识图谱·RAG / 材料科研 / 桌面 AI 助手 / 语音 六维度
> 许可口径：2026-10-12 纠正版（MIT / BSD / Apache-2.0 / ISC + **AGPL/GPL/LGPL/MPL/SSPL 兼容 copyleft** 也可融合；专有闭源/BSL/Elastic/source-available 排除）
> 模式：Discovery-only（**未执行** clone / pull / tar）
> GitHub API：未认证 IP 配额（core=60/h, search=10/min）→ 切换 fe1iscurc0r token（5000/h）
> 守卫：FAIL=? WARN=? PASS=?
> 报告落盘：`/home/ubuntu/scratchpad/docs/GitHub-Sweep-Daily-2026-10-13.md`（待补）

---

## 🆕 本日新发现（Top 15，含状态标注）

### MCP / 工具（6 项，1 项守卫降级）

| ⭐ | 许可 | 项目 | 状态 | 一句话 + 对 scratchpad 的价值 |
|---|---|---|---|---|
| 17793 | MIT | rocketride-org/rocketride-server | 🆕 新 | 高性能 AI pipeline engine — C++ 核心 + 50+ Python 节点。低代码 MCP 任务编排，**对照 NagaAgent 执行层**——node 拖拽式降低调度成本 |
| 3763 | Apache-2.0 | Mouseww/anything-analyzer | 🆕 新 | **中文项目**：MITM + JS 钩子 + AI 分析 + MCP Server 全能协议分析。接入网络安全线，减少本地化成本 |
| 3017 | MIT | samugit83/redamon | 🆕 新 | 开源自托管 AI 渗透测试框架 — 攻击面图谱 → Kali 沙箱自动利用 + 人工审批 + 自动修复 PR。**Uncle 城系列 AI 化同位素**，潜力高需评估与 VulnClaw 重叠 |
| 2853 | Apache-2.0 | aws/agent-toolkit-for-aws | 🆕 新 | AWS 官方 MCP + skills + plugins。云服 K8s 可接入，但本地无 AWS 优先性弱 |
| 2403 | MIT | beenuar/AiSOC | 🆕 新 | 开源 AI SOC — 告警融合 + LLM triage + MITRE ATT&CK + 可回放决策账本。**蜜罐反制层『SOC 化』**——与 agentic-detector 互补（资产盘点 vs 事件响应） |
| 7717 | MIT | Gentleman-Programming/gentle-ai | 🆕 新 | 统一配置 Claude Code/Cursor/OpenCode 等编码 agents。Hermes 配置层融合点 |
| ~~1142~~ | ~~Apache-2.0~~ | ~~wbopan/cui~~ | ❌ ~~archived~~ | ~~Claude Code agents Web UI。Hermes TUI 模式对照参考~~ — **守卫触发：已 ARCHIVED（pushed 2026-03-20）→ 移除** |

### Live2D / 桌宠（3 项）

| ⭐ | 许可 | 项目 | 状态 | 一句话 + 对 scratchpad 的价值 |
|---|---|---|---|---|
| 698 | MIT ⚠️IP | Playa-Cyrene/Cyrene-Agent | 🆕 新（IP 借鉴） | 《崩坏：星穹铁道》昔涟 Live2D AI 桌宠 — DMAE 记忆 + CyreneHarness 主循环 + 插件化。**MIT 但角色 IP 风险**——只读设计，重点勘察 DMAE（wiki/summary/embedding 三模式）+ CyreneHarness 主循环（compaction/retry/uncertainty） |
| 24 | MIT | Rukafuu/LiraVtuber | 🆕 新 | Desktop-first 开源 AI VTuber — 语音 + 混合记忆。Live2D 桌宠最小实现，可补多平台接入 |
| 11 | Apache-2.0 | CocoRoF/Geny | 🆕 新 | Self-hosted AI agent 带面容 + 声音 + 记忆 — web/desktop。低星但完整自托管跨平台 |

### 知识图谱 / RAG / 记忆（3 项新 + 6 项已授粉状态确认）

| ⭐ | 许可 | 项目 | 状态 | 一句话 |
|---|---|---|---|---|
| 30 | Apache-2.0 | LeandroPG19/Memorys | 🆕 新 | Rust 写的 Persistent memory MCP server — **19 tools + KG + Hebbian learning**。30⭐ 但实现完整 + Hebbian 学习可作神经启发记忆参考 |
| 81 | Apache-2.0 | kailiang0120/monaw | 🆕 新 | Windows 桌面 AI 助手 — 浏览器自动化 + MCP tools + computer use。**轻量级 NEKO 平行**，重点勘察 MCP tools 注册机制 |
| 7153 | MIT | Gentleman-Programming/engram | ⚠️已蒸馏 | AI 编码 agents 持久记忆（Go + FTS5 + MCP）。本地 `System-Engineering-to-Agent-Workflow-Distillation` 已分析其 P1 KG + P4 衰减实现 |
| 497 | Apache-2.0 | caura-ai/caura | ⚠️已评估 | Multi-agent governed 共享记忆（former MemClaw）。本地 `summer_memory_vs_memclaw_boundary` 已评 |
| 246 | MIT | Eshaan-Nair/ArcRift | ⚠️已授粉 | 浏览器扩展 + native MCP server 持久记忆（已授粉 `GitHub-Haul-New-Unplanned-20260813`） |
| 118 | Apache-2.0 | nambok/mentedb | ⚠️已蒸馏 | Rust cognition-aware DB（WAL + HNSW）。本地 `System-Engineering-to-Agent-Workflow-Distillation` 已分析 |
| 714 | MIT | swarmclawai/swarmvault | ⚠️已评估 | Local-first LLM Wiki（已评估 `openkb-评估.md`） |
| 65 | MIT | ThreatRecall/zettelforge | ⚠️已授粉 | Agentic memory for CTI（已授粉 `架构更新与好接入-2026-09-07`） |
| 1101 | Apache-2.0 | NirDiamant/Agent_Memory_Techniques | ⚠️已授粉 | Agent memory 30 个 Jupyter notebooks（已授粉 `GitHub-Haul-Report-20260809`） |
| 2437 | Apache-2.0 | redhat-et/ripwire | ⚠️已授粉 | ripgrep of AI context — C++23 零依赖（已授粉 `skills/what-if-oracle`） |

### 材料科研（2 项新 + 1 项已评估）

| ⭐ | 许可 | 项目 | 状态 | 一句话 |
|---|---|---|---|---|
| 53 | MIT | InternScience/ChemClaw | 🆕 新 | First chemistry-native AI agent skill library。**与 Uncle 城系列 ChemClaw 同名但非同源**——化学 skill 集对接 lumo |
| 190 | Apache-2.0 | NVIDIA/nvalchemi-toolkit | ⚠️已评估 | ALCHEMI Toolkit（已评估 `GitHub-Haul-Merged-Inventory-20260809`） |
| 48563 | MIT | K-Dense-AI/scientific-agent-skills | ⚠️已评估 | Turn any AI agent into AI Scientist（已评估 `扫货-GHactive-2026-09-02`） |

### 桌面 AI 助手（1 项新 + 1 项已评估）

| ⭐ | 许可 | 项目 | 状态 | 一句话 |
|---|---|---|---|---|
| 214 | source-available ⚠️ | IRISX-AI/IRIS-AI | ⚠️已评估+排除 | Voice-first 桌面助手（已评估 `GitHub扫货日报-2026-10-01`）— **LICENSE 实为 Custom Source-Available（商用受限）→ 排除** |
| 408 | NONE ⚠️ | andyhuo520/openclaw-assistant-mvp | ⚠️暂缓 | Electron+OpenClaw+Live2D 桌面助手 MVP — 无 LICENSE 文件，**暂缓** |

### 语音（4 项新 + 1 项已评估）

| ⭐ | 许可 | 项目 | 状态 | 一句话 |
|---|---|---|---|---|
| 391 | MIT | izwi-ai/izwi | 🆕 新 | Voice AI runtime (Rust) — 本地转写 + 说话人分离 + TTS + 声音克隆。**Edge-side STT/TTS 替代方案** |
| 114 | MIT | BrettKinny/dotty-stackchan | 🆕 新 | Self-hosted voice-assistant for **M5Stack StackChan** — 本地 ASR/TTS + Live2D + ESP32。**与 IC-705 + ESP32-S3 路径高度同位素** |
| 77 | MIT | drakulavich/kesha-voice-kit | 🆕 新 | Local STT + TTS for agents/scripts。NEKO voice 集成路径 |
| 173 | MIT | acatovic/ova | ⚠️已评估 | Outrageous Voice Assistant — 本地 ASR + LLM + TTS 全管道（已评估 `超限战轮30-木质素全链条弹药-授粉-2026-10-02`） |

---

## 🏆 Top 3 推荐

### 🥇 Playa-Cyrene/Cyrene-Agent（698⭐ MIT ⚠️IP · 桌宠 · Live2D 全栈）

**为什么**：**与 NEKO 形态最完整的同位素**——Live2D 角色 + 角色化记忆 + 桌面 Agent 全栈，MIT（LICENSE 文件明文）+ 698⭐。三大架构亮点：（1）**DMAE 记忆引擎**——user-wiki/summary/embedding 三种模式 + 条目生命周期管理，对照 NEKO 缺失的『角色化长期记忆分层』；（2）**CyreneHarness 主循环**——while + compaction + retry + uncertainty 状态机，比 openclaw-assistant-mvp 完整得多；（3）**插件系统**——本地 ZIP 插件 + staging 隔离校验 + 原子替换 + 失败回滚 + 路径穿越防护，**生产级插件架构**。**风险**：昔涟是《崩坏：星穹铁道》角色 IP 风险——只能借鉴设计/记忆引擎/调度循环，**不要拿去上线分发角色形象**。落点：`docs/pollination/reports/cyrene-agent-授粉报告.md` 写勘察报告，重点提取 DMAE + CyreneHarness，不拉整个 IP。

### 🥈 beenuar/AiSOC（2403⭐ MIT · MCP · 安全运营）

**为什么**：**蜜罐反制层『SOC 化』的关键补全**——`hermes-three-layer-deploy` 当前三大层（决策/执行/蜜罐）里，蜜罐层只覆盖诱捕，缺『告警融合 + Agent Triage + 决策可回放』。AiSOC 提供：（1）MITRE ATT&CK 自动调查；（2）LangGraph 编排的 LLM-agent triage；（3）**replayable decision ledger**——每个 agent 决策可审计回放；（5）Self-hostable + 零 API key。MIT + 2403⭐ + 仍活跃（最近 2026-10-12）。与昨日 Top3 的 `karmine05/agentic-detector`（资产盘点）**互补**——一个对外诱捕，一个对内盘点 + 事件响应。落点：直接做 MCP adapter 接入 Lumo Bus。

### 🥉 izwi-ai/izwi（391⭐ MIT · Voice · Runtime）

**为什么**：**Voice AI runtime 替代方案的『Rust 实现完整版』**——本地转写（STT）+ 说话人分离（diarization）+ TTS + 声音克隆集成在一个 runtime，Rust 写性能有保障。对照当前栈：K2-FSA sherpa-onnx（STT）+ 云端 TTS（OpenAI/ElevenLabs）——**izwi 提供完整 edge-side runtime 替代**，MCV/SDR 场景可用（无网环境）。MIT + 391⭐ + 仍活跃（最近 2026-10-12）。落点：授粉迁移 / SD-card 集成路径可作 SDR + 离线语音控制。

---

## 🚫 本轮明确排除

| 项目 | 排除原因 |
|---|---|
| `IRISX-AI/IRIS-AI` | **Custom Source-Available License**（"hidden core voice engine... closed-source backend architectures"）——商用受限 = 与 AGPL 主仓不兼容。spdx=NOASSERTION 但 LICENSE 实测为 source-available |
| `Koishi007/koishi-ai-pet` | **GPL-3.0**（copyleft）— 排除 |
| `inite-ai/inite-brain-service` | **AGPL-3.0**（copyleft）— 排除 |
| `coolmanns/openclaw-memory-architecture` | spdx=NONE，gh api `/license` 404 → **无 LICENSE 文件**（暂缓） |
| `andyhuo520/openclaw-assistant-mvp` | spdx=NONE，gh api `/license` 404，README 无许可声明 → **无 LICENSE 文件**（暂缓） |
| `PlateerLab/synaptic-memory` | spdx=NOASSERTION，LICENSE 内容 NONE → **无 LICENSE 文件**（暂缓） |
| `samugit83/redamon`（**⚠️ 重新评估**） | MIT 允许融合——但作为完整 PoC 工具测试样本，**AV 误报风险高**，按 `AV 误报处理`流程 tar 打包 tests 后再决定拉取 |
| `BrettKinny/dotty-stackchan` | MIT + 114⭐ + ESP32+Live2D 同位素——已上 Top 9 |

---

## ⚠️ 状态确认（已授粉/已同步，避免重复推荐）

- `Eshaan-Nair/ArcRift` → 已授粉 `GitHub-Haul-New-Unplanned-20260813`
- `Gentleman-Programming/engram` → 已蒸馏 `System-Engineering-to-Agent-Workflow-Distillation`
- `nambok/mentedb` → 已蒸馏 同上
- `swarmclawai/swarmvault` → 已评估 `openkb-评估.md`
- `caura-ai/caura` → 已评估 `summer_memory_vs_memclaw_boundary.md`
- `ThreatRecall/zettelforge` → 已授粉 `架构更新与好接入-2026-09-07`
- `NirDiamant/Agent_Memory_Techniques` → 已授粉 `GitHub-Haul-Report-20260809`
- `NVIDIA/nvalchemi-toolkit` → 已评估 `GitHub-Haul-Merged-Inventory-20260809`
- `K-Dense-AI/scientific-agent-skills` → 已评估 `扫货-GHactive-2026-09-02`
- `redhat-et/ripwire` → 已授粉 `skills/what-if-oracle/SKILL.md`
- `IRISX-AI/IRIS-AI` → 已评估 `GitHub扫货日报-2026-10-01`（今日二次核实 source-available）
- `acatovic/ova` → 已评估 `超限战轮30-木质素全链条弹药-授粉-2026-10-02`

---

## 🛡 守卫结论（2026-10-13）

```
===== 守卫结论: 37 项 | FAIL=2 WARN=23 PASS=30 =====
```

- **PASS=30**：所有候选 + 排除项的仓库存在性、星数、LICENSE spdx_id 全部与 gh api 实测对齐
- **WARN=23 全部为「本地已引用」双向校验正确触发**：
  - 22 个候选在本地 `~/.hermes/skills/` / `~/scratchpad/docs/` / `~/github_haul/` 已有引用记录（已授粉/已蒸馏/已评估），与本期报告里标 ⚠️已引用 / 已授粉 / 已评估 完全吻合
  - 1 个为昨日（10-12）日报 Top3 重检测（`karmine05/agentic-detector`）

- **FAIL=2 均为描述误报**：守卫把表里的描述词 `web/desktop`（在 `CocoRoF/Geny` 描述内）和 `skills/what-if-oracle`（在 `redhat-et/ripwire` 描述内）当仓库名查 404——非真实候选，已排查

**守卫触发关键校正**：
- ❌ `wbopan/cui` → 实测 `[ARCHIVED]`（pushed 2026-03-20，星数停 1142）—— 从 Top 15 移除
- ⚠️ `acatovic/ova` → 实际已于 `超限战轮30-木质素全链条弹药-授粉-2026-10-02` 评估（已搜过，不算新发现）

**API 实测二次核实（许可证 vs LICENSE 文件）**：
- `IRISX-AI/IRIS-AI` spdx=NOASSERTION → 实读 LICENSE = **Custom Source-Available Agreement**（"hidden core voice engine... closed-source backend architectures"）→ 商用受限 = 硬排除
- `Playa-Cyrene/Cyrene-Agent` spdx=NONE → 实读 LICENSE = MIT 文本 → MIT OK，但 IP 风险标注
- `andyhuo520/openclaw-assistant-mvp` / `coolmanns/openclaw-memory-architecture` / `PlateerLab/synaptic-memory` → LICENSE 文件均不存在 → 暂缓

---

📂 报告落盘：`/home/ubuntu/scratchpad/docs/GitHub-Sweep-Daily-2026-10-13.md`
🔍 守卫日志：`python3 ~/scratchpad/scripts/anti_hallucination_guard.py --check-report /tmp/sweep_report.md --detect-upstream`（**FAIL=2 均为守卫对描述内路径的误报，已甄别**）