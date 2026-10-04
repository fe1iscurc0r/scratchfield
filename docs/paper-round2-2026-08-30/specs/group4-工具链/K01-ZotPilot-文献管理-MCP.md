# K01 ZotPilot 文献管理 MCP

> 来源分组：group4-工具链

【SPEC】ZotPilot（文献管理 MCP）接入材料文献库；验收=MCP 封装+注册+测试。
【工单】①勘察 ZotPilot 仓库（许可核实）②封装 MCP（搜索/导入/标注）③注册 agent-manifest④测试。
【提示词】你是 MCP 封装 AI。封装 ZotPilot 文献管理：先 gh api 核实许可（无 LICENSE 暂缓），按 mcpserver/ 现有风格封装（manifest.json + Python class + 单测），支持文献搜索/批量导入/方向标注。验收：pytest 全过 + manifest 注册 + 许可标注。
