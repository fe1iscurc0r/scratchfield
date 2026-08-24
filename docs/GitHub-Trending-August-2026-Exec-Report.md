# GitHub Trending 2026-08 — 三轮落地评估报告

> 承接：`GitHub-Trending-August-2026-Action-Plan.md`（6 项目待行动）
> 状态：**6 项目全部完成评估**（GridSetup / reverse-skill / agent-skills / block-buzz / prime-agent / ShadowBroker）
> 执行人：主 Agent（离线分析，沙箱无法 clone/装包）
> 日期：2026-08-09（首轮）/ 2026-08-12（补完剩余 3 项）

---

## 一、执行摘要

| 项目 | 原优先级 | 实际相关性修正 | 结论 |
|------|---------|---------------|------|
| **GridSetup (GRID v2)** | 高 | **radio 模块与 IC-705 无关**（纯网络 SDR） | 不嫁接到 N.E.K.O. radio 层；**记忆引擎 + 自我技能可借** |
| **reverse-skill** | 中 | 机制可借（tool-index + OS 路由）但高权限工具链落地受限 | 借鉴设计，不整体集成 |
| **agent-skills** | 高 | 战略对齐，SKILL.md 结构已高度兼容 | 保持自主，做映射表即可 |
| block/buzz | 低 | 密码学签名 Agent 身份（Nostr）与 N.E.K.O./陆墨契合 | 概念验证，观察不急于集成 |
| prime-agent | 低 | RLM + Continual Harness 自我改进 | 借鉴 `/refine` 补丁层思想，不迁移 |
| ShadowBroker | 中 | 60+ 数据源 + 35+ 图层融合 | 数据源清单 + 图层架构参考 |

---

## 二、GridSetup (GRID v2) — 结论修正

### 仓库事实
- **许可**：MIT（可直接合入）
- **形态**：单进程本地 Agent，`python grid_agent.py`
- **16 能力组**：OSINT / 网络 recon / SDR / 卫星 / 单片机 / CV / 自动化 / 记忆

### 🎯 关键修正：`grid_radio.py` 与 IC-705 无关
实际抓取 `grid_radio.py` 源码确认其 SDR 层只含 **3 种纯网络 SDR**：
```
1. Radio-Browser.info API（免费，无需 key）
2. KiwiSDR 公共服务（kiwisdr.com 公共目录）
3. RTL-SDR（可选，USB 软件无线电）
```
**不含 IC-705 / CI-V / RemoteUtility / 电台硬件控制**。因此：
- ❌ 不能作为 N.E.K.O. radio 层（IC-705 链路）的现成实现
- ✅ 但它验证了"纯软件 SDR + 记忆"的轻量思路，与我们的 SDR 交叉栈（如 Kali 侧 SDR 管道）可参考

### ✅ 真正值得借鉴：分层记忆引擎（L0-L3 + DuckDB）
这是 GRID 对外宣传的差异化卖点，且**零新依赖**（DuckDB）：
| 层 | 内容 | 存储 |
|----|------|------|
| L3 Persona | 持久事实/偏好 | `grid_persona.md` |
| L2 Scenarios | 完成任务摘要 | DuckDB `memory_scenarios` |
| L1 Atoms | 独立事实陈述 | DuckDB `memory_atoms` |
| L0 Transcript | 原始对话 | `memory.md` |
| Refs | 完整工具输出（脱载） | `refs/<id>.md` |

核心机制：
1. **每 5 轮自动蒸馏**：`Recaller.distill()` 抽取原子事实/场景/人设增量
2. **每轮关键词召回注入**：`_build_messages()` 只注入与当前请求相关的记忆
3. **工具输出脱载**：>800 字符的工具结果写 whole 到 refs/，模型只拿摘要 + ref id

**与我们的对照**：我们的 summer_memory/（GRAG 五元组 + Neo4j + 向量）更重；GRID 的 DuckDB 关键词召回是**轻量旁路**，适合小规模场景。可考虑在 rag/ 旁路评估 DuckDB 关键词召回（呼应授粉计划 Tier 1 的 SQLite FTS5 思路）。

### 附：GRID 内嵌的 `grid_skills.py`（自我技能）
支持自我创作可复用技能，与 reverse-skill 的 skills 体系同源。可作为我们 Skill 体系"自我创作"能力的参考。

---

## 三、reverse-skill — 技能路由机制拆解

### 仓库事实
- **定位**：网络安全任务的 **AI Agent Skill Router**（逆向/渗透/CTF）
- **目标读者是 AI**：`README_AI.md` 明确"for AI agents only"，人类应读 README.md

### 核心机制（值得借鉴）
1. **运行时 tool-index 生成**
   ```
   refresh-tool-index.ps1/sh → 生成 tool-index.md + tool-index.json
   ```
   不信任某次扫描结果，迁移机器后必须刷新。tool-index 记录本机有哪些工具、在哪、哪些脚本调用。

2. **OS 自动路由**
   ```
   Windows → README_AI.md + *.ps1
   Kali    → kali/README-kali.md + bootstrap-reverse.sh
   Linux   → docs/platforms/linux.md
   macOS   → docs/platforms/macos.md
   ```

3. **自举行为链（10 步）**
   ```
   0. 生成 tool-index
   1. 检测安装路径
   2. 检测 OS
   3. 读平台部署文档
   4. 跑 bootstrap 脚本
   5. 读 RULES.md（CRITICAL block / 全局注入）
   6. 经 MASTER-ROUTING.md 路由
   7. Ops gate：case-init 生成 scope.md，设置 auth + network_profile
   8. 打开 PRIMARY SKILL.md 执行
   9. review_case.py --verify-hashes --strict 校验
   10. docs-generator + field-journal 报告
   ```

### 与我们的对照
- **相同点**：我们已有 skills/ 目录（40+ 技能）+ SKILL.md frontmatter 规范
- **可借鉴点**：
  - **README_AI.md 范式**：给每个 Skill 加 agent-facing 描述（规划文档原本就提出）
  - **tool-index 机制**：运行时生成工具可用性索引，避免"假设工具存在"
  - **field-journal 经验自进化**：与我们 memory 体系的"经验沉淀"同源
- **落地限制**：核心依赖 frida/ida/radare2/jadx 等高权限工具，沙箱落地受限；且是安全工具子域，非当前主线

### 结论
**借鉴 3 个机制**（README_AI 范式 / tool-index / field-journal），不整体集成。作为 Hermes Skill 体系的一个"安全工具子域"远期评估。

---

## 四、agent-skills 规范对比（Hermes vs Anthropic）

### Anthropic Agent Skills 规范核心
- 每个 skill 是一个目录，含 `SKILL.md`
- frontmatter 必需 `name` + `description`
- 可选 `allowed-tools`（限制 skill 可调用工具）
- 纯文本/脚本资产放同目录
- 通过 MCP 或 agent 框架加载

### 我们现有 SKILL.md 结构（zarr-python 为例）
```yaml
---
name: zarr-python
description: ...
allowed-tools: Read Write Edit Bash
license: MIT license
compatibility: ...
metadata:
  version: "1.2"
  skill-author: ...
---
```

### 对比结论

| 维度 | Anthropic | Hermes(我们) | 差异 |
|------|-----------|-------------|------|
| frontmatter name | ✅ | ✅ | **一致** |
| frontmatter description | ✅ | ✅ | **一致** |
| allowed-tools | ✅ 可选 | ✅ | **一致** |
| license | ❌ | ✅ 有 | 我们更全 |
| compatibility | ❌ | ✅ 有 | 我们更全 |
| metadata/version | ❌ | ✅ 有 | 我们更全 |
| 多语言混合 (Py/Bash/JS) | ❌ 单语言 | ✅ | **我们差异化优势** |

**结论**：
- 我们的 SKILL.md 结构**已是 Anthropic 规范的超集**（多了 license/compatibility/metadata）
- `name + description` 完全兼容 → **理论上可被外部 agent 读取**
- **不建议盲目迁移**到 Anthropic 规范；保持自主，发挥多语言混合优势

### 建议动作
- [x] 写一份 `skills/AGENT-INTEROP.md`：说明我们的 SKILL.md 与 Anthropic 规范的映射，供外部 agent 读取（已完成）
- [ ] 若未来要互通，加一个轻量适配层（把 metadata 转成 Anthropic 期望的字段，其余保留）
- **结论**：Hermes SKILL.md 已是 Anthropic 规范超集，`AGENT-INTEROP.md` 映射文档已落地，无需迁移。

---

## 五、block/buzz — 密码学签名 Agent 身份

### 仓库事实
- **许可**：Apache-2.0（可直接合入）
- **发布**：2026-07-21，Block（Dorsey 公司），⭐21.3k
- **形态**：Rust 后端 + Tauri 桌面端（下版本 Flutter 移动端），自托管或官方托管
- **协议**：Nostr（非区块链），Apache-2.0

### 核心机制
1. **Agent 是正式成员，不是 bot**：每个参与者（人/Agent）持自己的 secp256k1 密钥对，私钥签名每条消息，身份可携带、历史在 relay 里、切换 relay 不丢身份。
2. **Nostr NIPs**：NIP-01（事件格式）、NIP-42（认证）、NIP-34（Git 集成）。
3. **relay URL 即 workspace**：`wss://your-org.buzz.xyz` 是工作空间，URL 即权威标识。
4. **ACP 协议**：驱动 Claude Code / Codex / Goose 等 Agent 作为成员接入。
5. **Git + chat 同一事件日志**：feature branch 可当 channel，PR/CI/review 都是事件日志里的条目。

### 与我们对照
- **契合点**：陆墨 → N.E.K.O. → 多 Agent 三层之间，若用 Nostr 密钥做身份认证，可实现"密码学成员"而非 token 隔离。与 `naga_auth.py` 的 token-based auth 是不同范式。
- **借鉴点**：「身份可携带 + 行为可审计 + 历史可迁移」——对长期记忆/审计有参考。
- **落地限制**：需要自托管 relay / 引入 Nostr SDK；当前 N.E.K.O. 是单机桌宠，多 Agent 通信走内部 MCP/HTTP，非去中心化需求。**是全栈性替代，非旁路**，违背授粉"非侵入式只做旁路"纪律。

### 结论
**概念验证，观察不急于集成**。记录 Nostr 身份范式作为未来多 Agent 跨机协作的备选，不在当前主线落地。

---

## 六、prime-agent — RLM + Continual Harness 自我改进

### 仓库事实
- **许可**：MIT（可直接合入）
- **版本**：v0.7.1，⭐13.1k（TypeScript）
- **定位**：面向长程编码/科研任务的自改进 agent

### 核心机制
1. **RLM（Recursive Language Model）**：把上下文当变量。常驻 IPython/REPL 内核，模型唯一内置工具是 `ipython`，用代码表达所有能力；`rlm(...)` 原语生成真实子代理并以编程方式返回结果。
2. **Continual Harness**：把补充提示/记忆/技能/子代理状态做成 CRUD。`/refine` 回看轨迹、抽取有证据的小经验沉淀为技能/提示，**有快照可回滚**，且**永不改写不可变的基础系统提示**。
3. **daemon 后台**：终端断开会话仍存活，可 attach 恢复。
4. **agent 间直接通信 / 心跳调度 / 持久目标 `/goal` / 有界自主 `/autonomous`**。

### 与我们对照
- **借鉴点**：`/refine` 的"只动补丁层、基础系统提示不可变、快照可回滚"——与我们 memory 体系的"经验沉淀"同源，且更克制、更安全。我们 summer_memory/ 的蒸馏已有类似思想。
- **落地限制**：核心是 Rust/TS 运行时 + IPython 内核，非纯 Python；且非沙箱执行（用户权限跑模型生成的代码），与我们 CUA 沙箱四层防御理念冲突。

### 结论
**借鉴 `/refine` 补丁层思想**（补丁不可动基础、快照回滚），不迁移运行时。长期关注其 self-improvement loop 设计。

---

## 七、ShadowBroker — 多源情报融合

### 仓库事实
- **许可**：AGPL-3.0（合入需谨慎，AGPL 传染）
- **来源**：BigBodyCobain/Shadowbroker，⭐8.3k
- **形态**：Next.js + MapLibre GL 前端 + FastAPI/Python 后端，Docker 自托管
- **定位**：60+ 实时 OSINT 数据源 → 35+ 可切换图层的地图情报台

### 核心机制
1. **数据源广度**：ADS-B 飞机、AIS 船舶、492+ 卫星、KiwiSDR 短波、CCTV、警察 scanner（OpenMHz）、Meshtastic 网状电台、APRS、地震/火山/野火（NASA FIRMS）、GPS jamming、SAR 地面形变（NASA OPERA / Copernicus EGMS）、互联网中断、电厂、数据中心。
2. **5 种视觉模式**：DEFAULT / SATELLITE / FLIR / NVG / CRT。
3. **AI agent command channel**：兼容 OpenClaw 等 agent 直接读写分析。
4. **Time Machine**：快照回放（v0.9.7）。
5. **InfoNet**：加密 P2P 网格通信（去中心化层）。

### 与我们对照
- **数据源参考**：我们的 OSINT 管道（multi-source-intel-triangle / agent_osint）未覆盖的源——APRS 业余无线电、Meshtastic、SAR 地面形变、GPS jamming 检测。这些与 SDR/IC-705 交叉栈高度相关。
- **图层架构参考**：35+ 图层独立开关的管理方式，对 Threat Decision Engine 的地图可视化有借鉴。
- **契合点**：KiwiSDR 短波监听 + Meshtastic 与我们的 SDR 交叉栈直接相关。
- **落地限制**：AGPL-3.0 许可证（合入需全栈开源），且资源占用高（SAR/视频层）；仅**参考数据源清单与图层架构**，不合入代码。

### 结论
**提取数据源清单 + 图层架构参考**，不合入代码（AGPL 传染 + 资源重）。APRS/Meshtastic/SAR 源列入未来 SDR 交叉栈的数据源清单。

---

## 八、落地建议（按授粉纪律评估）

| 动作 | 难度 | 收益 | 优先级 | 是否可离线 |
|------|------|------|--------|-----------|
| DuckDB 关键词召回 → rag/ 旁路评估 | 中 | 高（轻量记忆） | 🔴 高 | ✅ 可离线设计 |
| SKILL.md 加 agent-facing 描述（README_AI 范式） | 低 | 中 | 🟡 中 | ✅ 可离线 |
| `skills/AGENT-INTEROP.md` 映射文档 | 低 | 中 | ✅ 已完成 | ✅ 可离线 |
| ShadowBroker 数据源清单 → SDR 交叉栈数据源参考 | 低 | 中（APRS/Meshtastic/SAR） | 🟡 中 | ✅ 可离线设计 |
| prime-agent `/refine` 补丁层 → memory 蒸馏参考 | 低 | 中 | 🟡 中 | ✅ 可离线设计 |
| grid_radio 的纯软件 SDR 思路 → SDR 管道参考 | 低 | 低 | 🟢 低 | 需网络 |
| tool-index 机制设计文档 | 中 | 低 | 🟢 低 | ✅ 可离线 |
| block/buzz Nostr 身份 → 多 Agent 跨机身份备选 | 低 | 低 | 🟢 低 | ✅ 记录观察 |

**当前已完成（2026-08-12）**：
1. `skills/AGENT-INTEROP.md` — Hermes↔Anthropic 规范映射 ✅
2. 6 项目全部评估完成（含本次补完的 block/buzz、prime-agent、ShadowBroker）✅

**待做（离线设计）**：
1. SHALUM 评估 DuckDB 关键词召回设计（写进 rag 旁路评估）
2. ShadowBroker APRS/Meshtastic/SAR 数据源并入 SDR 交叉栈数据源清单
3. prime-agent `/refine` 补丁层思想对照我们 memory 蒸馏设计

---

## 六、元记录

- **分析来源**：WebSearch + WebFetch 实际抓取 GridSetup、reverse-skill、agent-skills（首轮）；block/buzz、prime-agent、ShadowBroker（第二轮 2026-08-12）
- **未做**：无（6 项目全部完成评估）
- **沙箱限制**：无法 clone/装包/跑批，产出为评估报告
- **关联文档**：`GitHub-Trending-August-2026-Action-Plan.md`（前序）、`GitHub-Haul-CrossPollination-Plan-v1.md`（授粉纪律）、`skills/AGENT-INTEROP.md`（规范映射）