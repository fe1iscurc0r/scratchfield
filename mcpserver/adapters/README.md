# mcpserver/adapters — 第三方能力包 MCP 适配层

[实验田维护者架构建议] 不直接把 vendor/top5 各项目的 MCP 文件塞进 mcpserver/ 扁平目录，而是在此做薄封装，形成显式集成边界：
核心层保留扁平（manager/registry/server/security/mcporter_bridge），adapters/ 是独立的 vendor 适配子目录。

## 目录结构

```
mcpserver/adapters/
├── __init__.py          # register_all_adapters() 总入口
├── README.md            # 此文件
├── vulnclaw.py          # VulnClaw MCP（AI 渗透测试） MIT
├── agent_reach.py       # Agent-Reach MCP（多平台搜索 13 channel） MIT
├── memclaw.py           # MemClaw MCP（跨 Agent 记忆总线） Apache-2.0
└── headroom.py          # Headroom MCP（上下文压缩 CCR） Apache-2.0
```

## 职责

每个 adapter 只做 3 件事：
1. **凭证 fail-fast 检查**：在 import/构造阶段就 fail-fast（如 VulnClaw 需要 OPENAI_API_KEY、memclaw 需要 StorageBackend 配置），避免运行时才抛
2. **sys.path 注入**：vendor/top5/<项目>/*/src 不是默认 import 路径，adapter 在 `_ensure_path()` 时临时加路径，用完不移除以保持简单
3. **暴露适配函数**：统一返回 `register_scoped()` 注册自己的 tools 到 scratchpad MCP 服务、或 `get_mcp_app()` 作为独立 MCP 子服务挂载

adapter **不做业务逻辑**，不重写工具 schema 或实现，直接透传 vendor/top5 代码里的已注册工具。

## 启用方式

```python
from mcpserver.adapters import register_all_adapters
register_all_adapters(mcp_server, mcp_registry)  # 过滤未通过健康检查的 adapter
```

未通过健康检查（凭证缺失 / 依赖未装 / Windows Rust wheel 不可用等）的 adapter 自动跳过并打日志，不让全局启动失败。
