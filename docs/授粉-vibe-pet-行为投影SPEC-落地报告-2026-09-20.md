# 授粉 · vibe-pet 行为投影 SPEC — 落地报告（2026-09-20）

> 卷141 交付 | 实验田维护者签
> 上游：Seeed-Solution/vibe-pet（47★ · MIT ✅ gh api 核验 · 2026-07-15 后停更）
> SPEC 全文：`docs/SPEC-neko-行为投影-事件映射-2026-09-20.md`

## 一、上游实地调研结论（不是转述工单）

**定位**：给 AI coding agent 做硬件桌宠——监听 Codex/Cursor/Windsurf/Claude CLI/
Gemini CLI/Copilot CLI/CodeBuddy/Kimi/Qwen/OpenClaw 的活动，
把 **thinking / tool use / waiting for approval / completed / error** 五态
变成动画形态，并通过 BLE 同步到 Wio Terminal / ESP32-S3 硬件。

**文件结构（137 文件，实测）**，关键件：

| 文件 | 作用 | 对我们有价值吗 |
|---|---|---|
| `src/host/state-hub.js` | **状态中枢**：把多 agent 事件归并成宠物状态 | ★★★ 核心借鉴点 |
| `src/host/agent/*-monitor.js` | 各 agent 的日志/transcript 监视器（codex-log / cursor-transcript / presence） | ★★ 采集思路 |
| `src/host/protocol.js` + `docs/protocol.md` | 宿主↔宠的协议定义 | ★★★ 契约写法 |
| `src/hooks/*-hook.js` | 各 agent 的 hook 注入（Codex/Cursor 等） | ★ 与本仓 hook 体系可对照 |
| `src/host/petdex.js` + Petdex 外部仓 | 千款角色注册表 | ★ 资源来源，非架构 |
| `src/firmware/*` | 4 个硬件目标（Wio Terminal / ESP32-S3 / SenseCAP） | ○ 硬件线参考（本仓有 ESP32-S3 硬件，未来可接） |

## 二、源 → 目标映射表

| # | vibe-pet 设计 | 落到本仓的位置 | 说明 |
|---|---|---|---|
| 1 | **五态状态词表**（thinking/tool use/waiting approval/completed/error） | `docs/SPEC-...-事件映射.md` §2 事件词表 | 直接采用并扩展（+idle/token.high/cron.fired） |
| 2 | **state-hub 归并中枢** | Lumo 侧"投影消费者"（订阅事件总线 → 转 `POST /api/lumo/event`） | 归并逻辑在 Lumo 侧，NEKO 侧只消费 |
| 3 | **多 agent 分卡** | SPEC §4「多 agent 分卡」 | 每会话/子代理一个状态槽，不揉成一个 |
| 4 | **JSONL/日志监视**（codex-log-monitor） | 不需要——本仓有事件总线，事件是**一等公民**而非日志副产品 | **本仓架构更优，不抄这层** |
| 5 | 协议文档化（`docs/protocol.md`） | SPEC §6 Payload 契约（含敏感字段禁入） | 契约先行 |
| 6 | 硬件同步（BLE → ESP32-S3） | 预留（SPEC §8 与 W131-05 设备感知联动） | 本仓有 ESP32-S3 在手，属未来线 |

## 三、核心数据结构共鸣（附实测行号/文件）

| 源结构 | 本仓对应物 | 共鸣度 | 差异 |
|---|---|---|---|
| `src/host/state-hub.js` 的状态归并 | `apiserver/event_bus/bus.py` 的 `InProcessEventBus` + 消费者注册 | 高 | 上游是单进程 JS 状态对象；本仓是**总线 + 热插拔消费者**，扩展性更好 |
| `src/host/protocol.js` 消息协议 | `apiserver/routes/lumo_event.py` 的 `LumoEvent`（Pydantic 判别联合，L144-147） | 高 | 本仓已用判别联合做强校验；上游是裸 JSON 约定 |
| 五态定义 | `apiserver/agentic_tool_loop.py` 已有的 SSE 事件 `round_start` / `tool_results` / `round_end`（L2346/L2556/L2615） | 高 | **本仓已有等价事件，只是没投影成视觉**——所以本卷只需"翻译层"，不需新采集层 |
| `token` 用量告警 | `apiserver/llm_router.py` + `context_compressor.py`（token 计量已有） | 中 | 上游按 token 阈值换形态；本仓有计量但未外露为事件 |

**关键结论**：本仓**不缺数据源**（事件总线 + SSE + 设备感知都在），缺的是
「状态 → 视觉」的那一层映射契约。这正是本卷产出 SPEC 而非代码的原因。

## 四、难度 × 收益评估

| 维度 | 评估 |
|---|---|
| **实现难度** | 低-中。Lumo 侧只需一个消费者（约 150 行）+ 去抖/优先级；NEKO 侧是动画触发器 + 分卡 UI（前端工作量大于后端） |
| **收益** | 中-高。桌宠从"装饰"→"agent 可观测面板"；与既有 SS 事件天然契合，边际成本低 |
| **风险** | ①事件高频刷屏（已定去抖规则）②NEKO 前端渲染工作量被低估（故本卷只出 SPEC，交前端线评估）③上游停更（已标注：设计参考，不追上游） |
| **不做的事** | 不抄日志监视层（本仓有总线）；不抄硬件协议（属未来硬件线）；不动 NEKO 上游引擎 |

## 五、交付物

1. `docs/SPEC-neko-行为投影-事件映射-2026-09-20.md` —— **SPEC 全文**
   （8 事件词表 / 4 事件源 / 触发器契约 / 去抖与优先级 / Payload 契约 / 分工与验收）
2. 本报告

## 六、约束遵守与实测

- ✅ 只借鉴设计，不复制 C/JS 代码；MIT 合规（gh api 核验 `spdx_id=MIT`）
- ✅ 上游 2026-07 停更已在 SPEC 与报告双处标注「设计参考，不追上游」
- ✅ NEKO 上游零改动（本卷产物是 docs/ 下两份文档，不碰 `NEKO/`）
- ✅ SPEC 里给出的落点全部经实测确认存在（`event_bus/`、`lumo_event.py`、
  `agentic_tool_loop.py` 的 SSE 事件、`task_flow.py` 的 SCHEDULER_TICK）
- ✅ 验收 grep 计数达标（见下）

```
grep -c "agent.busy\|agent.idle\|agent.error" SPEC   → 命中（词表 + 触发器 + 去抖）
grep -c "事件源\|事件总线" SPEC                        → 命中（§3 标题与正文）
```
