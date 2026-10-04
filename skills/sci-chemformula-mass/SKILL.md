---
name: sci-chemformula-mass
description: 化学式解析与分子量计算（元素组成/分子量/放射性标记检测）。帮用户"算一下纤维素 C6H10O5 的分子量""这个化学式的元素占比""检查化学式写没写对"时使用。
version: 1.0.0
author: 陆墨
tags:
  - chemistry
  - materials
  - formula
  - academic
enabled: true
---

# 化学式解析与分子量计算

基于本仓 `mcpserver/academic/chemformula_interface.py`（已注册 academic 工具）。上游授粉：K-Dense-AI/scientific-agent-skills 化学计算类技能改造。

## 调用格式

```tool
{"agentType": "mcp", "service_name": "academic", "tool_name": "chem_parse", "formula": "C6H10O5"}
```

## 能力

| 能力 | 输出 |
|------|------|
| 分子量 | 标准原子量加权求和（g/mol） |
| 元素组成 | 各元素原子数 + 质量占比 |
| 合法性校验 | 化学式语法错误明确报错（不静默） |

## 材料线常用示例

- 纤维素单体 C6H10O5 → 162.14 g/mol（聚合度 n 换算链长分子量）
- 木质素单元（愈创木基 C10H12O3 / 紫丁香基 C11H14O4）→ 单元分子量对照
- 半纤维素（木糖 C5H10O5 / 甘露糖 C6H12O6）→ 糖单元比对

## 验证

- 已知分子量对照：C6H10O5 ≈ 162.14、C5H10O5 ≈ 150.13（±0.1 内算通过）。
