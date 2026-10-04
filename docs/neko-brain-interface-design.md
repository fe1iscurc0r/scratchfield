# NEKO 接脑 + 表情驱动设计（W65-01）

> 来源 docs/Meuxe-授粉报告.md · 参考设计（不抄 ACP 代码）

## 脑/皮分离架构

```
脑（Hermes/Naga）——MCP + 事件总线——> 皮（NEKO 渲染层）
  决策/推理                         动作/表情/台词
  <<expression>> 事件                只渲染
```

## 表情协议事件表

| 事件 | 渲染动作 |
|---|---|
| `<<happy>>` | smile |
| `<<thinking>>` | blink |
| `<<alert>>` | raise_brow |
| `<<sleepy>>` | half_close |
| 其他 | neutral |

## 实现

`tools/expression_protocol.py`：`extract_expressions` / `map_expression` / `render_actions`。
