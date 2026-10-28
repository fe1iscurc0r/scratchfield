# jamro/tiny-engineer 评估

## 1. 项目
- 定位：实体桌宠（软件 + 3D 打印硬件设计），带语音与动作
- 星数：**728** ／ Fork：94 ／ Open issues：10
- 许可：spdx_id = `NOASSERTION`；顶层许可文件 `LICENSE, LICENSING.md`
- 仓体大小：`384937` KB（≈ 375.9 MB，GitHub 计量，含资产）
- 最近 push：`2026-10-19` ；创建：`2026-08-21` ；语言：`C++`
- archived：`False`

## 2. 协议与架构
- 入口点：固件/上位机（软件段 MIT）
- 关键 API：动作控制、传感器输入
- 目录骨架（顶层，`gh api contents` 只读拉取，未 clone）：
```
  d .agents
  d .claude
  d .cursor
  d .github
  f .gitignore
  d 3d_models
  f AGENTS.md
  f CLAUDE.md
  f CODE_OF_CONDUCT.md
  f CONTRIBUTING.md
```
- 顶层共 36 项（截断显示前 10）。

## 3. 本侧对照
- 对应 `neko-electron-shell/`（虚拟桌宠对照）+ 未来实体化路线
- 判断依据：本项与上述模块解决的是同一层问题（实体桌宠（软件 + 3D 打印硬件设计），带语音与动作），因此对照点落在接口形态与数据流，而不是功能罗列。

## 4. 授粉价值（3 条）
1. 实体桌宠的动作-语音联动时序，可反推虚拟端的行为节奏 → ``neko-electron-shell/src/``
2. 硬件设计文件的组织方式（但硬件段 CERN-OHL-S-2.0 不引入） → ``docs/pollination/``
3. 低成本舵机/灯效方案作为实体化参考（不做代码引入） → ``docs/pollination/``

## 5. 难度 × 收益
- **高 × 低**：实体化不在近期路线内；仓体 376 MB 主要是 3D 资产，只读码不拉资产也不划算

## 6. 接入模式
- **设计输入**：**双许可（分段）**：`spdx_id = NOASSERTION`；`LICENSE`（1.2 KB）声明 **软件段 MIT**，`3d_models/cad/`、`3d_models/parts/` 为 **CERN-OHL-S-2.0**（见 `LICENSING.md`）。**资产体积**：仓体 384,937 KB ≈ 376 MB，`3d_models/` 是主因 ⇒ 只读码不拉资产。
