from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from apiserver.telemetry import get_telemetry_manager

router = APIRouter()


class TelemetryTrackRequest(BaseModel):
    event: str = Field(..., min_length=1, max_length=120)
    props: dict[str, Any] = Field(default_factory=dict)
    source: str = Field(default="frontend", max_length=60)
    trace_id: str | None = Field(default=None, max_length=120)
    session_id: str | None = Field(default=None, max_length=120)
    agent_id: str | None = Field(default=None, max_length=120)


@router.post("/telemetry/track")
async def track_telemetry(payload: TelemetryTrackRequest):
    manager = get_telemetry_manager()
    await manager.track(
        payload.event,
        payload.props,
        source=payload.source,
        trace_id=payload.trace_id,
        session_id=payload.session_id,
        agent_id=payload.agent_id,
    )
    return {"status": "accepted"}


@router.post("/telemetry/flush")
async def flush_telemetry():
    result = await get_telemetry_manager().flush_once(force=True)
    return {"status": "ok", "result": result}


@router.get("/telemetry/status")
async def telemetry_status():
    return {
        "status": "success",
        "telemetry": await get_telemetry_manager().get_status(),
    }


@router.get("/system/telemetry/summary")
async def telemetry_summary():
    """W120-04：关键指标仪表盘 —— 请求 / 工具 / 总线三类计数 + 失败率 + 最近错误 Top10（脱敏）。

    计数只存内存（重启清零）；总线部分取 W119-01 的 `get_bus().snapshot()`。
    """
    from apiserver.event_bus import get_bus
    from apiserver.telemetry import METRICS

    bus_snapshot = None
    try:
        bus_snapshot = get_bus().snapshot()
    except Exception:  # noqa: BLE001 - 总线不可用时降级为空
        bus_snapshot = None
    return {"status": "success", "summary": METRICS.snapshot(bus=bus_snapshot)}
