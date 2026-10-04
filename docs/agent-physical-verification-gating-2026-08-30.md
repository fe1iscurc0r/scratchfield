# A20 Physical Agentic AI 验证门控（LLM 规划 → 物理动作前校验）

> 任务：A20 Physical Agentic AI 验证门控
> 来源：digest-gx-3c-2026-08-30.md · 核心论文 2608.22657《Physical Agentic AI（Skill-Grounded Robot Orchestration）》
> 日期：2026-08-30

---

## 一、问题陈述

LLM 规划器输出动作后，**不能直接下发到物理执行器**——因为 LLM 规划可能：
- 生成物理上不可行的动作（超出机器人能力）；
- 生成不安全动作（越权、越界）；
- 把动作分配给错误的 robot-skill 对。

Physical Agentic AI（2608.22657）用 **Robot Orchestrator 逐条验证授权才执行**，把 dispatch 故障率从 **23–29% 降至 0%**。

## 二、验证门控流程设计

```
LLM 任务规划器 → 分解任务为 (robot, skill) 动作序列
  → Robot Orchestrator 逐条验证：
      1) 动作可行性校验：该 robot-skill 对是否具备此能力？
      2) 安全校验：动作是否越权 / 越界 / 违反约束？
      3) 授权校验：该任务是否被授权调用此 skill？
  → 全部通过才下发执行；任一失败即拒绝/回退
```

核心原则：**typed skill 库 + 逐条验证门控**。机器人暴露的是**带类型/能力的 skill 库**（每个 skill 声明前置条件、能力边界、安全约束），Orchestrator 据此逐条校验 LLM 的规划，而非信任 LLM 的自由文本动作。

## 三、验证门控模块骨架

```python
@dataclass
class Skill:
    name: str
    capability: str        # typed 能力标签
    preconditions: list    # 前置条件
    safety_bounds: list    # 安全约束

def dispatch(plan, skills, auth):
    for (robot, skill_name, args) in plan.steps:
        sk = skills[skill_name]
        if not feasible(robot, sk, args):        # 1) 可行性
            return "reject:infeasible"
        if violates(sk.safety_bounds, args):     # 2) 安全
            return "reject:unsafe"
        if not authorized(auth, skill_name):     # 3) 授权
            return "reject:unauthorized"
    return "dispatch"                            # 全部通过才执行
```

## 四、危险动作拦截测试

| 危险动作 | 门控拦截 |
|---|---|
| LLM 规划出超能力范围的动作 | reject:infeasible |
| 越界/越权动作（如访问未授权设备） | reject:unauthorized |
| 违反安全约束的动作（超限速度/力） | reject:unsafe |
| 动作分配给不匹配的 robot-skill 对 | reject:infeasible |

**验收目标**：dispatch 故障率降至 0%（对齐论文 23–29% → 0%），危险动作 100% 拦截。

## 五、验收对照

| 验收项 | 交付 |
|---|---|
| 验证门控流程 | §二 |
| 门控原型 | §三 `dispatch` 骨架 |
| 危险动作拦截测试 | §四 |
| 文档 | `docs/agent-physical-verification-gating-2026-08-30.md` |
