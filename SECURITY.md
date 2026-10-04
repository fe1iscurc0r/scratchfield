# 安全策略

## 报告漏洞

如果你发现安全漏洞，请**不要**提交公开 Issue。

请发送邮件至：fe1iscurc0r@users.noreply.github.com

请包含以下信息：
- 漏洞描述
- 复现步骤
- 影响范围
- 建议修复方案（如有）

我们会在 48 小时内确认收到报告，并在 7 天内给出初步评估。

## 支持版本

| 版本 | 支持状态 |
|------|---------|
| master（开发分支） | ✅ 安全更新 |

## 安全实践

- API Key 和 Token 使用环境变量，不落盘
- 敏感配置文件（.env.local）已在 .gitignore 中排除
- 蜜罐凭证通过自动化 cron 定期轮换
- 外部依赖在上游发布 CVE 修复后 7 天内更新

## 已知限制

- 本仓库包含渗透测试工具（VulnClaw）的适配器。测试代码和 PoC 已打包归档（tar.gz），不直接出现在源码树中。
- 安全工具的 MCP Agent 适配器是只读接口包装，不直接执行底层工具。

## 依赖审计

定期运行：
```bash
npm audit --audit-level=high
python -m pip audit
```
