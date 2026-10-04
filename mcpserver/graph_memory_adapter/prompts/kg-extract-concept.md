# 概念抽取 prompt（卷142）

> 设计借鉴 rahulnyk/knowledge_graph（MIT · 4060★）的 `helpers/prompts.py`：
> 固定类别词表 + importance 打分 + 「原子化」要求。**few-shot 示例见本文件末**。

## System prompt（逐字使用）

```
你的任务是从给定上下文中抽取关键概念（含非人称实体）。

要求：
1. 只抽最重要且**原子化**的概念；若一个概念可拆，拆成更简单的概念。
2. 类别只能从这个词表里选（不得自创）：
   [event, concept, place, object, document, organisation, condition, misc]
3. 只抽取上下文里**明确陈述**的内容，不要推断、不要补充外部知识。
4. 输出为 JSON 数组，每项格式：

[
   {
       "entity": 概念名（用最完整的形式）,
       "importance": 该概念在本上下文的相对重要性，1-5 的整数（5 最高）,
       "category": 上面词表里的类别,
       "aliases": [该概念在本上下文出现过的简称/别称，没有就给空数组]
   }
]

5. 不要输出 JSON 以外的任何文字（不要解释、不要 markdown 代码块标记）。
```

## User prompt 模板

```
context: ```{text}```

output:
```

## few-shot 示例（提升小模型的格式稳定性）

**示例 1**

输入 context：
```
木质素纳米颗粒（Lignin NPs）经 γ 射线交联后形成水凝胶。该水凝胶在 pH=7 时溶胀率达 340%。
```

期望输出：
```json
[
  {"entity": "木质素纳米颗粒", "importance": 5, "category": "object", "aliases": ["Lignin NPs"]},
  {"entity": "γ 射线交联", "importance": 4, "category": "event", "aliases": []},
  {"entity": "水凝胶", "importance": 5, "category": "object", "aliases": []},
  {"entity": "溶胀率", "importance": 3, "category": "condition", "aliases": []},
  {"entity": "pH=7", "importance": 2, "category": "condition", "aliases": []}
]
```

**示例 2**（条件类信息必须落成 condition 实体，别塞进别的实体里）

输入 context：
```
单笔报销超过 5000 元时，需财务总监审批。
```

期望输出：
```json
[
  {"entity": "报销", "importance": 5, "category": "concept", "aliases": []},
  {"entity": "单笔上限 5000 元", "importance": 4, "category": "condition", "aliases": []},
  {"entity": "财务总监", "importance": 4, "category": "organisation", "aliases": []},
  {"entity": "审批", "importance": 3, "category": "concept", "aliases": []}
]
```
