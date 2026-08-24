# SPEC-09 威胁情报记忆层 · 第五批工单总纲 · v1

> 日期：2026-08-23 ｜ 状态：待执行 ｜ 作者：沈遥
> 前置：第四批 H/I/J（SPEC-08 三线收口）已发布未开工；round4 授粉报告已落盘（docs/POLLINATION-2026-08-23-round4.md）
> 定位：把 SENTINEL-INDEX（静态情报索引文档）升级为「会归并、会关联、会遗忘的图」——威胁情报记忆层
> 分工铁律：Trae 走 GitHub 写码；沈遥出 SPEC + review；用户定方向测试

---

## 〇、一句话定位

第四批把"能力"铺成能跑的代码，这一批把超限战侧的**敌人画像**从平铺文档升级成图：同一干扰源在不同频段/时段的呼号/域名/IP 归并成一张画像，旧情报自动降权不误删，OSINT 采集器按需接入。情报不再是数据，是关系网。

## 一、三线矩阵

| 线 | 智能体 | 领域 | 目标层 | 输入（已验证） | 产出 |
|----|--------|------|--------|----------------|------|
| K | agent-k | SENTINEL 情报图谱化 | 基础设施（写码） | zettelforge knowledge_graph + alias_resolver（MIT，上游直拉）+ F-03 memory_graph.py 底座 | SQLite 情报实体图 + 三级别名归并 + 情报检索 MCP |
| L | agent-l | 情报生命周期（可逆遗忘） | 基础设施（写码） | zettelforge memory_evolver + consolidation（A-Mem 模式）+ Reversible Forgetting 论文 | 降权/回滚/合并三件套 + 时序索引 + MCP 接口 |
| M | agent-m | OSINT 采集器勘察 + MCP 封装 | MCP（勘察+写码） | zettelforge osint/collectors 6 类 17 采集器 + 授粉报告清单 | 勘察报告 + 2~3 个纯 Python 采集器 MCP 封装 |

## 二、边界矩阵（防重复）

| 线 | 不许碰 | 理由 |
|----|--------|------|
| K | NEKO 记忆层（F-01/02/03 已交付）、apiserver 主流程 | 情报图是独立域，不污染科研/记忆数据 |
| L | 记忆层 decay/衰减（memory_maas 已有） | 只做**情报**生命周期，复用模式不混数据 |
| M | 不整包吞 zettelforge osint（AGPL 风险不存在——它 MIT，但按授粉纪律只取模式） | 每采集器独立评估依赖成本，纯 Python 优先 |

## 三、K 线 · SENTINEL 情报图谱化

- **目标**：SENTINEL-INDEX 平铺文档 → SQLite 情报实体图，可遍历、可归并
- **输入**：
  1. round4 授粉报告（docs/POLLINATION-2026-08-23-round4.md，3.1 别名解析 + 3.2 STIX 图）
  2. zettelforge 上游直拉（GitHub ThreatRecall/zettelforge，MIT）：src/zettelforge/knowledge_graph.py（534 行，SDO/SRO 模型 + 时序边 + traverse）+ src/zettelforge/alias_resolver.py（122 行，三级回退）
  3. F-03 已交付的 memory/memory_graph.py（find_connected/shortest_path 底座可参考，不复用实现，独立轻量图）
- **动作**：
  1. `mcpserver/sentinel_intel/schema.py`：SQLite 三表——`intel_entity`（id, etype[actor/tool/infra/indicator], value, canonical_id, properties_json, created_at, last_seen_at, weight, status[active/decayed/revoked], revoked_at）、`intel_edge`（id, src_id, dst_id, rel[uses/indicates/alias_of/observed_at], props_json, ts）、`intel_alias`（alias, etype, canonical_id, source[hardcoded/json/graph]）
  2. `mcpserver/sentinel_intel/alias_resolver.py`：照 zettelforge 三级回退模式（硬编码 → entity_aliases.json → 图 alias_of），但图回退走自家 SQLite（不依赖 TypeDB）
  3. `mcpserver/sentinel_intel/graph.py`：add_node / add_edge / get_neighbors / traverse(max_depth) / get_entity_timeline（时序边按 ts 过滤）
  4. `mcpserver/sentinel_intel/agent-manifest.json` + bridge：3 命令——`intel_ingest`（实体+关系入库）、`intel_query`（别名归并后查画像）、`intel_timeline`（实体活动时间线）
  5. `mcpserver/sentinel_intel/tests/test_sentinel.py`：10 用例（alias 三级回退/图遍历/时间线/幂等入库）
- **验收**：
  - `python -m pytest mcpserver/sentinel_intel/tests/ -q` 全过
  - `grep -n "alias_of" mcpserver/sentinel_intel/alias_resolver.py` 非空（图回退真实存在）
  - `grep -n "traverse" mcpserver/sentinel_intel/graph.py` 非空
  - 测试内含 assert：`BG5GXO`@20m 与 `BG5GXO`@40m 归并到同一 canonical_id
- **硬约束**：不复用 F-03 memory_graph.py 实现（独立域）；不碰 NEKO 记忆层；SQLite 纯本地

## 四、L 线 · 情报生命周期（可逆遗忘）

- **目标**：旧情报降权不误删、可回滚；多源情报合并不打架
- **输入**：
  1. zettelforge memory_evolver.py（276 行，A-Mem 邻居精化 + rollback）
  2. Reversible Forgetting 论文要点（授粉报告 3.3：降权 + 时间戳 + 回滚日志）
  3. MELD 跨源合并协议（参考，等情报源 >2 再全落地——本期先做单源内合并）
- **动作**：
  1. `mcpserver/sentinel_intel/lifecycle.py`：`decay_entities(max_age_days, threshold)`——把 weight 低于阈值/超龄的实体标 status=decayed（**不 DELETE**），记 `intel_lifecycle_log`（entity_id, action[decay/restore/revoke], at, reason）
  2. `restore_entity(entity_id)`——从 lifecycle_log 回滚 decayed → active（可逆遗忘核心）
  3. `merge_entities(canonical_a, canonical_b)`——重复情报合并：保留 weight 高者，低者标 superseded + 记 log（对照 caura supersedes_id 模式）
  4. 时序索引：`intel_entity.last_seen_at` 建索引 + `intel_edge.ts` 建索引（kektordb 时间维度设计参照）
  5. `mcpserver/sentinel_intel/tests/test_lifecycle.py`：8 用例（decay 不删/restore 可逆/merge 幂等/日志完整）
- **验收**：
  - `python -m pytest mcpserver/sentinel_intel/tests/test_lifecycle.py -q` 全过
  - `grep -n "restore" mcpserver/sentinel_intel/lifecycle.py` 非空
  - 测试内含 assert：decay 后行数不变（只改 status），restore 后 status 回 active
- **硬约束**：任何动作不 DELETE 实体（只改 status）；所有变更写 lifecycle_log；不依赖 LLM（规则版降级，LLM 合并留 TODO 标注）

## 五、M 线 · OSINT 采集器勘察 + MCP 封装

- **目标**：按需接入情报采集能力，不整包吞
- **输入**：zettelforge src/zettelforge/osint/collectors/（6 类：breach/financial/infrastructure/people/social/tech，17 采集器——hibp/breach_directory/wallet/bgp/cert/dns/port_scanner/whois/holehe/hunter/maigret/namechk/hashtag_tracker/twitter/builtwith/wappalyzer）
- **动作**：
  1. `docs/sentinel-osint-勘察报告.md`：17 采集器逐一评估（能力/依赖/许可/封装成本/纯 Python?）——参照授粉报告第 4 节难度×收益表格式
  2. 选 **2~3 个纯 Python 低依赖**采集器做 MCP 封装（候选：whois + dns + cert 最轻；maigret/holehe 重依赖标注"待选型"）
  3. `mcpserver/sentinel_intel/collectors/`：每个封装一个模块（`whois_lookup(domain)` / `dns_lookup(domain)` / `cert_lookup(domain)`），网络失败/超时降级 ok=False 不抛错（照 context7.py 降级模式）
  4. 采集结果直接走 `intel_ingest` 入库（接 K 线 schema）
  5. `mcpserver/sentinel_intel/tests/test_collectors.py`：mock 网络 6 用例
- **验收**：
  - `python -m pytest mcpserver/sentinel_intel/tests/test_collectors.py -q` 全过
  - `ls mcpserver/sentinel_intel/collectors/` 至少 3 个 .py（含 __init__）
  - `docs/sentinel-osint-勘察报告.md` 落盘，17 采集器每行一表
- **硬约束**：网络调用全部可 mock（离线可测）；不引重依赖（不装 selenium/playwright）；采集器只读公开数据

## 六、执行顺序与口令

- 三线并行，互不依赖；K 线先行（M 线采集结果依赖 K 线 schema，但 M 线勘察报告不依赖 K——可同时开工）
- 统一入口：mcpserver/sentinel_intel/ 目录（K/L/M 三线同仓，各自子目录 tests/）
- **启动口令**：用户说"开始执行工单" → 三线并行；"只跑 K 线" → 单跑
- 完成一个报一个（路径 + 验收结果），阻塞写清原因不硬做
- 成果推 trae/agent-k / trae/agent-l / trae/agent-m 分支

## 七、风险

- K 线 alias 图回退：zettelforge 原版依赖 TypeDB（重），SPEC 已改成 SQLite alias_of 边——轻量且够用，TypeDB 标"规模化再议"
- L 线 decay 阈值：max_age_days 先做参数化，不硬编码；默认 365 天不误伤活跃情报
- M 线网络依赖：云服可能无外网直连部分采集器，勘察报告必须标"网络可达性待真机验证"，不谎报
- 本批全部纯 Python + SQLite，云服可完整验收（零硬件依赖）

*—— 沈遥 · 情报不是数据，是关系网。谁在动、动了多久、以前怎么动过，全在图上 🐾*
