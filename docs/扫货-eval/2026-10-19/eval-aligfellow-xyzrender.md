# aligfellow/xyzrender 评估

## 1. 项目
- 定位：分子结构渲染（xyz → 出版级图）
- 星数：**621** ／ Fork：60 ／ Open issues：14
- 许可：spdx_id = `MIT`；顶层许可文件 `LICENSE`
- 仓体大小：`537854` KB（≈ 525.2 MB，GitHub 计量，含资产）
- 最近 push：`2026-09-28` ；创建：`2026-02-20` ；语言：`Python`
- archived：`False`

## 2. 协议与架构
- 入口点：Python CLI + 渲染后端
- 关键 API：`xyzrender` 命令行、样式参数
- 目录骨架（顶层，`gh api contents` 只读拉取，未 clone）：
```
  f .copier-answers.yml
  d .github
  f .gitignore
  f .pre-commit-config.yaml
  f .readthedocs.yaml
  f CITATION.cff
  f LICENSE
  f README.md
  d docs
  d examples
```
- 顶层共 15 项（截断显示前 10）。

## 3. 本侧对照
- 对应 `mcpserver/`（材料可视化工具）+ `skills/`（材料绘图 skill）
- 判断依据：本项与上述模块解决的是同一层问题（分子结构渲染（xyz → 出版级图）），因此对照点落在接口形态与数据流，而不是功能罗列。

## 4. 授粉价值（3 条）
1. xyz 渲染的样式参数体系（配色/视角/标注） → ``mcpserver/``
2. 批量渲染的目录约定 → ``tools/``
3. 出版级图与交互式预览的分工 → ``docs/``

## 5. 难度 × 收益
- **低 × 中**：纯工具类，接入成本低；但仓体 525 MB 主要是示例资产

## 6. 接入模式
- **Skill**：**资产体积**：仓体 537,854 KB ≈ 525 MB（示例/输出占大头）⇒ **只读码不拉资产**。
