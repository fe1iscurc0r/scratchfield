"""bofire MCP 封装离线测试（不装 bofire 也全绿）。

覆盖：
  1. 功能（降级路径）：define_domain / ask_candidates（占位候选）/ tell_results 均返回 ok:true + degraded:true + pip 提示
  2. 真算路径：mock _load_bofire 返回 FakeBofire，ask 走 Strategy.make().ask() 序列化
  3. 参数非法 → ValueError（parametrize）
  4. source 字段全命令 = "bofire"
  5. 未知命令 → ValueError

运行：python -m pytest mcpserver/bofire/test_bofire.py -q
"""

from __future__ import annotations

import pytest

from mcpserver.bofire.agent import _DEGRADED_NOTE, BofireAgent, _load_bofire

ASPIRIN_DOMAIN = {
    "variables": [
        {"name": "温度", "type": "continuous", "bounds": [20, 80]},
        {"name": "催化剂", "type": "categorical", "values": ["A", "B", "C"]},
        {"name": "次数", "type": "discrete", "bounds": [1, 10]},
    ],
    "objectives": [{"name": "产率", "type": "maximize"}],
}


def _make_agent() -> BofireAgent:
    return BofireAgent()


# ---- Fake bofire 模块（真算路径） ----


class FakeStrategy:
    def __init__(self, domain):
        self.domain = domain

    def ask(self, n):
        return [{"温度": 50.0, "催化剂": "A", "次数": 5} for _ in range(n)]


class FakeStrategyApi:
    Strategy = type("Strategy", (), {"make": staticmethod(lambda domain: FakeStrategy(domain))})


class FakeBofire:
    class data_models:
        class strategies:
            api = FakeStrategyApi()


# ============ 功能（降级路径：bofire 未装） ============


def test_define_domain_degraded_returns_structure():
    out = _make_agent().invoke(
        "bofire_define_domain", {"variables": ASPIRIN_DOMAIN["variables"], "objectives": ASPIRIN_DOMAIN["objectives"]}
    )
    assert out["ok"] is True
    assert out["n_variables"] == 3
    assert out["n_objectives"] == 1
    assert out["n_constraints"] == 0
    assert out["degraded"] is True
    assert "pip install bofire" in out["note"]
    # domain 规范化：连续/离散带 bounds，分类带 values
    kinds = {v["type"] for v in out["domain"]["variables"]}
    assert kinds == {"continuous", "categorical", "discrete"}


def test_ask_candidates_degraded_returns_placeholders():
    out = _make_agent().invoke(
        "bofire_ask_candidates",
        {"domain": ASPIRIN_DOMAIN, "n_candidates": 3},
    )
    assert out["ok"] is True
    assert out["n_candidates"] == 3
    assert len(out["candidates"]) == 3
    assert out["degraded"] is True
    assert "pip install bofire" in out["note"]
    # 占位候选落在变量 bounds 内
    for cand in out["candidates"]:
        assert 20 <= cand["温度"] <= 80
        assert cand["催化剂"] in ("A", "B", "C")
        assert 1 <= cand["次数"] <= 10


def test_tell_results_degraded_accepts():
    out = _make_agent().invoke(
        "bofire_tell_results",
        {"experiments": [{"inputs": {"温度": 60, "催化剂": "B"}, "outputs": {"产率": 0.82}}]},
    )
    assert out["ok"] is True
    assert out["n_experiments"] == 1
    assert out["accepted"] is True
    assert out["degraded"] is True
    assert "pip install bofire" in out["note"]


def test_ask_default_n_candidates_is_five():
    out = _make_agent().invoke("bofire_ask_candidates", {"domain": ASPIRIN_DOMAIN})
    assert out["n_candidates"] == 5


def test_tell_results_validates_field_names_against_domain():
    agent = _make_agent()
    with pytest.raises(ValueError, match="未知变量"):
        agent.invoke(
            "bofire_tell_results",
            {"domain": ASPIRIN_DOMAIN, "experiments": [{"inputs": {"不存在变量": 1}, "outputs": {"产率": 0.5}}]},
        )
    with pytest.raises(ValueError, match="未知目标"):
        agent.invoke(
            "bofire_tell_results",
            {"domain": ASPIRIN_DOMAIN, "experiments": [{"inputs": {"温度": 50}, "outputs": {"不存在目标": 0.5}}]},
        )


# ============ 功能（真算路径：mock bofire） ============


def test_ask_real_path_uses_strategy(monkeypatch):
    monkeypatch.setattr("mcpserver.bofire.agent._load_bofire", lambda: FakeBofire)
    out = _make_agent().invoke("bofire_ask_candidates", {"domain": ASPIRIN_DOMAIN, "n_candidates": 2})
    assert out["ok"] is True
    assert out["n_candidates"] == 2
    assert out["degraded"] is False
    assert out["candidates"][0]["温度"] == 50.0


def test_define_domain_real_path_not_degraded(monkeypatch):
    monkeypatch.setattr("mcpserver.bofire.agent._load_bofire", lambda: FakeBofire)
    out = _make_agent().invoke(
        "bofire_define_domain", {"variables": ASPIRIN_DOMAIN["variables"], "objectives": ASPIRIN_DOMAIN["objectives"]}
    )
    assert out["degraded"] is False
    assert out["ok"] is True


def test_load_bofire_returns_none_when_missing():
    # 未安装依赖时 _load_bofire 返回 None（不抛错，走降级）；装了则返回 bofire 模块
    b = _load_bofire()
    assert b is None or hasattr(b, "data_models")


# ============ 参数校验 → ValueError ============


def test_unknown_command_raises_valueerror():
    with pytest.raises(ValueError, match="未知命令"):
        _make_agent().invoke("bofire_no_such", {})


@pytest.mark.parametrize(
    "cmd, params, match",
    [
        ("bofire_define_domain", {}, "variables 应为非空列表"),
        ("bofire_define_domain", {"variables": "not-list", "objectives": []}, "variables 应为非空列表"),
        ("bofire_define_domain", {"variables": [], "objectives": []}, "variables 应为非空列表"),
        (
            "bofire_define_domain",
            {"variables": [{"name": "x", "type": "magic", "bounds": [0, 1]}], "objectives": []},
            "type 应为",
        ),
        (
            "bofire_define_domain",
            {"variables": [{"name": "x", "type": "continuous", "bounds": [0]}], "objectives": []},
            "bounds",
        ),
        (
            "bofire_define_domain",
            {"variables": [{"name": "x", "type": "continuous", "bounds": [5, 5]}], "objectives": []},
            "下限 < 上限",
        ),
        (
            "bofire_define_domain",
            {"variables": [{"name": "x", "type": "categorical", "values": []}], "objectives": []},
            "values",
        ),
        ("bofire_define_domain", {"variables": ASPIRIN_DOMAIN["variables"]}, "objectives 应为非空列表"),
        (
            "bofire_define_domain",
            {"variables": ASPIRIN_DOMAIN["variables"], "objectives": [{"name": "o", "type": "neutral"}]},
            "type 应为",
        ),
        ("bofire_ask_candidates", {}, "domain 应为"),
        ("bofire_ask_candidates", {"domain": ASPIRIN_DOMAIN, "n_candidates": 0}, "1-100"),
        ("bofire_ask_candidates", {"domain": ASPIRIN_DOMAIN, "n_candidates": 101}, "1-100"),
        ("bofire_tell_results", {}, "experiments 应为非空列表"),
        ("bofire_tell_results", {"experiments": []}, "experiments 应为非空列表"),
        ("bofire_tell_results", {"experiments": [{"inputs": {"温度": 1}}]}, "inputs 与 outputs"),
    ],
)
def test_invalid_params_raise_valueerror(cmd, params, match):
    with pytest.raises(ValueError, match=match):
        _make_agent().invoke(cmd, params)


# ============ 契约：source 字段 ============


def test_all_commands_carry_source():
    agent = _make_agent()
    for cmd, params in [
        (
            "bofire_define_domain",
            {"variables": ASPIRIN_DOMAIN["variables"], "objectives": ASPIRIN_DOMAIN["objectives"]},
        ),
        ("bofire_ask_candidates", {"domain": ASPIRIN_DOMAIN, "n_candidates": 2}),
        ("bofire_tell_results", {"experiments": [{"inputs": {"温度": 60}, "outputs": {"产率": 0.8}}]}),
    ]:
        out = agent.invoke(cmd, params)
        assert out["source"] == "bofire", f"{cmd} 缺少 source='bofire'"


def test_manifest_has_three_commands():
    import json
    from pathlib import Path

    manifest = json.loads(Path("mcpserver/bofire/agent-manifest.json").read_text(encoding="utf-8"))
    assert manifest["license"] == "BSD-3-Clause"
    cmds = [c["command"] for c in manifest["capabilities"]["invocationCommands"]]
    assert cmds == ["bofire_define_domain", "bofire_ask_candidates", "bofire_tell_results"]
