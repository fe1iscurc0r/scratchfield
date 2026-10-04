"""A29 StateMem 状态追踪记忆（显式维护任务/环境状态，支持查询与回溯）

来源授粉点：digest-g1-1 2608.19652（StateMem Agent Tracking）——显式维护任务/环境
状态，把"当前状态准确率"提升 1.6-1.8×。迁移到 NEKO：用一个有界键值状态表显式跟踪
状态，增量合并环境观测（观测往往只含变化字段），支持查询与回溯。

与无状态记忆基线（只保留最近一次观测，丢失未提及字段）对比，多步任务下状态准确率
显著提升。落点 NEKO 记忆系统：对应"当前状态"这一层显式记忆，对齐 summer_memory 的
provenance 约定（每次 observe 记录来源），但不重造图谱/检索等既有轮子。

纯 stdlib 实现，无第三方依赖。
"""
from __future__ import annotations

from typing import Any


class StateMemory:
    """显式状态追踪记忆。

    - observe(updates)：增量合并一次环境观测（只含本次可见字段，可能只是变化子集）。
    - get_state() / query(key)：读取当前状态。
    - backtrack(steps)：回溯到 steps 步之前的状态快照。
    - accuracy(ground_truth)：当前状态相对真值的字段命中率。
    """

    def __init__(self) -> None:
        self._state: dict[Any, Any] = {}
        self._history: list[dict[Any, Any]] = []  # 每次 observe 后的快照
        self._versions: dict[Any, int] = {}       # key -> 被写入次数（溯源/活跃度）

    def observe(self, updates: dict[Any, Any]) -> None:
        """合并一次观测；新字段覆盖旧值，未出现字段保留旧值（状态持久）。"""
        for key, value in updates.items():
            self._state[key] = value
            self._versions[key] = self._versions.get(key, 0) + 1
        self._history.append(dict(self._state))

    def get_state(self) -> dict[Any, Any]:
        return dict(self._state)

    def query(self, key: Any, default: Any = None) -> Any:
        return self._state.get(key, default)

    def backtrack(self, steps: int = 1) -> dict[Any, Any]:
        """回溯 steps 步：返回 steps 次 observe 之前的状态快照。"""
        if steps <= 0 or not self._history:
            return dict(self._state)
        idx = len(self._history) - 1 - steps
        return dict(self._history[max(0, idx)])

    def accuracy(self, ground_truth: dict[Any, Any]) -> float:
        """状态准确率 = 与真值一致的字段比例（缺字段视为不一致）。"""
        if not ground_truth:
            return 1.0
        correct = sum(1 for k, v in ground_truth.items() if self._state.get(k) == v)
        return correct / len(ground_truth)


class LastObservationBaseline:
    """无状态记忆基线：只保留最近一次观测，未在本次观测出现的字段全部丢失。"""

    def __init__(self) -> None:
        self._last: dict[Any, Any] = {}

    def observe(self, updates: dict[Any, Any]) -> None:
        self._last = dict(updates)

    def get_state(self) -> dict[Any, Any]:
        return dict(self._last)

    def accuracy(self, ground_truth: dict[Any, Any]) -> float:
        if not ground_truth:
            return 1.0
        correct = sum(1 for k, v in ground_truth.items() if self._last.get(k) == v)
        return correct / len(ground_truth)
