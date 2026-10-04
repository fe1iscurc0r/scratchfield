# Agent Memory Techniques — 记忆层选型地图

> 2026-08-29 · 来源：NirDiamant/Agent_Memory_Techniques（Apache-2.0，938★，30 个可运行 Jupyter notebook）
> 用途：对照 SPEC-03 五件套 + memory_maas 设计，逐项标注"已有/缺/待做"，形成记忆层选型地图
> 完整 clone 在 github_haul/Agent_Memory_Techniques/all_techniques/

## 选型地图（30 项对照）

| # | 技术 | 五件套/设计现状 | 结论 |
|---|------|----------------|------|
| 01 | conversation buffer | 原始 turn 记录（index_cards 输入） | 已有（数据源） |
| 02 | sliding window | compaction_v2 分支摘要 | 已有等效 |
| 03 | summary memory | index_cards build_card | ✅ 已有 |
| 04 | summary buffer | lifecycle + BackgroundWriter | ✅ 已有 |
| 05 | token buffer | compaction_v2 measure（token 节省评测） | ✅ 已有 |
| 06 | vector store | hybrid_search hs_vecs（fp16） | ✅ 已有 |
| 07 | entity memory | ❌ 无实体记忆 | **缺** → memory_maas typed 层 |
| 08 | knowledge graph | ❌ 无 KG | **缺** → memory_maas P1 |
| 09 | episodic memory | lineage session 链 | 部分（会话级，非事件级） |
| 10 | semantic memory | hybrid_search FTS+向量 | ✅ 已有 |
| 11 | procedural memory | skills/ 体系 | ✅ 已有（skill 即程序记忆） |
| 12 | working memory | 上下文窗口管理（headroom/context_compressor） | ✅ 已有 |
| 13 | hierarchical layers | lineage 根-分支树 | 部分（缺跨层聚合） |
| 14 | consolidation | memory_maas P1（LLM 蒸馏） | **待做** |
| 15 | compaction | compaction_v2 | ✅ 已有 |
| 16 | self-reflection | ❌ | 缺（低优先） |
| 17 | memory routing | ❌ 检索无路由层 | **缺** → 可做（type/project 路由） |
| 18 | temporal memory | lifecycle half_life/decay | ✅ 已有 |
| 19 | forgetting/decay | lifecycle expire_decision | ✅ 已有 |
| 20 | retrieval patterns | hybrid_search RRF | ✅ 已有 |
| 21 | cross-session | lineage + index_cards touch 续命 | ✅ 已有 |
| 22 | multi-agent shared | weixin/qqbot/cli 共享工作树 | 部分（共享文件，无共享记忆协议） |
| 23 | memory with tools | ❌ 记忆不感知工具调用 | **缺** → claude-mem 捕获层（v2） |
| 24 | graphiti | ❌ | 缺（KG 参考，评估 temporal KG 价值） |
| 25 | mem0 patterns | ❌（SPEC-03 曾授粉 mem0） | 参照（混合检索） |
| 26 | letta/memgpt | ❌ | 低优先（重运行时） |
| 27 | zep | ❌ | 低优先（托管/重） |
| 28 | memory evaluation | ❌ 无评测集 | **缺** → 可做（检索质量回归） |
| 29 | LoCoMo benchmarks | ❌ | 低优先（长会话评测） |
| 30 | production patterns | 五件套 sidecar（单写者/RLock） | ✅ 已有（研究 v1） |

## 结论：记忆栈健康度

- **已有/等效：16/30** —— 五件套覆盖扎实，核心读写路径全在。
- **明确缺口（4 个，按优先级）**：
  1. 实体记忆 + KG（07/08）→ memory_maas typed 层，SPEC 已出，P0/P1
  2. 记忆路由（17）→ 检索前按 type/project 分流，成本低，可并入 memory_maas
  3. 记忆评测集（28）→ 建 30-50 条"应召回"用例做回归，防检索退化
  4. 工具感知捕获（23）→ claude-mem 捕获层，v2
- **不追（低价值）**：16 self-reflection（LLM 自省成本高）、24 graphiti（时序 KG 重）、26/27（重运行时）、29（评测基准重）。

## 落地建议

- P0：memory_maas typed 层按 SPEC 实现（覆盖 07/08 两个最大缺口）
- P1：记忆路由（17）并入 memory_maas 查询面（type + project 过滤器已有设计）
- P1：记忆评测集（28）—— 30 条用例 + 召回率脚本，落到 memory_maas 测试
- 本地图作为记忆层 backlog 的对照底稿，后续每次记忆迭代先对表。
