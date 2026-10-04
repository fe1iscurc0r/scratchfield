"""B-04 · 态势综合引擎（卷132）。

三个能力：

- `summarize_events(events, time_window_hours)` → 结构化摘要 + 风险等级
- `detect_anomaly(region, event_type, threshold)` → 事件密度异常
- `infer_impact(event, radius_km)` → 影响范围多边形

**关键设计决策：风险等级不由 LLM 决定。**
`risk_level` / `counts` / `key_events` 全部由**确定性规则**算出，LLM 只负责写
`summary` 那段话。理由：风险等级要可复现、可审计、可在测试里断言；把安全等级
交给一个随机性模型，等于让告警阈值随采样温度漂移。LLM 挂了摘要也能出（降级为
模板拼接），接口不会 500。

事件来源通过 `events_provider` 可调用对象注入，与存储层解耦（便于测试与替换）。
"""
from __future__ import annotations

import time
from collections import Counter
from datetime import datetime, timedelta
from typing import Any, Callable, Iterable, Sequence

from .coords import (
    bbox_intersects,
    circle_polygon,
    haversine_km,
    point_in_bbox,
)
from .models import CST, Event, EventType, Severity, severity_at_least

__all__ = ["SituationEngine", "assess_risk_level", "SUM_SYSTEM_PROMPT"]

# 风险等级判定阈值（确定性、可审计）
RISK_CRITICAL_MIN = 1        # 任一 critical 即 critical
RISK_HIGH_MIN = 1            # 任一 high
RISK_MEDIUM_MIN = 3          # 3 条以上 medium/low 组合抬到 medium

SUM_SYSTEM_PROMPT = (
    "你是态势分析助手。根据给出的事件列表，用简体中文写一段 120 字以内的态势概述，"
    "说明发生了什么、集中在哪个区域、整体趋势。只输出概述正文，不要 JSON、不要标题、"
    "不要复述原始数据条目。不要编造列表中不存在的信息。"
)


# --------------------------------------------------------------------------- #
# 确定性风险判定
# --------------------------------------------------------------------------- #

def assess_risk_level(events: Sequence[Event]) -> str:
    """按严重度分布判定风险等级（纯确定性，可测试、可审计）。

    规则（自上而下，命中即返回）：
      - 存在 critical                → critical
      - 存在 high 且 high 数 >= 2    → critical（多点高危视为整体危急）
      - 存在 high                    → high
      - high+medium 总数 >= 3        → high
      - 存在 medium                  → medium
      - 其余                         → low
    """
    if not events:
        return "low"
    ranks = Counter(e.severity.value for e in events)
    n_crit = ranks.get(Severity.CRITICAL.value, 0)
    n_high = ranks.get(Severity.HIGH.value, 0)
    n_med = ranks.get(Severity.MEDIUM.value, 0)

    if n_crit >= RISK_CRITICAL_MIN:
        return "critical"
    if n_high >= 2:
        return "critical"
    if n_high >= RISK_HIGH_MIN:
        return "high"
    if n_high + n_med >= RISK_MEDIUM_MIN:
        return "high"
    if n_med >= 1:
        return "medium"
    return "low"


def _fmt_event(e: Event) -> str:
    ts = e.reported_at.astimezone(CST).strftime("%m-%d %H:%M")
    return f"[{ts}] ({e.severity.value}/{e.event_type.value}) {e.title or e.description or '(无标题)'}"


class SituationEngine:
    """态势综合引擎。

    `gateway` 为 `LLMGateway`（可 None：无 LLM 时摘要降级为模板拼接）。
    `events_provider` 为无参可调用对象，返回当前事件列表。
    """

    def __init__(self, gateway: Any = None,
                 events_provider: Callable[[], Sequence[Event]] | None = None) -> None:
        self.gateway = gateway
        self.events_provider = events_provider

    # ---- 内部 ----

    def _all_events(self) -> list[Event]:
        if self.events_provider is None:
            return []
        try:
            return list(self.events_provider() or [])
        except Exception:                                   # noqa: BLE001
            return []

    @staticmethod
    def _within(events: Iterable[Event], hours: float | None,
                now: datetime | None = None) -> list[Event]:
        """按时间窗过滤（窗口按事件自带时区，默认 +08:00）。"""
        evs = list(events)
        if hours is None:
            return evs
        ref = now or datetime.now(CST)
        floor = ref - timedelta(hours=float(hours))
        return [e for e in evs if e.reported_at >= floor]

    # ---- B-04-1 摘要 ----

    def summarize_events(self, events: Sequence[Event] | None = None,
                         time_window_hours: float = 6.0,
                         region: tuple[float, float, float, float] | None = None,
                         use_llm: bool = True) -> dict[str, Any]:
        """多事件 → `{ok, summary, key_events, risk_level, counts, ...}`。"""
        pool = list(events) if events is not None else self._all_events()
        windowed = self._within(pool, time_window_hours)
        if region is not None:
            windowed = [e for e in windowed if point_in_bbox(e.lng, e.lat, region)]

        risk = assess_risk_level(windowed)
        by_type = Counter(e.event_type.value for e in windowed)
        by_severity = Counter(e.severity.value for e in windowed)

        # 关键事件：严重度优先，同级按时间新→旧
        key = sorted(windowed, key=lambda e: (-e.severity_rank, -e.reported_at.timestamp()))[:5]

        summary, source = self._compose_summary(windowed, time_window_hours, risk, by_type, use_llm)

        return {
            "ok": True,
            "summary": summary,
            "summary_source": source,               # llm | template | disabled
            "risk_level": risk,
            "counts": {
                "total": len(windowed),
                "by_type": dict(by_type),
                "by_severity": dict(by_severity),
            },
            "key_events": [e.to_feature() for e in key],
            "time_window_hours": time_window_hours,
            "region": list(region) if region else None,
            "generated_at": datetime.now(CST).isoformat(),
        }

    def _compose_summary(self, events: list[Event], hours: float, risk: str,
                         by_type: Counter, use_llm: bool) -> tuple[str, str]:
        """先试 LLM；不可用则模板拼接。模板也保证结构化输出非空。"""
        template = self._template_summary(events, hours, risk, by_type)
        if not use_llm or self.gateway is None or not events:
            return template, "template"

        listing = "\n".join(_fmt_event(e) for e in events[:40])     # 限长，控 token
        prompt = (f"时间窗口：最近 {hours} 小时\n系统判定风险等级：{risk}\n"
                  f"事件共 {len(events)} 条：\n{listing}\n\n请写态势概述。")
        try:
            out = self.gateway.chat([{"role": "user", "content": prompt}],
                                    system_prompt=SUM_SYSTEM_PROMPT)
        except Exception:                                   # noqa: BLE001
            return template, "template"
        if out.get("ok") and str(out.get("text") or "").strip():
            return str(out["text"]).strip(), "llm"
        return template, "template"

    @staticmethod
    def _template_summary(events: list[Event], hours: float, risk: str,
                          by_type: Counter) -> str:
        if not events:
            return f"最近 {hours} 小时内没有采集到事件，当前风险等级 {risk}。"
        top = "、".join(f"{k}{v}起" for k, v in by_type.most_common(3))
        newest = max(events, key=lambda e: e.reported_at)
        where = f"({newest.lng:.4f}, {newest.lat:.4f})"
        return (f"最近 {hours} 小时内共采集到 {len(events)} 起事件，主要集中在 {top}；"
                f"系统判定风险等级为 {risk}。最新一起为「{newest.title or newest.event_type.value}」"
                f"{where}。")

    # ---- B-04-2 异常检测 ----

    def detect_anomaly(self, region: Any = None, event_type: str | EventType | None = None,
                       threshold: int = 5, window_hours: float = 1.0,
                       events: Sequence[Event] | None = None,
                       include_expired: bool = False) -> bool:
        """区域内某类事件密度是否超阈值 → bool（工单要求的签名）。

        `region` 接受 `(w, s, e, n)` 或 `{"bbox": [...]}` 或 None（全域）。
        详细的计数请用 `anomaly_report()`。
        """
        return self.anomaly_report(region, event_type, threshold, window_hours,
                                   events, include_expired)["triggered"]

    def anomaly_report(self, region: Any = None, event_type: str | EventType | None = None,
                       threshold: int = 5, window_hours: float = 1.0,
                       events: Sequence[Event] | None = None,
                       include_expired: bool = False) -> dict[str, Any]:
        """异常检测明细：命中数、阈值、是否触发、参与事件 id。"""
        bbox = _normalize_region(region)
        pool = list(events) if events is not None else self._all_events()
        windowed = self._within(pool, window_hours)
        if not include_expired:
            windowed = [e for e in windowed if not e.is_expired]
        if bbox is not None:
            windowed = [e for e in windowed if point_in_bbox(e.lng, e.lat, bbox)]
        if event_type is not None:
            want = event_type.value if isinstance(event_type, EventType) else str(event_type)
            windowed = [e for e in windowed if e.event_type.value == want]

        count = len(windowed)
        return {
            "ok": True,
            "triggered": count >= int(threshold),
            "count": count,
            "threshold": int(threshold),
            "window_hours": window_hours,
            "region": list(bbox) if bbox else None,
            "event_type": (event_type.value if isinstance(event_type, EventType)
                           else (str(event_type) if event_type else None)),
            "event_ids": [e.id for e in windowed][:50],
        }

    # ---- B-04-3 影响范围 ----

    def infer_impact(self, event: Event, radius_km: float = 5.0,
                     points: int = 32) -> dict[str, Any]:
        """事件 → 影响范围多边形（GeoJSON Polygon）+ 覆盖与面积估计。"""
        r = float(radius_km)
        if r <= 0:
            r = float(event.bounding_box_km) or 1.0
        ring = circle_polygon(event.lng, event.lat, r, points=points)
        # 面积：等距圆柱近似下的圆面积，给出量级即可
        area_km2 = 3.141592653589793 * r * r
        return {
            "ok": True,
            "polygon": {
                "type": "Polygon",
                "coordinates": [ring],
            },
            "center": [event.lng, event.lat],
            "radius_km": r,
            "area_km2": round(area_km2, 3),
            "event_id": event.id,
        }

    # ---- F-05 自然语言查询（前端依赖，后端工单 B-07 漏列）----

    def answer_query(self, text: str, geocoder: Any = None,
                     top_k: int = 5, radius_km: float = 25.0) -> dict[str, Any]:
        """自然语言问题 → `{answer, cited_events, map_action, llm_source}`。

        流程：定位（geocoder 解析问题里的地点）→ 取该点周边事件 → LLM 组织回答。
        定位不到就按全域最近事件回答，并把 `map_action` 置空（不假装定位成功）。
        """
        text = str(text or "").strip()
        if not text:
            return {"ok": False, "error": "empty_query", "answer": "",
                    "cited_events": [], "map_action": None, "llm_source": None}

        focus: dict[str, Any] | None = None
        if geocoder is not None:
            # 从问题里抠出最长的可能地名片段交给 geocoder
            for candidate in _location_candidates(text):
                got = geocoder.geocode(candidate)
                if got.get("ok"):
                    focus = got
                    break

        pool = self._all_events()
        if focus is not None:
            pool = [e for e in pool
                    if haversine_km(e.lng, e.lat, focus["lng"], focus["lat"]) <= radius_km]
        pool = sorted(pool, key=lambda e: -e.reported_at.timestamp())[:max(1, top_k)]

        risk = assess_risk_level(pool)
        if self.gateway is not None and pool:
            listing = "\n".join(_fmt_event(e) for e in pool)
            prompt = (f"用户问题：{text}\n\n相关事件：\n{listing}\n\n"
                      "请用简体中文回答用户问题，并在末尾单独一行以「来源：」列出引用的事件序号。")
            try:
                out = self.gateway.chat([{"role": "user", "content": prompt}],
                                        system_prompt=SUM_SYSTEM_PROMPT)
            except Exception:                               # noqa: BLE001
                out = {"ok": False}
            if out.get("ok") and str(out.get("text") or "").strip():
                return {
                    "ok": True,
                    "answer": str(out["text"]).strip(),
                    "cited_events": [e.to_feature() for e in pool],
                    "map_action": _fly_to(focus),
                    "llm_source": out.get("route"),
                    "risk_level": risk,
                }

        # 降级：模板回答（无 LLM 也不空手）
        if pool:
            answer = (f"围绕该区域最近有 {len(pool)} 起相关事件，风险等级 {risk}；"
                      f"其中最新为「{pool[0].title or pool[0].event_type.value}」。"
                      f"（当前未接入 LLM，以上为统计结果）")
        else:
            answer = "没有检索到与该问题相关的事件。"
        return {
            "ok": True, "answer": answer,
            "cited_events": [e.to_feature() for e in pool],
            "map_action": _fly_to(focus),
            "llm_source": None,
            "risk_level": risk,
        }

    # ---- 汇总（给 /api/metrics）----

    def metrics(self, events: Sequence[Event] | None = None) -> dict[str, Any]:
        pool = list(events) if events is not None else self._all_events()
        today = datetime.now(CST).date()
        todays = [e for e in pool if e.reported_at.astimezone(CST).date() == today]
        return {
            "events_total": len(pool),
            "events_today": len(todays),
            "high_risk_today": sum(1 for e in todays if e.severity_rank >= 2),
            "risk_level": assess_risk_level(todays),
            "generated_at": time.time(),
        }


# --------------------------------------------------------------------------- #
# 辅助
# --------------------------------------------------------------------------- #

def _normalize_region(region: Any) -> tuple[float, float, float, float] | None:
    """把多种 region 写法归一为 (w, s, e, n)；无法识别返回 None（全域）。"""
    if region is None:
        return None
    if isinstance(region, dict):
        if "bbox" in region and region["bbox"]:
            return _normalize_region(region["bbox"])
        if {"west", "south", "east", "north"} <= set(region):
            return (float(region["west"]), float(region["south"]),
                    float(region["east"]), float(region["north"]))
        return None
    if isinstance(region, (list, tuple)) and len(region) == 4:
        try:
            return (float(region[0]), float(region[1]), float(region[2]), float(region[3]))
        except (TypeError, ValueError):
            return None
    return None


_CN_LOC_SUFFIX = "市区县镇街道省"
_CN_LOC_CHARS = "".join(chr(c) for c in range(0x4E00, 0x9FFF))


def _location_candidates(text: str) -> list[str]:
    """从问句里抽候选地名：优先「X市/区/县/镇/街道」整体，再退到连续汉字串。

    不做 NER —— 只做后缀启发式，够用且可解释。抽不出就返回空（调用方按全域处理）。
    """
    import re
    out: list[str] = []
    for m in re.finditer(rf"[{_CN_LOC_CHARS}]{{2,10}}[{_CN_LOC_SUFFIX}]", text):
        out.append(m.group(0))
    # 去掉过长的（多半把整句吞了）
    out = [s for s in out if 2 <= len(s) <= 10]
    if not out:
        for m in re.finditer(rf"[{_CN_LOC_CHARS}]{{2,8}}", text):
            seg = m.group(0)
            if len(seg) >= 2:
                out.append(seg)
    # 长优先：先试最具体的
    return sorted(set(out), key=len, reverse=True)[:5]


def _fly_to(focus: dict[str, Any] | None) -> dict[str, Any] | None:
    if not focus or not focus.get("ok"):
        return None
    return {"type": "flyTo", "center": [focus["lng"], focus["lat"]],
            "zoom": 13, "label": focus.get("display_name") or focus.get("grid") or ""}
