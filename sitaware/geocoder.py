"""B-01 · 地理编码服务（卷132）。

三种输入 → 统一 WGS84 输出：

1. **中文/英文地址** → `geocode_address()`
   优先 Nominatim（OSM 免费，返回即 WGS84），失败或离线时退到本地候选表。
2. **Maidenhead 网格** → `geocode_maidenhead()`（4/6/8/10 位，复用 `coords`）
3. **坐标反查** → `reverse_geocode()`

**坐标系纪律**：Nominatim 返回 WGS84，直接采信；本地表也按 WGS84 存。
若调用方给的是 GCJ-02/BD-09（高德/百度/腾讯来源），必须先过 `coords.to_wgs84()` 校正，
本模块的 `geocode(..., coord_source=)` 参数就是这个入口。

**为什么不用 `gcoord`**：它是 JS 库，PyPI 无同名 Python 包（实测 404）。
坐标校正已由 `sitaware.coords` 自研实现。

网络可注入：`GeoService(client=...)` 接受任何带 `.get(url, params=, timeout=)`
的对象（httpx.Client 或其替身），测试用替身即可完全离线。
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from .coords import VALID_PRECISIONS, maidenhead_to_lonlat, to_wgs84

__all__ = ["GeoService", "OFFLINE_PLACES", "looks_like_maidenhead", "nominatim_enabled"]

NOMINATIM_SEARCH = "https://nominatim.openstreetmap.org/search"
NOMINATIM_REVERSE = "https://nominatim.openstreetmap.org/reverse"

# Nominatim 使用条款要求可识别的 User-Agent
USER_AGENT = "sitaware/0.1 (situational-awareness backend; contact: local)"

# 离线候选表（WGS84）。仅作无网络时的兜底，不追求覆盖率。
OFFLINE_PLACES: dict[str, dict[str, Any]] = {
    "广州市": {"lng": 113.264434, "lat": 23.129162, "district": "越秀区", "province": "广东省", "country": "中国"},
    "广州": {"lng": 113.264434, "lat": 23.129162, "district": "越秀区", "province": "广东省", "country": "中国"},
    "广州市天河区": {"lng": 113.361200, "lat": 23.124700, "district": "天河区", "province": "广东省", "country": "中国"},
    "天河区": {"lng": 113.361200, "lat": 23.124700, "district": "天河区", "province": "广东省", "country": "中国"},
    "广州天河": {"lng": 113.361200, "lat": 23.124700, "district": "天河区", "province": "广东省", "country": "中国"},
    "琶洲": {"lng": 113.376800, "lat": 23.102900, "district": "海珠区", "province": "广东省", "country": "中国"},
    "广州市海珠区": {"lng": 113.317000, "lat": 23.083800, "district": "海珠区", "province": "广东省", "country": "中国"},
    "海珠区": {"lng": 113.317000, "lat": 23.083800, "district": "海珠区", "province": "广东省", "country": "中国"},
    "越秀区": {"lng": 113.266000, "lat": 23.128900, "district": "越秀区", "province": "广东省", "country": "中国"},
    "白云区": {"lng": 113.273000, "lat": 23.157300, "district": "白云区", "province": "广东省", "country": "中国"},
    "番禺区": {"lng": 113.384000, "lat": 22.938500, "district": "番禺区", "province": "广东省", "country": "中国"},
    "深圳市": {"lng": 114.057868, "lat": 22.543099, "district": "福田区", "province": "广东省", "country": "中国"},
    "北京市": {"lng": 116.407526, "lat": 39.904030, "district": "东城区", "province": "北京市", "country": "中国"},
    "上海市": {"lng": 121.473701, "lat": 31.230416, "district": "黄浦区", "province": "上海市", "country": "中国"},
    "guangzhou": {"lng": 113.264434, "lat": 23.129162, "district": "越秀区", "province": "广东省", "country": "中国"},
}

# Maidenhead 形态：分组交替（字母组 / 数字组），长 2/4/6/8/10
_MH_SHAPE = re.compile(r"^[A-Ra-r]{2}(?:[0-9]{2}(?:[A-Xa-x]{2}(?:[0-9]{2}(?:[A-Xa-x]{2})?)?)?)?$")


def looks_like_maidenhead(text: str) -> bool:
    """判断文本是否像 Maidenhead 网格（而非地址）。"""
    t = str(text or "").strip().replace(" ", "")
    if len(t) not in VALID_PRECISIONS:
        return False
    return bool(_MH_SHAPE.match(t))


def nominatim_enabled() -> bool:
    """`SITAWARE_NOMINATIM=0` 可全局关掉外呼（离线/测试环境用）。"""
    return os.environ.get("SITAWARE_NOMINATIM", "1") != "0"


class GeoService:
    """地理编码服务。`client` 可注入（httpx.Client 或其替身），便于离线测试。"""

    def __init__(self, client: Any = None, offline_path: str | Path | None = None,
                 timeout: float = 6.0, allow_network: bool | None = None) -> None:
        self._client = client
        self._owns_client = client is None
        self.timeout = timeout
        self.allow_network = nominatim_enabled() if allow_network is None else bool(allow_network)
        self._offline: dict[str, dict[str, Any]] = dict(OFFLINE_PLACES)
        if offline_path is not None:
            self._load_offline(offline_path)

    # ---- 基础设施 ----

    def _load_offline(self, path: str | Path) -> None:
        """加载扩展离线表（JSON: {名称: {lng, lat, district, province, country}}）。"""
        p = Path(path)
        if not p.exists():
            return
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            for key, val in data.items():
                if isinstance(val, dict) and "lng" in val and "lat" in val:
                    self._offline[str(key)] = val

    def _get_client(self) -> Any:
        if self._client is None:
            import httpx
            self._client = httpx.Client(timeout=self.timeout, headers={"User-Agent": USER_AGENT})
        return self._client

    def close(self) -> None:
        if self._client is not None and self._owns_client:
            try:
                self._client.close()
            except Exception:                               # noqa: BLE001
                pass
        self._client = None

    def _get_json(self, url: str, params: dict[str, Any]) -> Any:
        """GET 并解析 JSON。任何网络/解析异常都返回 None（由调用方走降级）。"""
        if not self.allow_network:
            return None
        try:
            resp = self._get_client().get(url, params=params, timeout=self.timeout)
            if getattr(resp, "status_code", 200) != 200:
                return None
            return resp.json()
        except Exception:                                   # noqa: BLE001
            return None

    # ---- 地址 → 坐标 ----

    def _offline_lookup(self, text: str) -> dict[str, Any] | None:
        """本地表精确匹配 → 去掉"市/区/省"后缀再试 → 子串包含匹配。"""
        key = text.strip()
        if key in self._offline:
            return dict(self._offline[key])
        for suffix in ("市", "区", "省", "县", "镇", "街道"):
            if key.endswith(suffix) and key[:-1] in self._offline:
                return dict(self._offline[key[:-1]])
        # 子串：取最长命中，避免「广州」抢走「广州天河」
        hits = [(k, v) for k, v in self._offline.items() if k and k in key]
        if hits:
            k, v = max(hits, key=lambda kv: len(kv[0]))
            return dict(v)
        return None

    def geocode_address(self, text: str, coord_source: str = "wgs84",
                        limit: int = 1) -> dict[str, Any]:
        """地址 → `{ok, lng, lat, district, province, country, source, ...}`。

        坐标一律 WGS84。`coord_source` 描述**输入若含坐标**时的来源坐标系
        （地址文本无坐标时该参数无作用，保留以统一签名）。
        """
        text = str(text or "").strip()
        if not text:
            return {"ok": False, "error": "empty_query", "lng": None, "lat": None}

        data = self._get_json(NOMINATIM_SEARCH, {
            "q": text, "format": "jsonv2", "limit": max(1, min(limit, 10)),
            "addressdetails": 1, "accept-language": "zh-CN,zh,en",
        })
        if data:
            item = data[0]
            addr = item.get("address") or {}
            lng = float(item["lon"])
            lat = float(item["lat"])
            return {
                "ok": True, "lng": lng, "lat": lat,
                "district": addr.get("city_district") or addr.get("suburb") or addr.get("county") or "",
                "province": addr.get("state") or addr.get("province") or "",
                "country": addr.get("country") or "",
                "display_name": item.get("display_name") or "",
                "source": "nominatim",
                "query": text,
            }

        local = self._offline_lookup(text)
        if local is not None:
            lng, lat = to_wgs84(float(local["lng"]), float(local["lat"]), coord_source)
            return {
                "ok": True, "lng": lng, "lat": lat,
                "district": local.get("district", ""),
                "province": local.get("province", ""),
                "country": local.get("country", ""),
                "display_name": text,
                "source": "offline",
                "query": text,
            }
        return {"ok": False, "error": "not_found", "lng": None, "lat": None, "query": text}

    # ---- Maidenhead → 坐标 ----

    def geocode_maidenhead(self, grid: str) -> dict[str, Any]:
        """Maidenhead → 格子中心坐标 + 该精度的实际格子尺寸。

        注意：返回的是**格子中心**；可达到的定位精度就是格子本身的量级，
        调用方不应把它当精确点用。`cell_m` 字段给出真实尺寸以免误判。
        """
        from .coords import maidenhead_cell_size_m

        raw = str(grid or "").strip()
        if not raw:
            return {"ok": False, "error": "empty_grid", "lng": None, "lat": None}
        try:
            lng, lat = maidenhead_to_lonlat(raw)
        except ValueError as exc:
            return {"ok": False, "error": "bad_grid", "message": str(exc),
                    "lng": None, "lat": None, "grid": raw}
        cell = maidenhead_cell_size_m(raw)
        return {"ok": True, "lng": lng, "lat": lat, "precision": len(raw.upper()),
                "grid": raw.upper(), "cell_m": [round(cell[0], 1), round(cell[1], 1)],
                "source": "maidenhead", "coord_source": "wgs84"}

    # ---- 坐标 → 地址 ----

    def reverse_geocode(self, lng: float, lat: float,
                        coord_source: str = "wgs84") -> dict[str, Any]:
        """坐标 → 地址字符串。`coord_source` 描述入参坐标系，内部统一转 WGS84。"""
        wlng, wlat = to_wgs84(float(lng), float(lat), coord_source)
        data = self._get_json(NOMINATIM_REVERSE, {
            "lat": wlat, "lon": wlng, "format": "jsonv2",
            "addressdetails": 1, "accept-language": "zh-CN,zh,en",
        })
        if data:
            return {"ok": True, "address": data.get("display_name") or "",
                    "lng": wlng, "lat": wlat, "source": "nominatim"}
        # 离线兜底：最近候选点
        if self._offline:
            best_key, best_d = None, None
            from .coords import haversine_km
            for key, val in self._offline.items():
                d = haversine_km(wlng, wlat, float(val["lng"]), float(val["lat"]))
                if best_d is None or d < best_d:
                    best_key, best_d = key, d
            if best_key is not None and best_d is not None and best_d <= 50.0:
                return {"ok": True, "address": best_key, "lng": wlng, "lat": wlat,
                        "source": "offline", "distance_km": round(best_d, 3)}
        return {"ok": False, "error": "not_found", "lng": wlng, "lat": wlat}

    # ---- 统一入口 ----

    def geocode(self, text: str, coord_source: str = "wgs84") -> dict[str, Any]:
        """自动判别 Maidenhead / 地址，返回统一结果。"""
        if looks_like_maidenhead(text):
            out = self.geocode_maidenhead(text)
            out["query"] = text
            return out
        return self.geocode_address(text, coord_source=coord_source)


class _StubResponse:
    """测试用极简响应替身（避免测试依赖 httpx）。"""

    def __init__(self, payload: Any, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> Any:
        return self._payload


class StubClient:
    """测试用替身客户端：按 url 关键字分发预设响应；未命中视为 404。

    用法：
        StubClient({"/search": [{...}], "/reverse": {...}})
    """

    def __init__(self, routes: dict[str, Any] | None = None) -> None:
        self.routes = routes or {}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get(self, url: str, params: dict[str, Any] | None = None,
            timeout: float | None = None) -> _StubResponse:
        self.calls.append((url, dict(params or {})))
        for marker, payload in self.routes.items():
            if marker in url:
                if isinstance(payload, tuple):
                    return _StubResponse(payload[0], payload[1])
                return _StubResponse(payload)
        return _StubResponse(None, 404)

    def close(self) -> None:
        pass
