# agentacct 架构分析

> 来源：[mikehasa/agentacct](https://github.com/mikehasa/agentacct) | ⭐530+ | 2026-07-26 创建
> 状态：📋 待消化 — 多 Agent 成本可视化，对 Hermes+NagaAgent+陆墨 三实例场景有参考

---

## 一句话

**Local-first，从本地 session 文件直接读取 token 消耗 + 工作内容，按 agent→model→day 三级聚合。** 不只是计数——追踪"做了什么"。

## 核心能力

- 从 Claude Code / Codex / OpenCode 等 coding agent 的本地 session 文件读取
- Token/agent/model/day 级别追踪
- 区分工作阶段：planning → file reads → tool output → retries → response
- 成本标注为 `pricing-table estimates`（非账单），明确标注不确定性
- 本地运行，数据不出机器

## 适用场景

针对的是 **coding agent 多实例场景**——你同时跑着 Claude Code + Codex + OpenCode，想知道各自花了多少钱、效率如何。

## 对 Hermes 的参考价值

| 能力 | Hermes 现状 | 可复用性 |
|------|------------|---------|
| 多 agent token 聚合 | 完全黑盒，靠 provider dashboard | 🔴 刚需 |
| 工作阶段拆分 | 无 | 🟡 有意义但非紧迫 |
| 本地 session 解析 | Hermes 有 SQLite session DB | 🟢 数据源现成 |
| 成本估算 | 无 | 🔴 刚需——DeepSeek vs MiniMax 切换决策需要数据 |

## 可行方案

不直接拿 agentacct 代码（针对 Claude Code/Codex 格式），但架构思路可以复刻到 Hermes：

1. **数据源**：Hermes 已有 SQLite session DB，每轮 tool call 有 token 估算
2. **聚合层**：按 profile（default / lumo / naga）→ provider → day 三级聚合
3. **输出**：简单 CLI 或 cron 日报，而不是 agentacct 的 Web UI
4. **成本映射**：维护一个 provider pricing 配置（DeepSeek/ MiniMax / OpenRouter）

## 结论

不是直接拿来用的轮子，但是 **多 Agent 成本可见性** 这个需求是真实存在的。当你的 MiniMax 账单突然飙升时，你需要知道是陆墨在狂调 MCP 还是 Hermes 在 loop。优先级低于 OptMem，但在三实例稳定运行后应该补上。
