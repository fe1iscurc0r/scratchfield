# Flowise 架构笔记

## 概述

Flowise 是一个基于节点的 AI Agent 构建器，以拖拽交互为核心交互范式，底层深度集成 LangChain 生态，让用户无需编写代码即可构建复杂的 LLM 应用。

## 拖拽交互范式

### 画布设计

Flowise 的核心是一个无限画布，用户通过以下操作构建工作流：

1. **节点面板**：左侧面板展示按类别组织的可用节点
2. **拖放**：从面板拖拽节点到画布
3. **连线**：从节点输出端口拖拽到目标节点输入端口
4. **配置**：点击节点在右侧属性面板修改参数
5. **执行**：一键运行，实时查看输出

### 交互约束

- 输入/输出端口类型匹配（类型安全连线）
- 循环依赖检测
- 必填参数校验
- 实时执行状态反馈（运行中/成功/失败/等待中）

## 节点组件模型

### 节点分类体系

```
Flowise 节点树
├── Agents（智能体）
│   ├── OpenAI Function Agent
│   ├── ReAct Agent
│   ├── Conversational Agent
│   └── MRKL Agent
├── Chains（链）
│   ├── LLM Chain
│   ├── Conversational Chain
│   └── Retrieval QA Chain
├── Chat Models（对话模型）
│   ├── ChatOpenAI
│   ├── ChatAnthropic
│   └── Azure ChatOpenAI
├── Document Loaders（文档加载）
│   ├── PDF, CSV, TXT
│   └── Web Scraper
├── Embeddings（嵌入）
├── Memory（记忆）
│   ├── Buffer Memory
│   └── Summary Memory
├── Tools（工具）
│   ├── Search, Calculator
│   └── Custom Tool
├── Vector Stores（向量存储）
│   ├── Pinecone, Chroma
│   └── FAISS, Weaviate
└── Output Parsers（输出解析）
```

### 节点内部结构

每个节点本质上是一个 LangChain 组件的封装：

```
┌─────────────────────────┐
│   ChatOpenAI 节点        │
├─────────────────────────┤
│ 属性:                    │
│  - model_name: gpt-4    │
│  - temperature: 0.7     │
│  - max_tokens: 2048     │
├─────────────────────────┤
│ 输入端口:                │
│  - prompt (string)      │
│  - systemMessage (string)│
├─────────────────────────┤
│ 输出端口:                │
│  - response (string)    │
└─────────────────────────┘
```

## LangChain 深度集成

### 集成层次

```
用户界面 (React Flow)
    ↓ 拖拽操作转化为
JSON 工作流定义
    ↓ 解析为
LangChain 对象图
    ↓ 执行
LangChain 运行时
```

### 自定义工具注册

Flowise 支持通过内置的 Custom Tool 节点扩展能力：

```javascript
// 在 Custom Tool 节点中直接编写
const tool = {
  name: "weather",
  description: "查询天气信息",
  schema: z.object({
    city: z.string().describe("城市名")
  }),
  func: async ({ city }) => {
    // 自定义逻辑
    return `城市 ${city} 天气晴朗`
  }
}
```

## 与 scratchpad 的对比

| 维度 | Flowise | scratchpad |
|------|---------|------------|
| 交互方式 | 拖拽画布 | 对话式 + skill 文件 |
| 底层引擎 | LangChain | 自定义 Agent 运行时 |
| 节点生态 | 预设节点库 | 无限制自定义 |
| 适用人群 | 非开发者/低代码 | 开发者 |
| 扩展方式 | Custom Tool 节点 | Skill 文件 + 任意代码 |
| 工作流保存 | JSON 导出 | Git 版本控制 |
