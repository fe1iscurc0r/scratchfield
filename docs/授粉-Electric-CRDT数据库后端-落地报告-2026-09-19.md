# 授粉 · Electric（CRDT 数据库后端）落地报告

> 卷138 · W138-01 | 2026-09-19 | 沈遥签
> 上游：electric-sql/electric（10364★ · Apache-2.0 ✅ LICENSE 原文确认 · 2026-09 活跃）
> 前置：超限战轮19 授粉报告（2026-09-19）P0-2

## 一、Electric 是什么（实地调研结论）

Electric 是 **Postgres 只读同步引擎**（read-path sync engine），不是传统认知里的
"CRDT 数据库"。它的核心原语是 **Shape**——用一个 `WHERE` 子句定义的表数据子集，
客户端通过 HTTP 长连接流式订阅该子集的增量变化。

**关键架构事实**（2024 年中重大重构后的现架构）：

1. **读路径走 Electric，写路径不动**：写入仍直连 Postgres（走你现有后端 API），
   Electric 只负责把 Postgres 变化（WAL）以 HTTP 流推给订阅方。
   这比旧版"全 CRDT 本地优先框架"大幅简化。
2. **冲突语义 = Rich-CRDT 行为**：列级 LWW（Last-Write-Wins，时间戳按列比较，
   不是整行）+ 因果一致性（causal consistency）+ 外键引用完整性。
   离线双写同一行不同列，合并后两列各自保留，不互踩。
3. **组件**：Electric Sync Service（Elixir，连 PG 读 WAL）+ 客户端库
   （TypeScript/React/Elixir/PGlite）+ `@electric-sql/client` 的 `ShapeStream` API。
4. **安全模型**：与 Postgres RLS（Row Level Security）集成——客户端带 JWT 订阅
   Shape，Sync Service 按 RLS 策略在源头过滤行。
5. **纯 HTTP**：无 WebSocket 常连（v9 起流式 HTTP），对多客户端/代理友好。

## 二、源设计 → 目标系统映射（架构图）

```
【Electric 源架构】                      【Lumo 目标架构（借鉴后）】
┌─────────────┐  WAL   ┌──────────────┐   ┌──────────────────────────┐
│  Postgres   │──────▶│ Electric Sync │   │ sitaware/知识库读写层     │
│ (写入口/真相) │       │ Service       │   │ (SQLite, 本地优先)        │
└─────────────┘       └──────┬───────┘   └───────────┬──────────────┘
      ▲ 写: 直连 PG          │ Shape 订阅             │ 借鉴点①
      │                     ▼ (HTTP 流)              ▼
┌─────────────┐       ┌──────────────┐   ┌──────────────────────────┐
│ 应用后端 API │       │ 客户端缓存    │   │ 订阅式增量同步层          │
│ (不变)       │       │ (SQLite/PGlite)│  │ events/tokens 变更推送   │
└─────────────┘       └──────────────┘   └──────────────────────────┘
```

**借鉴点**（只取设计，不引整体）：

| # | Electric 设计 | 落到 Lumo 的位置 |
|---|---|---|
| ① | Shape = WHERE 子句定义的数据订阅域 | sitaware 的 `/api/events` 已有 bbox/severity 筛选——补"订阅式 SSE 增量"（`/api/events/stream` 已有雏形，按 Shape 思想补"过滤条件持久化 + 断线续传 offset"） |
| ② | 列级 LWW + 因果一致性 | 知识库（vault/GRAG）多端合并策略：条目级字段不互踩 |
| ③ | WAL 追赶式增量（log-offset） | sitaware CacheStore 的 events 表加单调 log_id，SSE 断线重连按 last_id 补发，不整表重拉 |
| ④ | RLS 源头过滤 | agent 会话隔离：订阅流按 agent_id/角色过滤，与现有 Scope 闸门对齐 |

## 三、与 Loro 的全栈闭环路径（工单要求的对接设计）

Loro（前端 JSON CRDT，MIT）与 Electric（后端 PG 同步）的定位差异：

| 层 | Loro | Electric |
|---|---|---|
| 数据形态 | 任意 JSON 文档（LoroDoc/List/Text/MovableTree） | 关系表子集（Shape） |
| 冲突处理 | 真 CRDT（文本/列表可细粒度合并） | 列级 LWW + 因果序 |
| 持久化 | 前端（内存/IndexedDB 导出快照） | Postgres（真相源） |

**落地路径（三步）**：

1. **第一步（无后端改动）**：Lumo 前端用 Loro 管理多端会话状态
   （对话草稿/知识卡片编辑），快照存 sqlite。此步 Electric 不参与。
2. **第二步（引入同步）**：知识库主表落 Postgres（或继续 SQLite，
   起一个 PG 侧写副本），后端跑 Electric Sync Service，前端以 Shape
   订阅"我的知识库条目"。Loro 文档作为 blob 列存储，PG 只当传输与持久层。
3. **第三步（闭环）**：Loro 的 `export(mode='update')` 增量提交走后端写 API
   → PG WAL → Electric Shape 推给其他端 → 各端 Loro `import` 增量。
   冲突由 Loro CRDT 在文档层自动合并——**Electric 管传输，Loro 管合并**，职责不重叠。

**数据流**（第三步）：
`端A LoroDoc → update blob → POST /api/kb/entries/{id}/update → PG WAL → Electric → Shape 推流 → 端B/端C LoroDoc import → 收敛`

## 四、许可证与依赖确认

- **Apache-2.0** ✅（GitHub LICENSE 原文确认，2026-09 活跃）
- 自托管：Docker 单容器（`electric-sql/electric` 镜像）+ 现有 Postgres。
  无 Kafka/Redis 等额外基础设施。
- 约束：目标是 Postgres。Lumo 现役 SQLite——**第二步才需要为同步目标表起一个 PG**，
  或用 PGlite（浏览器内 PG，Electric 官方支持）过渡。SQLite 全量迁移 PG 不在本授粉范围。

## 五、结论

- **立即收益**：借鉴点③（log-offset 断线续传）与①（订阅过滤持久化）可直接进
  sitaware 的 SSE 层，无新依赖。
- **中期**：知识库多端同步采用"Loro(合并) + Electric(传输)"双件架构，
  在 PG 侧落地（作为 SQLite 之上的同步副本，不推翻现有存储）。
- **不采用**：整库接管（把 Lumo 存储全迁 Electric/PG）——违背最小改动纪律，
  且写路径收益为零。
