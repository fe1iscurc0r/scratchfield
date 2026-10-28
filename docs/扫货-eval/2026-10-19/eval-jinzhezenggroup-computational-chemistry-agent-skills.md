# jinzhezenggroup/computational-chemistry-agent-skills 评估

## 1. 项目
- 定位：计算化学 Agent Skills 集合（把计算化学流程写成 skill）
- 星数：**153** ／ Fork：29 ／ Open issues：10
- 许可：spdx_id = `LGPL-3.0`；顶层许可文件 `LICENSE`
- 仓体大小：`591` KB（≈ 0.6 MB，GitHub 计量，含资产）
- 最近 push：`2026-10-20` ；创建：`2026-02-20` ；语言：`Python`
- archived：`False`

## 2. 协议与架构
- 入口点：`skills/` 目录下的 skill 定义
- 关键 API：skill 触发描述 + 计算脚本
- 目录骨架（顶层，`gh api contents` 只读拉取，未 clone）：
```
  d .github
  f .gitignore
  f .pre-commit-config.yaml
  d .schema
  d .scripts
  f CONTRIBUTING.md
  f LICENSE
  f README.md
  d agent-workflow
  d analysis
```
- 顶层共 21 项（截断显示前 10）。

## 3. 本侧对照
- 对应 `skills/`（本仓已有 skill 体系）
- 判断依据：本项与上述模块解决的是同一层问题（计算化学 Agent Skills 集合（把计算化学流程写成 skill）），因此对照点落在接口形态与数据流，而不是功能罗列。

## 4. 授粉价值（3 条）
1. skill 描述与触发词的写法对照（提升 skill 命中率） → ``skills/``
2. 计算化学脚本的输入校验习惯 → ``skills/``
3. LGPL-3.0 边界下哪些可参考、哪些不能抄 → ``docs/pollination/``

## 5. 难度 × 收益
- **低 × 中**：结构同构（都是 skill 集合），可低成本对照写法

## 6. 接入模式
- **设计输入**：**许可**：`LGPL-3.0`（spdx 返回正常）。LGPL 对**库**有传染性，对**独立进程调用**较宽松；本仓只作写法参考，不复制其代码。
