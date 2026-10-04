# VoltAgent JavaScript Agent 栈勘察（Lumo TS / N.E.K.O. 前端层）

> 2026-09-04 · 94号 T1 · 勘察（不写实现、不整仓搬运）
> 上游：VoltAgent/voltagent（GitHub，MIT，★10545，TypeScript AI Agent 工程平台；npm `@voltagent/core`）
> 纪律：MIT 可直接参考（含源码思路）；探针以 npm 包类型定义/README 接口面为主。

## 一、能力矩阵

| 维度 | 内容 |
|------|------|
| Agent 抽象 | Agent 生命周期/编排抽象 |
| 工具注册 | MCP 工具集成 / 工具注册面 |
| 记忆 | 记忆面（上下文/持久化） |
| 推理 | 多模型推理接入 |
| 许可 | MIT（干净，可直接接入或对照） |

## 二、映射到 Lumo / N.E.K.O. TS 层（源→目标→方式→收益）

| 源组件 | 目标模块 | 接入方式 | 收益 |
|--------|---------|---------|------|
| VoltAgent TS agent 平台 | TS 前端 agent 扩展 | npm 包接入 / 参考架构 | TS 层原生 agent 能力 |
| MCP 工具集成 | Lumo 工具层 | MCP 生态对接 | 与 CAAL 动态发现互补 |

## 三、与 CAAL（AGENT_87，MCP 动态发现）分工

CAAL 解决「工作流自动发现 → MCP 工具注册」；VoltAgent 解决「TS 层 agent 工程平台」——CAAL 工作流注册出的工具，由 VoltAgent 框架消费执行，形成完整链路。

## 四、npm `@voltagent/core` 安装可行性

npm 环境可用则 `npm install @voltagent/core --no-save` 读取类型定义；不可用则读 GitHub README + 源码接口面（诚实降级）。

## 五、接入建议（≥3）

1. **npm 包接入**：Lumo TS 前端扩展直接依赖 `@voltagent/core`，做 agent 编排。
2. **参考架构**：参考其 Agent/Tool/Memory 抽象设计，对齐 N.E.K.O. 前端层。
3. **与 CAAL 链路组合**：CAAL 动态发现的 MCP 工具 → VoltAgent 框架执行。

## 六、结论

**接入（有保留）**：作为 Lumo TS 层 agent 框架候选；MIT 干净，npm 包可用则直接接入，不可用则参考架构。

---
*勘察：fe1iscurc0r · 2026-09-04 · 基于上游公开文档与扫货报告，未 clone 源码*
