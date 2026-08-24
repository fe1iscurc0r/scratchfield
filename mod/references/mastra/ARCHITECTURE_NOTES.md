# Mastra 架构笔记

## 概述

Mastra 是一个 TypeScript 优先的 AI Agent 框架，专为 TypeScript/JavaScript 生态设计，提供类型安全的 Agent 定义、工作流组合和工具注册。

## 工具注册模式

### 声明式工具定义

Mastra 通过 `createTool` 定义工具，利用 Zod schema 实现类型安全：

```typescript
import { createTool } from "@mastra/core/tools";
import { z } from "zod";

export const weatherTool = createTool({
  id: "get-weather",
  description: "获取指定城市的天气信息",

  // Zod schema 自动生成类型约束和参数校验
  inputSchema: z.object({
    city: z.string().describe("城市名称"),
    unit: z.enum(["celsius", "fahrenheit"]).default("celsius"),
  }),

  // 执行函数获得完整类型推断
  execute: async ({ context }) => {
    const { city, unit } = context;
    // context 自动携带 Agent 上下文（记忆、会话ID等）
    return { temperature: 22, condition: "晴" };
  },
});
```

### 类型安全的数据流

Mastra 的核心优势是利用 TypeScript 类型系统保证端到端类型安全：

```
Tool Input Schema (Zod)
    → TypeScript 类型推断
        → LLM Function Calling (自动生成 JSON Schema)
            → Tool 执行 (类型推断的 context)
                → 返回值类型 (自动推断)
```

## 工作流组合

### Workflow 定义

```typescript
const workflow = new Workflow({
  name: "research-and-report",

  // 步骤式定义，每个步骤都有类型安全的输入输出
  triggerSchema: z.object({
    topic: z.string(),
  }),

  // Step 按序执行，支持条件分支和循环
  steps: {
    research: {
      agent: researcherAgent,   // 绑定 Agent
      input: (trigger) => ({ topic: trigger.topic }),
    },
    analyze: {
      agent: analystAgent,
      input: (prev) => ({ findings: prev.research }),
    },
    report: {
      agent: writerAgent,
      input: (prev) => ({
        topic: prev.analyze.topic,
        analysis: prev.analyze.summary,
      }),
    },
  },
});
```

### 步骤间数据流

- **前向传递**：每个 step 的 `input` 函数接收上一步的输出，映射为本步骤的输入
- **触发数据**：第一步可从外部触发器（HTTP、cron 等）接收初始数据
- **全局上下文**：Workflow 级别的 context 在所有步骤间共享

## TypeScript 特有模式

### 1. 泛型 Agent 定义
```typescript
// Agent 带类型参数的泛型定义
const agent = new Agent<typeof myTools>({...})
// tools 的类型自动推断到 execution context
```

### 2. 装饰器式记忆
```typescript
// 通过 Memory 类实现 Agent 记忆
const memory = new Memory({
  storage: new LibSQLStore({ url: ":memory:" }),
  options: { lastMessages: 10 },
});
```

### 3. 流式原生支持
```typescript
// AsyncGenerator 模式处理流式输出
const stream = await agent.stream("你的问题");
for await (const chunk of stream) {
  console.log(chunk);
}
```

## 与 scratchpad 的对比

| 维度 | Mastra | scratchpad |
|------|--------|------------|
| 语言 | TypeScript | 语言无关（运行时层） |
| 类型安全 | Zod schema 端到端 | 无静态类型约束 |
| 工具定义 | createTool + Zod | SKILL.md 声明 |
| 工作流 | Workflow class | subagent 链式调用 |
| 流式 | AsyncGenerator 原生 | Agent 运行时层 |
| 记忆 | Memory class 插件化 | summer_memory |
| 生态 | TypeScript/Node.js | 跨语言 |
