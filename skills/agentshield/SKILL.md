---
name: agentshield
description: AI Agent 配置安全审计技能。用于扫描 Claude Code / 各类 AI Agent 配置目录，检测硬编码密钥、权限放行滥用、Hook 注入、MCP 服务器风险与提示词注入向量，输出 A-F 分级安全报告。当用户请求审计 agent 配置安全、检查 .claude 目录漏洞、或做 AI 配置安全扫描时使用。上游：ecc-agentshield (MIT)。
version: 1.0.0
author: Naga Team
tags:
  - security
  - audit
  - agent-config
  - mcp
enabled: true
---

# AgentShield 安全审计技能

本技能包装 `ecc-agentshield` CLI，对 AI Agent 配置目录（如 `.claude/`）做安全审计。
它是 CLI 扫描器（非 MCP 协议服务），因此作为 Skill 接入，而非外部 MCP 服务。

## 适用场景

- 审计 `.claude/` 或任意 agent 配置目录，发现**硬编码密钥 / 权限放行 / Hook 注入 / MCP 服务器风险 / 提示词注入**。
- CI 或人工评审前，对 agent 配置做一次自动化的安全体检。
- 生成 JSON / SARIF 报告供下游庭审。

## 运行方式

无需安装，直接通过 npx 调用（需 Node.js ≥ 18，本机已具备 npx 环境）：

```bash
# 扫描某个 agent 配置目录，输出 JSON（推荐，机器可读）
npx -y ecc-agentshield scan --path <配置目录> --format json

# 扫描当前项目里的 .claude / 配置
npx -y ecc-agentshield scan --format json

# 宽松版：只列出结果不因严重项失败
npx -y ecc-agentshield scan --path <配置目录> --format json --min-severity high
```

## 审计流程

1. **定位目标**：确认要扫描的配置目录（默认 `~/.claude` 或 `cwd`；通常传项目内 `.claude` 或 `~/` 全局配置）。
2. **扫描**：用 `--format json` 拿到结构化结果，避免终端样式干扰解析。
3. **解读**：按 `score.grade`（A-F）与 `findings[]` 分级，`severity` 取 `critical/high/medium/low/info`；`runtimeConfidence` 区分真实运行配置还是模板/文档示例（模板示例权重低，不必恐慌）。
4. **给出整改建议**：硬编码密钥 → 改为 `${ENV_VAR}` 引用；`Bash(*)` 通配权限 → 收窄到具体命令；高危 MCP / 未固定版本 `npx -y` → 固定版本并最小化暴露。

## 解读要点

- `findings[].file` 是问题文件；`findings[].runtimeConfidence` 为 `active-runtime` 说明是真实运行暴露，`template-example`/`docs-example` 多为仓库模板示例，按 0.25x 权重计分，不必过度解读。
- `score.numericScore` 0-100，`grade` A-F。
- 真正的密钥（如 `sk-ant-`、`sk-proj-`、`ghp_`）即便出现在示例/模板里也保持 critical，需优先处理。

## 输出规范

向用户汇报时，用简洁中文给出：
1. 总体等级（grade + 分数）与 5 类评分（secrets / permissions / hooks / mcp / agents）。
2. 命中条数与严重项分布（critical/high/...）。
3. 按严重度排序的 Top 问题：文件、标题、修复建议。
4. 明确区分"真实运行风险"与"模板/示例示例"。

## 使用示例

用户: "帮我审计一下我的 Claude 配置是否安全"
→ 运行 `npx -y ecc-agentshield scan --path ~/.claude --format json`，按上述规范输出分级报告与整改建议。