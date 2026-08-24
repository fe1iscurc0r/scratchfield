# Dify 架构笔记

## 概述

Dify 是一个可视化 AI 应用开发平台，核心是通过 DSL 定义工作流（Workflow），以节点拼接的方式构建 LLM 应用，降低 AI 开发的门槛。

## DSL 驱动的工作流设计

### 工作流 DSL 结构

Dify 使用声明式 DSL 描述工作流，每个工作流由一组节点和有向边组成：

```yaml
app:
  mode: workflow          # 应用模式: workflow / chat / agent
  description: "..."

workflow:
  graph:
    nodes:
      - id: "start"
        type: "start"
        data:
          variables: [...]
      - id: "llm-1"
        type: "llm"
        data:
          model: "gpt-4"
          prompt_template: "..."
      - id: "code-1"
        type: "code"
        data:
          code: "def main(arg): ..."
          language: "python3"
      - id: "end"
        type: "end"
        data:
          outputs: [...]
    edges:
      - source: "start"
        target: "llm-1"
      - source: "llm-1"
        target: "code-1"
      - source: "code-1"
        target: "end"
```

### 核心节点类型

| 节点类型 | 功能 | 关键配置 |
|---------|------|---------|
| **LLM** | 大模型调用 | 模型选择、提示词模板、上下文窗口 |
| **Knowledge Retrieval** | 知识库检索 | 知识库ID、召回策略、TopK |
| **Code** | 代码执行 | Python/JS 沙箱、输入输出变量 |
| **HTTP Request** | 外部API调用 | URL、Method、Headers、Body |
| **IF/ELSE** | 条件分支 | 条件表达式、分支路由 |
| **Template** | 文本模板 | Jinja2 模板、变量替换 |
| **Variable Aggregator** | 变量聚合 | 多源变量合并 |
| **Iteration** | 循环处理 | 数组遍历、并行度 |
| **Tool** | 内置工具调用 | 搜索、图片生成等 |

### Agent 节点模式

Dify 的 Agent 节点不同于普通 LLM 节点，支持：

- **Function Calling 循环**：自动选择工具 → 执行 → 分析结果 → 决定下一步
- **ReAct 策略**：Reasoning + Acting 循环
- **工具集绑定**：为 Agent 绑定一组可用工具
- **迭代上限**：防止无限循环

## 可视化编程范式

### 设计理念

1. **所见即所得**：画布拖拽节点，连线即数据流
2. **声明式 > 命令式**：描述"要什么"而非"怎么做"
3. **低代码**：无需编码即可构建复杂 LLM 管线
4. **可调试**：单节点运行、断点调试、变量查看

### 变量系统

- **环境变量**：工作流级别，在 DSL 顶层定义
- **节点输出变量**：每节点执行后产物，可被下游引用
- **会话变量**：跨轮对话持久化（仅 Chat 模式）
- **引用语法**：`{{node_id.output_name}}`

## 与 scratchpad 的对比

| 维度 | Dify | scratchpad |
|------|------|------------|
| 构建方式 | 可视化拖拽 | 声明式 SKILL.md + 代码 |
| 执行引擎 | DSL 解释器 | Agent 运行时 |
| 节点粒度 | 细粒度原子操作 | 粗粒度 Skill 调用 |
| 调试能力 | 单步执行 + 变量面板 | 日志查看 |
| 灵活性 | 受节点类型限制 | 完全自由编程 |
| 学习成本 | 低（拖拽即用） | 中（需理解 Skill 规范） |
