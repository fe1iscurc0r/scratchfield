"""统一的时空事件模型（卷132）。

设计要点：

1. **单一坐标契约**：模型里 `lng`/`lat` **永远**是 WGS84。`coord_source` 只记录
   *入站时* 声明的是什么坐标系，用于审计与回溯，不参与运行期计算。
   工单数据模型把 `coord_source` 写成 `"gcoord|wgs84|bd09"`，其中 `gcoord` 是
   JavaScript 库名而非坐标系 —— 已改成 `gcj02|wgs84|bd09`（见偏离说明第 9 条）。

2. **事件 id 时间有序**：用自实现的 UUIDv7（48 位毫秒时间戳 + 随机）。
   Python 3.12/3.13 标准库没有 `uuid7`，而时间有序 id 对事件流按时间范围扫描
   是实打实的收益（B-06 的 `load_events(bbox, time_range)` 直接受益）。

3. **GeoJSON 双向无损**：`to_feature()` / `from_feature()` 成对，保证落库、导出、
   SSE 推送、接口返回走的是同一套序列化，不会出现"库里有、接口没有"的字段漂移。
"""
from __future__ import annotations

import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator

# 广州默认时区（+08:00）；对外输出用 ISO8601 带偏移
CST = timezone(timedelta(hours=8))

# 默认事件存活时长（秒）—— 工单数据模型"默认 24h，可配置"
DEFAULT_TTL_SECONDS = 24 * 3600


# --------------------------------------------------------------------------- #
# UUIDv7（时间有序）
# --------------------------------------------------------------------------- #

def new_event_id(now: float | None = None) -> str:
    """生成 UUIDv7：48 位毫秒时间戳 + 版本/变体位 + 74 位随机。

    标准库（3.12/3.13）无 `uuid.uuid7`，故自实现。同一毫秒内随机位保证唯一；
    跨毫秒则字典序即时间序 —— 这是事件流排序与范围扫描依赖的性质。
    """
    ts_ms = int((time.time() if now is None else now) * 1000) & 0xFFFFFFFFFFFF
    rand = secrets.token_bytes(10)                      # 80 位随机
    b = bytearray(16)
    b[0:6] = ts_ms.to_bytes(6, "big")
    b[6] = 0x70 | (rand[0] & 0x0F)                      # version = 7
    b[7] = rand[1]
    b[8] = 0x80 | (rand[2] & 0x3F)                      # variant = RFC4122
    b[9:16] = rand[3:10]
    h = b.hex()
    return f"{h[0:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def id_timestamp(event_id: str) -> float | None:
    """从 UUIDv7 反解毫秒时间戳（Unix 秒）；非 UUIDv7 返回 None。"""
    try:
        hexstr = event_id.replace("-", "")
        if len(hexstr) != 32:
            return None
        ms = int(hexstr[0:12], 16)
        return ms / 1000.0
    except (ValueError, AttributeError):
        return None


# --------------------------------------------------------------------------- #
# 枚举
# --------------------------------------------------------------------------- #

class Source(str, Enum):
    """数据来源。工单数据模型取值：news|rss|ham_radio|sensor|user。"""
    NEWS = "news"
    RSS = "rss"
    HAM_RADIO = "ham_radio"
    SENSOR = "sensor"
    USER = "user"
    WEATHER = "weather"          # B-02 气象源（工单正文有，枚举补上）


class EventType(str, Enum):
    PROTEST = "protest"
    ACCIDENT = "accident"
    WEATHER = "weather"
    SIGNAL = "signal"
    HAZARD = "hazard"
    CUSTOM = "custom"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class CoordSource(str, Enum):
    """入站坐标系声明。**注意取值是坐标系名，不是库名。**

    工单原文写的 `"gcoord|wgs84|bd09"` 里 `gcoord` 是 JS 转坐标库的名字，
    不是一个坐标系 —— 已更正为 `gcj02`（国测局加密坐标，即 GCJ-02/Mars）。
    """
    WGS84 = "wgs84"
    GCJ02 = "gcj02"
    BD09 = "bd09"


# 严重度排序权重（异常检测与告警筛选用）
SEVERITY_RANK: dict[str, int] = {
    Severity.LOW.value: 0,
    Severity.MEDIUM.value: 1,
    Severity.HIGH.value: 2,
    Severity.CRITICAL.value: 3,
}


def severity_at_least(value: str, floor: str) -> bool:
    """`value` 的严重度是否 ≥ `floor`；未知取值按最低处理（不放大风险）。"""
    return SEVERITY_RANK.get(str(value), 0) >= SEVERITY_RANK.get(str(floor), 0)


# --------------------------------------------------------------------------- #
# 事件模型
# --------------------------------------------------------------------------- #

class Event(BaseModel):
    """一条感知事件。坐标恒为 WGS84。"""

    id: str = Field(default_factory=new_event_id, description="UUIDv7（时间有序）")
    source: Source
    event_type: EventType = EventType.CUSTOM
    lng: float = Field(..., ge=-180.0, le=180.0, description="经度（WGS84）")
    lat: float = Field(..., ge=-90.0, le=90.0, description="纬度（WGS84）")
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    severity: Severity = Severity.LOW
    title: str = ""
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    reported_at: datetime = Field(default_factory=lambda: datetime.now(CST))
    expires_at: datetime | None = None
    raw_refs: list[str] = Field(default_factory=list)
    author: str = "system"
    coord_source: CoordSource = CoordSource.WGS84
    bounding_box_km: float = Field(default=1.0, ge=0.0)
    is_verified: bool = False
    llm_summary: str | None = None

    @field_validator("reported_at", "expires_at")
    @classmethod
    def _ensure_aware(cls, v: datetime | None) -> datetime | None:
        """朴素时间一律按 +08:00 解释 —— 避免 later 与 aware 比较时抛 TypeError。"""
        if v is not None and v.tzinfo is None:
            return v.replace(tzinfo=CST)
        return v

    def model_post_init(self, _ctx: Any) -> None:      # noqa: D105
        if self.expires_at is None:
            self.expires_at = self.reported_at + timedelta(seconds=DEFAULT_TTL_SECONDS)

    # ---- 派生 ----

    @property
    def is_expired(self) -> bool:
        return self.expires_at is not None and datetime.now(CST) >= self.expires_at

    @property
    def severity_rank(self) -> int:
        return SEVERITY_RANK.get(self.severity.value, 0)

    def bbox(self) -> tuple[float, float, float, float]:
        """事件外接框 (west, south, east, north)，用 `bounding_box_km` 近似。

        小尺度下按等距圆柱近似：1° 纬 ≈ 110.574km，1° 经 ≈ 111.320·cos(φ) km。
        仅用于粗筛与地图渲染，不用于精确几何运算。
        """
        import math

        dlat = self.bounding_box_km / 110.574
        cosf = max(1e-6, math.cos(math.radians(self.lat)))
        dlon = self.bounding_box_km / (111.320 * cosf)
        return (self.lng - dlon, self.lat - dlat, self.lng + dlon, self.lat + dlat)

    # ---- GeoJSON ----

    def to_feature(self) -> dict[str, Any]:
        """→ GeoJSON Feature（coordinates 固定 [lng, lat]）。"""
        props = self.model_dump(mode="json")
        props.pop("lng", None)
        props.pop("lat", None)
        return {
            "type": "Feature",
            "id": self.id,
            "geometry": {"type": "Point", "coordinates": [self.lng, self.lat]},
            "properties": props,
        }

    @classmethod
    def from_feature(cls, feature: dict[str, Any]) -> "Event":
        """GeoJSON Feature → Event。缺字段用默认值，尽量不抛（脏数据要能落库待查）。"""
        geom = feature.get("geometry") or {}
        coords = geom.get("coordinates") or [0.0, 0.0]
        props = dict(feature.get("properties") or {})
        props.pop("lng", None)
        props.pop("lat", None)
        return cls(
            id=str(feature.get("id") or props.pop("id", None) or new_event_id()),
            lng=float(coords[0]),
            lat=float(coords[1]),
            **props,
        )

    @classmethod
    def from_feature_safe(cls, feature: dict[str, Any]) -> tuple["Event | None", str | None]:
        """容错版：返回 (event, error)。用于批量导入时不因单条脏数据中断。"""
        try:
            return cls.from_feature(feature), None
        except Exception as exc:                            # noqa: BLE001
            return None, f"{type(exc).__name__}: {exc}"


def feature_collection(events: list[Event]) -> dict[str, Any]:
    """[Event] → GeoJSON FeatureCollection。"""
    return {"type": "FeatureCollection", "features": [e.to_feature() for e in events]}


# --------------------------------------------------------------------------- #
# HAM 站点（B-08）
# --------------------------------------------------------------------------- #

class Station(BaseModel):
    """业余无线电站点（ADIF/APRS 记录的统一形态）。"""

    call: str
    lng: float | None = None
    lat: float | None = None
    freq_mhz: float | None = None
    mode: str | None = None
    grid: str | None = None
    qso_time: datetime | None = None
    symbol: str | None = None
    comment: str | None = None
    source: str = "adif"                     # adif | aprs | pota | sota

    @field_validator("qso_time")
    @classmethod
    def _aware(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            return v.replace(tzinfo=timezone.utc)
        return v

    def to_feature(self) -> dict[str, Any]:
        props = self.model_dump(mode="json")
        props.pop("lng", None)
        props.pop("lat", None)
        geom: dict[str, Any] = {"type": "Point", "coordinates": [self.lng, self.lat]}
        if self.lng is None or self.lat is None:
            geom = {"type": "Point", "coordinates": None}    # 无位置：保留属性便于排查
        return {"type": "Feature", "id": self.call, "geometry": geom, "properties": props}


# --------------------------------------------------------------------------- #
# 告警规则（F-04 前端依赖，后端工单 B-07 漏列 —— 见偏离说明第 6 条）
# --------------------------------------------------------------------------- #

class AlertRule(BaseModel):
    """区域 + 事件类型 + 最低严重度的告警规则。"""

    id: str = Field(default_factory=new_event_id)
    name: str = ""
    # 区域：矩形 bbox 或圆形
    bbox: tuple[float, float, float, float] | None = None   # (w, s, e, n)
    center_lng: float | None = None
    center_lat: float | None = None
    radius_km: float | None = Field(default=None, ge=0.0)
    event_types: list[EventType] = Field(default_factory=list)
    min_severity: Severity = Severity.MEDIUM
    enabled: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(CST))

    def contains(self, lng: float, lat: float) -> bool:
        """点是否落在规则区域内。未定义区域视为"全域"。"""
        if self.bbox is not None:
            w, s, e, n = self.bbox
            return w <= lng <= e and s <= lat <= n
        if self.center_lng is not None and self.center_lat is not None and self.radius_km:
            import math

            dlat = (lat - self.center_lat) * 110.574
            cosf = max(1e-6, math.cos(math.radians(self.center_lat)))
            dlon = (lng - self.center_lng) * 111.320 * cosf
            return math.hypot(dlat, dlon) <= self.radius_km
        return True

    def matches(self, event: Event) -> bool:
        if not self.enabled:
            return False
        if not self.contains(event.lng, event.lat):
            return False
        if self.event_types and event.event_type not in self.event_types:
            return False
        return severity_at_least(event.severity.value, self.min_severity.value)


__all__ = [
    "Event", "Station", "AlertRule",
    "Source", "EventType", "Severity", "CoordSource",
    "SEVERITY_RANK", "severity_at_least",
    "new_event_id", "id_timestamp", "feature_collection",
    "CST", "DEFAULT_TTL_SECONDS",
]
