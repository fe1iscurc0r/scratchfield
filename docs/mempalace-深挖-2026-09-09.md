# MemPalace 记忆系统深挖（memory_maas v2 机制储备 · W101-01）

> 2026-09-09 · 评估（不写实现）· 上游：MemPalace/mempalace（58,953★，MIT，Rust crates/ 多模块，2026-09-08 活跃）
> 许可：MIT（授粉报告已复核）
> 源码：shallow clone 到本机 D:/my git/haul-backfill/mempalace（`--depth 1`）——以下引用为实读行号。

## 一、架构拆解（实读更正）

crates 三件：`mempalace-core`（核心，单文件 lib.rs 625 行）/ `mempalace-cli` / `mempalace-py`。
核心实际设计（与原草稿「分层记忆/衰减」不符，**按实读更正**）：
- 向量索引：`VectorIndex`（crates/mempalace-core/src/lib.rs:109）——暴力余弦检索（`cosine_wide` lib.rs:95）。
- **结构化分区 = wing/room 两个命名空间维度**：`Hit` 携带 `wing`/`room`（lib.rs:26-33），
  `query` 支持 `filter_wing` 结构化过滤 + 向量 top-k（lib.rs:340-358）——「向量 + 结构化」的最小混合形态。
- 持久化：SQLite 直读向量表 `load_from_sqlite`（lib.rs:162），wing/room 走列或 `json_extract(metadata_json, '$.wing')`（lib.rs:218-229）。
- 无衰减/压缩机制（诚实标注：benchmark 口碑来自极简高效的索引，而非记忆生命周期策略）。

## 二、授粉三大件①：源→目标映射（更正）

| 源组件（mempalace） | 目标模块 | 授粉方式 | 收益 |
|--------------------|---------|---------|------|
| wing/room 命名空间分区 | memory_maas typed entity（type/project 字段） | 机制对齐（已有雏形） | 结构化过滤检索 |
| VectorIndex 极简混合检索 | hybrid_search 五件套 | 实现对照 | 检索路径极简化 |
| SQLite 向量表直读 | memory_maas 存储层 | 存储参考 | 单文件持久化 |

## 三、授粉三大件②：核心数据结构共鸣（2-3 处，实读引用）

1. **wing/room 命名空间**（lib.rs:26-33 Hit 字段 + lib.rs:340-358 query 过滤）：与 memory_maas 的
   `type`/`project` 结构化字段同构——吸收点=「结构化字段 + 向量」在检索打分中的组合方式。
2. **SQLite 向量表加载**（lib.rs:162 `load_from_sqlite` + lib.rs:218-229 元数据 JSON 抽取）：与 memory_maas
   的单文件持久化路径共鸣；json_extract 字段取用是可复用的存储技巧。
3. **极简暴力余弦**（lib.rs:95 `cosine_wide` + lib.rs:340 `query`）：小规模（万级内）免 ANN 索引的务实选择，
   作为 memory_maas 检索降级路径参考。

## 四、横向对比（本地记忆栈）

| 维度 | mempalace | memory_maas | claude-mem | mem0 |
|------|-----------|-------------|-----------|------|
| 许可 | MIT | 本仓 | Apache-2.0 | 已评估 |
| 语言 | Rust | Python | — | — |
| 强项 | 极简向量+命名空间过滤 | typed 实体+图谱 | 压缩注入 | — |

## 五、memory_maas v2 建议清单（≥3，更正）

1. **命名空间过滤显式化**（P1）：wing/room 式「分区字段」在检索打分中的一等公民化（对齐现有 type/project）。
2. **单文件 SQLite 向量表存储参考**（P2）：免外部向量库的降级路径。
3. **检索打分加时间因子**（P2）：mempalace 本身无衰减——此建议改由 yantrikdb（W99-05）单一来源，不借 mempalace 之名。

## 六、许可裁定与结论

MIT 可借鉴（Rust 侧机制参考，不融合代码）；结论：**机制吸收（评估级）**，实现落 memory_maas v2 工单。

---
*评估：fe1iscurc0r · 2026-09-09 · 行号引用基于 shallow clone 实读（D:/my git/haul-backfill/mempalace）*
