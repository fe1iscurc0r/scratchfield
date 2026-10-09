"""spectrum_events_bridge.py — 事件驱动频谱缓存 MCP 注册（K09）。

把 spectrum_events.SpectrumEventCache（R01）注册为 mcpserver 工具：
- spectrum_events.ingest_frame        吞一帧频谱（freqs/db），检测并缓存事件
- spectrum_events.current_interferers 当前活跃干扰源（按强度降序）
- spectrum_events.recent_events       最近 n 条事件（旧→新）

纯 numpy，无硬件依赖，可离线单测。结构照 sentinel_bridge 范式
（agent-manifest entryPoint → Bridge 类 → handle_handoff 分发）。
"""
from __future__ import annotations

import json
import logging
from typing import Any

from mcpserver.rf_brain.spectrum_events import SpectrumEventCache
import threading

logger = logging.getLogger(__name__)

_cache: SpectrumEventCache | None = None


_cache_lock = threading.Lock()


def get_cache() -> SpectrumEventCache:
    """进程级单例缓存（跨调用保持事件状态）。"""
    global _cache
    if _cache is None:
        with _cache_lock:
            if _cache is None:
                _cache = SpectrumEventCache()
    return _cache


def reset_cache() -> None:
    """清空缓存（测试/重启用）。"""
    global _cache
    _cache = None


class SpectrumEventsBridge:
    """事件驱动频谱缓存 MCP 服务实例。"""

    async def handle_handoff(self, tool_call: dict[str, Any]) -> str:
        tool_name = str(tool_call.get("tool_name") or "").strip()
        params = {
            k: v
            for k, v in tool_call.items()
            if k not in ("service_name", "tool_name", "message", "session_id", "callback_url")
        }
        try:
            result = self._dispatch(tool_name, params)
        except Exception as e:  # noqa: BLE001 - 参数错误 fail-fast 返回
            logger.warning("[spectrum_events] %s 失败: %s", tool_name, e)
            return json.dumps(
                {"status": "error", "service": "spectrum_events",
                 "tool": tool_name, "error": str(e)},
                ensure_ascii=False,
            )
        return json.dumps(
            {"status": "ok", "service": "spectrum_events", "tool": tool_name, "result": result},
            ensure_ascii=False,
        )

    def _dispatch(self, tool_name: str, p: dict[str, Any]) -> dict[str, Any]:
        if tool_name == "spectrum_events.ingest_frame":
            freqs = p.get("freqs")
            db = p.get("db")
            if freqs is None or db is None:
                raise ValueError("ingest_frame 需要 freqs 与 db 两个数组")
            events = get_cache().ingest_frame(freqs, db, timestamp=p.get("timestamp"))
            return {"ok": True, "new_events": [e.as_dict() for e in events],
                    "cached": len(get_cache())}

        if tool_name == "spectrum_events.current_interferers":
            return {"ok": True,
                    "interferers": [e.as_dict() for e in get_cache().current_interferers(now=p.get("now"))]}

        if tool_name == "spectrum_events.recent_events":
            n = int(p.get("limit", 10) or 10)
            return {"ok": True, "events": [e.as_dict() for e in get_cache().recent_events(n)]}

        raise ValueError(
            f"spectrum_events 不支持的工具: {tool_name!r}（可用: spectrum_events.ingest_frame/"
            "spectrum_events.current_interferers/spectrum_events.recent_events）"
        )
