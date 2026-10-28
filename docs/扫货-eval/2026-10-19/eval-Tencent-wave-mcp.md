# Tencent/wave-mcp 评估

## 1. 项目
- 定位：腾讯开源的 MCP 服务（具体能力见顶层树）
- 星数：**243** ／ Fork：36 ／ Open issues：4
- 许可：spdx_id = `NOASSERTION`；顶层许可文件 `LICENSE`
- 仓体大小：`13090` KB（≈ 12.8 MB，GitHub 计量，含资产）
- 最近 push：`2026-10-14` ；创建：`2026-07-27` ；语言：`Python`
- archived：`False`

## 2. 协议与架构
- 入口点：服务入口 + MCP 工具定义
- 关键 API：MCP 工具集合
- 目录骨架（顶层，`gh api contents` 只读拉取，未 clone）：
```
  f .gitignore
  f CHANGELOG.md
  f LICENSE
  f MANIFEST.in
  f README.en.md
  f README.md
  d deploy
  d docs
  d examples
  f pyproject.toml
```
- 顶层共 14 项（截断显示前 10）。

## 3. 本侧对照
- 对应 `mcpserver/`（本仓 MCP 服务形态）
- 判断依据：本项与上述模块解决的是同一层问题（腾讯开源的 MCP 服务（具体能力见顶层树）），因此对照点落在接口形态与数据流，而不是功能罗列。

## 4. 授粉价值（3 条）
1. MCP 工具定义与错误码的组织方式 → ``mcpserver/``
2. 服务启动/健康检查的约定 → ``mcpserver/``
3. 与 wave-mcp 能力重叠部分的取舍 → ``docs/``

## 5. 难度 × 收益
- **低 × 低**：同为 MCP 服务，可直接对照协议细节；能力重叠需先判定

## 6. 接入模式
- **设计输入**：**许可**：`spdx_id = NOASSERTION`，实读 `LICENSE`（205 KB）为 **Apache-2.0 + 第三方组件清单**（体积大是因内嵌 NOTICE）；实际许可仍为 Apache-2.0，引用时需保留第三方声明。
