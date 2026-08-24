# GitHub Trending 2026-08 上旬 — 行动计划

> 信号采集时间：2026-08-12  
> 状态：**6 项目已全部评估完成**（详见 `GitHub-Trending-August-2026-Exec-Report.md`）  
> 关联：Hermes Agent 体系 / SDR+OSINT 栈 / N.E.K.O. Fusion

---

## 信号汇总

### 趋势：三方向同时加速

| 方向 | 信号强度 | 与我们栈的重合度 |
|------|---------|----------------|
| Agent 从工具→队友（密码学身份、写给AI看的README） | ⚡⚡⚡ | **极高** — Hermes 核心定位 |
| Skills > 模型（Agent Skills 规范基建化） | ⚡⚡⚡ | **极高** — 已有 Skill 体系 |
| OSINT 工具化加速（多源情报融合 TUI） | ⚡⚡ | **高** — SDR/OSINT 交叉栈 |

---

## 六个项目逐项分析

### 1. zhaoxuya520/reverse-skill ⭐12.5k

**是什么**：逆向/渗透/安全研究的 AI Agent 技能路由包。AI 自动选工具链 + 按需自举 + 经验自进化。

**关键信号**：README 写在 `README_AI.md` 里直接给 AI agent 读而不是给人读。**范式信号**——文档的目标读者从人类变为 Agent。

**行动**：
- [x] Clone 分析其技能路由机制（`execute_code` 沙箱？self-bootstrap 怎么做的？）— 已拆解 tool-index + OS 路由机制
- [x] 评估能否作为 Hermes Skill 体系的一个「安全工具子域」— 结论：借鉴设计，不整体集成
- [x] 借鉴 `README_AI.md` 范式——是否该在 Hermes skills/ 里为每个 Skill 加 agent-facing 描述？
- **优先级：中**（模式借鉴 > 直接集成，安全工具非当前主线）

### 2. block/buzz ⭐7.6k+（Block/Square 官方，Apache-2.0）

**是什么**：跑在 Nostr 协议上的自托管协作空间。AI Agent 作为**密码学签名成员**加入频道，能开 repo、交 patch、review 代码、跑 workflow、切语音频道。

**关键信号**：Agent 有身份。不是被限制了权限的 bot，是队友。

**行动**：
- [x] 评估 Nostr 身份体系能否嫁接到 Hermes → N.E.K.O. 的 agent 间通信 — 结论：概念验证，观察不急于集成（全栈替代非旁路）
- [x] 关注：密码学签名 agent 身份 vs 当前 token-based auth 的差异 — 已对比
- [x] 若可行，Hermes ↔ NagaAgent ↔ N.E.K.O. 三层之间用 Nostr key 做身份认证 — 记录为跨机身份备选
- **优先级：低**（概念验证阶段，不急于集成）

### 3. PrimeIntellect-ai/prime-agent — RLM 自改进 Agent

**是什么**：自改进的 RLM agent，面向长程编程任务和自主工作流。能在任务中自己优化自己的策略。

**关键信号**：Agent 不再只是执行，而是**在任务中进化**。超越了 codex delegate 的"单次任务"模型。

**行动**：
- [x] 观望。RLM 自改进在当前 Hermes 栈中的收益不明确 — 已评估：借鉴 `/refine` 补丁层思想
- [x] 关注其 self-improvement loop 的架构设计（失败→反思→策略更新）— 已拆解 Continual Harness / 快照回滚
- **优先级：低**（长期关注，不急于集成）

### 4. agent-skills 生态 — 主 SDK ⭐167k / 技能包 ⭐99.9k

**是什么**：Anthropic 的 Agent Skills 规范，已和 MCP 一样成为基础设施。Simon Willison：「Skills 可能比 MCP 更大」。

**关键信号**：**不卷模型大小，卷 agent 能正确调用什么能力**。这验证了 Hermes 从 Day 1 就走的 Skills-first 路线。

**行动**：
- [x] 对比 Hermes Skill 规范与 Anthropic Agent Skills 规范的差异 — 已完成，Hermes 是超集
- [x] 如果 API 兼容，考虑做适配层（让 Hermes skills 可被外部 Agent 调用）— 已产出 `skills/AGENT-INTEROP.md` 映射文档
- [x] **警惕**：不要盲目迁移到 Anthropic 规范。Hermes 的 skills + 多语言混合（Python/Bash/JS）是差异化优势 — 确认保持自主
- **优先级：高**（战略对齐，但保持自主）

### 5. rounakagrawal7/GridSetup — GRID v2 ⭐增长中

**是什么**：OSINT + SDR/无线电 + 卫星追踪 + 物联网 + 计算机视觉，一体的键盘驱动 Windows TUI。

**关键信号**：正好踩在 IC-705 / SDR / OSINT 交叉领域上。Windows 原生 TUI。

**行动**：
- [x] **优先 Clone 分析**——这是直接可借力的轮子 — 已分析
- [x] 重点看：SDR 集成方式（什么硬件？什么驱动？）、卫星追踪数据源 — 结论：radio 模块仅网络 SDR，**与 IC-705 无关**
- [x] 评估能否抽出 SDR/radio 模块嫁接到 N.E.K.O. 的 radio 层 — 结论：不嫁接到 radio 层；**记忆引擎（L0-L3+DuckDB）可借**
- [x] 对比：GRID 的 OSINT 融合 vs 我们已有的 multi-source-intel-triangle
- **优先级：高**（直接可用，交叉领域重合度高）

### 6. ShadowBroker — 开源版 Palantir

**是什么**：60+ 公开数据源实时情报（航班/船舶/卫星/CCTV/火灾/地震/军事活动），35+ 图层叠加 + AI Agent 支持 + 去中心化聊天。

**关键信号**：多源情报融合从「军方/情报机构专属」走向「开源 TUI」。OSINT 工具箱正在模块化、开箱即用化。

**行动**：
- [x] Clone 分析其数据源列表（60+ 源）——哪些是我们 OSINT 管道没覆盖的？ — 已提取：APRS/Meshtastic/SAR/GPS-jamming 未覆盖
- [x] 评估图层叠加架构（35+ 图层怎么管理的？）——对 Threat Decision Engine 的地图可视化有参考价值 — 已评估
- [x] 去中心化聊天部分可能与 block/buzz (Nostr) 有关联 — 确认 InfoNet 加密 P2P 电网层
- **优先级：中**（数据源参考 + 可视化架构借鉴）

---

## 行动计划时间线

### 本周（2026-08-12 ~ 08-17）— ✅ 已完成

| 任务 | 项目 | 状态 |
|------|------|------|
| Clone + 结构分析 GridSetup | GRID v2 | ✅ 完成 |
| GRID SDR 模块评估报告 | GRID v2 | ✅ 完成（确认与 IC-705 无关） |
| reverse-skill 技能路由机制文档 | reverse-skill | ✅ 完成 |
| Agent Skills 规范对比（Hermes vs Anthropic） | agent-skills | ✅ 完成（产出 AGENT-INTEROP.md） |

**本周额外提前完成**（原下周计划）：
- ShadowBroker 数据源列表提取 + 对比 ✅
- block/buzz Nostr 身份体系评估 ✅
- prime-agent RLM/Continual Harness 拆解 ✅

### 下周（2026-08-18 ~ 08-24）→ 转「落地设计」

| 任务 | 项目 | 说明 |
|------|------|------|
| DuckDB 关键词召回设计 → rag/ 旁路评估 | GRID 借鉴 | 轻量记忆旁路 |
| ShadowBroker APRS/Meshtastic/SAR 并入 SDR 交叉栈数据源清单 | ShadowBroker | 数据源参考 |
| prime-agent `/refine` 补丁层对照 memory 蒸馏设计 | prime-agent | 设计借鉴 |
| README_AI.md 范式评估——是否在 Hermes skills 推行 | reverse-skill | agent-facing 描述 |

### 长期（8月下旬后）

| 任务 | 说明 |
|------|------|
| Agent Skills 互通适配层 | AGENT-INTEROP 映射已就绪，需要时再加轻量适配层 |
| prime-agent 自改进机制跟踪 | 持续观望 |
| block/buzz Nostr 身份 → 多 Agent 跨机身份 | 概念验证备选，不急于落地 |

---

## 风险评估

| 风险 | 级别 | 说明 |
|------|------|------|
| 分散注意力 | 中 | 6 个项目同时看会稀释主线（N.E.K.O. Fusion + IC-705 链路）——评估已完成，落地按优先级收敛 |
| 过度依赖外部轮子 | 低 | 已确认 ShadowBroker 为 AGPL，仅取数据源清单；GridSetup 为 Windows TUI，仅借记忆引擎思路 |
| 许可证冲突 | 低 | block/buzz Apache-2.0、prime-agent MIT、GridSetup MIT 安全；ShadowBroker AGPL 不合入代码 |

---

## 元记录

- **分析者**：沈遥（Hermes Agent）
- **输入来源**：用户手动采集的 GitHub Trending 数据
- **进度**：6 项目评估全部完成（2026-08-12），进入落地设计阶段
- **下次更新**：DuckDB 关键词召回 / SDR 数据源清单设计完成后
- **关联文档**：
  - `GitHub-Trending-August-2026-Exec-Report.md` — 6 项目完整评估
  - `skills/AGENT-INTEROP.md` — Hermes↔Anthropic 规范映射
  - `GitHub-Haul-CrossPollination-Plan-v1.md` — 之前的扫货交叉授粉计划
  - `Fusion-Topology-Audit-v1.md` — 三层融合拓扑审计
  - `multi-source-intel-triangle` Skill — OSINT 多源情报现有能力
