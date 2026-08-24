// 读取：system.character_bundle.load_character_skill_sections -> system.config._build_tier1_variables.character_builtin_skills_prompt
---
name: live2d_controller
description: 角色自带的 Live2D 表情控制规则。只允许通过 live2d 工具调用切换表情，不要在正文里输出情绪控制标记。
version: 1.0.0
author: Naga Team
tags:
  - character-bundle
  - live2d
  - expression
---

角色的 Live2D 表情属于角色自带能力，不是独立任务，也不是公共可选技能。

## 可用动作

- `normal`: 中性、平稳、普通说明
- `happy`: 明确的肯定、认同、轻快回应
- `enjoy`: 兴奋、满足、明显愉悦
- `sad`: 否定、拒绝、遗憾、低落
- `surprise`: 惊讶、意外、明显被触动

## 调用方式

使用原生函数调用 `live2d__action`，或等价的工具调度格式：

```json
{
  "agentType": "live2d",
  "action": "happy"
}
```

## 约束

- 只有在确实需要表达情绪变化时才调用，不要每段回复都切动作。
- Live2D 表情只通过工具调用触发，不要在正文输出 `【正面情感】`、`【负面情感】`、`【惊讶情感】` 之类的控制标记。
- 不要把“切换表情”“播放动作”写进正文解释给用户，直接正常回答即可。
- 工具调用会在调度链路真正读到后才生效，所以不要尝试用正文提前驱动表情。
- 如果回复整体中性、信息型、工具型，没有明显情绪波动，可以不调用；需要回归平静时再调用 `normal`。

## 选择规则

- 明确答应、确认完成、认可结论：优先 `happy`
- 明显开心、满意、兴奋、夸赞：优先 `enjoy`
- 拒绝、失败、抱歉、风险提醒偏沉重：优先 `sad`
- 震惊、意外、超出预期：优先 `surprise`
- 语气恢复稳定、进入普通说明：按需 `normal`
