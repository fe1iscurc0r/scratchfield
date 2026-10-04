# gemini-cli 终端 agent 行为可视化参考（W101-06）

> 2026-09-09 · 评估（不写实现）· 上游：google-gemini/gemini-cli（106,876★，Apache-2.0，TypeScript，2026-09-09 活跃）
> 许可：Apache-2.0（授粉报告已复核）
> 源码：shallow clone 到本机 D:/my git/haul-backfill/gemini-cli——以下引用为实读行号。

## 一、架构拆解（实读）

- 主循环：`GeminiClient`（packages/core/src/core/client.ts:93）——`startChat`（client.ts:380）→
  流式 `sendMessageStream`（client.ts:910）→ 逐回合产出。
- 会话恢复：`startChat(history, resumedSessionData)` 第三参恢复态（client.ts:343）。
- 工具体系：声明式工具基类（tools/shell.ts:1090 `ShellTool`）+ MCP 工具（tools/mcp-client.ts:1416
  `McpCallableTool`）；多 agent 调度 agents/agent-scheduler.ts。

## 二、授粉三大件①：源→目标映射

| 源组件（gemini-cli） | 目标模块 | 授粉方式 | 收益 |
|---------------------|---------|---------|------|
| agent 行为可视化/调试机制 | NEKO（lumo 前端可视化 agent 行为） | 前端呈现模式参考 | 行为透明可调试 |
| 工具调用可视化 | NEKO 交互层 | 模式吸收 | 工具链路可见 |
| 会话恢复 | lumo 会话管理 | 机制对照 | 断点续接 |

## 三、授粉三大件②：核心数据结构共鸣（2-3 处，实读引用）

1. **流式回合产出（sendMessageStream 生成器，client.ts:910-1026 内部自递归调用）**：事件流式输出模型
   ——与 petdex-cc 事件→动画映射（89号已授粉）同源，吸收点=把回合事件升级为结构化行为流。
2. **会话恢复参数（client.ts:343 startChat(history, resumedSessionData)）**：恢复态作为一等参数——
   lumo 会话断点续接的对照样本。
3. **声明式工具基类（ShellTool tools/shell.ts:1090 / McpCallableTool mcp-client.ts:1416）**：
   NEKO 行为面板「工具调用可视化」的事件字段来源参考。
3. **会话恢复**（中断后重建上下文）：lumo 会话管理的对照样本。
> 行号级引用待 github_haul/fusion/gemini-cli 快照回填。

## 四、与 NEKO/UI 对照 + 借鉴点（≥3）

借鉴点：① 行为流事件模型（步骤/工具/结果三段） ② 长任务进度呈现 ③ 会话恢复交互；
与 89号 petdex 事件动画联动组合成「agent 行为 → 桌宠反应 + 行为面板」双通道呈现。

## 五、许可裁定与结论

Apache-2.0 可借鉴；结论：**前端呈现模式参考（评估级）**，落点 NEKO 行为可视化工单。

---
*评估：fe1iscurc0r · 2026-09-09 · 行号引用基于 shallow clone 实读（D:/my git/haul-backfill）*
