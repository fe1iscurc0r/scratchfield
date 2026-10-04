"""W119-01：总线调试 dump 端点（可观测层对外出口）。

- GET /debug/dump/bus              → 统计快照（总量 / 各 mode / 各 topic / 错误 / veto）
- GET /debug/dump/bus/events?limit → 最近事件环形缓冲（新→旧，含 topic/mode/timestamp/error 摘要）

鉴权：复用 lumo_proxy.require_proxy_token（LUMO_PROXY_TOKEN），与 /api/lumo/event 同源。
只读、无副作用；数据全部来自进程内总线统计，不落盘（落盘见 W119-02 event_store）。

文件名说明：不叫 debug_*.py——.gitignore 用该模式保护本地调试脚本，路由模块改名避免撞规则。
"""
from __future__ import annotations

import logging
from collections import deque

from fastapi import APIRouter, Depends, Query

from apiserver.event_bus import get_bus
from apiserver.routes.lumo_proxy import require_proxy_token

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/debug/dump/bus")
async def dump_bus_stats(_: dict = Depends(require_proxy_token)):
    """总线统计快照。"""
    return {"status": "success", "bus": get_bus().snapshot()}


@router.get("/debug/dump/bus/events")
async def dump_bus_events(
    limit: int = Query(default=50, ge=1, le=200),
    _: dict = Depends(require_proxy_token),
):
    """最近事件（新→旧）。limit 上限 = 环形缓冲容量（默认 200）。"""
    events = get_bus().recent_events(limit)
    return {"status": "success", "count": len(events), "events": events}


@router.get("/debug/dump/bus/history")
async def dump_bus_history(
    topic: str | None = Query(default=None, max_length=200),
    since: float | None = Query(default=None, description="起始 unix 时间戳（含之后）"),
    limit: int = Query(default=50, ge=1, le=500),
    _: dict = Depends(require_proxy_token),
):
    """事件历史回放（W119-02，append-only JSONL）。返回最近 limit 条（新→旧）。

    用 deque(maxlen=limit) 做滑动窗口：流式扫全量但内存只保留尾部 limit 条。
    """
    from apiserver.event_bus.event_store import get_event_store

    store = get_event_store()
    window: deque = deque(maxlen=limit)
    scanned = 0
    for item in store.replay(topic=topic, since_ts=since):
        window.append(item)
        scanned += 1
    events = list(reversed(window))
    return {
        "status": "success",
        "count": len(events),
        "scanned": scanned,
        "store": store.stats(),
        "events": events,
    }


@router.get("/debug/dump/surface")
async def dump_surface_view(
    surface: str = Query(default="model", description="model / transcript / replay / telemetry / router"),
    session_id: str = Query(default="", max_length=200),
    limit: int = Query(default=50, ge=1, le=500),
    _: dict = Depends(require_proxy_token),
):
    """W124-04/W125-04：事件溯源 surface 投影（含 router 决策面）。"""
    from apiserver.event_bus.surface import dump_surface, surface_stats

    payload = dump_surface(surface, session_id=session_id, limit=limit)
    body = {"status": "success", **payload, "store": surface_stats()}
    if surface == "router" and session_id:
        # 顺带把库里的权威记录也带上（内存窗口会被轮转挤掉，库里是全量）
        try:
            from apiserver.llm_router import decisions_for_session

            body["decisions"] = decisions_for_session(session_id, limit=limit)
        except Exception as e:  # noqa: BLE001 - 查询失败不影响接口
            body["decisions_error"] = str(e)
    return body


@router.get("/debug/trace/{trace_id}")
async def get_trace_by_id(trace_id: str, _: dict = Depends(require_proxy_token)):
    """W120-01：按 trace_id 查全链路 span 链（活动上下文 → 近期缓存 → 落盘回放）。"""
    from apiserver.event_bus.trace import get_trace

    record = get_trace(trace_id)
    if record is None:
        return {
            "status": "not_found",
            "trace_id": trace_id,
            "message": "trace 未持久化或已过保留期",
        }
    return {"status": "success", "trace": record}
