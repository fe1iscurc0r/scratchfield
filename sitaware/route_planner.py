"""B-05 · 路径规划服务（卷132，避高风险）。

    GET /api/route?start_lng=&start_lat=&end_lng=&end_lat=&avoid_risk=true

后端 OSRM（self-hosted，`http://localhost:5000/route/v1/{profile}/`）。
**OSRM 不可用时降级为直线并明确标注** `source="fallback_line"` ——
宁可给出"这不是真实路径"的诚实结果，也不假装规划成功。

避风险的做法：对每条候选路线的**每一段**做「线段 vs 高风险事件外接框」求交
（Liang-Barsky，见 `coords.segment_intersects_bbox`）。只判端点是否在框内会漏掉
「路线横穿风险区」这一最主要场景，所以必须做线段级判定。

挑选规则：在候选中优先取「穿越风险事件数最少」的一条；并列时取距离最短的。
决策过程写进 `warnings`，让前端能解释"为什么给我绕了路"。
"""
from __future__ import annotations

import math
from typing import Any, Iterable, Sequence

from .coords import haversine_km, segment_intersects_bbox
from .models import Event, severity_at_least

__all__ = ["RoutePlanner", "OSRMProfile", "OSRM_UNAVAILABLE_HINT"]

OSRMProfile = str  # foot | bike | car

OSRM_UNAVAILABLE_HINT = (
    "OSRM 不可达，已降级为两点直线（非真实路网路径）。"
    "部署方式见 docs/sitaware-osrm-deploy.md。"
)

# 参与避让的最低严重度：low/medium 不绕路（否则地图会被迫到处绕行）
DEFAULT_AVOID_SEVERITY = "high"


class RoutePlanner:
    """路径规划。`client` 可注入（httpx.Client 或替身）。"""

    def __init__(self, client: Any = None,
                 base_url: str = "http://localhost:5000",
                 timeout: float = 12.0,
                 allow_network: bool = True) -> None:
        self._client = client
        self._owns_client = client is None
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.allow_network = bool(allow_network)
        self.last_error: str | None = None

    # ---- 基础设施 ----

    def _get_client(self) -> Any:
        if self._client is None:
            import httpx
            self._client = httpx.Client(timeout=self.timeout)
        return self._client

    def close(self) -> None:
        if self._client is not None and self._owns_client:
            try:
                self._client.close()
            except Exception:                               # noqa: BLE001
                pass
        self._client = None

    # ---- OSRM ----

    def fetch_osrm(self, start_lng: float, start_lat: float,
                   end_lng: float, end_lat: float,
                   profile: OSRMProfile = "foot",
                   alternatives: bool = True) -> dict[str, Any] | None:
        """调 OSRM，返回原始 JSON；不可达返回 None（并记 `last_error`）。"""
        if not self.allow_network:
            self.last_error = "network_disabled"
            return None
        # OSRM 坐标顺序是 lon,lat
        coords = f"{start_lng},{start_lat};{end_lng},{end_lat}"
        url = f"{self.base_url}/route/v1/{profile}/{coords}"
        params = {
            "overview": "full",
            "geometries": "geojson",
            "alternatives": "true" if alternatives else "false",
            "steps": "false",
        }
        try:
            resp = self._get_client().get(url, params=params, timeout=self.timeout)
            if getattr(resp, "status_code", 200) != 200:
                self.last_error = f"http_{getattr(resp, 'status_code', '?')}"
                return None
            data = resp.json() or {}
            if data.get("code") not in (None, "Ok"):
                self.last_error = str(data.get("code"))
                return None
            self.last_error = None
            return data
        except Exception as exc:                            # noqa: BLE001
            self.last_error = f"{type(exc).__name__}"
            return None

    @staticmethod
    def get_route_geometry(osrm_response: dict[str, Any]) -> dict[str, Any]:
        """OSRM 响应 → GeoJSON LineString（工单要求的接口名）。

        取 `routes[0].geometry`；若响应是 polyline 编码格式则无法直接转，
        抛 ValueError 让调用方显式处理（`geometries=geojson` 时不会有此情况）。
        """
        routes = (osrm_response or {}).get("routes") or []
        if not routes:
            raise ValueError("OSRM 响应中没有 routes")
        geom = routes[0].get("geometry")
        if geom is None:
            coords = routes[0].get("coordinates")
            if coords:
                return {"type": "LineString", "coordinates": coords}
            raise ValueError("OSRM 响应缺少 geometry（需请求 geometries=geojson）")
        if isinstance(geom, dict):
            return geom
        raise ValueError("geometry 为 polyline 编码，无法离线转换；请请求 geometries=geojson")

    # ---- 风险判定 ----

    @staticmethod
    def _risk_events(events: Iterable[Event] | None,
                     min_severity: str = DEFAULT_AVOID_SEVERITY) -> list[Event]:
        out = []
        for e in (events or []):
            if severity_at_least(e.severity.value, min_severity):
                out.append(e)
        return out

    @classmethod
    def _crossings(cls, coordinates: Sequence[Sequence[float]],
                   risky: Sequence[Event]) -> list[dict[str, Any]]:
        """路线穿越了哪些高风险事件（线段级判定）。"""
        hits: list[dict[str, Any]] = []
        for ev in risky:
            box = ev.bbox()
            for i in range(len(coordinates) - 1):
                p1 = (coordinates[i][0], coordinates[i][1])
                p2 = (coordinates[i + 1][0], coordinates[i + 1][1])
                if segment_intersects_bbox(p1, p2, box):
                    hits.append({
                        "event_id": ev.id,
                        "title": ev.title or ev.event_type.value,
                        "severity": ev.severity.value,
                        "segment_index": i,
                        "at": list(p1),
                    })
                    break                                       # 同一事件只记一次
        return hits

    @staticmethod
    def _fallback_route(start_lng: float, start_lat: float,
                        end_lng: float, end_lat: float,
                        points: int = 24) -> dict[str, Any]:
        """直线降级：等分插值 + 大圆距离/步行速度估时。"""
        n = max(2, int(points))
        coords = []
        for i in range(n):
            t = i / (n - 1)
            coords.append([round(start_lng + (end_lng - start_lng) * t, 6),
                           round(start_lat + (end_lat - start_lat) * t, 6)])
        dist_km = haversine_km(start_lng, start_lat, end_lng, end_lat)
        return {
            "geometry": {"type": "LineString", "coordinates": coords},
            "distance_m": round(dist_km * 1000, 1),
            "duration_s": round(dist_km / 5.0 * 3600, 1),        # 步行 5km/h
            "source": "fallback_line",
        }

    # ---- 主入口 ----

    def plan_route(self, start_lng: float, start_lat: float,
                   end_lng: float, end_lat: float,
                   avoid_events: Sequence[Event] | None = None,
                   avoid_risk: bool = True,
                   profile: OSRMProfile = "foot",
                   min_avoid_severity: str = DEFAULT_AVOID_SEVERITY,
                   with_alternatives: bool = True) -> dict[str, Any]:
        """起点+终点(+风险事件) → 推荐路线 + 替代路线 + 警告。

        `avoid_risk=False` 时不参与避让，但仍会报告穿越了哪些风险区（只报不改）。
        """
        warnings: list[str] = []
        risky = self._risk_events(avoid_events, min_avoid_severity) if avoid_risk else []

        raw = self.fetch_osrm(start_lng, start_lat, end_lng, end_lat,
                              profile=profile, alternatives=with_alternatives)
        candidates: list[dict[str, Any]] = []
        if raw:
            for r in (raw.get("routes") or []):
                geom = r.get("geometry")
                if not isinstance(geom, dict):
                    continue
                candidates.append({
                    "geometry": geom,
                    "distance_m": r.get("distance"),
                    "duration_s": r.get("duration"),
                    "source": "osrm",
                })
            if not candidates:
                warnings.append("OSRM 返回了响应但没有可用几何，已降级为直线。")
                candidates = [self._fallback_route(start_lng, start_lat, end_lng, end_lat)]
        else:
            warnings.append(OSRM_UNAVAILABLE_HINT
                            + (f"（原因：{self.last_error}）" if self.last_error else ""))
            candidates = [self._fallback_route(start_lng, start_lat, end_lng, end_lat)]

        # 逐候选算穿越
        for c in candidates:
            coords = (c["geometry"] or {}).get("coordinates") or []
            c["crossings"] = self._crossings(coords, risky) if coords else []

        # 推荐：穿越最少 → 距离最短
        ranked = sorted(candidates,
                        key=lambda c: (len(c["crossings"]),
                                       c["distance_m"] if c["distance_m"] is not None else 1e18))
        best = ranked[0]
        alternatives = [c for c in ranked[1:]]

        if risky and best["crossings"]:
            names = "、".join(sorted({h["title"] for h in best["crossings"]}))[:80]
            warnings.append(f"推荐路线仍穿越 {len(best['crossings'])} 个高风险区（{names}）；"
                            f"已无更优候选。")
        elif risky and ranked[0] is not candidates[0]:
            # 说明原始首选被换掉了
            skipped = len(candidates[0]["crossings"])
            warnings.append(f"已为你避开 {skipped} 个高风险区，改用替代路线。")

        return {
            "ok": True,
            "route": best,
            "alternatives": alternatives,
            "warnings": warnings,
            "avoided_risk": bool(avoid_risk and len(candidates) > 1 and candidates[0] is not best),
            "risky_event_count": len(risky),
            "profile": profile,
            "start": [start_lng, start_lat],
            "end": [end_lng, end_lat],
        }

    # ---- 汇总给前端 ----

    @staticmethod
    def to_frontend_payload(plan: dict[str, Any]) -> dict[str, Any]:
        """裁剪成前端 F-06 需要的形态：主路线 + 替代 + 风险段落。"""
        route = plan.get("route") or {}
        return {
            "ok": plan.get("ok", False),
            "primary": {
                "geometry": route.get("geometry"),
                "distance_m": route.get("distance_m"),
                "duration_s": route.get("duration_s"),
                "source": route.get("source"),
            },
            "alternatives": [
                {"geometry": a.get("geometry"), "distance_m": a.get("distance_m"),
                 "duration_s": a.get("duration_s"), "source": a.get("source")}
                for a in (plan.get("alternatives") or [])
            ],
            "risk_segments": route.get("crossings") or [],
            "warnings": plan.get("warnings") or [],
            "start": plan.get("start"),
            "end": plan.get("end"),
        }
