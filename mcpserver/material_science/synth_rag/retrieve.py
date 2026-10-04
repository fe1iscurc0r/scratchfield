"""合成路线检索（I-02）：按产物/反应物/条件过滤 + 轻量相似度排序。

不引向量 DB：用子串命中 + 词元重合给分（英文词 / CJK 二元组），量级小足够用。
召回与校验解耦——本模块只管召回与打分，物理校验交给 validator.py 叠加。
"""
from __future__ import annotations

import re
from typing import Any

from .schema import Route
from .store import RouteStore

_EN_WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_\-]{1,}")


def _tokens(text: str) -> set[str]:
    """轻量词元：英文小写词 + CJK 二元组（继承 graphrag 的切分思路，不引依赖）。"""
    out: set[str] = set()
    for w in _EN_WORD_RE.findall(text):
        out.add(w.lower())
    for i in range(len(text) - 1):
        a, b = text[i], text[i + 1]
        if "\u4e00" <= a <= "\u9fff" and "\u4e00" <= b <= "\u9fff":
            out.add(a + b)
    return out


def _match_score(query: str, target: str) -> float:
    """单字段匹配分：精确(含大小写不敏感) → 子串 → 词元重合，0–1。"""
    if not query or not target:
        return 0.0
    q, t = query.strip().lower(), target.strip().lower()
    if not q:
        return 0.0
    if t == q:
        return 1.0
    if q in t:
        return 0.8
    qt, tt = _tokens(q), _tokens(t)
    if not qt or not tt:
        return 0.0
    inter = len(qt & tt)
    return round(0.5 * inter / max(len(qt), 1), 4)


def _route_reactant_names(route: Route) -> str:
    return " ".join(r.name for r in route.reactants)


def _route_condition_text(route: Route) -> str:
    c = route.conditions
    return " ".join(str(x) for x in (
        c.temp_min_c, c.temp_max_c, c.pressure_bar, c.time_h, c.atmosphere) if x not in (None, ""))


def search(store: RouteStore, product: str = "", reactant: str = "",
           condition: str = "", top_k: int = 10) -> dict[str, Any]:
    """按产物/反应物/条件过滤 + 相似度排序。全部过滤词为空时返回全量（按 id）。

    返回 {success, count, results:[{route_id, name, product, score, matched_on}]}。
    """
    try:
        routes = store.list_routes()
    except Exception as e:  # 库未初始化等
        return {"success": False, "error": str(e)}

    scored: list[dict[str, Any]] = []
    for route in routes:
        if route is None:
            continue
        s_product = _match_score(product, route.product) if product else 0.0
        s_reactant = _match_score(reactant, _route_reactant_names(route)) if reactant else 0.0
        s_condition = _match_score(condition, _route_condition_text(route)) if condition else 0.0

        # 过滤：任一显式过滤词存在但完全不命中则剔除
        has_filter = any((product, reactant, condition))
        matched_on = []
        if product:
            if s_product <= 0:
                continue
            matched_on.append("product")
        if reactant:
            if s_reactant <= 0:
                continue
            matched_on.append("reactant")
        if condition:
            if s_condition <= 0:
                continue
            matched_on.append("condition")

        # 相似度：过滤词命中分加权求和；无过滤词时给 0（按 id 稳定排序）
        score = round(
            (s_product + s_reactant + s_condition)
            / max(len(matched_on), 1) if matched_on else 0.0, 4)
        scored.append({
            "route_id": route.id,
            "name": route.name,
            "product": route.product,
            "score": score,
            "matched_on": matched_on if has_filter else [],
        })

    # 无过滤词时按 route_id 稳定排序；有过滤词按分数降序、同分按 id 升序
    if any((product, reactant, condition)):
        scored.sort(key=lambda x: (-x["score"], x["route_id"]))
    else:
        scored.sort(key=lambda x: x["route_id"])
    return {
        "success": True,
        "count": len(scored),
        "results": scored[: max(top_k, 0)],
    }
