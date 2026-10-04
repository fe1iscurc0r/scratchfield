"""B-07 · FastAPI 服务（卷132 · REST + SSE）。

把后端各模块组装成可运行 HTTP 服务，供前端 F-01~F-08 调用：

    GET  /api/events             事件列表（bbox/类型/严重度/来源/时间窗过滤）→ FeatureCollection
    GET  /api/events/{id}        事件详情 → Feature
    POST /api/events             创建事件 → Feature（并 SSE 广播）
    POST /api/situation/summary  态势综合 → {summary, risk_level, counts, key_events}
    POST /api/situation/query    自然语言查询 → {answer, cited_events, map_action, llm_source}
    POST /api/geocode            地理编码（地址/Maidenhead）→ {ok, lng, lat, ...}
    GET  /api/route              路径规划（避高风险）→ {primary, alternatives, risk_segments}
    GET  /api/alerts             告警规则列表
    POST /api/alerts             创建告警规则
    DELETE /api/alerts/{id}      删除告警规则
    GET  /api/ham/stations       HAM 站点 → FeatureCollection
    GET  /api/metrics            核心指标
    GET  /api/events/stream      SSE 实时推送（event / alert / ping）

启动：``python -m sitaware.api_server``（默认 :18000，可用 SITAWARE_PORT 改）。
开发环境 CORS 放开给 Vite（:5173/:5174）以及任意源，便于本地联调。
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import random
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from .cache_store import AlertStore, CacheStore, to_unix
from .collectors import DemoCollector
from .collectors.seed import _SAMPLE, _SEVERITY_PROBS, _SEVERITY_WEIGHTS, CITY_ANCHORS
from .event_pipeline import EventPipeline
from .geocoder import GeoService
from .ham_processor import load_stations
from .llm_gateway import LLMGateway
from .models import (
    CST,
    AlertRule,
    Event,
    EventType,
    Severity,
    Source,
    Station,
    feature_collection,
)
from .route_planner import RoutePlanner
from .situation_engine import SituationEngine

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("sitaware.api")


# --------------------------------------------------------------------------- #
# 请求体
# --------------------------------------------------------------------------- #

class EventIn(BaseModel):
    source: Source
    event_type: EventType = EventType.CUSTOM
    lng: float
    lat: float
    severity: Severity = Severity.LOW
    title: str = ""
    description: str = ""
    confidence: float = 0.5
    tags: list[str] = Field(default_factory=list)
    coord_source: str = "wgs84"


class SummaryIn(BaseModel):
    time_window_hours: float = 6.0
    region: list[float] | None = None   # [w, s, e, n]


class QueryIn(BaseModel):
    text: str


class GeocodeIn(BaseModel):
    text: str


class AlertIn(BaseModel):
    name: str = ""
    bbox: list[float] | None = None
    center_lng: float | None = None
    center_lat: float | None = None
    radius_km: float | None = None
    event_types: list[EventType] = Field(default_factory=list)
    min_severity: Severity = Severity.MEDIUM
    enabled: bool = True


# --------------------------------------------------------------------------- #
# SSE 广播
# --------------------------------------------------------------------------- #

async def _broadcast(state: Any, payload: dict) -> None:
    dead = []
    for q in list(state.subscribers):
        try:
            q.put_nowait(payload)
        except Exception:  # noqa: BLE001
            dead.append(q)
    for q in dead:
        state.subscribers.discard(q)


async def _live_injector(state: Any) -> None:
    """演示用实时注入：周期性产生 1 条新事件并 SSE 广播（可关 SITAWARE_LIVE=0）。"""
    rng = random.Random()
    interval = int(os.environ.get("SITAWARE_LIVE_SEC", "20"))
    while True:
        await asyncio.sleep(interval)
        try:
            city = rng.choice(list(CITY_ANCHORS))
            clng, clat = CITY_ANCHORS[city]
            et = rng.choice(list(EventType))
            sev = rng.choices(_SEVERITY_WEIGHTS, weights=_SEVERITY_PROBS)[0]
            lng = round(clng + rng.uniform(-0.12, 0.12), 6)
            lat = round(clat + rng.uniform(-0.10, 0.10), 6)
            ev = Event(
                source=rng.choice(list(Source)), event_type=et, lng=lng, lat=lat,
                severity=sev, title=f"[{city}] 实时{rng.choice(_SAMPLE[et])}",
                reported_at=datetime.now(CST), author="live",
                tags=[city, et.value, sev.value],
            )
            res = state.pipeline.ingest([ev])
            if res.get("saved", 0) > 0:
                await _broadcast(state, {"type": "event", "action": "upsert",
                                         "feature": ev.to_feature()})
        except Exception as exc:  # noqa: BLE001
            logger.warning("live injector error: %s", exc)


# --------------------------------------------------------------------------- #
# 生命周期
# --------------------------------------------------------------------------- #

@asynccontextmanager
async def lifespan(app: FastAPI):
    db_path = os.environ.get("SITAWARE_DB",
                             str(Path(__file__).resolve().parent / "sitaware.db"))
    store = CacheStore(db_path)
    alerts = AlertStore(store)
    gateway = LLMGateway(allow_network=os.environ.get("SITAWARE_LLM", "0") == "1")
    geocoder = GeoService()
    planner = RoutePlanner()
    pipeline = EventPipeline(store)
    engine = SituationEngine(
        gateway=gateway,
        events_provider=lambda: store.load_events(limit=5000, include_expired=True),
    )

    app.state.store = store
    app.state.alerts = alerts
    app.state.gateway = gateway
    app.state.geocoder = geocoder
    app.state.planner = planner
    app.state.pipeline = pipeline
    app.state.engine = engine
    app.state.subscribers = set()

    # 离线种子：空库时灌入合成事件，保证前端联调有数据
    if store.count() == 0:
        res = pipeline.ingest(DemoCollector(seed=20260918, days=7).collect(limit=140))
        logger.info("seeded demo events: %s", res)

    # 默认告警规则：琶洲 2km 内 ≥ high 事件
    if not alerts.list():
        alerts.add(AlertRule(
            name="琶洲 2km 高危", center_lng=113.3768, center_lat=23.1029,
            radius_km=2.0, min_severity=Severity.HIGH,
            event_types=[EventType.ACCIDENT, EventType.HAZARD, EventType.WEATHER],
        ))

    task = None
    if os.environ.get("SITAWARE_LIVE", "1") != "0":
        task = asyncio.create_task(_live_injector(app.state))
    logger.info("sitaware API up (db=%s, events=%d)", db_path, store.count())
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
        store.close()


app = FastAPI(title="sitaware", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------- #
# 工具
# --------------------------------------------------------------------------- #

def _find_event(state: Any, event_id: str) -> Event | None:
    for e in state.store.load_events(limit=5000, include_expired=True):
        if e.id == event_id:
            return e
    return None


def _parse_bbox(bbox: str | None) -> tuple[float, float, float, float] | None:
    if not bbox:
        return None
    parts = [float(x) for x in bbox.split(",") if x != ""]
    return tuple(parts) if len(parts) == 4 else None


# --------------------------------------------------------------------------- #
# 事件
# --------------------------------------------------------------------------- #

@app.get("/api/events")
async def list_events(request: Request, bbox: str | None = None,
                      event_type: str | None = None, severity: str | None = None,
                      source: str | None = None, date_from: str | None = None,
                      date_to: str | None = None, limit: int = 2000):
    state = request.app.state
    evs = state.store.load_events(bbox=_parse_bbox(bbox), source=source,
                                  limit=limit, include_expired=True)
    if event_type:
        evs = [e for e in evs if e.event_type.value == event_type]
    if severity:
        evs = [e for e in evs if e.severity.value == severity]
    if date_from or date_to:
        lo = to_unix(date_from) if date_from else None
        hi = to_unix(date_to) if date_to else None
        evs = [e for e in evs
               if (lo is None or e.reported_at.timestamp() >= lo)
               and (hi is None or e.reported_at.timestamp() <= hi)]
    return feature_collection(evs)


# --------------------------------------------------------------------------- #
# SSE（必须先于 /api/events/{event_id} 注册，否则 "stream" 会被当成事件 id 匹配）
# --------------------------------------------------------------------------- #

@app.get("/api/events/stream")
async def events_stream(request: Request):
    q: asyncio.Queue = asyncio.Queue()
    request.app.state.subscribers.add(q)

    async def gen():
        try:
            yield {"event": "ready", "data": json.dumps({"type": "ready"}, ensure_ascii=False)}
            while True:
                if await request.is_disconnected():
                    break
                try:
                    item = await asyncio.wait_for(q.get(), timeout=25)
                    yield {"event": item.get("type", "message"),
                           "data": json.dumps(item, ensure_ascii=False, default=str)}
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": "{}"}
        finally:
            request.app.state.subscribers.discard(q)

    return EventSourceResponse(gen())


@app.get("/api/events/{event_id}")
async def get_event(request: Request, event_id: str):
    ev = _find_event(request.app.state, event_id)
    if ev is None:
        raise HTTPException(status_code=404, detail="event_not_found")
    return ev.to_feature()


@app.post("/api/events")
async def create_event(request: Request, body: EventIn):
    ev = Event(**body.model_dump())
    res = request.app.state.pipeline.ingest([ev])
    if res.get("saved", 0) == 0:
        raise HTTPException(status_code=400, detail="event_rejected")
    await _broadcast(request.app.state, {"type": "event", "action": "upsert",
                                         "feature": ev.to_feature()})
    return ev.to_feature()


# --------------------------------------------------------------------------- #
# 态势
# --------------------------------------------------------------------------- #

@app.post("/api/situation/summary")
async def situation_summary(request: Request, body: SummaryIn):
    region = tuple(body.region) if body.region else None
    return request.app.state.engine.summarize_events(
        time_window_hours=body.time_window_hours, region=region)


@app.post("/api/situation/query")
async def situation_query(request: Request, body: QueryIn):
    return request.app.state.engine.answer_query(body.text, geocoder=request.app.state.geocoder)


@app.post("/api/geocode")
async def geocode(request: Request, body: GeocodeIn):
    return request.app.state.geocoder.geocode(body.text)


# --------------------------------------------------------------------------- #
# 路径规划
# --------------------------------------------------------------------------- #

@app.get("/api/route")
async def route(request: Request, start_lng: float = 113.26, start_lat: float = 23.13,
                end_lng: float = 113.38, end_lat: float = 23.10,
                avoid_risk: bool = True, profile: str = "foot"):
    state = request.app.state
    events = state.store.load_events(limit=5000, include_expired=False)
    plan = state.planner.plan_route(
        start_lng, start_lat, end_lng, end_lat,
        avoid_events=events, avoid_risk=avoid_risk, profile=profile,
    )
    return RoutePlanner.to_frontend_payload(plan)


# --------------------------------------------------------------------------- #
# 告警
# --------------------------------------------------------------------------- #

@app.get("/api/alerts")
async def list_alerts(request: Request):
    return [r.model_dump(mode="json") for r in request.app.state.alerts.list()]


@app.post("/api/alerts")
async def create_alert(request: Request, body: AlertIn):
    rule = AlertRule(**body.model_dump())
    request.app.state.alerts.add(rule)
    return rule.model_dump(mode="json")


@app.delete("/api/alerts/{alert_id}")
async def delete_alert(request: Request, alert_id: str):
    ok = request.app.state.alerts.delete(alert_id)
    if not ok:
        raise HTTPException(status_code=404, detail="alert_not_found")
    return {"ok": True, "id": alert_id}


# --------------------------------------------------------------------------- #
# HAM / 指标 / 健康
# --------------------------------------------------------------------------- #

@app.get("/api/ham/stations")
async def ham_stations():
    stations: list[Station] = load_stations()
    return {
        "type": "FeatureCollection",
        "features": [s.to_feature() for s in stations if s.lng is not None and s.lat is not None],
    }


@app.get("/api/metrics")
async def metrics(request: Request):
    return request.app.state.engine.metrics()


@app.get("/api/health")
async def health(request: Request):
    return {"ok": True, "events": request.app.state.store.count(),
            "subscribers": len(request.app.state.subscribers)}


def main() -> None:  # pragma: no cover
    import uvicorn

    port = int(os.environ.get("SITAWARE_PORT", "18000"))
    uvicorn.run("sitaware.api_server:app", host="0.0.0.0", port=port,
                reload=False, log_level="info")


if __name__ == "__main__":  # pragma: no cover
    main()
