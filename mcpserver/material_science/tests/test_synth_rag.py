"""synth_rag 合成路线旁路测试（I-02 验收：≥6 用例）。

覆盖：入库 / 查询 / 过滤检索 / 物理校验通过/拒绝 / 示例数据 / 坏输入 / CLI 集成。
纯内存库（":memory:"）+ 临时库，不碰真实数据库与 graphrag 主流程。
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from mcpserver.material_science.synth_rag import cli, example_data, retrieve, validator
from mcpserver.material_science.synth_rag.schema import Conditions, Reactant, Route
from mcpserver.material_science.synth_rag.store import RouteStore


@pytest.fixture()
def store():
    s = RouteStore(":memory:")
    yield s
    s.close()


def _sample_route(**overrides) -> Route:
    base = dict(
        name="测试木质素碳化路线",
        product="木质素基多孔碳",
        method="碳化",
        yield_min=30.0,
        yield_max=45.0,
        source="测试数据",
        is_example=False,
        reactants=[Reactant(name="木质素", amount=10.0, unit="g", role="原料"),
                   Reactant(name="KOH", amount=20.0, unit="g", role="活化剂")],
        conditions=Conditions(temp_min_c=700.0, temp_max_c=900.0,
                              pressure_bar=1.0, time_h=2.0, atmosphere="氮气"),
        properties=[{"name": "specific_surface_area_m2_g", "value": 1500.0, "unit": "m²/g"}],
    )
    base.update(overrides)
    return Route(**base)


# ---------- 入库 / 查询 ----------

def test_add_and_get_route(store):
    rid = store.add_route(_sample_route())
    assert rid > 0
    r = store.get_route(rid)
    assert r is not None
    assert r.product == "木质素基多孔碳"
    assert r.yield_min == 30.0
    assert {x.name for x in r.reactants} == {"木质素", "KOH"}
    assert r.conditions.temp_max_c == 900.0


def test_add_route_bad_input_raises(store):
    # 产物为空 → 坏输入拒绝
    with pytest.raises(ValueError):
        store.add_route(_sample_route(product=""))
    # 名称为空 → 坏输入拒绝
    with pytest.raises(ValueError):
        store.add_route(_sample_route(name="   "))


def test_update_and_delete_route(store):
    rid = store.add_route(_sample_route())
    assert store.update_route(rid, {"yield_max": 55.0})
    assert store.get_route(rid).yield_max == 55.0
    # 非白名单字段不应生效
    assert not store.update_route(rid, {"bogus_col": 1})
    assert store.delete_route(rid)
    assert store.get_route(rid) is None


# ---------- 过滤检索 ----------

def test_search_filter_by_product(store):
    example_data.seed_examples(store)
    res = retrieve.search(store, product="木质素")
    assert res["success"]
    assert res["count"] >= 1
    for item in res["results"]:
        assert "木质素" in item["product"]


def test_search_filter_by_reactant(store):
    example_data.seed_examples(store)
    res = retrieve.search(store, reactant="氢氧化钾")
    assert res["success"]
    # 氢氧化钾 只出现在「木质素基多孔碳 KOH 活化」路线
    names = [item["name"] for item in res["results"]]
    assert any("多孔碳" in n for n in names)


def test_search_no_filter_returns_all(store):
    example_data.seed_examples(store)
    res = retrieve.search(store)
    assert res["success"]
    assert res["count"] == 5


# ---------- 物理校验 ----------

def test_validate_passes_valid_route(store):
    route = _sample_route()
    res = validator.validate(route)
    assert res["valid"] is True
    assert res["issues"] == []


def test_validate_rejects_bad_yield_and_temp(store):
    bad = _sample_route(yield_max=150.0,
                        conditions=Conditions(temp_min_c=-300.0, temp_max_c=900.0))
    res = validator.validate(bad)
    assert res["valid"] is False
    rule_ids = {it["rule"] for it in res["issues"]}
    assert "yield_range" in rule_ids      # 产率越界
    assert "condition_range" in rule_ids  # 温度低于绝对零度


def test_validate_rule_configurable(store):
    bad = _sample_route(yield_max=150.0)
    # 禁用 yield_range 后，仅剩的 yield 违规不再拒绝
    res = validator.validate(bad, rules={"yield_range": False})
    assert res["valid"] is True


# ---------- 示例数据 ----------

def test_seed_examples(store):
    n = example_data.seed_examples(store)
    assert n == 5
    assert store.count() == 5
    for r in store.list_routes():
        assert r.is_example is True
        assert "待真机采集" in r.source


def test_seed_idempotent(store):
    example_data.seed_examples(store)
    example_data.seed_examples(store)
    assert store.count() == 5  # 重复 seed 不累积


# ---------- CLI 集成 ----------

def test_cli_seed_and_search(tmp_path: Path, capsys):
    db = tmp_path / "routes.db"
    assert cli.main(["seed", "--db", str(db)]) == 0
    assert cli.main(["search", "--product", "木质素", "--db", str(db)]) == 0
    out = capsys.readouterr().out
    assert "木质素" in out  # search 能搜到内置示例路线
    assert cli.main(["validate", "--all", "--db", str(db)]) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-q"])
