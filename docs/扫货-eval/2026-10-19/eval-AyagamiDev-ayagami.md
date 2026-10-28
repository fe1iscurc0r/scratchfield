# AyagamiDev/ayagami 评估

## 1. 项目
- 定位：Web 端 Live2D 渲染运行时（Cubism 的替代实现，面向浏览器）
- 星数：**367** ／ Fork：18 ／ Open issues：0
- 许可：spdx_id = `Apache-2.0`；顶层许可文件 `LICENSE-APACHE, LICENSE-MIT`
- 仓体大小：`1645` KB（≈ 1.6 MB，GitHub 计量，含资产）
- 最近 push：`2026-09-14` ；创建：`2026-07-11` ；语言：`Rust`
- archived：`False`

## 2. 协议与架构
- 入口点：`src/`（TS 运行时）+ 示例 `demo/`
- 关键 API：模型加载、参数驱动、物理/表情接口
- 目录骨架（顶层，`gh api contents` 只读拉取，未 clone）：
```
  d .github
  f .gitignore
  f .gitmodules
  f AGENTS.md
  f CONTRIBUTING.md
  f COPYRIGHT
  f Cargo.toml
  f FUNDING.yml
  f LICENSE-APACHE
  f LICENSE-MIT
```
- 顶层共 14 项（截断显示前 10）。

## 3. 本侧对照
- 对应 `neko-electron-shell/src/`（桌宠渲染）+ `frontend/src/components/`（Live2D 展示组件）
- 判断依据：本项与上述模块解决的是同一层问题（Web 端 Live2D 渲染运行时（Cubism 的替代实现，面向浏览器）），因此对照点落在接口形态与数据流，而不是功能罗列。

## 4. 授粉价值（3 条）
1. 渲染入口抽象成可切换后端（Cubism / Ayagami 双渲染并行） → ``docs/operate/cubism-deprecation-roadmap.md``
2. 参数/物理/表情/遮罩/口型五类能力对照表 → ``docs/operate/cubism-deprecation-roadmap.md` §差异矩阵`
3. 灰度期的可判定回退条件（表情参数偏差阈值） → ``docs/operate/cubism-deprecation-roadmap.md` §回退条件`

## 5. 难度 × 收益
- **高 × 高**：换渲染内核是全局影响，收益是摆脱 Cubism 授权与体积，但差异矩阵必须先做实

## 6. 接入模式
- **设计输入**：**双许可**：本仓有 `LICENSE-APACHE` 与 `LICENSE-MIT` 两个文件（**非标准命名**），故 `spdx_id` 只返回 `Apache-2.0`、**不能**据此判定为单许可；实读为 **Apache-2.0 OR MIT 双许可**，二者择一即可。
