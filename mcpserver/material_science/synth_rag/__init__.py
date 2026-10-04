"""材料合成路线 RAG 旁路（I-02：PIRAG SSKB + 物理信息范式落地）。

用法（旁路，独立于 graphrag 主流程）：
1. store.RouteStore    结构化路线入库/更新/查询（SQLite，纯标准库）
2. retrieve.search     按产物/反应物/条件过滤 + 相似度排序（无向量 DB）
3. validator.validate  物理校验（规则表，非 LLM）
4. cli                  add / search / validate / seed 子命令
5. example_data         5 条木质素示例路线（is_example，来源标注待收集）

数据库默认 %APPDATA%/Lumo/synth_rag/routes.db（LUMO_SYNTHRAG_DB 可覆盖）。
硬约束：只做旁路，不触碰 graphrag 主流程；示例数据非科研引用依据。
"""
from . import example_data, retrieve, schema, store, validator

__all__ = ["schema", "store", "retrieve", "validator", "example_data"]
