"""mcpserver 注册域分组验收（工单204 任务二）。

覆盖：名字规则推导（四域 + general 兜底）/ 显式登记覆盖规则 / 非法域拒绝 /
分组输出结构 / 统计含空域 / 与真实注册表集成（分组覆盖全部服务不重不漏）。
"""
from __future__ import annotations

import pytest

from mcpserver import mcp_registry as R


@pytest.fixture(autouse=True)
def _isolate_overrides():
    """备份/还原显式域登记表，避免测试间污染。"""
    snap = dict(R._DOMAIN_OVERRIDES)
    yield
    R._DOMAIN_OVERRIDES.clear()
    R._DOMAIN_OVERRIDES.update(snap)


@pytest.mark.parametrize("name,expect", [
    ("rf_brain", "radio"),
    ("antenna_sim", "radio"),
    ("ptz_service", "radio"),
    ("sentinel_intel", "radio"),
    ("hamlog_adapter", "radio"),
    ("material_science", "material"),
    ("bio_adapter", "material"),
    ("biopred", "material"),
    ("eis", "material"),
    ("agent_frida", "agent"),
    ("agent_browser", "agent"),
    ("graph_memory_adapter", "memory"),
    ("memory_maas", "memory"),
    ("summer_memory", "memory"),
    ("something_unknown", "general"),
    ("", "general"),
])
def test_rule_based_domain(name, expect):
    assert R.get_service_domain(name) == expect


def test_explicit_registration_overrides_rule():
    assert R.get_service_domain("rf_brain") == "radio"
    R.register_service_domain("rf_brain", "general")
    assert R.get_service_domain("rf_brain") == "general", "显式登记必须优先于规则"
    R.register_service_domain("weird_name_xyz", "memory")
    assert R.get_service_domain("weird_name_xyz") == "memory"


def test_invalid_domain_rejected():
    with pytest.raises(ValueError):
        R.register_service_domain("x", "not_a_domain")
    with pytest.raises(ValueError):
        R.register_service_domain("", "radio")


def test_domains_tuple_is_stable():
    assert R.DOMAINS == ("radio", "material", "agent", "memory", "general")
    assert R.DEFAULT_DOMAIN == "general"


def test_statistics_include_empty_domains():
    stats = R.get_domain_statistics()
    assert set(stats) == set(R.DOMAINS), "统计必须含全五域（含 0 的域）"
    assert all(isinstance(v, int) and v >= 0 for v in stats.values())


def test_by_domain_covers_all_services_exactly_once():
    """分组必须覆盖 all_service_names 全集、不重不漏。"""
    grouped = R.list_services_by_domain()
    flat = [n for names in grouped.values() for n in names]
    assert sorted(flat) == R.all_service_names(), "分组与全量服务清单必须一致"
    assert len(flat) == len(set(flat)), "同一服务不得出现在多个域"
    assert set(grouped) <= set(R.DOMAINS)
    for names in grouped.values():
        assert names == sorted(names), "域内服务名应有序"


def test_grouping_reflects_newly_registered_services(monkeypatch):
    """新登记的服务（含冷表项）必须即时出现在分组里。"""
    R.MANIFEST_CACHE["zz_new_radio_svc"] = {"name": "zz_new_radio_svc"}
    R._COLD_TABLE["zz_new_radio_svc"] = {"kind": "mcporter", "service_config": {}, "manifest": {}}
    try:
        grouped = R.list_services_by_domain()
        assert "zz_new_radio_svc" in grouped.get("general", []) or \
               "zz_new_radio_svc" in grouped.get("radio", [])
        assert "zz_new_radio_svc" in sum(grouped.values(), [])
    finally:
        R.MANIFEST_CACHE.pop("zz_new_radio_svc", None)
        R._COLD_TABLE.pop("zz_new_radio_svc", None)


def test_real_registry_distribution_is_nonempty_for_core_domains():
    """真实扫描后，核心域（radio/material/agent/memory）至少各有 1 个服务。"""
    R.scan_and_register_mcp_agents("mcpserver")
    grouped = R.list_services_by_domain()
    for domain in ("radio", "material", "agent", "memory"):
        assert grouped.get(domain), f"域 {domain} 不应为空（实际分组：{ {k: len(v) for k, v in grouped.items()} }）"
