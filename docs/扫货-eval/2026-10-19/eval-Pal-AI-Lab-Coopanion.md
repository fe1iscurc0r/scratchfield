# Pal-AI-Lab/Coopanion 评估

## 1. 项目
- 定位：桌面 AI 伴侣（桌宠 + 对话 + 行为编排）
- 星数：**429** ／ Fork：44 ／ Open issues：10
- 许可：spdx_id = `NOASSERTION`；顶层许可文件 `LICENSE`
- 仓体大小：`35311` KB（≈ 34.5 MB，GitHub 计量，含资产）
- 最近 push：`2026-10-19` ；创建：`2026-09-23` ；语言：`TypeScript`
- archived：`False`

## 2. 协议与架构
- 入口点：应用主入口（Electron/Tauri 待定，见顶层树）
- 关键 API：对话状态机、行为触发、桌宠交互
- 目录骨架（顶层，`gh api contents` 只读拉取，未 clone）：
```
  f .gitattributes
  d .github
  f .gitignore
  f .gitmodules
  f AGENTS.md
  f CLA.md
  f CLAUDE.md
  f CONTRIBUTING.md
  f LICENSE
  f README.md
```
- 顶层共 34 项（截断显示前 10）。

## 3. 本侧对照
- 对应 `neko-electron-shell/`（桌宠窗口与行为）+ `src/`（会话/记忆）
- 判断依据：本项与上述模块解决的是同一层问题（桌面 AI 伴侣（桌宠 + 对话 + 行为编排）），因此对照点落在接口形态与数据流，而不是功能罗列。

## 4. 授粉价值（3 条）
1. 行为编排的状态机抽象（当前 NEKO 的行为触发散在窗口管理器里） → ``neko-electron-shell/src/``
2. 桌面伴侣的交互范式参考（不做代码引入） → ``docs/pollination/``
3. 多角色切换与场景隔离的组织方式 → ``frontend/src/views/``

## 5. 难度 × 收益
- **中 × 低**：产品形态接近，但 AGPL-3.0 决定了只能作设计输入，且我们已有桌宠实现

## 6. 接入模式
- **设计输入**：**许可**：`spdx_id = NOASSERTION`，实读 `LICENSE`（35 KB）为 **AGPL-3.0-or-later + §7 附加许可**；AGPL 对网络分发有传染性，**任何代码引入都会波及主仓**，故只作设计输入。
