from __future__ import annotations

import logging
from typing import Any

import httpx

from system.config import get_server_port

logger = logging.getLogger(__name__)


async def emit_local_telemetry(
    event: str,
    props: dict[str, Any] | None = None,
    *,
    source: str = "agentserver",
    trace_id: str | None = None,
    session_id: str | None = None,
    agent_id: str | None = None,
) -> None:
    payload = {
        "event": event,
        "props": props or {},
        "source": source,
        "trace_id": trace_id,
        "session_id": session_id,
        "agent_id": agent_id,
    }
    url = f"http://127.0.0.1:{get_server_port('api_server')}/telemetry/track"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(3.0), trust_env=False) as client:
            await client.post(url, json=payload)
    except Exception as exc:
        logger.debug("[Telemetry] local emit failed: %s", exc)
