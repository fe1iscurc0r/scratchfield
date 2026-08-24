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
