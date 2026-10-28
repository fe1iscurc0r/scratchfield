# HexRaysSA/ida-mcp 评估

## 1. 项目
- 定位：IDA Pro 的 MCP 服务（把 IDA 能力暴露成工具）
- 星数：**1298** ／ Fork：95 ／ Open issues：12
- 许可：spdx_id = `MIT`；顶层许可文件 `LICENSE`
- 仓体大小：`372` KB（≈ 0.4 MB，GitHub 计量，含资产）
- 最近 push：`2026-10-08` ；创建：`2026-08-27` ；语言：`Python`
- archived：`False`

## 2. 协议与架构
- 入口点：MCP server 入口 + IDA 插件
- 关键 API：反编译/交叉引用/函数列表等工具
- 目录骨架（顶层，`gh api contents` 只读拉取，未 clone）：
```
  d .claude-plugin
  d .codex-plugin
  d .github
  f .gitignore
  f .python-version
  f LICENSE
  f README.md
  d docs
  f ida-mcp.test.ts
  f ida-mcp.ts
```
- 顶层共 19 项（截断显示前 10）。

## 3. 本侧对照
- 对应 `mcpserver/`（本仓已有逆向类工具）+ `tools/`
- 判断依据：本项与上述模块解决的是同一层问题（IDA Pro 的 MCP 服务（把 IDA 能力暴露成工具）），因此对照点落在接口形态与数据流，而不是功能罗列。

## 4. 授粉价值（3 条）
1. 工具粒度设计（反编译返回值如何裁剪体积） → ``mcpserver/``
2. IDA 侧插件与 MCP 侧的通信约定 → ``tools/``
3. 大体量返回值的分页策略 → ``mcpserver/``

## 5. 难度 × 收益
- **中 × 中**：协议层可借鉴，但运行需要 IDA 商业授权，本机不验运行

## 6. 接入模式
- **设计输入**：**两件事必须分开写**：① 许可 = MIT（无问题）；② **依赖门槛** = 需 **IDA Pro 9.4+ 商业授权**才能运行。本单**仅评估，不验运行**（无授权环境）。
