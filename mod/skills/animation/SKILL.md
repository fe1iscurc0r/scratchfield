---
name: animation
description: 静态图表生成技能，接收需求→选模板→生成图表→导出。调用 agent_animation API 完成。
version: 1.0.1
author: QClaw 改造
tags:
  - animation
  - diagram
  - visualization
enabled: true
---

# 图表生成技能 (animation)

## 概述

本技能提供端到端的静态图表生成工作流，接收用户的自然语言描述，自动选择合适的图表类型，生成图表并导出为图像文件。底层通过调用 `agent_animation` 服务提供的 API 工具完成。

## 触发条件

- 用户请求"生成图表"、"画架构图"、"做流程图"、"序列图"、"数据流图"、"生命周期图"
- 用户描述了可视化需求（架构、流程、序列、数据流等）
- 用户需要将结构化描述转化为可视化图表

## 工作流程

### 第一步：需求解析

1. 解析用户输入，提取图表主题、要展示的关系/流程
2. 确定图表类型：架构图、工作流图、序列图、数据流图、生命周期图等
3. 提取关键节点、连接关系、分组信息

### 第二步：选择图表类型

调用 `agent_animation` 工具浏览可用模板：

**工具: `list_templates`**

```
list_templates()
```

返回所有可选的图表类型及其描述。支持的 diagram type：

| type | 名称 | 用途 |
|------|------|------|
| `architecture` | 架构图 | 系统架构、模块关系、部署拓扑 |
| `workflow` | 工作流图 | 业务流程、操作步骤、决策分支 |
| `sequence` | 序列图 | 时序交互、消息传递、调用链 |
| `dataflow` | 数据流图 | 数据流转、处理管道、ETL |
| `lifecycle` | 生命周期图 | 状态迁移、生命周期阶段 |

根据用户需求匹配最合适的图表类型。

### 第三步：生成图表

调用 `agent_animation` 工具生成图表：

**工具: `generate_diagram`**

```
generate_diagram(type, spec)
```

参数：
- `type` (string, 必填)：图表类型，可选 `"architecture"` | `"workflow"` | `"sequence"` | `"dataflow"` | `"lifecycle"`
- `spec` (object, 必填)：图表规格定义 (JSON)，描述节点、连线、分组、标签等

**spec 通用结构：**

```json
{
  "title": "图表标题",
  "nodes": [
    { "id": "n1", "label": "节点1", "shape": "box|circle|diamond|cylinder|person", "group": "group1" },
    { "id": "n2", "label": "节点2", "shape": "box", "group": "group1" }
  ],
  "edges": [
    { "from": "n1", "to": "n2", "label": "调用/流转", "style": "solid|dashed|dotted" }
  ],
  "groups": [
    { "id": "group1", "label": "分组名称", "style": "solid|dashed" }
  ],
  "direction": "TB|LR|RL|BT",
  "theme": "default|dark|minimal|colorful"
}
```

不同 type 的 spec 字段可能有差异，以 `list_templates` 返回的说明为准。

返回包含 `diagram_id` 的响应，用于后续导出。

### 第四步：导出

调用 `agent_animation` 工具导出最终图表：

**工具: `export_diagram`**

```
export_diagram(diagram_id, format)
```

参数：
- `diagram_id` (string, 必填)：由 `generate_diagram` 返回的图表ID
- `format` (string, 必填)：导出格式，可选：
  - `"png"`   - PNG 位图（默认，适合嵌入文档）
  - `"jpeg"`  - JPEG 位图（体积小）
  - `"svg"`   - SVG 矢量图（可无限缩放，适合网页）
  - `"gif"`   - GIF 动图（适合简单动画）
  - `"webm"`  - WebM 视频（适合复杂动画演示）

返回导出文件的下载链接或本地路径。

## 完整调用示例

```
用户: 画一个微服务架构图

→ Step 1: 解析需求 → 架构图/微服务拓扑
→ Step 2: list_templates() → 确认使用 architecture 类型
→ Step 3: generate_diagram(type="architecture", spec={
    "title": "微服务架构",
    "nodes": [
      {"id":"gw","label":"API网关","shape":"box"},
      {"id":"svc1","label":"用户服务","shape":"box"},
      {"id":"svc2","label":"订单服务","shape":"box"},
      {"id":"db","label":"数据库","shape":"cylinder"}
    ],
    "edges": [
      {"from":"gw","to":"svc1"},
      {"from":"gw","to":"svc2"},
      {"from":"svc1","to":"db"},
      {"from":"svc2","to":"db"}
    ]
  }) → 返回 diagram_id="diag_abc123"
→ Step 4: export_diagram("diag_abc123", "png") → 下载链接
```

```
用户: 做一个订单状态流转的生命周期图

→ Step 1: 解析 → 生命周期图/订单状态
→ Step 2: list_templates() → 确认 lifecycle 类型
→ Step 3: generate_diagram(type="lifecycle", spec={
    "title": "订单生命周期",
    "states": ["待支付","已支付","处理中","已发货","已完成","已取消"],
    "transitions": [
      {"from":"待支付","to":"已支付","label":"付款成功"},
      {"from":"待支付","to":"已取消","label":"超时"},
      {"from":"已支付","to":"处理中","label":"确认"},
      ...
    ]
  })
→ Step 4: export_diagram(diagram_id, "svg")
```

## agent_animation 工具汇总

| 工具名 | 用途 | 关键参数 |
|--------|------|---------|
| `list_templates` | 浏览可用的图表类型 | 无 |
| `generate_diagram` | 生成图表 | type, spec |
| `export_diagram` | 导出图像/视频 | diagram_id, format |

## 注意事项

- 支持的导出格式：png、jpeg、svg、gif、webm（不支持 mp4/mov）
- 复杂图表建议先用小尺寸预览，确认布局后再导出高分辨率版本
- SVG 格式适合嵌入网页和文档，可无损缩放
- GIF/WebM 适合展示有动画效果的图表（如序列图中的消息流）
- spec 结构因 type 而异，生成前务必参考 `list_templates` 返回的说明
