# 三方记忆互通预研（工单214 任务二 · 预研不实现）

> 日期：2026-10-08 ｜ **承接 SPEC-05 五维记忆融合**（本文件是 SPEC-05 的续篇素材，
> 亦衔接工单209 任务三调研卡：`fusion-candidates-2026-10/topoteretes-cognee.md`（记忆分层）、
> `MemTensor-MemOS.md`（记忆调度）与本批 `EverMind-AI-EverOS.md`（可移植格式））。
> 素材边界：本仓代码实测 + EverOS/tigerless README 与 storage_layout 实读；**未写任何实现代码**。

---

## 0. ⚠️ 先纠工单前提的一个偏差

工单写"陆墨生态三套记忆在跑：apiserver 记忆（SPEC-05）、NEKO facts.py、**Hermes 本地 memory**"。
实测（2026-10-08）：

- **"Hermes" 在本仓不是本地组件**——它是云端决策层的设计参照（`apiserver/skill_loader.py:3`
  "Hermes 的 skills 模式落到陆墨"、`apiserver/subagent.py:4` "借鉴 Hermes 的 delegate_task"、
  `mcpserver/event_protocol.py:7` "事件流可被 Hermes 决策层消费"）；本机**不存在** Hermes 本地
  memory 存储（工单210 已证 `~/.hermes/` 不存在）。
- 实际在跑的第三套是 **`mcpserver/memory_maas`**（记忆五件套，SPEC-05 落地物）。

→ 本预研的"三方"按实测修正为：**apiserver 记忆（event_bus 线）· NEKO facts.py · memory_maas**。

---

## 1. 三方现状表（实测）

| 维度 | ① apiserver 记忆（event_bus 线） | ② NEKO `memory/facts.py` | ③ memory_maas |
|---|---|---|---|
| **存储格式** | 事件流 JSONL（`event_store/events.jsonl` 轮转）+ 派生 | **JSON 文件**（"persists to JSON files"，SHA-256 去重 + FTS5 语义检索） | **SQLite**（sessions / index_cards / hs_records / typed_entities 四表） |
| **规模** | 事件总线（append + rename 轮转） | **5964 行**（NEKO 记忆中枢，含 persona 副本） | 五件套（core + lineage + cards + hs + typed） |
| **读写入口** | `event_bus/__init__.py get_bus()`；`memory_lifecycle` 消费 | NEKO 进程内模块（上游代码，**不改**） | `get_core()` 单例（sidecar，MEMORY_MAAS_DATA_DIR） |
| **写入时机** | 事件驱动（bus 订阅 5m 档 scheduler tick） | NEKO 会话内事实抽取 | agent 工具调用 `memory_write_card` 等 |
| **淘汰机制** | 轮转保留（max_bytes + keep_files） | SHA-256 去重（同内容不重复存） | `memory_lifecycle` 分层（short→long，`promote_after_seconds` 时间阈值） |
| **单写者纪律** | ✅（工单222 确认：单写者 + rename 轮转） | NEKO 自己写 | ✅ SQLite 单写者（刻意的 WAL 未开决策） |
| **可移植性** | JSONL 可读但 schema 随事件演化 | JSON 可读，schema 在 NEKO 侧 | SQLite 二进制，**不可读不可 diff** |

## 2. 若对齐到 Markdown 交换格式（借 EverOS 约定）：转换损耗清单

以 EverOS 的三层约定（md+frontmatter 真源 / 路径即 scope / 索引派生可重建）为基准：

| 方 | 转换方向 | 损耗 / 阻力 |
|---|---|---|
| ① event_bus | JSONL 事件 → md episodes（按日追加） | **低**：事件本就是 append 型，映射到 `episode-<date>.md` 语义天然；丢的是**事件类型枚举的强 schema**（md frontmatter 需自定义字段承载） |
| ② NEKO facts | JSON 事实 → `.atomic_facts/*.md` | **低-中**：事实是原子条目，天然适合；但 **NEKO 是上游代码，写入侧不能改** → 只能做**单向导出**（NEKO→md），反向注入不可行（违反"不吃上游改动"铁律） |
| ③ memory_maas | SQLite 表 → md + 派生索引 | **中**：`index_cards`（带 lineage 链）/`hs_records`/`typed_entities` 是**关系型**结构——拍平成 md 会丢**跨表关联**（lineage 链、typed 实体图）；且 md 化后 SQLite 检索/事务全要重建。**这是三方中损耗最大的一家** |

**反向损耗**（md → 各方）：三方各自的检索/去重/分层逻辑都建立在自己的存储假设上
（FTS5 / SQLite 事务 / 事件轮转），把 md 当**交换层**不碰运行时则无损耗；
把 md 当**真源替换**SQLite 则是 memory_maas 的重写级工程。

## 3. 结论（三选一）

### ✅ 推荐：自定义最小子集（选项 B）

**理由**：
1. **EverOS 格式不能直接采用**（选项 A 否决）：它的 frontmatter chassis / OME / cascade /
   LanceDB 是**一整套运行时**——直接采用等于整库引入，破坏 memory_maas 的
   "SQLite 单写者 + 零新重依赖"纪律（工单222 刚钉下的架构约束）；
2. **维持现状各管各的**（选项 C）也不取：三套记忆的**互通刚需已经存在**
   （陆墨本体 ↔ NEKO 桌宠壳 ↔ 科研线的记忆断头），且 EverOS/tigerless 证明了
   "md 做交换层"的技术可行性——窗口期值得抓住；
3. 但要的只是它的**格式约定**，不是运行时——所以自定义**最小子集**：

### 最小子集的具体形状（供 SPEC-05 续篇立项时讨论）

```
lumo-memory-exchange/（建议名，单一交换根）
├── MEMORY.md                     ← 根索引（借 tigerless：一行一条，常驻注入可预算）
├── <source>/                     ← 路径即来源命名空间（借 EverOS：lumo / neko / maas）
│   ├── episodes/…md              ← 日追加（①事件流、②事实时间线映射到此）
│   └── facts/<id>.md             ← 原子事实（②NEKO facts 单向导出到此）
│       （frontmatter 最小集：source_id / created / kind / confidence / links）
└── index/（各方自己的派生缓存，可重建，不入交换协议）
```

**协议只约定三件事**：①frontmatter 最小字段集；②路径命名空间；③**写入权分片**
（每个 source 目录只允许其属主写——NEKO 目录由导出器写、maas 目录由 maas 写，
天然规避多写者冲突，与工单222 的单写者纪律同构）。

### 落地路径建议（不在本单做）

1. 先做**单向导出**（零风险）：memory_maas → md、NEKO facts → md（只读导出，不碰写入侧）；
2. `MEMORY.md` 根索引 + frontmatter 最小集写成 `SPEC-05 续篇`（格式 spec，非代码）；
3. 反向注入（md → 各方检索面）等格式稳定后再议——**不与导出捆绑**。

## 4. 边界

- 本预研**未写任何实现代码**（工单红线）；
- EverOS 冲突解决细节以其源码为准（本预研只读了 README + storage_layout.md）；
- NEKO 侧**只能单向导出**（上游铁律）这一点直接塑造了上面的"写入权分片"设计。
