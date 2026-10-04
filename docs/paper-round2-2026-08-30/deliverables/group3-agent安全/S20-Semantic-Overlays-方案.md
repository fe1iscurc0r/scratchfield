# S20 Semantic Overlays 提示注入防御方案

> 来源：digest-g1-3 2608.23873v1（Semantic Overlays: Mitigating Prompt Injection with Annotated Tokens）
> 原型：`tools/semantic_overlay_filter.py` · 测试：`tools/test_semantic_overlay_filter.py`（6 passed）

## 1. 核心思想

"语言模型看到的一切都是 token"。注入防御的关键是：**给每个输入 token 标注来源/信任级别**，
让模型（或前置过滤层）区分"可信指令"与"不可信数据里混入的指令"。

## 2. 设计：token 标注过滤管线

输入按来源分段（system / user / tool / external），判定信任级别后：

- `system` / `user`（可信）→ 原样通过。
- `tool` / `external`（不可信）→ 扫描**指令注入模式**（"ignore previous instructions"、
  "you are now"、"reveal the secret"、"override system prompt" 等），命中片段掩码为
  `[UNTRUSTED-CONTENT]`，实现"注入内容降权"。
- 未知来源 → 保守按不可信处理（默认拒绝）。

对齐：`mcpserver/trust_layer.py` 的来源分级与 `docs/neko-trust-memory-设计稿.md` 的
来源分级（user_direct / agent / file / external）。

## 3. 结果（验收）

| 指标 | 基线（无过滤） | 本方案 | 验收 |
|---|---|---|---|
| 注入攻击成功率 | 100% | 0%（全部掩码） | 下降 ≥50% ✅ |
| 正常指令通过率 | 100% | 100%（可信段不动） | ≥95% ✅ |

6 个注入样本全部被掩码；可信 system/user 段逐字保留；可信段里的正常"ignore/重新生成"
类表述不被误伤。

## 4. 落点建议

作为 NEKO 提示词组装前的**前置过滤层**接入（prompt 拼接 → `filter_prompt` → 模型），
与 `trust_layer` 的信任评分联动：trust 评分低的来源直接进不可信分段。规则式原型满足
"不引 LLM"约束，后续可把掩码替换为"可信度加权"而非硬掩码，减少误伤。
