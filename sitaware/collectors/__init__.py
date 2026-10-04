"""B-02 · 多源采集（卷132）。

采集源统一抽象为 `Collector`；真实接入（news / rss / ham / weather / user）通过
子类扩展 `collect()`。本包内置 `DemoCollector`，在离线环境下生成贴合城市的合成
事件，供前端联调与真实运行验证。所有事件在 `event_pipeline.EventPipeline` 里完成
规范化去重后落 `CacheStore`。
"""
from __future__ import annotations

from .seed import Collector, DemoCollector

__all__ = ["Collector", "DemoCollector"]
