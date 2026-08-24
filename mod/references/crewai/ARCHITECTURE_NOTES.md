# crewAI 架构笔记

## 概述

crewAI 是一个基于角色的 AI Agent 编排框架，核心理念是将多个 AI Agent 组织成"团队（Crew）"协同完成复杂任务。

## 核心概念

### Agent（智能体）
每个 Agent 通过角色定义（role-based）来限定其行为边界和能力范围：

```python
agent = Agent(
    role="高级研究员",          # 角色名，定义职责边界
    goal="发现前沿技术趋势",     # 目标，驱动行为
    backstory="拥有十年研究经验", # 背景故事，影响决策风格
    tools=[search_tool, ...],       # 工具集
    verbose=True
)
```

**角色驱动设计**：Agent 的行为由 role/goal/backstory 三元组决定，而非硬编码的提示词。系统自动将角色定义转化为 system prompt。

### Task（任务）
任务是 Agent 的最小工作单元：

- `description`：任务描述（支持 {variable} 模板变量）
- `expected_output`：期望输出格式
- `agent`：指派执行者（可为 None，由 Crew 自动分配）
- `context`：依赖的前置任务输出（实现任务链）
- `async_execution`：是否异步执行

### Crew（团队）
Crew 是多 Agent 协作的顶层容器：

- `agents`：团队成员列表
- `tasks`：任务列表
- `process`：执行流程类型

## 执行流程类型

### Sequential（顺序执行）— 默认模式
按 tasks 列表顺序逐任务执行，前一任务输出作为下一任务的 context：

```
Task 1 → Task 2 → Task 3 → ... → Task N
```

适用场景：线性工作流（如 调研→写作→审校）

### Hierarchical（层级执行）
指定一个 Manager Agent，由它根据任务描述动态分配给团队成员：

```
        Manager Agent
       /      |      \
  Agent A  Agent B  Agent C
```

Manager 负责：任务分解、分配、结果验证、汇总。适用于复杂、非线性的协作场景。

## 任务委托模式

- **显式指派**：task.agent 指定执行者
- **Manager 分配**：Hierarchical 模式下的动态分配
- **上下文传递**：通过 task.context 引用前置任务，实现数据流
- **异步任务**：async_execution=True 允许并行执行无依赖任务

## 与 scratchpad 的对比

| 维度 | crewAI | scratchpad |
|------|--------|------------|
| Agent 定义 | role/goal/backstory | skill 文件 |
| 编排方式 | Sequential/Hierarchical | 手动 subagent 调用 |
| 工具集成 | tools 列表注册 | skill tool 声明 |
| 数据流 | context 链式传递 | 显式消息传递 |
| 适用规模 | 3-10 Agent 协作 | 1-3 Agent 轻量协作 |
