# GitHub 扫货日报 — 2026-10-18

**扫描**：6 维度 × 35 条查询 → 617 原始候选 → 对照近 5 期日报 + 历史文档去重 → 143 项 `gh api` 补 license/archived → 铁条件过滤 → **15 项入表（新发现 12 + 状态修正/复扫 3）**
**模式**：Discovery-Only（只发现 + 评估，**未** clone / pull）
**许可口径**：2026-10-12 纠正版（MIT/BSD/Apache/ISC ✅；AGPL/GPL/LGPL/MPL/SSPL ✅ 可融合；专有/BSL/Elastic/source-available ❌；无 LICENSE ⚠️暂缓）
**核实**：星数与许可全部 `gh api repos/*` 实测，关键项再走 `repos/*/license` 文件级二次确认

---

## ① Hermes 插件生态（本日最大发现：生态已成规模）

| 项目 | ⭐ | 许可 | 分类 | 一句话 | 对 scratchpad 的价值 |
|---|---|---|---|---|---|
| `rlaope/oh-my-hermes` | 3420 | MIT | 插件/记忆 | Hermes 全家桶插件：长期记忆 + 技能管理 + 模型路由 + 编码智能 | 🆕 已有人在 Hermes 上做「记忆+技能+路由」三合一——正是 lumo 侧现在的手工活。重点看它的记忆 schema 与技能选择策略（我们的记忆已 98% 占用） |
| `stephenschoettler/hermes-lcm` | 1279 | MIT | 上下文引擎 | Hermes 的无损上下文管理插件：DAG 式上下文引擎（lossless context management） | 🆕 **直击上下文膨胀**：用 DAG 替代线性摘要，与 headroom 的「压缩」是正交两条路，可三方对比出 SPEC；227 open issue = 有真实用户在压测 |
| `NousResearch/hermes-official-plugins` | 315 | MIT | 官方插件 | Nous 官方维护的 Hermes 插件集（10-10 新建，10-17 仍在推） | 🆕 **插件契约权威范本**：lumo 与 NEKO 要做的插件应照这份 manifest 与 packaging 组织，省掉自己发明协议 |
| `allmodels-io/hermes-speech` | 202 | MIT | 语音插件 | Hermes 形态的 TTS + STT 插件（AllModels 语音模型与音色） | 🆕 NEKO 语音层缺的正是「插件化 TTS/STT 接入点」——抄它的 provider 抽象，而不是重写一套 |

## ② 记忆 / RAG

| 项目 | ⭐ | 许可 | 分类 | 一句话 | 对 scratchpad 的价值 |
|---|---|---|---|---|---|
| `akitaonrails/ai-memory` | 9924 | MIT | 记忆（Rust） | 编码 CLI 的长期记忆 + agent 间交接（handoff） | 🆕 重点看 **handoff 协议**：云服 / 天选7 / Kali 多实例之间交接状态，目前没有标准结构 |
| `itechmeat/open-second-brain` | 487 | MIT | 记忆（Obsidian） | 本地优先的 Hermes 记忆，直接落在 Obsidian vault 内 | 🆕 与已有 `obsidian` skill 同向：记忆做成可读 md 而非黑盒 DB，正好治「记忆看不见、改不动」 |

## ③ Live2D / 桌宠

| 项目 | ⭐ | 许可 | 分类 | 一句话 | 对 scratchpad 的价值 |
|---|---|---|---|---|---|
| `rullerzhou-afk/clawd-on-desk` | 6469 | AGPL-3.0 | 桌宠 | 像素桌宠实时显示 Claude Code / Codex / Cursor 等编码 agent 的运行状态 | ⚠️**复扫纠正**：10-03、10-12 两期按旧口径（AGPL 一律排除）剔除，**10-12 纠正后可融合**。价值：把「agent 运行态」映射成桌宠动作状态机——NEKO 目前只有静态交互，缺这层状态驱动 |
| `X-T-E-R/OpenPet` | 57 | GPL-3.0 | 桌宠运行时 | 本地桌宠运行时，宠物可导入，暴露 **CLI / MCP / HTTP 三套 API** 给 agent 控制 | 🆕 把桌宠当**服务**而不是进程内嵌：MCP 控桌宠 = NEKO 可被 Hermes 工具直接驱动。⚠️ 最后 push 2026-05-06，5 个月不活跃 |

## ④ 桌面 AI 助手 / 计算机控制

| 项目 | ⭐ | 许可 | 分类 | 一句话 | 对 scratchpad 的价值 |
|---|---|---|---|---|---|
| `AMAP-ML/LongHorizon-Harness` | 1750 | MIT | computer-use | 长时程 computer-use 试验台：让 agent 跨桌面应用与 CLI 连续作业 | 🆕 长任务「不崩、不断、可恢复」的 harness 结构，正对我们多步链（扫货→授粉→落地）容易断在中间的毛病 |
| `agent-sh/computer-use-linux` | 706 | MIT | 桌面控制（Rust） | Linux 原生桌面控制 MCP：语义化 AT-SPI 树 + 截图，非坐标盲点 | 🆕 补上 Linux 侧「真·操作桌面」能力（当前只有 shell）；AT-SPI 语义树比坐标点击稳得多 |

## ⑤ 语音

| 项目 | ⭐ | 许可 | 分类 | 一句话 | 对 scratchpad 的价值 |
|---|---|---|---|---|---|
| `k2-fsa/OmniVoice` | 14702 | Apache-2.0 | TTS/克隆 | 高质量零样本克隆 TTS，覆盖 600+ 语言 | 🆕 多语言 + 换音色的现成弹药；纯 PyTorch、依赖轻，是 AudioCraft 与 Fish 之外的一条干净 Apache 路线 |
| `OpenMOSS/MOSS-TTS-Nano` | 4505 | Apache-2.0 | TTS（端侧） | 1 亿参数多语言 TTS，**CPU 实时**推理 + 克隆 | 🆕 「CPU 也能跑」= 云服无 GPU 时 NEKO 仍能出声，正好做低功耗模式下的兜底语音 |

## ⑥ 材料 / 化学

| 项目 | ⭐ | 许可 | 分类 | 一句话 | 对 scratchpad 的价值 |
|---|---|---|---|---|---|
| `kairosmaterial/prophet` | 55 | MIT | 原子势 | 面向材料模拟与发现的原子间势基础模型（atomistic foundation models），研究预览 | 🆕 木质素 / 水凝胶做力学热学之前的势函数层；与已入库 MACE、deepmd-kit 同赛道，可作轻量对照基线 |
| `Hello-QM/catgo-LRG` | 207 | AGPL-3.0 | 科研工作台 | 计算材料学 AI 工作台：交互式 3D 结构可视化 + 计算流程编排 | ⚠️**复扫增量**（09-02 材料软件清单已扫）：AGPL 现按 10-12 口径可融合；重点看它的 3D 结构 viewer 怎么接进 lumo 科研前端 |

---

## Top 3 推荐

1. **`stephenschoettler/hermes-lcm`（1279★ MIT）** — 上下文/记忆膨胀是我们最贵的结构性问题（记忆 98%、压缩全靠 headroom）。它用 DAG 做「无损」上下文管理，和压缩路线的思路正好互补；227 个 open issue 说明这不是玩具，能直接读出别人踩过的坑。落地方式是纯旁路，不碰主链路。
2. **`NousResearch/hermes-official-plugins`（315★ MIT）** — 星数最低但**最省未来的钱**：官方插件契约（manifest + packaging + 注册）一旦照抄，lumo 与 NEKO 的插件化不用再自己发明协议，也不会跟上游 Hermes 版本演进打架。
3. **`k2-fsa/OmniVoice`（14702★ Apache-2.0）** — 语音层要的「多语言 + 换音色 + 许可干净」它三项全占，且不是重框架。NEKO 多角色音色可以一步到位，不必在 AudioCraft 与 Fish 的许可/依赖上纠缠。

> 备注：**`rlaope/oh-my-hermes`（3420★）是今日最高星新发现**，但定位偏「编码 CLI 的智能与模型路由」，对伴侣/科研线是半相关，故不进 Top3，列 ① 首位待评估。

## 📦 状态修正 / 已扫（禁止当新发现立项）

- **已扫（10-04 已推荐为架构对照组）**：
  - `momori777/Artemis` 392★ Apache-2.0（LICENSE 原文已核实；10-04 报 374★ → 今 392★）——与 NEKO+Lumo 定位同构，**无需重复立项，直接进架构对比**
- **已授粉**：
  - `liwenka1/bongo-cat-next` 151★ MIT（`coupled/bongo-cat-next/`，见 `docs/bongo-cat-next-桌宠授粉-2026-09-09.md`）
- **已入流水线（不重复拉）**：
  - `NanmiCoder/cc-haha` 15050★ NOASSERTION（`docs/fusion-candidates-2026-10/NanmiCoder-cc-haha.md` + `TRAE_WORKORDER_PROMPT_AGENT_209.md`）
  - `lulu930128/desktop-agent-runtime` 8★ Apache-2.0（`GitHub-Haul-Report-20260809` 已录）
- **本地同源上游（只做同步，不当授粉对象）**：
  - `Graphify-Labs/graphify` 127800★ Apache-2.0（本地 `graphify` skill 上游）
  - `headroomlabs-ai/headroom` 75590★ Apache-2.0（本地 context-compression skill 上游）
- **排除 / 暂缓**：
  - `DevAgentForge/Open-Claude-Cowork` 3396★ 无 LICENSE（10-01 已排）
  - `apify/apify-mcp-server` 11733★ MIT 但需 APIFY_TOKEN 付费云依赖
  - `skalesapp/skales` 2195★ NOASSERTION
  - `swarmclawai/swarmvault` 722★ MIT（已评估 `openkb-评估.md`）
  - `DasterProkio/awesome-ai-companion` 999★ CC-BY-4.0（目录类）
  - `wildminder/awesome-ai-voice` 516★ MIT（目录类）
  - `alterhq/openpets` 105★ MIT（仅 macOS）
  - `BinaryFroggy/Hopet` 63★ MIT（仅 macOS）
  - `NousResearch/hermes-agent-self-evolution` 5515★ 无 LICENSE 文件（暂缓）
  - `ksimback/hermes-ecosystem` 1321★ 无 LICENSE（Hermes Atlas 目录，暂缓）
  - `rainnoon/oc-claw` 359★ NOASSERTION（暂缓）
- **备选（贴手，未入前 15）**：
  - `AtlasOmnia/hermes-tool-router` 131★ MIT（Hermes 确定性工具路由 + 本地模型兜底）
  - `42-evey/hermes-plugins` 531★ MIT
  - `Graphicle-AI/graphicle` 261★ Apache-2.0（Rust 代码图记忆）
  - `Humalike/hermes-humalike-plugin` 211★ MIT（聊天拟人化）
  - `8bit64k/cronalytics` 112★ MIT（cron 可观测性，对上现有 20+ cron）
  - `K-Dense-AI/drug-discovery-agent-skills` 42★ MIT
  - `HolobiomicsLab/asb-skill-collections` 16★ Apache-2.0（科研 skill 集合）

**守卫结论**：FAIL=0 / WARN=20（WARN 两类均已处置：①本地已引用项已在「状态修正」区标注为已扫/已授粉/上游；②无 LICENSE / NOASSERTION 项已按铁条件暂缓。星数全部 `gh api` 实测，无灌水）
