"""态势感知后端（卷132 · B-01..B-08）。

> 工单原名目录为 `gevent/`，本实现改名 `sitaware/`。原因见
> `docs/sitaware-工单缺陷与偏离说明-2026-09-18.md` 第 1 条：
> 顶层包名 `gevent` 会遮蔽同工单声明的 pip 依赖 `gevent`（greenlet 协程库），
> 是自造的导入冲突；且该依赖在本架构中根本不需要（FastAPI/httpx 已覆盖异步 HTTP）。

模块地图（与工单 B-xx 的对应）：

    models.py            统一的时空事件模型（Pydantic + GeoJSON 互转）
    coords.py            坐标系：WGS84 / GCJ02 / BD09 互转 + Maidenhead 网格
    geocoder.py          B-01 地理编码服务
    collectors/          B-02 多源采集（news / ham / weather / user）
    event_pipeline.py    B-02 采集管道（采集→规范化→去重→落库）
    llm_gateway.py       B-03 LLM 脱敏路由网关（Ollama 本地 / MiniMax 云端）
    situation_engine.py  B-04 态势综合引擎（摘要 / 异常检测 / 影响范围）
    route_planner.py     B-05 路径规划（OSRM，避高风险）
    cache_store.py       B-06 SQLite 缓存 + 同步队列
    offline_manager.py   B-06 在线检测 + 瓦片预取
    ham_processor.py     B-08 HAM 无线电接入（ADIF / APRS / Maidenhead）
    api_server.py        B-07 FastAPI（REST + SSE）

坐标约定：**内部存储与对外接口一律 WGS84**，只在入站解析时按来源声明转换。
"""
from __future__ import annotations

from .coords import (
    bd09_to_wgs84,
    gcj02_to_wgs84,
    lonlat_to_maidenhead,
    maidenhead_to_lonlat,
    to_wgs84,
    wgs84_to_bd09,
    wgs84_to_gcj02,
)
from .models import (
    AlertRule,
    CoordSource,
    Event,
    EventType,
    Severity,
    Source,
    Station,
    new_event_id,
)

__all__ = [
    # models
    "Event", "EventType", "Severity", "Source", "CoordSource", "Station",
    "AlertRule", "new_event_id",
    # coords
    "to_wgs84", "wgs84_to_gcj02", "gcj02_to_wgs84",
    "wgs84_to_bd09", "bd09_to_wgs84",
    "maidenhead_to_lonlat", "lonlat_to_maidenhead",
]

__version__ = "0.1.0"
