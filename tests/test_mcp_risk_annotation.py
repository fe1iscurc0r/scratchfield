"""风险等级注解验收（工单205 任务一）。

不变量：注解**只读**（不改变装配/调用行为）；判据优先级 = 显式登记 > manifest.tier > 名字规则 > low。
"""
from __future__ import annotations

import pytest

from mcpserver import mcp_registry as R


@pytest.fixture(autouse=True)
def _isolate():
    snap = (dict(R._RISK_OVERRIDES), dict(R.MANIFEST_CACHE))
    yield
    R._RISK_OVERRIDES.clear(); R._RISK_OVERRIDES.update(snap[0])
    R.MANIFEST_CACHE.clear(); R.MANIFEST_CACHE.update(snap[1])


def test_risk_levels_shape():
    assert R.RISK_LEVELS == ("low", "medium", "high")


@pytest.mark.parametrize("tier,expect", [
    ("read-only", "low"), ("local-write", "medium"),
    ("process-control", "high"), ("offensive", "high"),
])
def test_risk_derived_from_manifest_tier(tier, expect):
    R.MANIFEST_CACHE["svc_x"] = {"classification": {"tier": tier}}
    assert R.get_service_risk("svc_x") == expect


def test_risk_name_fallback_without_classification():
    R.MANIFEST_CACHE.pop("agent_decompile", None)
    assert R.get_service_risk("agent_decompile") == "high"   # 名字兜底
    assert R.get_service_risk("totally_unknown") == "low"     # 兜底 low


def test_tier_beats_name_rule():
    """manifest 的 tier 优先于名字规则（权威判据在 manifest）。"""
    R.MANIFEST_CACHE["agent_decompile"] = {"classification": {"tier": "local-write"}}
    assert R.get_service_risk("agent_decompile") == "medium"


def test_explicit_override_wins():
    R.MANIFEST_CACHE["svc_y"] = {"classification": {"tier": "offensive"}}
    assert R.get_service_risk("svc_y") == "high"
    R.register_service_risk("svc_y", "low")
    assert R.get_service_risk("svc_y") == "low"


def test_invalid_risk_rejected():
    with pytest.raises(ValueError):
        R.register_service_risk("x", "critical")
    with pytest.raises(ValueError):
        R.register_service_risk("", "low")


def test_statistics_cover_all_services():
    R.scan_and_register_mcp_agents("mcpserver")
    stats = R.get_risk_statistics()
    assert set(stats) == set(R.RISK_LEVELS)
    assert sum(stats.values()) == len(R.all_service_names()), "每个服务必须恰好归入一档"
