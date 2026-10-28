# deeplethe/solid-glass 评估

## 1. 项目
- 定位：Web 玻璃拟态（glassmorphism）组件/样式库
- 星数：**2375** ／ Fork：29 ／ Open issues：3
- 许可：spdx_id = `MIT`；顶层许可文件 `LICENSE`
- 仓体大小：`17546` KB（≈ 17.1 MB，GitHub 计量，含资产）
- 最近 push：`2026-10-18` ；创建：`2026-10-12` ；语言：`TypeScript`
- archived：`False`

## 2. 协议与架构
- 入口点：组件与 CSS token
- 关键 API：玻璃效果组件、design token
- 目录骨架（顶层，`gh api contents` 只读拉取，未 clone）：
```
  d .github
  f .gitignore
  f CODE_OF_CONDUCT.md
  f CODE_OF_CONDUCT.zh-CN.md
  f CONTRIBUTING.md
  f CONTRIBUTING.zh-CN.md
  f LICENSE
  f NOTICE.md
  f README.md
  f SECURITY.md
```
- 顶层共 25 项（截断显示前 10）。

## 3. 本侧对照
- 对应 `frontend/src/components/`（Lumo 前端换皮候选）
- 判断依据：本项与上述模块解决的是同一层问题（Web 玻璃拟态（glassmorphism）组件/样式库），因此对照点落在接口形态与数据流，而不是功能罗列。

## 4. 授粉价值（3 条）
1. 玻璃拟态的 blur/透明度组合参数 → ``frontend/src/components/``
2. design token 的组织方式（主题化） → ``frontend/src/styles/``
3. 与 PrimeVue 主题的叠加方式（避免样式打架） → ``frontend/src/``

## 5. 难度 × 收益
- **中 × 中**：视觉收益明确，但当前前端刚锁 PrimeVue 4.5.5，换皮要等主题层稳定

## 6. 接入模式
- **融合参考**：**次级候选 · 6 个月复核触发条件（任务 F，四条全满足才进换皮候选）**

| # | 条件 | 判定方式 |
|---|---|---|
| 1 | 发版节奏 ≥ 1 release/月，连续 3 个月 | releases API 按月计数 |
| 2 | design token 数量 ≥ 50 且文档完整 | 读 token 文件计数 + README 覆盖 |
| 3 | 近 90 天 breaking change ≤ 1 次 | CHANGELOG/compare 里标 breaking 的条目数 |
| 4 | 有 ≥ 3 个非作者的公开使用案例 | 依赖方/示例仓检索，排除作者自用 |

四条全满足才进 Lumo 换皮候选；任一不满足则**继续观察**，不进入排期。
