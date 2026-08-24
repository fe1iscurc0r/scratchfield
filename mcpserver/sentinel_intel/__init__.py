"""sentinel_intel — 威胁情报记忆层（SPEC-09 第五批：K/L/M 三线共建）。

K 线：schema.py / alias_resolver.py / graph.py（情报图谱化）
L 线：lifecycle.py（可逆遗忘：decay/restore/merge + 时序索引）
M 线：collectors/（OSINT 采集器 MCP 封装）

K 线：schema.py / alias_resolver.py / graph.py（情报图谱化）
L 线：lifecycle.py（可逆遗忘：decay/restore/merge + 时序索引）
M 线：collectors/（OSINT 采集器 MCP 封装）

授粉源（只读参考，独立轻量重写，未 copy 代码）：
- ThreatRecall/zettelforge（MIT）src/zettelforge/knowledge_graph.py
  —— SDO/SRO 模型 + 时序边 + traverse（DFS 环预防）+ get_entity_timeline
- ThreatRecall/zettelforge（MIT）src/zettelforge/alias_resolver.py
  —— 别名规范化（lower + 连字符转空格）+ 多级回退解析，未命中原样返回

与 zettelforge 的差异：图回退走自家 SQLite intel_edge 的 alias_of 边
（上游依赖 TypeDB，太重）；K/L/M 三线同仓，各自 tests/。
硬约束：纯 Python + SQLite 零新增依赖；不复用 F-03 memory_graph.py 实现。
"""
