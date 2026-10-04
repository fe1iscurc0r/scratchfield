"""tools_health.py — 工具调用画像与熔断状态端点（卷189-B）。

前端「工具健康」只读页消费。数据源 = ``mcpserver.telemetry``
（SQLite ``tool_calls`` 表 + 进程内熔断器）。

- ``GET /tools/stats?window=7d``   按工具聚合：调用数 / P50 / P95 / 失败率 / 最近错误
- ``GET /tools/circuit``           非 closed 的熔断工具（样本/失败率/冷却截止）

说明：画像与调用可能落在不同进程（apiserver 读、mcp_server 写），两者共用同一
SQLite 文件（WAL 模式允许多进程并发读写），故本端点直接读库即可，无需转发。
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter

router = APIRouter(tags=["tools"])


@router.get("/tools/stats")
async def tools_stats(window: str = "7d") -> dict[str, Any]:
    """调用画像：按工具聚合 调用数/P50/P95/失败率/最近错误。"""
    from mcpserver.telemetry import get_recorder
    rec = get_recorder()
    try:
        rec.flush()          # 让刚入队的数据可见
    except Exception:
        pass
    return {"window": window, "stats": rec.stats(window)}


@router.get("/tools/circuit")
async def tools_circuit() -> dict[str, Any]:
    """熔断状态：非 closed 的工具及窗口样本/失败率/冷却截止。"""
    from mcpserver.telemetry import get_breaker
    return {"circuits": get_breaker().states()}
