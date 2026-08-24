"""Planner-Executor：Send() fan-out 图结构（授粉-C3）。

语义对齐 LangGraph/ChemGraph 的 ``Send()`` map-reduce：

1. **plan**  —— ``planner(task)`` 返回一批 ``Send(target, payload)`` 分支指令
2. **fan-out** —— 每个 Send 按 ``target`` 找到注册的 handler，
   包成 ``TaskSpec`` 经 ``ExecutionBackend.submit_batch`` 并行派发
3. **reduce** —— 按**分解顺序**收齐结果，交给 ``reducer`` 汇总

不引入 langgraph 依赖；并行度由后端线程池决定（LocalBackend 默认 4）。
"""

from __future__ import annotations

import logging
from concurrent.futures import Future
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from pydantic import BaseModel, Field

from research.execution.base import ExecutionBackend, TaskSpec

logger = logging.getLogger(__name__)

Handler = Callable[[dict], Any]
Planner = Callable[[Any], list["Send"]]
Reducer = Callable[[list[Any]], Any]


class Send(BaseModel):
    """map 阶段的一个分支指令：把 payload 发给名为 target 的 handler。"""

    target: str = Field(description="注册的 handler 名。")
    payload: dict = Field(default_factory=dict, description="传给 handler 的参数。")


@dataclass
class SubTaskError:
    """分支执行失败的占位结果（保留序号，保证汇总顺序可追溯）。"""

    index: int
    target: str
    error: Exception

    def __str__(self) -> str:
        return f"分支#{self.index}[{self.target}] 失败: {type(self.error).__name__}: {self.error}"


@dataclass
class PlanResult:
    """一次 plan → fan-out → reduce 的完整产出。"""

    sends: list[Send]
    results: list[Any]
    summary: Any
    errors: list[SubTaskError] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


class PlannerExecutor:
    """Send() fan-out 图：注册 handler → 规划 → 并行执行 → 按序汇总。

    用法
    ----
    >>> with LocalBackend() as backend:
    ...     backend.initialize()
    ...     pe = PlannerExecutor(backend)
    ...     pe.register("fetch", fetch_fn)
    ...     result = pe.run(planner_fn, task, reducer_fn)
    """

    def __init__(self, backend: ExecutionBackend) -> None:
        self._backend = backend
        self._handlers: dict[str, Handler] = {}

    def register(self, target: str, handler: Handler) -> None:
        """注册一个分支 handler；重名覆写。"""
        self._handlers[target] = handler

    def plan(self, planner: Planner, task: Any) -> list[Send]:
        """分解任务为 Send 列表；planner 必须返回非空 list[Send]。"""
        sends = planner(task)
        if not isinstance(sends, list) or not sends:
            raise ValueError(f"planner 必须返回非空 list[Send]，实际: {sends!r}")
        for i, s in enumerate(sends):
            if not isinstance(s, Send):
                raise TypeError(f"分支#{i} 不是 Send 实例: {s!r}")
            if s.target not in self._handlers:
                raise KeyError(f"分支#{i} 的 target '{s.target}' 未注册（现有: {list(self._handlers)}）")
        return sends

    def run(
        self,
        planner: Planner,
        task: Any,
        reducer: Optional[Reducer] = None,
        *,
        raise_on_error: bool = True,
    ) -> PlanResult:
        """plan → fan-out → reduce 全流程。

        Parameters
        ----------
        reducer
            汇总函数；缺省为 ``list`` 原样保留有序结果。
        raise_on_error
            分支失败时是否立刻抛出（True）；False 时失败分支在
            ``results`` 里以 ``SubTaskError`` 占位，``errors`` 记录详情。
        """
        sends = self.plan(planner, task)
        tasks = [
            TaskSpec(
                task_id=f"branch-{i}-{s.target}",
                task_type="python",
                callable=self._handlers[s.target],
                kwargs={"payload": s.payload},
            )
            for i, s in enumerate(sends)
        ]
        logger.info("[planner] fan-out %d 个分支: %s", len(tasks), [t.task_id for t in tasks])
        futures: list[Future] = self._backend.submit_batch(tasks)

        results: list[Any] = []
        errors: list[SubTaskError] = []
        # 按提交顺序逐个收果 —— 汇总顺序 == 分解顺序（map-reduce 语义）
        for i, (fut, s) in enumerate(zip(futures, sends)):
            try:
                results.append(fut.result())
            except Exception as exc:  # noqa: BLE001 —— 分支失败不串扰其它分支
                errors.append(SubTaskError(index=i, target=s.target, error=exc))
                results.append(None)
                if raise_on_error:
                    raise RuntimeError(str(SubTaskError(index=i, target=s.target, error=exc))) from exc

        reducer = reducer or list
        summary = reducer(results)
        return PlanResult(sends=sends, results=results, summary=summary, errors=errors)
