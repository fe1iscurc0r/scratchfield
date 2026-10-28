# AtomFlow-AI/MoleCode 评估

## 1. 项目
- 定位：分子/材料领域的 LLM 工具（代码生成 + 计算流程）
- 星数：**306** ／ Fork：9 ／ Open issues：2
- 许可：spdx_id = `MIT`；顶层许可文件 `LICENSE`
- 仓体大小：`12833` KB（≈ 12.5 MB，GitHub 计量，含资产）
- 最近 push：`2026-06-04` ；创建：`2026-05-30` ；语言：`Python`
- archived：`False`

## 2. 协议与架构
- 入口点：CLI / Python 包
- 关键 API：分子性质计算、流程编排
- 目录骨架（顶层，`gh api contents` 只读拉取，未 clone）：
```
  d .claude
  f .gitattributes
  d .github
  f .gitignore
  f AGENTS.md
  f LICENSE
  f PYPI_README.md
  f README.md
  f README.zh-CN.md
  d docs
```
- 顶层共 14 项（截断显示前 10）。

## 3. 本侧对照
- 对应 `skills/`（材料类 Skill）+ `mcpserver/`（计算工具封装）
- 判断依据：本项与上述模块解决的是同一层问题（分子/材料领域的 LLM 工具（代码生成 + 计算流程）），因此对照点落在接口形态与数据流，而不是功能罗列。

## 4. 授粉价值（3 条）
1. 分子描述符计算流程的编排方式 → ``skills/``
2. 与 RDKit 类库的边界划分（哪些进 MCP、哪些进 Skill） → ``mcpserver/``
3. 材料任务的 prompt 结构参考 → ``skills/``

## 5. 难度 × 收益
- **中 × 中**：材料线已有邵长优方向的独立线；此仓最后一次 push 在 06-04，活跃度偏低

## 6. 接入模式
- **设计输入**：最近 push **2026-06-04**（>4 个月未更新），接入前需确认是否仍维护。
