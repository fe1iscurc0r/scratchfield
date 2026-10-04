# A02 Recuris 递归工作记忆 → 长时域 Agent 架构设计

> 任务：A02 Recuris 递归工作记忆 → 长时域 Agent
> 来源：digest-g1-3-2026-08-30.md · 核心论文 2608.24876《Recursive Experiential-Working Memory Evolution (Recuris)》
> 日期：2026-08-30

---

## 一、问题陈述

长时域（long-horizon）任务里，递归自改进（RSI）的核心瓶颈不是"模型不够强"，而是**技能调用与任务状态错配**：Agent 在长任务后期，依然沿用任务早期形成的技能/记忆，而这些技能所依赖的任务状态早已改变，导致"用对的方法解错的状态"。

论文（2608.24876）实验覆盖 10 模型 × 4 基准，37 个 pair 中 35 个成功提升，把前沿模型带到 SOTA 级任务成功率，且优势随时域增长而扩大（最长任务 +32.2pp）。它是本组唯一把**记忆架构、证据追踪、验证门控、元更新**统一在一个形式化框架内、并有强实验支撑的工作。

## 二、核心概念：Experiential-Working Memory（EWM）

区别于"参数记忆"（模型权重）和"普通上下文记忆"（把轨迹塞进 prompt），EWM 是一层**显式的、可验证、可自我更新的经验工作记忆**，位于任务执行循环之上。它要解决的本质问题：**在任务状态漂移时，及时让技能缓存失效并重建，而不是让旧经验继续错误地指导动作。**

## 三、四组件架构设计

### 组件 1：记忆（Experiential-Working Memory / 技能缓存）
- **技能条目**：`skill = {触发条件, 动作序列, 前置任务状态指纹, 成功记录}`。
- 每个技能入库时，记录其**成立的任务状态指纹**（关键环境变量/目标的哈希），而非只存动作本身。
- 提供**按状态指纹检索**的能力：执行前，先查"当前状态"最匹配的技能；若无匹配，则视为新状态、走通用推理路径。

### 组件 2：证据追踪（Evidence Tracking）
- 对每个技能条目维护**证据链**：哪些执行实例在哪些状态下成功/失败、失败时的状态偏差量。
- 记录形式：`evidence = [(state_fingerprint, outcome, delta_state, t), ...]`，带时间戳，支持过期衰减。
- 目的：让"技能是否仍适用于当前状态"成为一个**可计算、可追溯**的问题，而不是靠模型临场猜测。

### 组件 3：验证门控（Verification Gating）
- 技能调用前经过一道门控：`适用性 = sim(current_state, skill.state_fingerprint) > θ`。
- 门控判定"通过"才允许直接复用缓存技能；否则降级到完整推理路径（重新规划动作）。
- 门控失败（技能被否决）本身也是一个证据事件，回写进组件 2，驱动后续修正。

### 组件 4：元更新（Meta-Update）
- 任务结束/阶段结束时，用执行回放把"技能调用 → 实际结果"的反馈**批量回写**到 EWM：
  - 成功且状态匹配 → 强化该技能的证据权重；
  - 状态错配导致的失败 → 标记该技能在**新状态区间失效**，触发重建或细分（按状态分区拆分技能）；
  - 持续失效的技能 → 淘汰或降权。
- 元更新是"递归自改进"的落点：RSI 不是重训模型，而是**对经验工作记忆做结构化在线更新**。

## 四、数据流（一帧执行循环）

```
观察当前状态 s_t
  → 计算 state_fingerprint(s_t)
  → 检索 EWM 中最匹配技能 k
  → 验证门控：sim(s_t, k.fingerprint) > θ ?
       ├─ 是 → 复用 k 的动作序列
       └─ 否 → 通用推理路径生成动作（并可能孵化新技能候选）
  → 执行，获得结果与下一状态
  → 证据追踪：记录 (fingerprint, outcome, delta)
  → 阶段末元更新：回写/重建/淘汰 EWM 条目
```

## 五、原型（最小可运行骨架）

```python
from dataclasses import dataclass, field
from typing import Any, Optional

@dataclass
class Skill:
    trigger: Any                 # 触发条件描述
    actions: list                # 动作序列
    state_fingerprint: Any       # 成立时的任务状态指纹
    evidence: list = field(default_factory=list)  # [(fp, outcome, delta, t)]
    weight: float = 1.0

class ExperientialWorkingMemory:
    def __init__(self, sim_fn, theta=0.8, decay=0.05):
        self.skills = {}
        self.sim = sim_fn           # 状态指纹相似度函数
        self.theta = theta
        self.decay = decay

    def retrieve(self, fp):
        best, best_s = None, -1.0
        for k, sk in self.skills.items():
            s = self.sim(fp, sk.state_fingerprint) * sk.weight
            if s > best_s:
                best, best_s = sk, s
        return best if best_s >= self.theta else None   # 验证门控

    def record(self, key, fp, outcome, delta):
        self.skills[key].evidence.append((fp, outcome, delta))

    def meta_update(self, key, fp, outcome, delta):
        sk = self.skills[key]
        sk.record(fp, outcome, delta)
        if outcome == "success":
            sk.weight = min(2.0, sk.weight + 0.1)
        else:
            sk.weight *= (1 - self.decay)              # 状态错配 → 降权
            if sk.weight < 0.1:
                del self.skills[key]                    # 淘汰
```

> 注：上述为示意骨架；生产实现需把 `state_fingerprint` 换成真实任务状态编码（如目标列表哈希 + 关键资源状态），`sim_fn` 换成语义/结构化相似度，`meta_update` 接入执行回放。

## 六、验收对照

| 验收项 | 交付 |
|---|---|
| 4 组件设计（记忆/证据追踪/验证门控/元更新） | §三 组件 1–4 逐一设计 |
| 架构设计 | §四 数据流 |
| 原型 | §五 最小可运行骨架 |
| 解决"技能调用与任务状态错配" | §一/§三（状态指纹 + 门控 + 错配降权） |
| 文档 | `docs/agent-recuris-experiential-memory-2026-08-30.md` |
