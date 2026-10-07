# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/) 格式，
版本号遵守 [语义化版本](https://semver.org/lang/zh-CN/)。

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
