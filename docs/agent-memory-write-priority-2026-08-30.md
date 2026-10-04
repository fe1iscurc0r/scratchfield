# A12 记忆写入优先级策略（按来源可信度 / 工具结果重排）

> 任务：A12 记忆写入优先级策略
> 来源：digest-g2-4b-2026-08-30.md · 核心论文 2608.26295《MemToC》
> 日期：2026-08-30

---

## 一、问题陈述

MemToC（2608.26295）揭示：**工具返回强烈主导模型**——冲突时模型仅 6.5–17.1% 保留正确记忆，却 86–93% 遵循正确工具。这个"工具主导"偏差不仅影响**读取仲裁**（A04 已覆盖），也影响**写入优先级**：当工具结果与既有记忆冲突时，系统默认让工具结果覆盖记忆，导致正确记忆被错误覆盖。

A12 的目标：**在写入阶段就按来源可信度/工具结果重排写入优先级**，让"该覆盖谁"成为一个有依据的决策，而不是默认工具覆盖。

## 二、策略设计：写入优先级评分

每条待写入的候选记忆，按其来源与证据强度打分，决定是否覆盖、覆盖到什么权重：

```
write_priority(candidate) =
    w1 * source_trust(candidate.source)   # 来源可信度（参数记忆 > 受信工具 > 可疑工具）
  + w2 * corroboration(candidate)         # 与其他证据的交叉验证
  + w3 * freshness(candidate)             # 新鲜度
  + w4 * confidence(candidate)            # 模型/工具置信度
```

### 覆盖规则（按优先级）
| 情形 | 处置 |
|---|---|
| 新记忆优先级 > 既有记忆 | 覆盖（或提升权重） |
| 新记忆优先级 ≈ 既有记忆 | 并存，标记冲突，交由 A04 仲裁 |
| 新记忆优先级 < 既有记忆（低信任工具结果） | **拒绝覆盖**，仅记为该工具的"待验证返回" |
| 工具返回与参数记忆冲突 | 不默认工具覆盖，触发验证后决定 |

关键变化：**工具结果不再默认获得最高写入优先级**——它必须通过与来源可信度、交叉验证、新鲜度共同打分后，才能决定能否写入/覆盖。

## 三、原型骨架

```python
def write(memory, candidate, env_facts):
    p_new = write_priority(candidate, env_facts)
    for m in memory:
        if same_subject(m, candidate):
            p_old = write_priority(m, env_facts)
            if p_new > p_old + TAU:
                m.update(candidate); return "overwrite"
            elif p_new < p_old - TAU:
                return "reject"           # 低信任工具结果不覆盖正确记忆
            else:
                m.conflicts.append(candidate); return "conflict"  # 交 A04 仲裁
    memory.append(candidate); return "append"
```

## 四、保留率测试

复用 MemToC 冲突场景，对比：
1. **基线**：默认工具覆盖（对应论文 6.5–17.1% 保留正确记忆）。
2. **本策略**：写入优先级评分 + 覆盖规则。

**指标**：正确记忆保留率、错误覆盖率。
**验收目标**：正确记忆保留率相对基线显著提升，且工具结果**确实可信时**仍能正常写入（不矫枉过正）。

## 五、验收对照

| 验收项 | 交付 |
|---|---|
| 写入优先级策略 | §二（评分 + 覆盖规则） |
| 原型 | §三 `write` 骨架 |
| 保留率测试 | §四 对比实验 |
| 文档 | `docs/agent-memory-write-priority-2026-08-30.md` |
