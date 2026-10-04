"""memory_maas — 记忆 MaaS sidecar + MCP 桥（W-06 + X 线 + v2 借鉴点）。

- core.py：NEKO 记忆五件套组合层（血统/索引卡/混合检索/衰减过期）+ typed 实体委托
- entities.py：MemoryEntity typed 实体模型（decision/insight/handoff/note）+ SQLite 双表
  （v2：observation_hash 去重列 + platform_source 平台列 + provenance 投影）
- capture.py：观察捕获层（03-01 内容哈希去重，写前校验=来源分级→哈希去重→入库）
- paths.py：路径归一化三形式等价匹配（03-02，防 claude-mem #2691）
- xml_template.py：压缩块 XML 模板 + 三层容错解析（03-03）
- maintenance.py：遗忘调度 / 相似合并（XML 模板升级）/ 快照旁路（cron 触发）
- guard.py：写前校验 + 来源分级 + 隔离区 + 流策略
- app.py：FastAPI HTTP 面（127.0.0.1:48919）
- bridge.py：MCP 工具桥（sidecar 不通时进程内降级）
- tools_policy.json：实体类型 → 工具白名单流策略
- 调研与端点设计：docs/Memory-MaaS-Research-v1.md
"""
