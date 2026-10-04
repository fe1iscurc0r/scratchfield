"""B-02 合成事件采集器（离线联调用）。

`DemoCollector` 在离线环境生成贴合广州等城市的合成事件：经纬度落在城市锚点附近、
严重度/类型/时间窗分布可控，便于前端验证筛选、热力、时间轴、SSE 推送等能力。
合成的经纬度为 WGS84，与全局坐标约定一致。
"""
from __future__ import annotations

import math
import random
from datetime import datetime, timedelta
from typing import Iterable, Iterator

from ..models import CST, Event, EventType, Severity, Source

# 城市锚点（WGS84）。键用于事件 tag 与标题，便于城市选择器联调。
CITY_ANCHORS: dict[str, tuple[float, float]] = {
    "guangzhou": (113.2644, 23.1291),
    "shenzhen": (114.0579, 22.5431),
    "beijing": (116.4074, 39.9042),
    "shanghai": (121.4737, 31.2304),
    "chengdu": (104.0668, 30.5728),
}

# 各事件类型的样例标题（中文）。
_SAMPLE: dict[EventType, list[str]] = {
    EventType.PROTEST: ["市民集会活动", "广场聚集", "游行请愿"],
    EventType.ACCIDENT: ["交通事故", "道路塌陷", "工地坠落", "燃气泄漏"],
    EventType.WEATHER: ["暴雨红色预警", "雷暴大风", "高温预警", "台风临近"],
    EventType.SIGNAL: ["基站信号中断", "无线电干扰", "GPS 失锁", "对讲占频"],
    EventType.HAZARD: ["危化品泄漏", "建筑火灾", "电力故障", "道路积水"],
    EventType.CUSTOM: ["异常人员聚集", "设备离线", "交通管制"],
}

_SOURCES = [Source.NEWS, Source.RSS, Source.HAM_RADIO, Source.SENSOR, Source.USER, Source.WEATHER]

_SEVERITY_WEIGHTS = [Severity.LOW, Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL]
_SEVERITY_PROBS = [0.45, 0.30, 0.18, 0.07]


def _jitter(lat: float, lng: float, km: float = 10.0) -> tuple[float, float]:
    """在经纬度上叠加 ±km 的高斯近似抖动（城市内散布）。"""
    dlat = random.uniform(-km, km) / 110.574
    cosf = max(1e-6, math.cos(math.radians(lat)))
    dlng = random.uniform(-km, km) / (111.320 * cosf)
    return round(lng + dlng, 6), round(lat + dlat, 6)


class Collector:
    """采集源抽象。子类实现 `collect()` 返回 Event 迭代器。"""

    name = "base"

    def collect(self, limit: int = 100) -> Iterator[Event]:  # pragma: no cover
        raise NotImplementedError


class DemoCollector(Collector):
    """合成事件采集器（离线联调 / 演示）。"""

    name = "demo"

    def __init__(self, seed: int | None = 20260918, days: int = 7) -> None:
        self._seed = seed
        self._days = days

    def collect(self, limit: int = 120) -> Iterator[Event]:
        rng = random.Random(self._seed)
        now = datetime.now(CST)
        for i in range(limit):
            city = rng.choice(list(CITY_ANCHORS))
            clng, clat = CITY_ANCHORS[city]
            et = rng.choice(list(EventType))
            sev = rng.choices(_SEVERITY_WEIGHTS, weights=_SEVERITY_PROBS)[0]
            src = rng.choice(_SOURCES)
            age_h = rng.uniform(0, self._days * 24)
            reported = now - timedelta(hours=age_h)
            lng, lat = _jitter(clat, clng, km=10.0)
            title = rng.choice(_SAMPLE[et])
            conf = round(rng.uniform(0.4, 0.95), 2)
            yield Event(
                source=src,
                event_type=et,
                lng=lng, lat=lat,
                severity=sev,
                title=f"[{city}] {title}",
                description=f"{title}（{city}）发生于 {reported.strftime('%m-%d %H:%M')}，"
                            f"置信度 {int(conf * 100)}%。",
                confidence=conf,
                tags=[city, et.value, sev.value],
                reported_at=reported,
                author="demo-collector",
                raw_refs=[f"https://example.com/{city}/{i}"],
            )


def seed_demo_events(limit: int = 120, seed: int | None = 20260918,
                     days: int = 7) -> list[Event]:
    """便捷函数：直接产出一份合成事件列表。"""
    return list(DemoCollector(seed=seed, days=days).collect(limit=limit))


__all__ = ["Collector", "DemoCollector", "seed_demo_events", "CITY_ANCHORS"]
