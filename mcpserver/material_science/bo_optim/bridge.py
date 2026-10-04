"""BO 寻优 MCP 桥 — BoOptimBridge（HOTEL 线，挂进 material_science）。

U-03（UNIFORM 总装线）：把 bo_optim 的 BOLoop 挂成 material_science 的 MCP 工具。
本桥只封装 loop/params 现有接口，不重写任何寻优逻辑；不引向量 DB。

工具（3 个）：
- recommend(k, strategy)：推荐下一实验点（数据不足自动退化为随机采样）
- record(recipe, metrics|failed|objective)：回填实测（与 pending 去重）
- get_params()：参数空间（连续范围/离散选项/约束）+ 当前观测/待测计数
"""
from __future__ import annotations

import logging
from typing import Any

from mcpserver.material_science.bo_optim.loop import BOLoop
from mcpserver.material_science.bo_optim.params import lignin_hydrothermal_space

logger = logging.getLogger(__name__)


class BoOptimBridge:
    """BO 寻优桥（进程内持有单个 BOLoop，供 record→recommend 多轮闭环）。"""

    def __init__(self, space=None, seed: int = 0):
        # 默认木质素水热参数空间（示例空间，真机接入前可替换）
        self._loop = BOLoop(space or lignin_hydrothermal_space(), seed=seed)

    # ---- 工具实现（封装，不重写）----

    def recommend(self, k: int = 1, strategy: str | None = None) -> dict[str, Any]:
        """推荐 k 个下一实验点（配方 dict 列表）。"""
        try:
            k = max(1, int(k))
        except (TypeError, ValueError):
            k = 1
        recipes = self._loop.recommend(k=k, strategy=strategy or None)
        return {"status": "ok", "count": len(recipes), "recipes": recipes,
                "observed": len(self._loop.points),
                "pending": len(self._loop.pending)}

    def record(self, recipe: dict | None = None,
               metrics: dict | None = None, *,
               failed: bool = False,
               objective: float | None = None) -> dict[str, Any]:
        """回填一次实测（或标记失败），供后续推荐消费。"""
        if not isinstance(recipe, dict) or not recipe:
            return {"status": "error", "error": "recipe 必须是非空对象"}
        self._loop.record(recipe, metrics, failed=bool(failed),
                          objective=objective)
        return {"status": "ok", "observed": len(self._loop.points),
                "pending": len(self._loop.pending)}

    def get_params(self) -> dict[str, Any]:
        """参数空间清单（与代码同源）+ 循环状态。"""
        space = self._loop.space
        return {"status": "ok",
                "continuous": {k: list(v) for k, v in space.continuous.items()},
                "categorical": {k: list(v) for k, v in space.categorical.items()},
                "constraints": list(space.constraints),
                "observed": len(self._loop.points),
                "pending": len(self._loop.pending)}


def register_bo_tools(agent) -> None:
    """往 MaterialScienceAgent 注入 bo_recommend / bo_record / bo_get_params。"""
    bridge = BoOptimBridge()  # 实例内共享一个 BOLoop，支持多轮闭环

    def _tool_recommend(params: dict[str, Any]) -> dict[str, Any]:
        return bridge.recommend(k=params.get("k", 1),
                                strategy=params.get("strategy"))

    def _tool_record(params: dict[str, Any]) -> dict[str, Any]:
        return bridge.record(params.get("recipe"),
                             metrics=params.get("metrics"),
                             failed=bool(params.get("failed", False)),
                             objective=params.get("objective"))

    def _tool_params(params: dict[str, Any]) -> dict[str, Any]:
        return bridge.get_params()

    agent.tools["bo_recommend"] = _tool_recommend
    agent.tools["bo_record"] = _tool_record
    agent.tools["bo_get_params"] = _tool_params
    logger.info("[MCP] bo_recommend/bo_record/bo_get_params 已注入 material_science agent")


__all__ = ["BoOptimBridge", "register_bo_tools"]
