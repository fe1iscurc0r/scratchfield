"""科研任务规划器：Planner-Executor fan-out（授粉-C3）。

参考 ChemGraph graphs/multi_agent.py 的 ``Send()`` map-reduce 语义
（LangGraph 同构，但不引入 langgraph 依赖，自写 fan-out）：

* ``Send(target, payload)`` —— map 阶段的一个分支指令
* planner 把总任务分解为一批 ``Send``（fan-out）
* executor 并行执行所有分支（复用 research.execution.ExecutionBackend）
* reducer 按分解顺序汇总结果（map-reduce 的 reduce）
"""

from __future__ import annotations

from research.planner.planner import (
    PlanResult,
    PlannerExecutor,
    Send,
    SubTaskError,
)

__all__ = ["Send", "PlanResult", "PlannerExecutor", "SubTaskError"]
