# tsunehimatoi/psd2live 评估

## 1. 项目
- 定位：PSD → Live2D 自动化绑定管线（解析 PSD 图层 → 中立 IR → 编译成可动模型）
- 星数：**694** ／ Fork：60 ／ Open issues：0
- 许可：spdx_id = `GPL-3.0`；顶层许可文件 `LICENSE`
- 仓体大小：`171148` KB（≈ 167.1 MB，GitHub 计量，含资产）
- 最近 push：`2026-10-19` ；创建：`2026-09-03` ；语言：`Kotlin`
- archived：`False`

## 2. 协议与架构
- 入口点：`crates/`（Rust 工作区）+ `python/` 绑定层
- 关键 API：IR 解析/导出命令；层分离与网格生成
- 目录骨架（顶层，`gh api contents` 只读拉取，未 clone）：
```
  d .claude
  f .editorconfig
  f .gitattributes
  d .github
  f .gitignore
  f LICENSE
  f README.md
  f THIRD_PARTY_NOTICES.md
  f build.gradle.kts
  d docs
```
- 顶层共 29 项（截断显示前 10）。

## 3. 本侧对照
- 对应 `neko-electron-shell/src/`（Live2D 资源装载）与 `carpet/N.E.K.O/character_cards/`（角色卡资产）
- 判断依据：本项与上述模块解决的是同一层问题（PSD → Live2D 自动化绑定管线（解析 PSD 图层 → 中立 IR → 编译成可动模型）），因此对照点落在接口形态与数据流，而不是功能罗列。

## 4. 授粉价值（3 条）
1. 把 PSD 分层命名约定固化成资产管线的输入规范 → ``docs/SPEC-neko-asset-pipeline-2026-10.md``
2. 导出目标（model3.json / moc3 之外的中间格式）作为桥接 CLI 的输出约定 → ``tools/psd2live-bridge/cli.sh``
3. 失败回退到手工绑骨的判据（层结构不满足约定时直接拒单） → ``tools/psd2live-bridge/README.md``

## 5. 难度 × 收益
- **高 × 高**：Rust 工具链 + 绑定质量评估都不轻松，但能替掉当前手工绑骨这条最贵的工序

## 6. 接入模式
- **融合参考**：**许可分段（红线）**：引擎 `umamo` = GPL-3.0，一颗字节不进仓；中立绑定 IR / 导出框架 / Rust 运行时 = MIT 段可取。本仓只引用 MIT 段，NOTICE 里明确声明不引入、不链接、不随包分发 GPL 部分。
