# 工单 211 · Dependabot 安全债大清盘

> 委托方：用户 · 执行：Trae（GitHub 线，仓库 fe1iscurc0r/scratchpad）· 出单：沈遥 · 日期：2026-10-08
> 背景：GitHub 推送时持续报警：**125 个 dependabot 漏洞待处理（9 critical / 63 high / 43 moderate / 10 low）**，远超上次清账时的警戒线。按 github-security-debt-clearing skill 流程走。

## 任务一（P0）：Critical × High 全量 triage

1. 用 `gh api repos/fe1iscurc0r/scratchpad/dependabot/alerts` 拉全量 dependabot alerts（含 severity/state/dependency/package_ecosystem）
2. 按 severity 分三档处理策略：
   - **Critical**：全部处理（升级到 patched version 或 pin 已知安全版本）
   - **High**：按利用复杂度分（CVSS ≥ 8.0 直接修；7.0-7.9 评估实际暴露面再决定修/接受）
   - Moderate/Low：建忽略理由（documented reason），不做实际改动
3. 对每个 Critical/High 出 patch commit：单独 commit message 格式 `fix(security): bump <package> to <safe_version> (GHSA-xxxx)`，不与其他改动混

## 任务二（P1）：忽略理由规范化

1. Moderate/Low 的 53 个告警逐条补 documented reason（不在 PR 里暴露漏洞细节，只写"低利用率/内网/测试依赖"等笼统理由）
2. 用 `gh dependabot alert update` 逐条加 dismiss_reason，避免每次 push 都推送通知

## 验收
- [ ] 任务一：Critical 全修；High 分两批（修 CVSS≥8.0 + 评估 7.0-7.9），patch commit 格式合规
- [ ] 任务二：53 个 Moderate/Low 全部加 dismiss_reason，gh api 验证
- [ ] 清完后 gh api dependabot/alerts 返回空（只剩 0 个 open）
