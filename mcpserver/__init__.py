"""MCP 服务包 — manifest 注册、agent 实例创建、适配层、服务发现与查询。

子模块：
- mcp_registry: 三表注册中心（MCP_REGISTRY / MANIFEST_CACHE / _ADAPTER_CAPABILITIES）
- mcp_manager: MCPManager 单例，unified_call 路由
- mcp_server: FastAPI HTTP 入口
- adapters/: 第三方能力包适配层（agent_reach / vulnclaw / memclaw / headroom）
"""
