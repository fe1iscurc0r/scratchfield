# 融合候选：tigerless-labs/agent-memory

> **优先级 P2（对读价值最高）** ｜ 采集：2026-10-08 GitHub API + README 实读
> 承接：工单 209 任务三调研卡目录

## 0. 实测元数据

| 项 | 值 |
|---|---|
| 仓库 | `tigerless-labs/agent-memory` |
| ★ | **2646**（工单初勘 2381，一周涨 ~11%） |
| 许可 | **MIT** ✓ |
| 语言 / 体积 | Python / **120 MB**（⚠️ 大头是测试夹具/模型文件，源码本体小；不 clone） |
| 最近 push | 2026-10-07 |
| 定位 | "Long-term memory runtime — plain Markdown as the source of truth, local ranked retrieval, and an independent sleep-time Manage…" |

## 1. 架构一句话

**纯 Markdown 记忆运行时**：记忆就是文件系统上的 `.md`（可 `ls`/`grep`/git），
检索引擎给这套文件建索引——"retrieval engine 索引一个 agent 可直接读的 filesystem"二合一；
配独立的"睡眠期"管理进程做整理。

## 2. 记忆数据格式（README 实读）

```
$AGENT_MEMORY_STORE/
├── MEMORY.md            ← 根索引：每条记忆一行 —— **唯一的常驻注入物**
├── schemas/             ← 每类型一文件：关键字段、分组字段、写模式
├── decision/            ← 记忆本体在 <type>/<group>/<name>.md，由 schema 决定位置
│   └── agent-memory/…/markdown-files-are-the-single-source-of-truth.md
└── …
```

关键约定：
- **三读轨**（deterministic `MEMORY.md` 注入 + 检索 + 邻域漫游）："一条轨道 miss 不是 miss"；
- **同目录 = 免费邻域**，frontmatter 里的 `links` 携带关联；
- **"零知识丢失"是由测试保证的**（"enforced by a test, not promised in a doc"——这句工程态度值得学）。

## 3. ⭐ 重点问题（工单点名）：Markdown-as-source-of-truth 的冲突解决 / 增量同步机制

README 实读能确认的：
- **冲突解决**：以**文件为合并单元**（每条记忆一个 md 文件）→ 冲突面被切到文件粒度；
  schema 目录决定"写模式"（每类型声明自己的写语义，如追加/整写），**不同类型不共享合并逻辑**；
- **增量同步**：`MEMORY.md` 根索引（一行一条）是**唯一常驻注入物**——同步增量的单位是
  "索引行 + 对应文件"，而不是整库；检索命中解析回磁盘上的整个 md 文件；
- ⚠️ **边界如实标注**：更细的冲突策略（并发写/三方合并的精确算法）README 没展开，
  需要读源码或 CLAUDE.md（Invariants 文档）才能定论——本卡不下结论。

**对照 Hermes 注入式设计**（本仓 `apiserver/skill_loader.py:3` 借的正是 Hermes 的
"清单 → 检索 → 读 SKILL.md → 注入 → 回写"模式）：
- Hermes/我们的注入式：**运行时检索、动态注入**——灵活但每次都要查；
- tigerless：**常驻索引注入（MEMORY.md 一行一条）+ 按需展开文件**——注入成本恒定、
  可确定性预算上下文占用。两者是互补而非替代。

## 4. 与 memory_maas + SPEC-05 的差距

| 维度 | tigerless | 陆墨现状 |
|---|---|---|
| 真源 | Markdown 文件 | SQLite |
| 注入 | 常驻根索引 + 三读轨 | 检索时动态注入 |
| 类型系统 | schemas/（每类型一文件：字段/分组/写模式） | index_cards/typed_entities（表结构） |
| 整理 | 睡眠期独立进程 | memory_lifecycle 事件驱动 |

**差距的本质**：它是"**文件系统 + 索引**"的极简派；我们是"**数据库 + 事件**"的工程派。
它的 **schema 即文件**（类型定义也可 grep）和**零知识丢失用测试钉住**两条最值得借。

## 5. 可借用的具体设计（非代码）

1. ⭐ **MEMORY.md 根索引常驻注入**：上下文占用可预算（一行一条），对我们
   `intent_router` 的工具列表缓存（同样是大清单注入问题）有直接启发；
2. **schema 即 md 文件**：类型定义与数据同构同存；
3. **"零知识丢失"写成测试**：与我们工单222 的"测试钉住语义"完全同宗；
4. **三读轨设计**（确定性注入/检索/邻域）——比单通道检索的鲁棒性高一档。

## 6. 许可与边界

**MIT** ✓。体积 120MB 不 clone（源码本体小，需要时按路径读）。
素材边界：README 实读；冲突解决的精确算法与睡眠期实现**未读源码**，已如实标注。
