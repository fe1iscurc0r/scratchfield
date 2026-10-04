"""物理信息校验器（I-02）：规则表而非 LLM 判断。

对一条合成路线做可行性校验：
- reactant_present     至少 1 个反应物且名称非空（error）
- product_present      产物名称非空（error）
- yield_range          产率 ∈ [0, 100]（error）
- condition_range      温度/压力/时长落在物理合理区间（error）
- property_consistency 产物物性落在已知范围表内（warning，范围表可扩展）

规则可配置：validate(route, rules=None) 中 rules 可传 {规则id: bool 或参数 dict}
来启用/禁用/覆盖单条规则。规则判定不调用 LLM，全部确定性。
"""
from __future__ import annotations

from typing import Any

from .schema import Route

# 已知产物物性合理范围（示例，可扩展；单位在 name 中约定）
KNOWN_PROPERTY_RANGES: dict[str, tuple[float, float]] = {
    "decomposition_temp_c": (150.0, 1200.0),
    "density_g_cm3": (0.1, 20.0),
    "specific_surface_area_m2_g": (1.0, 5000.0),
    "yield_percent": (0.0, 100.0),
}

# 物理常数/经验边界（确定性，非 LLM）
_ABS_ZERO_C = -273.15
_TEMP_MAX_C = 3000.0


def _check_reactant_present(route: Route) -> tuple[bool, str]:
    names = [r.name.strip() for r in route.reactants if r.name and r.name.strip()]
    if not names:
        return False, "无有效反应物（至少需要一个非空反应物）"
    return True, f"{len(names)} 个反应物"


def _check_product_present(route: Route) -> tuple[bool, str]:
    if not route.product or not route.product.strip():
        return False, "产物 product 为空"
    return True, "产物已声明"


def _check_yield_range(route: Route) -> tuple[bool, str]:
    ys = [v for v in (route.yield_min, route.yield_max) if v is not None]
    if not ys:
        return True, "未声明产率，跳过"
    if any(not (0.0 <= v <= 100.0) for v in ys):
        return False, f"产率越界（应在 0–100%）：{ys}"
    if route.yield_min is not None and route.yield_max is not None and route.yield_min > route.yield_max:
        return False, f"产率区间颠倒：min={route.yield_min} > max={route.yield_max}"
    return True, f"产率 {ys} 在合理范围"


def _check_condition_range(route: Route) -> tuple[bool, str]:
    c = route.conditions
    tmin, tmax = c.temp_min_c, c.temp_max_c
    if tmin is not None and tmin < _ABS_ZERO_C:
        return False, f"温度低于绝对零度：{tmin}℃"
    if tmax is not None and tmax > _TEMP_MAX_C:
        return False, f"温度超出上限：{tmax}℃"
    if tmin is not None and tmax is not None and tmin > tmax:
        return False, f"温度区间颠倒：min={tmin} > max={tmax}"
    if c.pressure_bar is not None and c.pressure_bar < 0:
        return False, f"压力为负：{c.pressure_bar} bar"
    if c.time_h is not None and c.time_h <= 0:
        return False, f"时长必须为正：{c.time_h} h"
    return True, "条件在合理范围"


def _check_property_consistency(route: Route) -> tuple[bool, str]:
    bad = []
    for p in route.properties:
        rng = KNOWN_PROPERTY_RANGES.get(p.name)
        if rng is None or p.value is None:
            continue
        lo, hi = rng
        if not (lo <= p.value <= hi):
            bad.append(f"{p.name}={p.value}（应 {lo}–{hi}）")
    if bad:
        return False, "物性与已知范围不一致：" + "、".join(bad)
    return True, "物性一致（或未登记可核验物性）"


# 规则注册表：id → (检查函数, 默认严重级)。validate() 据此迭代。
_RULES: dict[str, tuple[Any, str]] = {
    "reactant_present": (_check_reactant_present, "error"),
    "product_present": (_check_product_present, "error"),
    "yield_range": (_check_yield_range, "error"),
    "condition_range": (_check_condition_range, "error"),
    "property_consistency": (_check_property_consistency, "warning"),
}


def validate(route: Route | dict[str, Any],
             rules: dict[str, bool] | None = None) -> dict[str, Any]:
    """物理校验一条路线，返回 {valid, passed[], issues[{rule,severity,message}]}。

    rules 可配置：{规则id: bool}，False 表示禁用该规则；None 表示全部启用。
    """
    r = route if isinstance(route, Route) else Route.from_dict(route)
    enabled = dict(_RULES) if rules is None else {
        k: v for k, v in _RULES.items() if rules.get(k, True)
    }

    passed: list[str] = []
    issues: list[dict[str, str]] = []
    for rule_id, (fn, severity) in enabled.items():
        ok, msg = fn(r)
        if ok:
            passed.append(rule_id)
        else:
            issues.append({"rule": rule_id, "severity": severity, "message": msg})

    return {
        "valid": len(issues) == 0,
        "passed": passed,
        "issues": issues,
    }
