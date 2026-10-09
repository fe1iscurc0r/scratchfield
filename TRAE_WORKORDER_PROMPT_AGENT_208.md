# 工单 208 · 扫货模式升级——GitHub 扫货日报接入「AI 编码计划筛选」

> 委托方：用户 · 执行：Trae（GitHub 线，仓库 fe1iscurc0r/scratchpad）· 出单：沈遥 · 日期：2026-10-08
> 背景：用户现有 zhipu GLM coding 订阅**仅剩两天有效期**（约 2026-10-10 到期）。当前「GitHub 扫货日报」cron（每天 09:00）没有利用"哪些仓库的最近提交出自 AI 编码计划"这一强信号。趁订阅窗口，给扫货管线加上 AI 编码计划筛选维度，到期后脱敏降级也能跑。**只做筛选器与报告改造，不动 cron 调度本体。**

## 任务一（P0）：AI 编码计划提交探测器

1. 新建 `tools/ai_commit_detector.py`：
   - 输入：仓库 owner/name（或 gh repo list 输出）
   - 检测规则（全部走 `gh api` / GitHub REST，零额外依赖）：
     a. 最近 N（默认 30）条 commit message 匹配 AI 编码计划特征串：`Co-Authored-By: Claude` / `Generated with [Claude Code]` / `🤖 Generated with` / `noreply@anthropic.com` 等（规则表放脚本顶部常量，可增删）
     b. commit author/committer email 域名匹配（claude.ai / anthropic.com / openai.com 等）
   - 输出：JSON——每仓 `{repo, ai_commit_count, ai_ratio, matched_rules}`，支持批量仓列表文件输入
2. 用本仓 fe1iscurc0r/scratchpad 自测：跑一遍输出真实结果（本仓 Trae 提交应被检出），附输出到 PR 描述

## 任务二（P0）：扫货日报接入 AI 信号维度

1. 修改 GitHub 扫货日报的产出逻辑（github-sweep-and-classify 流程的报告生成部分）：
   - 对候选仓库在常规打分（角度相关性×价值密度×落点明确）之外增加 `ai_velocity` 维度：最近 30 天 commit 中 AI 编码计划占比
   - 报告表格新增一列「AI 活跃度」（高/中/低/无），高 = ai_ratio > 30% 且 ai_commit_count ≥ 5
   - 只改报告生成器与打分逻辑，cron 调度（时间/交付渠道）不动
2. 规则表内注明数据来源仅为公开 commit 元数据（message trailer / committer email），不做任何账号关联推断——这是筛选不是侦查

## 任务三（P1）：订阅到期降级预案

GLM coding 端点 2026-10-10 前后失效属预期事件：
1. 在扫货日报的报告模板头部加一行状态注记机制：若当日 LLM 摘要步骤失败（API 4xx/超时），报告降级为"纯列表模式"（表格数据照常，仅无文字点评），并注明「摘要降级：LLM 端点不可用」
2. 降级路径写进 `docs/sweep-pipeline-degrade.md` 一页备忘：哪些步骤依赖 LLM、哪些纯 API 可跑、降级触发条件、恢复条件（换 key/换 provider 后自动回全量模式）

## 验收
- [ ] 任务一：ai_commit_detector.py 落盘且本仓自测输出贴 PR；规则表常量可维护
- [ ] 任务二：日报报告模板含 AI 活跃度列；打分函数含 ai_velocity；cron 调度零改动
- [ ] 任务三：纯列表降级模式可手动触发验证（临时断端点或 mock）；docs/sweep-pipeline-degrade.md 一页落盘
- [ ] 全程 CI 绿（lint/smoke 若闸门未开则本地等价复现，参照 ci.yml 注释的两步法）
