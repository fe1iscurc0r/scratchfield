# Glass-HQ/liquid-glass 评估

## 1. 项目
- 定位：液态玻璃（liquid glass）效果实现
- 星数：**447** ／ Fork：20 ／ Open issues：0
- 许可：spdx_id = `MIT`；顶层许可文件 `LICENSE`
- 仓体大小：`23743` KB（≈ 23.2 MB，GitHub 计量，含资产）
- 最近 push：`2026-10-10` ；创建：`2026-10-06` ；语言：`TypeScript`
- archived：`False`

## 2. 协议与架构
- 入口点：组件 + 样式
- 关键 API：液态玻璃视觉组件
- 目录骨架（顶层，`gh api contents` 只读拉取，未 clone）：
```
  d .github
  f .gitignore
  f .oxlintrc.json
  f .vercelignore
  f AGENTS.md
  f CONTRIBUTING.md
  f LICENSE
  f README.md
  d apps
  f bun.lock
```
- 顶层共 14 项（截断显示前 10）。

## 3. 本侧对照
- 对应 `frontend/src/components/`（与 solid-glass 同类，作对照）
- 判断依据：本项与上述模块解决的是同一层问题（液态玻璃（liquid glass）效果实现），因此对照点落在接口形态与数据流，而不是功能罗列。

## 4. 授粉价值（3 条）
1. 液态玻璃的形变/高光参数（与 solid-glass 的差异） → ``frontend/src/components/``
2. 性能取舍（blur 层数与帧率） → ``frontend/src/``
3. 同一效果的两种实现对照，便于选型 → ``docs/``

## 5. 难度 × 收益
- **中 × 低**：与 solid-glass 功能重叠，二者只需留一个候选

## 6. 接入模式
- **不引入**：与 `deeplethe/solid-glass` **同层重叠**：若 solid-glass 通过 6 个月复核，本项不再单独评估。
