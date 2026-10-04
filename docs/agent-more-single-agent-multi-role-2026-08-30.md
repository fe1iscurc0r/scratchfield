# A05 MoRE 单 Agent 多角色（20× token 节省）

> 任务：A05 MoRE 单 Agent 多角色
> 来源：digest-gx-5b-2026-08-30.md · 核心论文 2608.27338《One Model, Many Minds: MoRE（Mixture of Roles）》
> 日期：2026-08-30

---

## 一、问题陈述

多 Agent 协作场景（规划者 / 执行者 / 评审者各一个模型实例）虽然效果好，但 token 开销巨大——每个角色都要完整复述上下文、独立推理，且角色间需要消息往返。MoRE（2608.27338）的发现是：**单 Agent 单次推理中融合多角色专长，可以匹配多 Agent 协同效果，同时节省 20× token**，为边缘部署的 Agent 系统提供新范式。

## 二、核心机制：Mixture of Roles（角色混合）

不做多个独立 Agent 进程，而是在**同一个模型的单次前向里，注入多个角色的专家先验**，让模型在"一个推理通道"内同时扮演多角色：

- **角色专长编码**：每个角色（规划 / 执行 / 评审 / 纠错）的专长被编码为提示片段 + 专家路由权重。
- **单次推理多角色融合**：模型在一次解码中，按任务阶段动态加权混合各角色的贡献，而非串行调用多个模型。
- **输出等价性**：多角色混合的输出与多 Agent 串行协作的输出在任务成功率上匹配，但省掉了 N 份上下文重复与消息往返。

## 三、设计：角色混合改造一个多 Agent 场景

选定场景：**"任务规划 → 执行 → 评审"三段式多 Agent 流水线**（本项目最典型的多 Agent 模式）。

### 3.1 原多 Agent 流程（token 重）
```
planner_agent(上下文) → 计划
  → executor_agent(上下文 + 计划) → 结果
    → reviewer_agent(上下文 + 计划 + 结果) → 修正/验收
```
三份上下文、两次消息往返、三个独立推理预算。

### 3.2 MoRE 改造（单 Agent 多角色）
```
single_agent(
  上下文,
  role_mix = {planner: w1, executor: w2, reviewer: w3}   # 按阶段动态权重
) → 一次推理产出"计划 + 执行结果 + 自评审"
```
- 上下文只编码一次；角色通过**前缀注入 + 阶段切换**在同一解码通道内切换。
- 阶段切换由内部状态触发（计划产出 → 切 executor → 结果产出 → 切 reviewer），不产生跨模型消息。

### 3.3 角色混合权重
```
w_stage(task_state):
  规划阶段  → {planner: 0.9, executor: 0.05, reviewer: 0.05}
  执行阶段  → {planner: 0.05, executor: 0.9, reviewer: 0.05}
  评审阶段  → {planner: 0.05, executor: 0.1, reviewer: 0.85}
```
角色权重作为**可训练/可调的 router**，而非硬编码。

## 四、原型骨架

```python
ROLES = {"planner": ..., "executor": ..., "reviewer": ...}  # 角色提示片段

def more_infer(context, task):
    state = "plan"
    history = []
    for _ in range(MAX_STEPS):
        mix = role_mix(state)                       # 阶段 → 角色权重
        prompt = build_prompt(context, history, mix)
        out = single_model(prompt)                  # 单模型单次推理
        state, result = transition(state, out)      # 阶段切换 + 结果累积
        history.append(out)
        if state == "done":
            return result
```

> 关键差异：全程只有一个模型实例、一份上下文编码；`role_mix` 仅改变注入的提示与权重，不产生第二/第三个模型调用链。

## 五、Token 对比报告（模板）

| 指标 | 多 Agent 基线 | MoRE 单 Agent | 节省 |
|---|---|---|---|
| 上下文编码次数 | 3 次 | 1 次 | ~3× |
| 消息往返 | 2 轮 | 0 轮 | — |
| 总输入 token | T×3（近似） | T×1 | ~3× |
| 总推理预算 | 3 模型实例 | 1 模型实例 | ~3× |
| 任务成功率 | 基线 | 匹配 | — |

论文口径的 **20× token 节省**来自：上下文去重 + 去消息往返 + 单实例推理的复合效应（在角色数更多、任务更长的场景下放大）。实测以本地基准为准，报告应给出**成功率持平 + token 显著下降**的量化结论。

## 六、验收对照

| 验收项 | 交付 |
|---|---|
| 角色混合设计 | §二/§三（角色编码 + 阶段权重路由） |
| 改造一个多 Agent 场景 | §三（规划→执行→评审流水线） |
| 原型 | §四 `more_infer` 骨架 |
| token 对比报告 | §五 报告模板 |
| 文档 | `docs/agent-more-single-agent-multi-role-2026-08-30.md` |
