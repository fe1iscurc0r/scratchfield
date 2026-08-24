# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/) 格式，
版本号遵守 [语义化版本](https://semver.org/lang/zh-CN/)。

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
