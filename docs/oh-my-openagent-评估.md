# W67-07 · oh-my-openagent 编排对比（coding agent harness）

> 2026-09-02 · 第二十一期 GitHub 新扫货批 · 评估（不写实现）
> 上游：code-yeongyu/oh-my-openagent（**NOASSERTION 待核**，68595★，TypeScript，2026）

## 一、项目定位

coding agent harness（token 优化向）：`omo/lazycodex`——面向「tokenmaxxer」的编码 Agent 执行框架，强调 token 经济性（少 token 完成编码任务）。68595★（高热度）。

## 二、架构拆解

- harness：编码 Agent 的执行框架（工具循环、上下文管理、token 预算）。
- token 优化：精简上下文、token 复用、增量输入等机制（tokenmaxxer 定位）。
- 多 agent 编排：编码子任务编排/分工。

## 三、与本仓对照

| 维度 | 本仓 W64-01 orchestration + Trae 体系 | oh-my-openagent |
|------|--------------------------------------|----------------|
| 定位 | 通用 agent 编排 | coding agent harness（token 向） |
| 语言 | Python | TypeScript |
| token 优化 | 待核 | 强调（tokenmaxxer） |
| 许可 | 本仓 | NOASSERTION（待核） |

## 四、值得借鉴 vs 重平台跳过结论

**结论：值得借鉴「token 优化机制」，但作为平台整体跳过（重平台，与本仓 orchestration/Trae 重叠）。**

- 理由：它是完整 harness 平台（TypeScript），与本仓 Python orchestration + Trae 体系重平台；但其「token 经济性」的机制设计值得提取借鉴。

## 五、可落地借鉴点（≥3）

1. **token 预算与复用**：编码 Agent 的 token 经济机制（上下文精简、增量输入、复用），可借鉴到本仓 orchestration 的 token 优化。
2. **coding harness 工具循环**：编码任务专用的工具循环（读代码→改→测），可对照本仓 W64-01 的编排模块。
3. **多 agent 编码分工**：子任务编排/分工，对照 Trae 体系的多 agent 协作。

## 六、许可裁定

**NOASSERTION（GitHub API 无法自动识别许可）→ 标「待核」**：许可文件存在但未自动识别，接入前须人工读 LICENSE 确认。
