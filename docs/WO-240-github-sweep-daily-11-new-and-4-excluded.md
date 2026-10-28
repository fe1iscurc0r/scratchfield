# 工单 240 · GitHub 扫货日报（10-15）· 11 个新候选立项评估 + 4 个排除项二级核验 + 22 个 haul 重复项归档

> **⚠️ 交付状态（2026-10-17 沈遥复核）**：交付物未落地 —— `docs/` 下无 11 候选评估文件，`docs/GitHub-Sweep-Daily-*` 最新仍停在 **2026-10-13**，`/tmp/issue_bodies/` 草稿不可追溯（/tmp 已清）。
> **处置（师傅 2026-10-17「你看着办」授权）**：**不复活**。理由：本单是 10-15 那一期 sweep 的**时点性**产物，候选窗口已被 10-16 之后的日报自然覆盖；旧候选若要重评，走当期日报即可，重开旧单只增加口径分叉。若某个候选确实重要，由最新日报重新提出。

> ⚠️ **编号体系**：本文件是**施工记录**（记录 WO-240 这一号实际完成了什么）。仓库根另有**指令文件** `TRAE_WORKORDER_PROMPT_AGENT_240.md`。
> 两套编号借用了同一批数字，**内容不是同一件事**；引用时请写全路径区分（`docs/WO-240-*` = 施工记录 / 根 `TRAE_WORKORDER_PROMPT_AGENT_240.md` = 指令）。

> 委托方：用户 · 执行：Trae（GitHub 线，仓库 `fe1iscurc0r/scratchpad`）· 出单：沈遥 · 日期：2026-10-15
> **触发**：师傅 10-15 13:18 在 QQ 下令"把这三个 cron 产出转成工单"（授粉 / 论文 / 日报），本单负责**日报**那条
> **素材漏斗**：6 维度 × 13 查询 → 37 候选去重 → **真正新增 11 个** + 边界 4 个 + 排除 4 个 + 已有 22 个
> **cron 触发源**：`a37ffecbd730` GitHub 扫货日报（`0 9 * * *`），今天 09:06:21 跑批产出 = 本工单触发源
> **报告原文**：`/home/ubuntu/.hermes/cron/output/a37ffecbd730/2026-10-15_09-06-21.md`（1043 行 / 78 KB）
> **归档索引**：`/home/ubuntu/github_haul/SWEEP-2026-10-15.md`（已落盘）
> **守卫结论**：✅ FAIL=0 / WARN=21（21 项已全部处置：标"已融合/上游"或 NOASSERTION 二次核实）

## §0 · 沈遥已执行动作（自检 + 数据搬运）

| # | 动作 | 状态 | 备注 |
|---|------|------|------|
| 1 | 读 09:06 跑批产出（1043 行 / 78 KB） | ✅ | SKILL.md 头 + Response 段全抓 |
| 2 | 校验 11 个新候选 star 数 | ✅ | 全部 gh api 实测，零偏差 |
| 3 | 校验 4 个排除项实际许可 | ✅ | 全部 NOASSERTION 二次核实 |
| 4 | 校验 22 个 haul 重复项 | ✅ | 与 `github_haul/` 目录、`SWEEP-2026-09-29.md` 等历史报告 grep 对照 |
| 5 | 校验守卫 FAIL=0 | ✅ | 反幻觉守卫自检通过 |

---

## §1 · 工单目标

| 维度 | 内容 |
|------|------|
| **S** Specific | 对今天 11 个新候选按"P0 接入 / P1 仅授粉 / P2 暂缓"三档分桶 + 4 个排除项做"许可可信度"二级核验 |
| **M** Measurable | ① 11 个新候选每落 1 份评估 md（项目 / 协议 / 架构 / 授粉价值 / 难度×收益 / 接入模式）；② 4 个排除项落 1 份"为什么排除 + 反向激活路径"；③ 22 个 haul 重复项落 1 份"已存在索引"表 |
| **A** Achievable | 全部候选已在报告中标好星数 / 协议 / 分类，不需重新 gh api 拉数据 |
| **R** Relevant | 师傅四条主方向：MCP / Live2D 桌宠 / 知识图谱记忆 / 材料科研 + 桌面 AI 助手 + 语音 |
| **T** Time-bound | 1 周（W1 评估 + 立项决策，W2 接入 P0）|

---

## §2 · 11 个新候选·三档分桶

### 🥇 P0 接入候选（**最高价值** / W2 重点施工）

#### P0-1 · agentic-community/mcp-gateway-registry — 981★ Apache-2.0
- **分类**：MCP 基础设施
- **授粉价值**：企业级中央 MCP Gateway + Registry（OAuth 鉴权 + 动态发现）；与 scratchpad 当前 mcpserver 散装完全对接
- **接入模式**（参考日报 SKILL 562-583"五层分类"）：**MCP** —— `agent-manifest.json` + Python class → `mcpserver/mcp_gateway/`
- **目标**：
  1. 抽中央 registry 模式 → Lumo bus MCP 路由子模块吸收
  2. 抽 OAuth 鉴权 + 动态发现 → NEKO harness 鉴权门（与 WO-239 任务 B-2 Object-Bound 协同）
  3. 写 mcp_gateway/agent-manifest.json + handler（Registry 拉取 / 鉴权 / 路由）
- **运行时依赖**：无（Python + requests）

#### P0-2 · PV-Bhat/vibe-check-mcp-server — 501★ MIT
- **分类**：MCP
- **授粉价值**：防过度工程/隧道视野的 mentor 反馈工具；TS 极轻量；「mentor 视角」是 scratchpad 当前未覆盖的 self-correction hook
- **接入模式**：**MCP** —— `mcpserver/vibe_check/`
- **目标**：
  1. 抽「mentor 视角」三步评估（建设性 / 风险 / 建议）
  2. 接入 NEKO harness 作为"自检 hook"——长 Agent 任务每 5 步调一次 vibe_check
  3. 写 mcp_gateway 注册
- **运行时依赖**：Node 24+（标注，但不阻塞接入）

### 🥈 P1 仅授粉候选（**设计参考** / W1 评估后入仓）

#### P1-1 · krillinai/OpenCreator — 13066★ Apache-2.0
- **分类**：桌面 AI 融合参考
- **授粉价值**：前身 KrillinAI，视频翻译+配音桌面工作台（Codex 驱动 + Skills）；**Skills 模块化设计**可授粉
- **接入模式**：**融合参考** —— 走 `docs/授粉报告/KrillinAI-Skills-Modular.md`，**384MB 大体积不整包 clone**，走 API 读 schema
- **关键提取**：Skills 注册表 / 模块加载顺序 / Codex-driven 工作流

#### P1-2 · vocodedev/vocode-core — 3802★ MIT
- **分类**：语音框架融合参考
- **授粉价值**：STT→LLM→TTS 全链路抽象，VAD 切音策略成熟；与 NEKO 语音栈直接对应
- **接入模式**：**融合参考** —— `docs/授粉报告/Vocode-VAD-Speech-Stack.md`
- **关键提取**：VAD 切音策略 / 全链路抽象层 / 语音 ↔ 文本桥接
- **与已有 OpenArc 对比**：写一份"OpenArc vs Vocode"差异分析

#### P1-3 · aws/agent-toolkit-for-aws — 2877★ Apache-2.0
- **分类**：MCP 融合参考
- **授粉价值**：⚡ 与 googleapis/mcp-toolbox 同位类；授粉价值在 **Skill+Plugin 打包模式**
- **接入模式**：**融合参考** —— `docs/授粉报告/AWS-Toolkit-Packaging.md`

#### P1-4 · vmoranv/jshookmcp — 2045★ AGPL-3.0
- **分类**：MCP 融合参考（**仅设计**）
- **授粉价值**：735 工具跨 36 域的逆向工程 MCP；工具 registry/编排模式极成熟
- **接入模式**：**只读 schema 不并包**（AGPL-3.0 强 copyleft，整包吞入会强制主仓全部源码公开——日报 SKILL 1035 行铁律）
- **关键提取**：工具 registry / 编排 / 域分类

#### P1-5 · jofizcd/Soul-of-Waifu — 1394★ GPL-3.0
- **分类**：Live2D 融合参考（**仅设计**）
- **授粉价值**：Live2D/VRM 桌面角色扮演伴侣
- **接入模式**：**只读 schema 不并包**（GPL-3.0 整包吞入会强制主仓源码公开——日报 SKILL 1035 行铁律）
- **关键提取**：Live2D 资源加载 / 角色状态机 / 互动层抽象

### 📦 P1-2 旁路 / 备查

#### P1-6 · inni918/warashi — 119★ MIT
- **分类**：Live2D 融合参考
- **授粉价值**：基于 Open-LLM-VTuber 的桌面伴侣（Live2D+长记忆+主动对话）；与 NEKO 同源更新版；VOICEVOX 整合路径可借鉴
- **接入模式**：**融合参考** —— `docs/授粉报告/Warashi-Open-LLM-VTuber-Derivative.md`
- **运行时依赖**：无

#### P1-7 · vbcherepanov/total-agent-memory — 73★ MIT
- **分类**：记忆融合参考
- **授粉价值**：时序 KG + 本地持久记忆；与 mcp-memory-service/caura 同位
- **接入模式**：**融合参考** —— `docs/授粉报告/Total-Agent-Memory-Temporal-KG.md`
- **与已有同位类对比**：写"mcp-memory-service / caura / total-agent-memory"三方对比

#### P1-8 · tteon/seocho — 59★ MIT
- **分类**：记忆融合参考
- **授粉价值**：本体对齐的 agentic 图谱记忆中间件；59★ 低星但命中 AI 未吃透的"本体论"甜点区
- **接入模式**：**融合参考** —— `docs/授粉报告/Seocho-Ontology-Alignment-Memory.md`
- **关键提取**：本体对齐 schema / 图谱记忆中间件

#### P1-9 · paiml/paiml-mcp-agent-toolkit — 165★ MIT
- **分类**：MCP
- **授粉价值**：Rust 实现，封装成 mcpserver/ 成员
- **接入模式**：**MCP** —— `mcpserver/paiml_mcp_toolkit/`
- **运行时依赖**：Rust 工具链（标注）

---

## §3 · 4 个排除项·二级核验（**不能信 spdx_id**）

日报 SKILL 第 1023 行铁律："本日 NOASSERTION badge 4 例中 3 例是 source-available/商业限制——必须读 LICENSE 文件原文，不能凭 spdx_id 拍板"。本任务做"二次核验"：

| # | 项目 | ⭐ | API 标 | 实际许可 | 排除原因 | 反向激活路径 |
|---|------|-----|--------|----------|----------|--------------|
| 1 | voquill/voquill | 1014 | NOASSERTION | Voquill Enterprise | enterprise 目录走企业 license | 不可激活（企业 license，无个人非商用路径）|
| 2 | rapidaai/voice-ai | 746 | NOASSERTION | modified GPL-2.0 + 限制 | GPL-2.0 加额外商业限制 | 不可激活（双重限制叠加）|
| 3 | TEN-framework/ten-framework | 11163 | NOASSERTION | Apache 2.0 + Agora 限制 | 禁止与 Agora 竞争 | **可激活**（非 Agora 竞争场景可用，写"NON-AGORA-USE"声明）|
| 4 | neo4j-labs/meta-knowledge-graph | 32 | NOASSERTION | 无 LICENSE | 默认保留所有权利 | **可激活**（代发 issue 询问，可走日报 SKILL 480 行萌新小白话术）|

**验收 grep/assert**：
```bash
# 1. 4 份二级核验 md 落盘
ls scratchpad/docs/sweep-2026-10-15-excluded-4/*.md | wc -l  # = 4
# 2. TEN-framework 反向激活路径：写一份"NON-AGORA-USE 声明"草稿
ls scratchpad/docs/sweep-2026-10-15-excluded-4/TEN-framework-NON-AGORA-USE-declaration.md
# 3. neo4j-labs/meta-knowledge-graph issue 草稿（参考日报 SKILL 475-487"外部 issue 起草铁律"）
ls /tmp/issue_bodies/neo4j-labs-meta-knowledge-graph.md  # 先给师傅过目
```

---

## §4 · 22 个 haul 重复项·归档索引（**只记录** / 不重推）

日报 SKILL 1029 行已明列 22 个 haul 重复项。本任务只生成 1 份**"已存在索引"表**（`scratchpad/docs/sweep-2026-10-15-haul-repeat-22.md`），不重推任何代码。

| 类别 | 项目示例 | 状态 |
|------|----------|------|
| 已融合 | headroom (scratchpad context_compressor 已覆盖) | ⚡ |
| 已在 haul | airi 50394★ MIT、mcp-memory-service、caura、cortexdb、kektordb、pipecat、speech-to-speech、agentshield 等 | 📦 |
| 已在授粉报告 | ArcRift、Live2DPet、Miru、graph-rag-agent、nvalchemi-toolkit、ARPAHLS-avatar | 📄 |
| 文档/MCP 站点 | MicrosoftDocs | 🌐 |
| **与本地 fork 同源**（日报 SKILL 155-164 行 Pitfall）| airi (589MB) | 🆙 上游 |

**特别警示（日报 SKILL 1037 行铁律）**：
> headroom = scratchpad `apiserver/context_compressor.py` 已实现的**功能重叠**（8-21 教训），绝不能再次推荐为"新发现"

**验收 grep/assert**：
```bash
ls scratchpad/docs/sweep-2026-10-15-haul-repeat-22.md  # 1 份索引
grep -c '| ⚡ | 已融合 |' scratchpad/docs/sweep-2026-10-15-haul-repeat-22.md  # ≥ 1
grep -c '| 📦 | 已在 haul |' scratchpad/docs/sweep-2026-10-15-haul-repeat-22.md  # ≥ 10
```

---

## §5 · 仓库与文件落点

- **工单 doc**：`scratchpad/docs/WO-240-github-sweep-daily-11-new-and-4-excluded.md`（本文件）
- **9 份新候选评估 md**：
  - P0：`scratchpad/docs/sweep-2026-10-15-new/P0-1-mcp-gateway-registry.md`、`P0-2-vibe-check-mcp-server.md`
  - P1：`P1-1-krillinai-OpenCreator.md` ... `P1-9-paiml-mcp-agent-toolkit.md`
- **4 份排除项核验**：`scratchpad/docs/sweep-2026-10-15-excluded-4/*.md`
- **1 份 haul 索引**：`scratchpad/docs/sweep-2026-10-15-haul-repeat-22.md`
- **mcpserver 接入**（P0-1 / P0-2 / P1-9）：`scratchpad/mcpserver/<name>/`
- **TEN-framework 声明草稿**：`scratchpad/docs/sweep-2026-10-15-excluded-4/TEN-framework-NON-AGORA-USE-declaration.md`
- **neo4j issue 草稿**：`/tmp/issue_bodies/neo4j-labs-meta-knowledge-graph.md`（先给师傅过目再发）

---

## §6 · 风险与边界

| 风险 | 缓解 |
|------|------|
| 11 个新候选中 2 个是 AGPL/GPL-3.0（P1-4 vmoranv/jshookmcp / P1-5 jofizcd/Soul-of-Waifu）| 严格走"只读 schema 不并包"（日报 SKILL 1035 行铁律）|
| 384MB / 589MB / 207MB 大体积（OpenCreator / airi / pipecat）| 不整包 clone，走 API 读 schema |
| TEN-framework 反向激活需要写"NON-AGORA-USE"声明 | 草稿先过师傅 |
| neo4j-labs 32★ 低星 + 无 LICENSE | 走日报 SKILL 480 行萌新小白话术（**先草稿**给师傅过目）|
| vibe-check-mcp-server 需 Node 24+ | 标注运行依赖，不阻塞接入 |
| paiml-mcp-agent-toolkit 需 Rust 工具链 | 标注运行依赖，不阻塞接入 |

**不在本工单范围**：
- WO-238 授粉-轮 41 弹药入仓（独立工单）
- WO-239 论文限流护栏（独立工单）
- 22 个 haul 重复项**重新入仓**（只归档，不重推）
- 已有授粉报告（轮 30-41）的回看

---

## §7 · 验收不变量

```bash
# 1. 11 个新候选评估 md 全部存在
ls scratchpad/docs/sweep-2026-10-15-new/*.md | wc -l  # ≥ 9（airi 等已有 haul 重复项不算）

# 2. P0 接入代码
ls scratchpad/mcpserver/mcp_gateway/ scratchpad/mcpserver/vibe_check/ 2>/dev/null
# 期望 2 个目录存在 + 各有 agent-manifest.json

# 3. 4 份排除项核验
ls scratchpad/docs/sweep-2026-10-15-excluded-4/*.md | wc -l  # = 4

# 4. 1 份 haul 索引
ls scratchpad/docs/sweep-2026-10-15-haul-repeat-22.md  # = 1

# 5. 反向激活路径就位
ls scratchpad/docs/sweep-2026-10-15-excluded-4/TEN-framework-NON-AGORA-USE-declaration.md
ls /tmp/issue_bodies/neo4j-labs-meta-knowledge-graph.md

# 6. 守卫
python3 ~/scratchpad/scripts/anti_hallucination_guard.py --check-report /tmp/wo240_final.md --detect-upstream
# 期望输出：FAIL=0
```

---

## §8 · 与已有工单的关系

| 现有 | 关系 |
|------|------|
| cron `a37ffecbd730` GitHub 扫货日报 | **数据源** |
| WO-238 授粉-轮 41 弹药入仓 | **协同**（P1-1 OpenCreator 的 Skills 模式 vs WO-238 的 CRNN 接入）|
| WO-239 论文限流护栏 | **协同**（P0-2 vibe_check 的 self-correction hook ↔ WO-239 任务 B-2 Object-Bound 鉴权门）|
| `github_haul/SWEEP-2026-10-15.md` | **基线**（日报自归档）|
| `github_haul/FUSION-LOG-*.md` | **增量**（本工单完成后追加 FUSION-LOG-2026-10-15.md）|

---

> 沈遥出单 · 师傅 1 句话确认/调整后转 Trae
