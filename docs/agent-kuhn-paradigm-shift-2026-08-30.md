# A10 Kuhn 范式转换 Agent（Little Scientist 循环）

> 任务：A10 Kuhn 范式转换 Agent
> 来源：digest-g7-1-2026-08-30.md · 核心论文 2608.16951《The Little Scientist: LLM Agent-Driven Discovery via the Scientific Method》
> 日期：2026-08-30

---

## 一、问题陈述

LLM Agent 做科学探索时，会在某个假设空间内**反复收敛到局部最优**——不断微调同一个假设，却无法跳出该范式去尝试全新方向。这正是 Thomas Kuhn 说的"常规科学 vs 范式转换"的张力：常规优化解决不了"需要换范式"的问题。

The Little Scientist（2608.16951）的答案是：**Scientist Agent 陷入局部最优时，由 Kuhn Agent 注入"跨学科灵感 + 范式转换猜想"**，迫使探索不同的 latent space 区域。实证：Delta V 在 ProteinGym 登顶（+0.033 超 VenusREM），DALE 超越 STREME 11×。

## 二、核心机制：双 Agent 科学方法循环

### Scientist Agent（常规科学）
- 循环执行：**假设 → 实现 → 测试 → 反馈**。
- 在当前范式内做局部优化：提出假设、跑实验、根据结果修正假设。

### Kuhn Agent（范式转换）
- **触发条件**：Scientist Agent 连续多轮无显著进步（收敛检测）时被唤醒。
- **动作**：注入跨学科灵感 + 范式转换猜想（如"从代谢工程范式转向蛋白质开关设计范式"），把搜索推向不同 latent space 区域。

## 三、Kuhn 循环流程设计

```
loop:
    hypothesis = scientist.propose(state)          # 常规假设
    result = evaluate(hypothesis)                  # 实验/仿真反馈
    state.update(hypothesis, result)
    if stuck(state):                                # 收敛检测：多轮无提升
        paradigm_shift = kuhn.inject(state)         # 范式转换猜想（跨学科灵感）
        state.redirect(paradigm_shift)              # 重定向到新 latent space 区域
        scientist.reset_local_opt(state)            # 在新范式下重新常规优化
    if converged(state): break
```

## 四、收敛检测与范式注入策略

1. **收敛检测**：滑动窗口内目标指标（如精度 / 损失 / 命中率）的改进量低于阈值，判定"陷入局部最优"。
2. **范式转换猜想来源**：
   - 跨物理原理（流体力学 ↔ 生物输运）；
   - 跨尺度（分子动力学 ↔ 连续介质力学）；
   - 跨领域文献（自然光合系统 → 人工光催化剂）。
3. **强制重定向**：不是"微调旧假设"，而是显式切换假设空间，避免路径依赖。

## 五、收敛案例（模板）

| 阶段 | 假设范式 | 指标 | 说明 |
|---|---|---|---|
| 常规科学 | 范式 A 内局部优化 | 平台期 | Scientist 反复微调，无提升 |
| 触发 | 收敛检测命中 | — | 唤醒 Kuhn Agent |
| 范式转换 | 注入范式 B 猜想 | 跳变 | 探索新 latent 区域 |
| 结果 | 范式 B 继续优化 | 突破 | 跳出局部最优 |

论文实证锚点：Delta V（ProteinGym 登顶）、DALE（超越 STREME 11×）即为"范式转换跳出局部最优"的收敛案例。

## 六、验收对照

| 验收项 | 交付 |
|---|---|
| Kuhn 循环流程 | §三 流程图 |
| Scientist + Kuhn 双 Agent | §二 |
| 一个收敛案例 | §五 案例模板（锚定论文 Delta V/DALE） |
| 文档 | `docs/agent-kuhn-paradigm-shift-2026-08-30.md` |
