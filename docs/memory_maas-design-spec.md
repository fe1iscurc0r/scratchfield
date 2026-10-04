# memory_maas 设计 SPEC v1

> 2026-08-29 · 授粉落地（round9 遗留）· 参照 par typed memory schema + claude-mem 压缩注入 + SPEC-03 五件套现状
> 上游：latentfidelity/par（MIT，9★）· thedotmack/claude-mem（Apache-2.0，92522★）
> 状态：设计稿，待 review 后交 Trae 实现

## 1. 背景

- SPEC-03 五件套（hybrid_search / index_cards / lineage / lifecycle / compaction_v2）已落地，但记忆是 **blob 级**：卡片是整段文本+向量，无实体类型、无关系、无显式生命周期元数据。
- round9 授粉结论：记忆不是 blob，是带类型的可查询实体（decision/insight/handoff…），"跨 session 记忆融合"应从向量拼接升级为实体图谱遍历。
- claude-mem 提供另一条线：session 观察自动捕获 → LLM 压缩 → 未来 session 按需注入（token-efficient 3层工作流），92k star 验证了"压缩+注入"路径的工程可行性。

## 2. 核心设计：typed memory 实体

### 2.1 实体类型（par 5 类 + 本土化 2 类）

| type | 含义 | 五件套映射 |
|------|------|-----------|
| decision | 决策（选型/裁决/取舍） | lineage 分支摘要、review 结论 |
| insight | 洞察（跨域发现/授粉点） | index_cards 高 confidence 卡片 |
| task | 任务状态 | TODO/工单 |
| handoff | 交接（跨 session/跨 agent） | lineage summary、工单提示词 |
| observation | 观察（事实/事件，claude-mem 线） | 原始 turn 摘要 |
| **warning**（本土） | 风险/坑/铁律（用户纠正） | lifecycle expire 决策、用户纠正记录 |
| **intent**（本土） | 用户意图/偏好（可推导） | 用户 profile 类 |

### 2.2 实体字段（par Memory 裁剪 + 供应链铁律扩展）

```
id: string
type: decision|insight|task|handoff|observation|warning|intent
content: string
project?: string
tags?: string[]
refs?: string[]          # 关联实体 id（实体图谱边）
embedding?: float32[]   # 向量路（hybrid_search 复用）
pinned: bool            # 防止被 consolidation/retention 清掉
pinned_reason?: string
archived: bool
archived_at/by?: string
consolidated_from?: int  # 合并来源数（溯源）
consolidated_into?: id
retention_rule?: {max_age_days, applied}
**provenance**: {source: session_id|agent|file, ts, confidence, origin_rank}  # 供应链铁律：写时来源分级
created/updated: iso
```

关键差异 vs par：**provenance 字段必填**（论文 08-25/08-26 授粉点：持久记忆=攻击面，写时校验+来源分级；与用户供应链铁律同构）。

### 2.3 知识图谱层（par KnowledgeEntity/Relationship 裁剪）

- 实体表 `entities` 之上加 `entity_mentions`（name → memory_id 提及计数）与 `entity_relations`（from/to/type/weight）。
- 构建时机：不实时抽取（省算力），随 consolidation 批处理抽 KG（par 做法：auto-consolidation 时 extractKG）。
- 查询：图遍历只在 refs 命中时展开，默认仍走 hybrid_search RRF。

## 3. 生命周期与自维护（par schedulers 移植）

| 调度 | 周期 | 动作 | 五件套对应 |
|------|------|------|-----------|
| consolidation | 6h 或阈值触发（≥N 活跃记忆） | 同 project+同主题聚类 → LLM 蒸馏成 insight 实体，旧实体标 consolidated_into | compaction_v2（升级：从纯计算到 LLM 蒸馏） |
| retention sweep | 6h | 未 pinned + 无 consolidation 来源 + 超 90 天 → archived + retention_rule 记录 | lifecycle.expire_decision（对齐参数） |
| heartbeat | 15min | 写 system.heartbeat 事件（幂等，仅存最近 N 条） | lineage register（轻量健康探针） |
| epistemic audit（可选） | 6h | par 特有：记忆间矛盾检测 | 暂缓，v2 |

默认值对齐：retention 90 天、consolidation 阈值、heartbeat 15min（与 claude-mem 心跳一致）。

## 4. 与五件套的关系：sidecar 化（沿用 Memory-MaaS-Research-v1 结论）

- memory_maas = 五件套之上的 **typed 层**，不是重写：
  - 新表：`typed_memories`（实体表）+ `entity_mentions` + `entity_relations`
  - hybrid_search / index_cards 保持原样，typed 实体写入时同步建索引（复用 BackgroundWriter 单写者模型）
  - 读路径：typed 查询优先，未命中回退 blob 检索（渐进增强，不破坏现有调用方）
- 暴露面：HTTP sidecar（研究 v1 已评估：读路径幂等可直曝，写路径单写者串行化），端点：
  - `POST /memory/typed/store`（带 provenance 必填）
  - `GET /memory/typed/search?type=&project=&q=`
  - `GET /memory/typed/entity/{id}/relations`
  - `POST /memory/consolidation/run`（手动触发，v1 不做自动 6h，先手动+工单）
- 单写者铁律：sidecar 是数据目录唯一写进程，进程内 RLock 串行化；写路径走 BackgroundWriter。

## 5. claude-mem 借鉴点（压缩+注入，v2 候选）

- observation 捕获：hook 层记录 turn（files_read/files_modified/type），sha256 内容哈希去重（claude-mem computeObservationContentHash）
- 压缩：LLM 压缩成 XML 结构块，session 结束时写 summary checkpoint
- 注入：新 session 按（project + 关键词 + 路径）检索注入，limit 默认 15、上限 100（claude-mem 实测参数）
- 多路径匹配：PreToolUse/PostToolUse 路径形式不一致坑（#2691）→ 注入检索要同时匹配绝对/相对/项目根三种路径形式

## 6. 优先级

- P0：typed_memories 表 + provenance 必填 + store/search 端点（sidecar）
- P1：consolidation 手动触发 + KG 批处理抽取
- P2：heartbeat 事件、retention 参数对齐
- v2：observation 自动捕获 + 注入工作流（claude-mem 全链路）

## 7. 差距清单（对照 par/claude-mem）

1. 五件套无 typed 实体层 —— 本 SPEC 补
2. 无 KG（实体关系图谱）—— P1 补
3. compaction_v2 是纯计算无 LLM 蒸馏 —— consolidation 升级补
4. 无写时 provenance —— 供应链铁律要求，P0 内置
5. 无 observation 自动捕获/注入 —— v2
6. retention 参数未对齐（14天 vs par 90天）—— P2 评审定
