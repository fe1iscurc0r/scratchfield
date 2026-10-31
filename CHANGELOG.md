# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/) 格式，
版本号遵守 [语义化版本](https://semver.org/lang/zh-CN/)。

## [5.2.10]

> 2026-10-31 · 自 5.2.9 起 11 个提交 / 20 个文件

这一版**只动 CI 与打包链路，不改运行时行为**。目的很具体：让「发版能产出安装包」
第一次真正成立 —— 5.2.9 只发了 tag 和 Release 正文，三个平台的打包全红，Release 里
一个产物都没有。

### Added
- **`typecheck` job**（`ci.yml`）：每次 push 跑 `vue-tsc -b`。此前类型检查只存在于
  `build-release.yml` 的 build job 里，而那只在**打 tag** 时触发 ⇒ 类型错误可以一直躺在
  main 上，直到发版当天才炸。变异验证过：把修复回退，`vue-tsc` 退出码 2，该 job 会红。

### Fixed
- **前端类型错误** `McpAddDialog.vue(275,5) TS2322`（`string | undefined` 不能赋给
  `string`）。根因不是笔误：`@vue/tsconfig@0.8.1` 默认开启 `noUncheckedIndexedAccess`
  （TS 5.9 推荐项）。这类错误 eslint 抓不到，只有 tsc 抓得到。
- **electron-builder 打包失败** `Cannot read properties of null (reading 'provider')`。
  `publish` 整段注释掉（= undefined）**不等于**「不发布」：只有显式 `publish: null` 才走
  `PublishManager.getPublishConfigs` 的短路分支 `if (publishers === null) return null`。
  打包本身是成功的（已产出 AppImage），死在生成更新元数据那一步。
- **CI 全量测试 38 failed → 0 failed**（1625 passed / 44 skipped）：
  - `tools/peak_switch.sh` 是 `#!/bin/sh` 却用了 bash 专有的 `$((10#$x))` ⇒ 改 POSIX（19 条）；
  - `mcpserver/breeze_tts` 有 manifest 却缺 `entryPoint` 与 `handle_handoff` ⇒ 照同构的
    `tts_api` 补齐（3 条）；
  - `code_exec` 的审计条目没记录被沙箱挡掉的环境变量数 ⇒ 补 `env_dropped_n`（只记数量）；
  - **`.gitattributes` 的 `* text=auto eol=crlf` 让所有检出都是 CRLF**，与「交付物必须 LF」的
    逐字节断言直接冲突 ⇒ 给相关路径钉 `eol=lf`。这是那批 CRLF 失败的**真根因**，
    不是文件被编辑器污染；
  - toolknit / acoustics 数据集等**环境缺件**改为精确 skip 并写明原因，不再假红。
- **`ci-nightly.yml` 从来没成功过**：`pytest` 不在 pyproject 的任何依赖组里（`build`=pyinstaller、
  `test`=google-genai），所以 `uv run pytest` 报 `Failed to spawn: pytest`。改用
  `uv run --with "pytest==9.1.1" python -m pytest`（不用 `uv pip install` 后再 `uv run`：
  uv run 会按 lockfile 精确同步，把手工装的包剪掉）。
- **`release` job 手动触发时的假失败**：不带 version 时 `Determine version` 会把
  `refs/heads/main` 当版本号 ⇒ release 收紧为「有 tag，或手动且给了 version」。

### Known limits
- 44 个 skip 是**环境缺件**（qpdf / PDF 引擎 / libreoffice / ToolKnit CLI / acoustics 数据集），
  不是「没做」；要真跑得在 runner 里装依赖。
- scratchfield 与 scratchpad 的镜像仍差约 9000 个路径，本版未处理。

## [5.2.9]

> 2026-10-30 · 自 5.2.8 起 51 个提交 / 300 个文件

pet 窗 `contextIsolation` 迁移收口（WO-278 P2 六域 + P3 写方向），
并把「迁移有没有把功能弄坏」固化成就地可跑的契约测试与活体验证脚本。

### Added
- **pet 窗活体验证脚本** `neko-electron-shell/scripts/pet-live-verify.mjs`：
  `list / probe / drag / verify / eval / chat`。`verify` 是断言式的（失败退出码 1），
  跑一次就知道迁移有没有把拖拽弄坏；`chat` 用来区分「窗口被 hide」「折叠成球」
  「真死状态」三种情形，排查“对话框不见了”不用再靠猜。
- **契约闸进 CI**：`preload-page-global.contract.test.js`（裸读棘轮 + 按成员双向断言）、
  `preload-pet-jukebox.runtime.test.js`（vm 双端联跑：真 preload + 真页面桥 + 假管理器）、
  `window-hardening` 增加「pet preload 直写页面全局」白名单。

### Changed
- **模型态 / 测量 / 渲染控制 / 视线 / 点歌台 / 穿透判定六个域**全部从
  「preload 直读页面全局」迁到页面注册面（`window.nekoPetHost`）。
  三个管理器的成员裸读 **97 → 5 处**，剩下的都是过不了桥的两类：
  非隔离回落取实例、以及 `mgr.onModelLoaded` 这类**写穿**补丁。
- **preload 往页面写**从 14 处收到 **2 个名字**（`window.WebSocket` 必须主世界替换、
  `__nekoPetInteracting__` 是逐帧读的活值），其余 11 个改走 `exposeToPage`
  （隔离时自动走 `contextBridge`，非隔离行为不变）。
- 前端 lint 清零（91 problems → 0），CI 补 `workflow_dispatch` 可手动触发。

### Fixed
- `pet-live-verify` **认错窗口**：`/character_card_manager`、`/model_manager` 等子窗口
  也挂 `live2dManager`，旧判据会把它们当成 pet 窗，报「模型未加载 + 没有
  nekoPetDiagnostics」的假故障。现在钉「根路径 `/` + 有模型全局」。
- `pet-live-verify verify` **不幂等**：每跑一次把模型净挪 (+120,+60) 且不还原，
  跑几次就飘出视口，后续验证在边缘态误判失败。现在验证完按原位置还原（`restored`）。
- `chat` 探针**误判**：折叠态下 `document.visibilityState` 仍是 `visible`，
  旧版报「窗口在场且可见」，把排查带偏。现在单列「折叠成球」一档，并区分
  「折叠了但球不可见」这种真正的死状态。

### Security
- dompurify 3.4.16 → 3.4.17、authlib >=1.6.9 → >=1.9.1、fastapi >=0.142.2 → >=0.143.0、
  scipy >=1.18.0 → >=1.18.1 等依赖升级（均为补丁/次要版本，无 major 跳跃）。

### Notes
- 5.2.6 / 5.2.7 / 5.2.8 三个 tag 未补 CHANGELOG 条目，本次一并说明，不回填。
- 本版本**不含** pet 窗 `contextIsolation` 的实际开启：实测仍有两条阻塞
  （`window.WebSocket` 替换需改 WS 适配层；鼠标合成事件在隔离态会污染横向拖拽位移），
  细节见 `docs/WO-278-pet-migration-plan-2026-10-27.md` §10。

## [5.2.5]

> 2026-10-05 · scratchfield（展示仓）首发 · 本条为补记（2026-10-09，原断档于 5.1.6）

首个三平台正式发布版本（Win / macOS arm64 / Linux AppImage），CI 全自动构建出包。

### Added
- **配置页 Tab 化**（卷181）：ConfigView 拆分 Tab 组件，新增 AudioTab（629 行）与 ModelTab（383 行），替换原单页配置
- **发布管线完善**：build-release.yml 三平台构建（PyInstaller 后端 + electron-builder 前端），release 自动落草稿、人工发布

### Fixed
- **CI 修复三连**：build 步对齐发布口径（--skip-openclaw）；package-lock 同步；AudioTab/ModelTab 拆分时未随工单提交导致构建失败，自悬空 commit 捞回完整版
- **发布修复**（首发验收发现）：安装包版本与 tag 断裂 → CI 新增版本一致性防线；产物名非 ASCII 前缀被 asset 上传剥掉 → artifactName ASCII 化（Lumo-*）
- package.json 补 repository 字段，修 electron-builder publish null.provider 崩溃

### Changed
- release 标题与 CI artifact 命名统一为「陆墨 Lumo」（Lumo-*）

> v5.2.0–v5.2.4 tag 存在但未形成正式发布（CI 红/草稿废弃），无独立条目；详见发布实录 skill 文档。

## [5.1.6]

总线能力体系收刀：分类 → 深检 → 装配策略 → 依赖预检 → 前端消费全链路。

### Added
- **能力分类体系**：53 个内置 agent manifest + 3 个 tool_registry yaml 全量携带
  `classification`（families/domains/tier/origin 四正交标签，9 族 / 4 tier）；
  静态校验脚本 `check_classification.py` 与 `check_agent_requirements.py`
  （规范层 / 能力层分立），词汇表单一真源在 `apiserver/mcp_assembly.py`
- **entrypoint 深检**：`verify_entrypoint`（零实例化：解析 → 白名单 → import →
  getattr → handle_handoff 契约），`GET /mcp/services` 的 available 与注册表
  运行时语义对齐并透出 `unavailable_reason`；修复 6 个 agent 缺
  `handle_handoff` 契约、`rf_brain` manifest 指向纯函数（该能力从未注册成功）
- **装配策略**：`GET/PUT /mcp/assembly`（按族白名单 / 按 tier 关闭 /
  agent 黑名单，缺省 = 全启用）；前端技能页新增可折叠「装配策略」面板；
  词汇表校验（非法族/tier 400 带提示）
- **requires 软依赖语义**：条目对象化 `{"name", "optional": true}`，缺依赖
  分「必须缺失（missing）」与「功能降级（optional_missing）」两路；预检
  verdict 三态 ready / missing / degraded；前端「缺 N 项」暖标与
  「降 N 项」灰标区分；查实 bofire / agent_animation 为软依赖
- **Facet 槽位设计稿**（`docs/Facet槽位-设计-2026-09-29.md`）：manifest 面板
  契约、前端组件注册表、offensive 双闸门在面板层的落法与分期

### Fixed
- **rotator_core 缺陷修复**（#121）：`mcpserver/ptz_service` 的 4 个模块寄生在
  `antenna_rotator` 上而其源码从未进仓——从历史提交收编被依赖闭包为
  `rotator_core` 子包，干净环境下机械核心能力恢复可用
- **pyproject 依赖审计**：补录 `dashscope`（qwen realtime 适配器模块级硬
  import，缺包整链崩）与 `starlette`（直接 import 显式化）；`scikit_fingerprints`
  manifest requires 补 skfp 本体
- 前端内置 agent 开关此前对 PUT `/mcp/services/{name}` 直接 404（开关失效）

### Changed
- 13 个桥接 agent 吸纳入仓（offense 等族，offensive 四个带 `*_ENABLE_INVOKE`
  入口闸门，默认关闭）
- ruff 批修 29 条；`uv.lock` 同步（dashscope / rdflib 校验基线）

## [5.1.5]

Windows 安装包构建 → GitHub Release 发布管线（首个走完整发布链路的版本）。

### Added
- `scripts/build-win.py`：版本号单一来源（annotated git tag），`--tag vX.Y.Z` 校验 tag 与
  `frontend/package.json` 一致后才构建，不一致即报错停下，绝不自动改写文件
- `scripts/build-win.py --verify-only`：不构建，只按产物清单校验既有构建（后端主程序 /
  Node 运行时 / npm / NSIS 安装包，含体积下限）
- `scripts/release-win.py`：一条命令完成 release 前置校验 + 生成 notes + 创建 draft Release
  + 上传安装包直链（draft 起步，发布动作永远留在本地）
- 发布隐私闸门 `scripts/release-notes-blocklist.txt`：发布前扫描真实人名 / 账号 / 内网地址 /
  内部路径等敏感词
- `.github/workflows/build-windows.yml`：Windows 后端构建验证骨架（push tag 触发，只验证不发布）
- `doctor_env.py` 环境自检接入构建前置流程

### Changed
- `README.md`：新增「两种安装方式」（普通用户下载安装包 / 开发者从源码构建），
  修正 Python 版本要求（`3.11+` → `3.12.x`，与 `pyproject.toml` 对齐）
- `build.md`：重写为构建与发布操作手册（版本号约定、产物清单、发布流程、隐私铁律）

### Fixed
- 修正构建脚本指向的产物名（`lumo-backend` → 实际产物 `naga-backend`），
  修复前该脚本因 spec 文件不存在而无法运行
- 修正构建脚本编译 OpenClaw 时引用的 tsconfig 名（`tsconfig.lumo.json` 不存在 → `tsconfig.naga.json`）
- 停用失效的前端签名钩子：`cscLink` 证书已移除但 `signtoolOptions.sign` 仍启用，
  导致 `doSign(null)` 崩溃、NSIS 打包必失败

### Removed
- **打包范围按架构边界收刀**：`NEKO` 与 `neko-electron-shell`（上游独立项目，本仓仅含
  桥接改动）、`HamLog`（第三方 GPL-3.0 项目）、`coupled/*`（standalone 插件 + 商业许可）
  不再进发布包，改由用户按需自行获取（`local_apps.py` 已有「未找到则提示 clone」降级）；
  同时排除 `mod/sources`（工具源码缓存，其 jadx 产物路径超长会撞 Windows MAX_PATH）、
  `tmp`、`github_haul`、`carpet`（`core_config.json` 含真实 API key，防泄漏）
  与 `sitaware-ui/node_modules`（构建依赖，后端不引用）。
  spec `datas` 实测体积 **4.37 GiB → 117 MiB**（-97.4%）

## [Unreleased]

### Added
- NEKO × 陆墨融合架构：双向事件通道、Live2D 桌宠、MCP 注册链路
- 14 个安全/逆向/渗透 MCP Agent（VulnClaw、Agent-Reach 等）
- 161 个科学 Agent Skills（学术研究、实验设计等）
- 5 个 Top5 Vendor 项目集成（headroom、scientific-agent-skills、VulnClaw、caura-memclaw、Agent-Reach）
- GitHub 扫货自动化：每日 09:00 自动扫描 + 授粉三原则分类
- 社区规范：CODE_OF_CONDUCT、CONTRIBUTING、SECURITY、CODEOWNERS、ISSUE/PR 模板
- NOTICE 第三方许可声明（13 个组件）
- Lumo Bus 集成总线规范 v1：A2A/AgentBus/三层总线架构
- 融合拓扑审计 v1：进程/数据/许可证三层拓扑 + 13 处 AGPL 溯源
- CI/CD：GitHub Actions Build & Release（Win/Mac/Linux 三平台）
- Qwen ASR 接入 + 7 模型 fallback 机制
- 前端：vite-plugin-electron 完整模式、Electron 桌宠窗口、系统托盘菜单
- Proactive Vision 配置
- 108 项目授粉清单（docs/GitHub-Haul-Merged-Final）
- WorkBuddy AI 编程助手行为规则

### Changed
- 项目目标从独立 NagaAgent 变更为 NEKO × 陆墨融合系统
- README 重写为融合架构说明
- 铁律 8 overlay 约束

### Fixed
- 多智能体联合审查：2 CRITICAL + 14 HIGH + 14 MEDIUM 修复
- 路径逃逸防御 + 跨源测试
- MCP 注册表幂等隔离
- 铁锚审查：5 个 HIGH 工具路径错位
- SSL 未验证 + fetch 无 ok 检查
- emotion 断裂 + respawn race + debug 鉴权
- M4 speak 不透传前端双消息冲突
- PowerShell 控制台窗口隐藏
- VulnClaw 测试代码 AV 误报处理

### Security
- VulnClaw PoC/exploit 测试代码打包归档（tar.gz），AV 不扫描
- SSH 暴力破解处置：fail2ban maxretry 5→3，bantime 1h→24h
- 公网端口清理：关闭 18181 裸奔文件服务器
- 敏感凭证跟踪清理 + .gitignore 增强
