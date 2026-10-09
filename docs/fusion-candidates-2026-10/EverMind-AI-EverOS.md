# 融合候选：EverMind-AI/EverOS

> **优先级 P1（第二梯队之首）** ｜ 采集：2026-10-08 GitHub API + `docs/storage_layout.md`/README 实读
> 承接：工单 209 任务三调研卡目录（cognee/MemOS/airi 等第一批的续篇）

## 0. 实测元数据

| 项 | 值 |
|---|---|
| 仓库 | `EverMind-AI/EverOS` |
| ★ | **13364**（工单初勘 13359） |
| 许可 | **Apache-2.0** ✓ |
| 语言 / 体积 | Python / **3.3 MB**（本批最轻，源码可读） |
| 最近 push | 2026-10-06 |
| 定位 | "One portable memory layer for every AI agent: local-first, Markdown-native, user-owned, self-evolving" |

## 1. 架构一句话

**Markdown 为真源的可移植记忆运行时**：记忆以可读可编辑可 diff 可 Git 版本化的 `.md` 落盘，
SQLite + LanceDB 只是**派生索引**（可随时从 Markdown 重建）；配 "OME"（Offline Memory Engine）
在会话间离线整理（episode 聚合 / profile 精炼），`cascade watcher` 监听 md 手改并回流索引。

## 2. ⭐ 记忆数据格式（storage_layout.md 实读，任务一必答的地基）

```
<memory-root>/（默认 ~/.everos，EVEROS_ROOT 可覆盖）
├── <app_id>/<project_id>/          ← 按 (应用, 项目) 分区；scope 编码在路径里而非 frontmatter
│   ├── users/<user_id>/
│   │   ├── user.md                 ← 单文件整写（profile）
│   │   ├── episodes/episode-<日期>.md       ← 日志追加
│   │   ├── .atomic_facts/… .md    ← 隐藏目录，原子事实日追加
│   │   └── .foresights/… .md
│   ├── agents/<agent_id>/
│   │   ├── .cases/agent_case-<日期>.md
│   │   └── skills/skill_<name>/SKILL.md（+references/+scripts/）
│   └── knowledge/                  ← 用户可见的共享知识页（taxonomy + CRUD API + 主题检索）
├── .index/                         ← 系统管理、可重建（gitignore）：sqlite/ + lancedb/
├── ome.toml                        ← 用户可编辑的整理策略（热重载）
└── .tmp/                           ← 批量/多步写入的暂存区
```

写入语义按文件分三类：**单文件整写**（user.md）/ **日志追加**（episodes、atomic_facts、foresights）/
**技能目录**（SKILL.md + 资源）。崩溃恢复走 SQLite `md_change_state` 持久队列（不是日志文件）。

## 3. ⭐ 必答问题："portable memory layer" 的跨 agent 协议是怎么设计的

**它没有发明一个新的线上协议——"可移植"由三层约定实现**（storage_layout.md 实读结论）：

1. **交换格式 = Markdown 文件本身 + YAML frontmatter chassis**（entry-id 编码在 frontmatter/路径里）。
   任何能读写文件的 agent 都能消费——协议就是文件系统；
2. **命名空间 = 路径分区 `<app_id>/<project_id>`**：多 agent 各占一个 app_id，**共享同一 memory-root**
   即共享记忆；`knowledge/` 是跨 agent 的公共区（users/agents 是私有区）。跨 agent 互通
   = 同 root 不同 app_id + 公共 knowledge 目录，**不需要点对点转换**；
3. **API/CLI 收口**（docs/api.md + cli.md）：`memory add / flush / recall` 等原语统一入口，
   索引一致性由 cascade watcher + LSN 水位保证——外部 agent 只要走 API 或直接改 md（watcher 会接住）。

**对本仓三方的适配性初判**（详见 `../memory-interop-prestudy.md`）：
- 借它的**目录约定 + frontmatter**做交换层是可行的（纯文件，无运行时绑定）；
- 但**整库引入**会把 SQLite+LanceDB+OME 调度器全带进来——与 memory_maas 的"SQLite 单写者、
  零新重依赖"纪律冲突 → 建议**只借格式不借运行时**。

## 4. 与 memory_maas + SPEC-05 五维记忆的差距

| 维度 | EverOS | 陆墨现状 |
|---|---|---|
| 真源 | Markdown（可 git） | SQLite（memory_maas：sessions/index_cards/hs_records/typed_entities） |
| 派生 | SQLite+LanceDB 索引可重建 | 向量+图谱双通道（影子模式） |
| 离线整理 | OME（episode 聚合/profile 精炼） | `memory_lifecycle`（分层提升，时间阈值） |
| 跨 agent | 路径分区 + knowledge 公共区 | 各自为政（apiserver/NEKO/memory_maas 三套） |
| 技能记忆 | skills/（SKILL.md） | 无（正是 MemOS 调研卡指出的缺口，两边对上了） |

**差距的本质**：我们有"检索与分层"，缺"**可移植的真源格式**与**跨 agent 命名空间**"。

## 5. 可借用的具体设计（非代码）

1. ⭐ **"真源 = md，索引 = 派生可重建"的架构立场**——我们恰好相反（SQLite 是真源），
   这个立场值得在 SPEC-05 续篇里认真辩论一次；
2. **路径即 scope**（app_id/project_id）+ 公共 knowledge 区的命名空间划法；
3. **写入语义三分**（整写/追加/技能目录）——比统一 JSON 覆写更贴记忆的自然形态；
4. **崩溃恢复用持久队列（md_change_state）而非日志文件**——与工单222 的原子写纪律同宗。

## 6. 许可与边界

**Apache-2.0** ✓ 可引码；但本卡仍按"只借设计"处理（整库引入破坏零新重依赖纪律）。
素材边界：README + storage_layout.md 实读，**未读源码、未跑**；OME/cascade 的实现细节以文档为准。
