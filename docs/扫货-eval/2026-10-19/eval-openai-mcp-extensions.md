# openai/mcp-extensions 评估

## 1. 项目
- 定位：MCP 协议扩展集合（官方维护的扩展提案/实现）
- 星数：**1088** ／ Fork：53 ／ Open issues：13
- 许可：spdx_id = `Apache-2.0`；顶层许可文件 `LICENSE`
- 仓体大小：`72514` KB（≈ 70.8 MB，GitHub 计量，含资产）
- 最近 push：`2026-10-10` ；创建：`2026-09-29` ；语言：`TypeScript`
- archived：`False`

## 2. 协议与架构
- 入口点：各扩展子目录
- 关键 API：MCP 扩展能力（如 resources/prompts 增强）
- 目录骨架（顶层，`gh api contents` 只读拉取，未 clone）：
```
  d .agents
  d .github
  f .gitignore
  f .prettierignore
  f .release-please-manifest.json
  f AGENTS.md
  f CHANGELOG.md
  f LICENSE
  f README.md
  f SECURITY.md
```
- 顶层共 21 项（截断显示前 10）。

## 3. 本侧对照
- 对应 `mcpserver/`（本仓 MCP 服务）+ `mcpserver/agentic_inventory/`（工具盘点）
- 判断依据：本项与上述模块解决的是同一层问题（MCP 协议扩展集合（官方维护的扩展提案/实现）），因此对照点落在接口形态与数据流，而不是功能罗列。

## 4. 授粉价值（3 条）
1. 扩展能力的落地形态，作为我们 MCP 服务的兼容参考 → ``mcpserver/``
2. 工具清单/能力声明的写法（与 agentic_inventory 对照） → ``mcpserver/agentic_inventory/``
3. 协议演进方向，避免自造不兼容扩展 → ``docs/``

## 5. 难度 × 收益
- **低 × 中**：官方仓，协议口径权威；接入成本低（读规范为主）

## 6. 接入模式
- **设计输入**：仓体 72,514 KB ≈ 71 MB（含示例与测试数据），只读规范与关键实现。
