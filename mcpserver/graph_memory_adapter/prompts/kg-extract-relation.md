# 关系抽取 prompt（卷142）

> 设计借鉴 rahulnyk/knowledge_graph（MIT · 4060★）的 `graphPrompt`：
> **Thought 1/2/3 分步脚手架**（先找术语 → 再找配对 → 再定关系词），
> 输出 node_1 / node_2 / edge 三元组。few-shot 见文末。

## System prompt（逐字使用）

```
你是一个网络图构建器：从给定上下文里抽取术语及其关系。
上下文由 ``` 包围。你的任务是抽取这些术语的本体关系。

Thought 1：逐句读，找出句中提到的关键术语。
    术语可以是 object / entity / location / organization / person /
    condition / acronym / document / service / concept 等。
    术语应尽可能原子化。

Thought 2：思考这些术语两两之间能形成什么关系。
    出现在同一句或同一段里的术语通常相关。
    一个术语可以关联多个术语。

Thought 3：为每一对相关术语定出关系词。

输出为 JSON 数组，每项是一对术语与其关系：

[
   {
       "node_1": "本体里的一个概念",
       "node_2": "另一个相关概念",
       "edge": "node_1 与 node_2 的关系，用一两个词或一句话"
   }, {...}
]

约束：
- 每条边的两个端点都必须出现在前面概念抽取的实体清单里（不要凭空造节点）。
- 同一对节点只输出一条最强的关系边（去重）。
- 只输出 JSON，不要解释文字、不要 markdown 代码块标记。
```

## User prompt 模板

```
context: ```{text}```

已知实体清单（边端点必须来自这里）：
{entities}

output:
```

## 关系词建议表（供 LLM 优先选择，非强制）

| 关系词 | 用法 |
|---|---|
| `part_of` | 结构/组成包含 |
| `delegates_to` | 授权/指派 |
| `approved_by` | 审批归属 |
| `held_by` | 职位/角色持有 |
| `references` | 文档/引用关系 |
| `has_property` | 实体具备某性质/参数 |
| `produced_by` | 由某过程/方法产生 |
| `measured_by` | 由某仪器/方法测出 |
| `located_in` | 位置归属 |

## few-shot 示例

**示例 1**

输入 context：
```
木质素纳米颗粒经 γ 射线交联后形成水凝胶，溶胀率用称重法测定。
```
已知实体清单：木质素纳米颗粒 / γ 射线交联 / 水凝胶 / 溶胀率 / 称重法

期望输出：
```json
[
  {"node_1": "木质素纳米颗粒", "node_2": "水凝胶", "edge": "produced_by"},
  {"node_1": "γ 射线交联", "node_2": "水凝胶", "edge": "produced_by"},
  {"node_1": "溶胀率", "node_2": "水凝胶", "edge": "has_property"},
  {"node_1": "溶胀率", "node_2": "称重法", "edge": "measured_by"}
]
```

**示例 2**（层级关系用 part_of，别用泛化的 related_to）

输入 context：
```
陆墨生态由桌宠 NEKO、科研脑 Lumo 与 MCP 工具总线组成。
```
已知实体清单：陆墨生态 / NEKO / Lumo / MCP 工具总线

期望输出：
```json
[
  {"node_1": "NEKO", "node_2": "陆墨生态", "edge": "part_of"},
  {"node_1": "Lumo", "node_2": "陆墨生态", "edge": "part_of"},
  {"node_1": "MCP 工具总线", "node_2": "陆墨生态", "edge": "part_of"}
]
```
