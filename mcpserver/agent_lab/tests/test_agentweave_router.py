"""A52 AgentWeave 工具路由测试：召回超随机基线 / 域路由 / 成本比。"""
from __future__ import annotations

from mcpserver.agent_lab.prototypes.agentweave_router import (
    AgentWeaveRouter,
    evaluate,
    make_toolset,
)


def test_recall_far_above_random():
    r = evaluate(seed=2, n_queries=80, k=5)
    assert r["recall_at_k"] >= 0.8
    assert r["recall_at_k"] > r["random_baseline"] * 10


def test_domain_routing_accurate():
    r = evaluate(seed=2, n_queries=80, k=5)
    assert r["domain_accuracy"] >= 0.9


def test_routing_cost_small():
    r = evaluate(seed=2, per_domain=25, k=5)
    assert r["cost_ratio"] == 5 / 200  # 只带 2.5% 工具进入推理阶段


def test_router_returns_k_names():
    tools = make_toolset(per_domain=10, seed=1)
    router = AgentWeaveRouter(tools)
    names, dom = router.route("会议 日程 提醒", k=3)
    assert len(names) == 3 and dom == "日历"
