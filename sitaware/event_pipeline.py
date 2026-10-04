"""B-02 · 采集管道（卷132）。

采集 → 规范化 → 去重 → 落库。去重键为（来源, 经纬度≈4 位, 标题, 上报小时），
避免同一事件被多个采集源重复入库。`ingest()` 返回落库统计，供 API / 采集器消费。
"""
from __future__ import annotations

import logging
from typing import Iterable

from .cache_store import CacheStore
from .models import Event

logger = logging.getLogger("sitaware.pipeline")


class EventPipeline:
    """采集管道：去重后批量写入 `CacheStore`。"""

    def __init__(self, store: CacheStore) -> None:
        self.store = store

    @staticmethod
    def _dedup_key(e: Event) -> tuple:
        return (
            e.source.value,
            round(e.lng, 4),
            round(e.lat, 4),
            e.title,
            e.reported_at.strftime("%Y%m%d%H"),
        )

    def ingest(self, events: Iterable[Event]) -> dict:
        seen: set[tuple] = set()
        uniq: list[Event] = []
        for e in events:
            key = self._dedup_key(e)
            if key in seen:
                continue
            seen.add(key)
            uniq.append(e)
        if not uniq:
            return {"ok": True, "ingested": 0, "saved": 0, "failed": 0, "errors": []}
        res = self.store.save_events(uniq)
        return {**res, "ingested": len(uniq)}


__all__ = ["EventPipeline"]
