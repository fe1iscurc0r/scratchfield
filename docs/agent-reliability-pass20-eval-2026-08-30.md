# A03 Thinkingbox 测量失效 → Agent 可靠性评测（pass²⁰）

> 任务：A03 Thinkingbox 测量失效 → 可靠性评测
> 来源：digest-g2-1-2026-08-30.md · 核心论文 2608.19741《Thinkingbox（One Success Isn't Reliability）》
> 日期：2026-08-30

---

## 一、问题陈述

当前 Agent 评测用 **pass@1（"曾经成功过"）** 作为可靠性的代理变量，系统性测量了错误的量。Thinkingbox（2608.19741）在 507 个有状态业务工作流上的实证结果：

- **pass@1 = 65%**（单次运行成功）
- **pass²⁰ = 25%**（20 次重复运行**终端状态全部一致成功**）

这个 40pp 的鸿沟说明：**"响应正确" ≠ "任务完成"**。Agent 可能在单次采样里碰巧输出正确答案，但无法在重复运行中稳定收敛到正确的终端状态。对任何生产级 Agent，可靠性（终端一致性）比峰值能力更重要。

## 二、pass²⁰ 评测定义

- **pass@1**：对任务 t，运行 1 次，终端状态正确即记为成功。`pass@1 = E_t[ 1{R_t^1 正确} ]`。
- **passᵏ（本文取 k=20）**：对任务 t，独立运行 k 次（不同随机种子/采样温度），**k 次终端状态全部正确**才记为成功。`pass^k = E_t[ ∏_{i=1..k} 1{R_t^i 正确} ]`。

pass²⁰ 度量的是**重复执行的终端一致性**，直接暴露"单次侥幸成功"型 Agent。

## 三、评测脚本设计

要求被测 Agent 提供统一接口：`run(task, seed) -> terminal_state`，且环境可重置/可种子化。

```python
# docs/agent-reliability-pass20-eval-2026-08-30.py
import random
from collections import defaultdict

def evaluate(agent, tasks, k=20, judge=None):
    """judge: terminal_state -> bool（判定终端状态是否正确）"""
    judge = judge or (lambda st: st.get("done") and st.get("correct"))
    pass_at_1 = pass_at_k = 0
    report = defaultdict(list)
    for t in tasks:
        outcomes = []
        for i in range(k):
            seed = i  # 或 hash(t.id, i)
            st = agent.run(t, seed=seed)
            ok = judge(st)
            outcomes.append(ok)
        p1 = any(outcomes)                       # pass@1
        pk = all(outcomes)                       # pass^k（终端一致）
        pass_at_1 += p1
        pass_at_k += pk
        report[t.id] = {
            "pass@1": p1,
            f"pass^{k}": pk,
            "success_rate": sum(outcomes) / k,
            "outcomes": outcomes,
        }
    n = len(tasks)
    return {
        "pass@1": pass_at_1 / n,
        f"pass^{k}": pass_at_k / n,
        "reliability_gap": (pass_at_1 - pass_at_k) / n,
        "per_task": dict(report),
    }
```

## 四、pass@1 vs pass²⁰ 对比报告（模板）

| 指标 | 值 | 含义 |
|---|---|---|
| pass@1 | ~65%（示例） | 单次成功概率 |
| pass²⁰ | ~25%（示例） | 20 次重复终端一致 |
| 可靠性鸿沟 | ~40pp | "响应正确"与"任务完成"的差距 |
| 一致成功率均值 | （各任务 success_rate 均值） | 平均每任务 20 次中成功次数占比 |

**关键观察**：pass@1 与 pass²⁰ 的差距主要由**状态泄露/环境未重置/轨迹级随机性**三类原因造成。报告中应按任务分组给出 pass²⁰ < 1 的任务清单，并标注失败模式（终端状态不一致的具体表现），作为 Agent 修复的输入。

## 五、落地建议

1. **默认同时上报 pass@1 和 pass²⁰**（或 pass³/pass⁵ 的折中，视运行成本），把终端一致性纳入 CI 门禁。
2. **对齐 A01**：pass²⁰ 用"终端状态正确"而非"step-level 正确性"作为 ground truth，天然规避 A01 揭示的 credit 自欺问题。
3. **失败模式分类**：将 pass²⁰ 失败归因到"状态管理错误 / 工具调用副作用未回滚 / 采样脆弱"三类，分别修复。

## 六、验收对照

| 验收项 | 交付 |
|---|---|
| 评测脚本 | §三（`evaluate` + `agent.run(task, seed)` 接口） |
| pass@1 vs pass²⁰ 对比报告 | §四 报告模板 |
| 暴露"响应正确≠任务完成" | §一/§二 定义与鸿沟 |
| 文档 | `docs/agent-reliability-pass20-eval-2026-08-30.md` |
