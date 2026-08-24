"""memory_maas — 记忆 MaaS sidecar + MCP 桥（W-06）。

- core.py：NEKO 记忆五件套组合层（血统/索引卡/混合检索/衰减过期）
- app.py：FastAPI HTTP 面（127.0.0.1:48919）
- bridge.py：memory_search 等 MCP 工具（sidecar 不通时进程内降级）
- 调研与端点设计：docs/Memory-MaaS-Research-v1.md
"""
