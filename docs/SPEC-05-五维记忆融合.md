# SPEC-05 · 五维记忆融合方案（调研+设计）

> 日期 2026-08-22 深夜 | 状态：调研完成，方案待评审
> 目标：summer_memory 五元组 GRAG 不再"废掉"，做真正的混合记忆融合

## 一、现状盘点（代码实测）

### 1.1 summer_memory = 五维记忆本体（主链路 SSOT）
- 数据模型：五元组 `(e1, r, e2, t, extra)` 知识图谱，Neo4j + 本地 `quintuples.json` 双后端
- 写入：`memory_manager.add_conversation_memory(user, ai)` → `quintuple_extractor` → `quintuple_graph.store_quintuples`（post-chat 异步回调）
- 读取：`lumo_proxy._hybrid_recall` 在 prompt 注入前召回（3s 超时保护）
- 模块清单：quintuple_extractor / quintuple_graph / memory_manager / reversible / rag_query_tri / quintuple_rag_query / memory_client / task_manager / graph

### 1.2 lumo_proxy 当前已是 4 路并行召回（asyncio.gather）
| 路径 | 实现 | 擅长 |
|------|------|------|
| P1 GRAG | summer_memory 五元组图谱查询 | 关系推理 |
| P2 向量 RAG | RAGService SQLite 向量（bge-small-zh）| 事实查询/笔记匹配 |
| P3 语义推理 | 五元组→RDF 本体规则推理（只读）| 规则推导新事实 |
| P4 化学计算 | ChemFormula 确定性计算（只读）| 分子量/组成 |

### 1.3 差距清单（"废掉"的真正原因）
1. **融合是字符串拼接**：4 路结果 `"\n\n".join()` 直接堆进 prompt，无 RRF/加权排序，无去重——关系命中可能被向量噪声淹没
2. **无索引卡层**：缺 mempalace AAAK 式"扫一眼定位"的压缩索引，长会话主题漂移后召回弱
3. **无会话血统**：记忆项不带 session lineage，跨会话引用无法溯源
4. **无记忆更新/过期**：只增不改，低频记忆冗余
5. **无时间维度**：mem0 有 Temporal Reasoning（"最近/过去/将来"），我们 t 字段没用于排序
6. **写路径仍是前台**：post-chat 回调占异步任务，无后台静默批量写入

## 二、参考项目调研（混合记忆怎么融合）

### 2.1 mem0（Apache-2.0）— multi-signal retrieval 标杆
- **三路并行打分融合**：semantic（向量）+ BM25（关键词）+ entity matching（实体匹配），各自打分后融合排序
- **Temporal Reasoning**：时间感知排序——同一实体在不同日期的实例，按"当前/过去/未来"语境选对的那个
- **实体图谱关联**：记忆项带实体关系，跨记忆关联检索
- **Benchmark**：92.5 LoCoMo（+21 分）
- **对我们的启示**：我们的 P1 GRAG 本身就是"实体匹配"的超级形态（五元组关系），缺的是把 P2 向量分数与图谱命中做**统一排序**而非拼接

### 2.2 mempalace（MIT）— 索引卡/分层标杆
- **AAAK 压缩索引**：名字/词/概念 → AI 可读简写，索引卡指向 drawer 原文——"扫一眼就知道在哪"
- **宫殿分层**：wings(人/项目) → rooms(主题) → closets(压缩索引) → drawers(原文)
- **后台 hooks 静默写入**：subagent 后台跑，不进 chat token（v4 教训：前台写 $1.13/会话）
- **Benchmark**：96.6% R@5 raw on LongMemEval（zero API calls）
- **对我们的启示**：给 summer_memory 加 `index_cards` 表——会话主题/关键实体写压缩卡片，检索先查卡片再定位五元组

### 2.3 cozo（MPL-2.0）— 三合一存储候选
- 关系 + 图 + 向量三合一，Datalog 查询语言，事务性
- 与 Apache-2.0 的 NEKO/scratchpad 组合合法（文件级 copyleft，调用不传染）
- **对我们的启示**：远期可替代"Neo4j + SQLite + 向量库"三套分家；但当前主链路稳定，仅作 Phase6 候选

### 2.4 其他
- **duckdb**：分析查询加速（已评估，材料数据场景用）
- **graphify**：代码库/文献 → 知识图谱（Lumo P2，与记忆图谱互补，不重叠）

## 三、混合方案设计（五维融合 = 5 路信号统一排序）

### 3.1 目标架构（升级 lumo_proxy 召回）

```
question
  │
  ├─► 维度1 GRAG 图谱（五元组关系推理）  ─┐
  ├─► 维度2 向量语义（bge-small-zh）     ─┤
  ├─► 维度3 BM25/FTS 关键词（quintuples.json）─┤→ RRF 融合排序
  ├─► 维度4 索引卡（index_cards 表，新增）─┤   (Reciprocal Rank Fusion)
  ├─► 维度5 时间/会话血统（t + session_id）─┘    + 去重 + 截断
  │
  └─► P3 语义推理 / P4 化学 保持旁路（确定性，不进排序）
```

### 3.2 RRF 融合（替代字符串拼接）
- 每路返回 top-k（k=5~10），每项记 rank，RRF score = Σ 1/(60 + rank)
- 简单、无需训练权重、跨异构信号天然可比（mem0/graphite 同款思路）
- 融合后按 score 降序，截断前 2000 字符进 prompt
- 附加：去重（同一原文多路命中只留一次，score 累加）

### 3.3 index_cards 索引卡（新增表）
- 字段：`card_id, topic, entities(JSON), keywords, created_at, last_access, session_id, ref_quintuple_ids`
- 写入：后台异步（post-chat 摘主题 → 生成卡片 → 关联五元组）
- 检索：先关键词匹配卡片 → 命中则直接取卡片关联的五元组，未命中走 5 路融合

### 3.4 会话血统 + 时间排序
- 五元组已带 t（时间戳）字段 → 查询时按 t 加权（近期 ↑）
- 记忆项补 `session_id` 血缘 → 可追溯"这条记忆来自哪次会话"

### 3.5 记忆更新/过期（低频衰减）
- `last_access` + 置信度；90 天未访问的降权，180 天可归档（不动原文，只降检索优先级）

## 四、工作量与落地路径

| 步 | 内容 | 代码量 | 模式 |
|----|------|--------|------|
| S1 | RRF 融合模块（lumo_proxy 改造） | ~150 行 | 沈遥自做 |
| S2 | index_cards 表 + 后台写入 | ~250 行 | 沈遥自做 |
| S3 | BM25/FTS 第三路召回 | ~120 行 | 沈遥自做 |
| S4 | 会话血统 + 时间加权 | ~100 行 | 沈遥自做 |
| S5 | 记忆过期/降权 | ~80 行 | 沈遥自做 |
| S6 | 回归测试（对照 4 路拼接基线） | ~200 行 | 沈遥自做 |

**总计 ≈ 900 行，全部沈遥线（不占 Trae 工单），且不侵入 NEKO 核心**（改 lumo_proxy + summer_memory 新增表，NEKO 桌宠壳零改动）

## 五、dsh（deepseek-harness）有没有搞头？

**结论：有参考价值，无依赖价值——取思想，不引 Node 栈。**

| 维度 | 评估 |
|------|------|
| 定位 | DeepSeek 官方 agent harness，"Everything is a Plugin"，基于 Cordis（时空可组合编程范式） |
| 现状 | 184k★，MIT，developer preview（明示 compatibility-breaking changes 频繁） |
| 架构 | Node.js/npm/pnpm/npx 生态，Web UI :3080，插件化注册 |
| 与我们关系 | mcpserver 的 Service Definition 模式已参考过它（Batch-1A）；Plugin 注册机制与我们的三表注册中心同构 |
| 为什么不依赖 | ① 栈不匹配（我们 Python，它 Node）；② preview 期 breaking changes 频繁，深度依赖会拖垮维护 |
| 取什么 | ① Cordis 的"插件=可组合单元"心智 → mcpserver 适配器进一步解耦；② AGENTS.md 面向 agent 的文档写法 → 我们 apiserver/mcpserver 已有，保持 |

**一句话**：dsh 是"看它怎么组织插件生态"的参考书，不是要搬进来的依赖。

## 六、进一步优化总线（mcpserver）

### 6.1 现状（AGENTS.md + 代码实测）
- 三表注册中心：`MCP_REGISTRY` / `MANIFEST_CACHE` / `_ADAPTER_CAPABILITIES`，跨源冲突检测只 WARNING 不阻断
- `MCPManager.unified_call()` 统一路由；`security_utils` 白名单（`mcpserver.` / `vendor.` 前缀）
- 外部 MCP：`mcporter_bridge.py` + `external_services.example.json`（toolbox-postgres / swarmvault / mentedb / arcrift / apify 全 `_disabled`）
- 参考仓已记：mcp-gateway-registry（鉴权/动态发现/安全扫描）、arcade-mcp（decorator + 声明式 OAuth）

### 6.2 优化点（按优先级）

| # | 优化 | 动作 | 优先级 |
|---|------|------|--------|
| B1 | 跨源冲突升级 | 冲突从 WARNING 升为可配置 FAIL（`CONFLICT_STRICT=1`） | P1 |
| B2 | Context7 MCP 接入 | 防 API 幻觉，注册进总线 | P1 |
| B3 | 外部服务解禁 | 按需启用 mentedb（AI 记忆引擎）/ arcrift（编程跨会话记忆）——与五维记忆融合互补 | P2 |
| B4 | 声明式鉴权 | 借鉴 arcade-mcp `requires_auth=` 模式，给需凭证 adapter 加声明式 OAuth | P2 |
| B5 | 工具级可观测 | unified_call 增加 latency/失败率指标表，暴露 `/metrics` | P2 |
| B6 | dsh 插件解耦心智 | 适配器注册进一步"插件化"（热插拔开关，不重启） | P3 |

### 6.3 总线与五维记忆的接口
- 记忆 sidecar/索引卡检索注册为 MCP 工具 `memory_search`（供其他 agent 调）
- 总线不接管主链路（summer_memory 仍走 apiserver 直连），只提供跨 agent 访问

## 七、行动顺序（沈遥线，不占 Trae）

1. S1 RRF 融合（五维记忆第一步，立竿见影）
2. B2 Context7（写码质量立即提升）
3. S2 索引卡 + S3 BM25 第三路
4. B1 冲突严格化（低风险配置改动）
5. S4/S5 血统+过期 → S6 回归
6. B3 按需解禁外部记忆服务

**铁律遵守**：NEKO 桌宠壳零改动，全部改 lumo_proxy / summer_memory / mcpserver 外围；token 不给图像。
