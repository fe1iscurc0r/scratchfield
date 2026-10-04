"""轻量 KG 记忆适配器（卷139）——三表 + recursive CTE 的对话记忆层。

设计借鉴 Glitch-Cat-Club/graph-memory-starter（MIT · 227★），只取设计不复制代码。
与既有 graphify 适配器的分工（避免重复造轮子）：
  * graphify  = **语料级**知识图谱（文件目录批量建图，供检索问答，agent 主动调用）
  * 本适配器 = **对话记忆级**知识图谱（边聊边增量写入，按提问自动注入上下文）
两者写入模式（批量 vs 增量）与触发方式（工具调用 vs prompt hook）不同，互补。

与 claude-mem 的分工：claude-mem 是"压缩+注入"（无实体/KG），本模块是实体图谱路线。
"""
from mcpserver.graph_memory_adapter.engine import (
    Facts,
    GraphMemory,
    default_db_path,
    entity_id,
    get_graph_memory,
    normalise,
    reset_graph_memory,
)

__all__ = [
    "Facts",
    "GraphMemory",
    "default_db_path",
    "entity_id",
    "get_graph_memory",
    "normalise",
    "reset_graph_memory",
]
