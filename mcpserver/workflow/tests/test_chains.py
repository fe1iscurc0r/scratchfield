"""卷189-C 验收测试：声明式工具链（插值 / 重试 / 短路 / 种子链）。

工单验收：三条种子链各有 ≥3 个单测（插值/重试/短路）。
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mcpserver.workflow.chains import (  # noqa: E402
    Chain,
    ChainExecutor,
    ChainStep,
    cooccurrence_pairs,
    get_chain,
    load_chain,
    resolve,
    seed_chains,
    suggest_chains,
)

# ---------------------------------------------------------------- 插值

def test_resolve_basic_forms():
    ctx = {"query": "perovskite", "hits": [{"id": "a1"}, {"id": "a2"}],
           "meta": {"n": 3}}
    assert resolve("{{query}}", ctx) == "perovskite"
    assert resolve("{{meta.n}}", ctx) == 3
    assert resolve("{{hits[0].id}}", ctx) == "a1"
    assert resolve("{{hits[].id}}", ctx) == ["a1", "a2"]
    # 整串单占位 → 保留原类型（不转字符串）
    assert resolve("{{hits}}", ctx) == [{"id": "a1"}, {"id": "a2"}]


def test_resolve_embedded_and_nested():
    ctx = {"q": "x", "n": 2}
    assert resolve("prefix-{{q}}-suffix", ctx) == "prefix-x-suffix"
    out = resolve({"a": "{{q}}", "b": ["{{n}}"]}, ctx)
    assert out == {"a": "x", "b": [2]}
    assert resolve("{{missing}}", ctx) is None


def test_resolve_collect_over_scalar():
    """key[] 对非列表值退化为单元素列表（容错）。"""
    assert resolve("{{x[].id}}", {"x": {"id": 9}}) == [9]


# ---------------------------------------------------------------- 执行：插值

def _mk_executor(responses, calls=None):
    async def call(service, tool_call):
        if calls is not None:
            calls.append((service, tool_call))
        r = responses.get(service, {"status": "ok"})
        return r(service, tool_call) if callable(r) else r
    return ChainExecutor(call, sleep_fn=lambda s: asyncio.sleep(0))


def test_chain_passes_interpolated_params():
    calls: list = []
    ex = _mk_executor({"paper_miner": {"status": "ok", "data": [{"id": "p1"}]}}, calls)
    chain = Chain.from_dict({
        "name": "t",
        "steps": [{"tool": "paper_miner.extract_paper", "in": {"pid": "{{query}}"},
                   "out": "hit"}],
    })
    run = asyncio.run(ex.run(chain, {"query": "q1"}))
    assert run.status == "ok"
    svc, tc = calls[0]
    assert svc == "paper_miner" and tc["tool_name"] == "extract_paper"
    assert tc["pid"] == "q1"
    assert run.context["hit"]["data"] == [{"id": "p1"}]


# ---------------------------------------------------------------- 执行：短路 + 部分结果

def test_chain_short_circuit_keeps_partial():
    def failing(_s, _t):
        return {"status": "error", "message": "boom"}
    ex = _mk_executor({"good": {"status": "ok", "v": 1}, "bad": failing})
    chain = Chain.from_dict({
        "name": "t",
        "steps": [
            {"tool": "good.step1", "out": "first"},
            {"tool": "bad.step2", "out": "second"},
            {"tool": "good.step3", "out": "third"},
        ],
    })
    run = asyncio.run(ex.run(chain))
    assert run.status == "partial"
    assert run.failed_step == "bad.step2"
    assert [s.ok for s in run.steps] == [True, False]      # 第三步未执行
    assert run.context["first"]["v"] == 1                  # 已成功步骤结果保留
    assert "third" not in run.context


def test_chain_optional_step_does_not_short_circuit():
    def failing(_s, _t):
        return {"status": "error", "message": "boom"}
    ex = _mk_executor({"good": {"status": "ok"}, "bad": failing})
    chain = Chain.from_dict({
        "name": "t",
        "steps": [
            {"tool": "bad.opt", "out": "a", "optional": True},
            {"tool": "good.after", "out": "b"},
        ],
    })
    run = asyncio.run(ex.run(chain))
    assert run.status == "partial"
    assert "b" in run.context                          # 可选失败后继续
    assert run.failed_step == ""


# ---------------------------------------------------------------- 执行：重试

def test_chain_retry_then_success():
    attempts: list[int] = []

    def flaky(_s, _t):
        attempts.append(1)
        if len(attempts) < 3:
            raise RuntimeError("transient")
        return {"status": "ok", "n": len(attempts)}

    ex = _mk_executor({"flaky": flaky})
    chain = Chain.from_dict({
        "name": "t",
        "steps": [{"tool": "flaky.go", "out": "r"}],
        "retry": {"max": 3, "backoff": 0},
    })
    run = asyncio.run(ex.run(chain))
    assert run.status == "ok"
    assert run.steps[0].attempts == 3
    assert run.context["r"]["n"] == 3


def test_chain_retry_exhausted_fails():
    def always_bad(_s, _t):
        raise RuntimeError("nope")
    ex = _mk_executor({"x": always_bad})
    chain = Chain.from_dict({"name": "t",
                             "steps": [{"tool": "x.go"}],
                             "retry": {"max": 2, "backoff": 0}})
    run = asyncio.run(ex.run(chain))
    assert run.status == "failed"
    assert run.steps[0].attempts == 3          # 1 + max(2)
    assert "RuntimeError" in run.steps[0].error


# ---------------------------------------------------------------- 三条种子链

@pytest.mark.parametrize("name", ["paper_pipeline", "spectrum_scan", "daily_report"])
def test_seed_chain_runs_with_mock(name):
    """每条种子链至少有一个「全绿跑通」用例（mock 工具）。"""
    ex = _mk_executor({})            # 所有服务默认 status=ok
    chain = get_chain(name)
    assert chain is not None and chain.steps
    run = asyncio.run(ex.run(chain, {"query": "q", "source": "s",
                                     "since": "2026-10-01", "topic": "t"}))
    assert run.status == "ok"
    assert len(run.steps) == len(chain.steps)
    assert all(s.ok for s in run.steps)


@pytest.mark.parametrize("name", ["paper_pipeline", "spectrum_scan", "daily_report"])
def test_seed_chain_interpolates(name):
    """每条种子链：入参插值确实发生（mock 记录到解析后的参数）。"""
    calls: list = []
    ex = _mk_executor({}, calls)
    run = asyncio.run(ex.run(get_chain(name), {"query": "QQ", "source": "SS",
                                               "since": "D", "topic": "TT"}))
    assert run.status == "ok"
    flat = repr(calls)
    assert any(v in flat for v in ("QQ", "SS", "D", "TT"))


@pytest.mark.parametrize("name", ["paper_pipeline", "spectrum_scan", "daily_report"])
def test_seed_chain_short_circuits(name):
    """每条种子链：首步失败 → 短路且如实反映（optional 步除外）。"""
    chain = get_chain(name)

    def first_fails(service, _t):
        return ({"status": "error", "message": "boom"}
                if service == chain.steps[0].service else {"status": "ok"})
    ex = _mk_executor({"__default__": first_fails})
    # _mk_executor 用 service 键查表，改为直接构造：
    async def call(service, tool_call):
        return {"status": "error", "message": "boom"}
    ex = ChainExecutor(call, sleep_fn=lambda s: asyncio.sleep(0))
    run = asyncio.run(ex.run(chain))
    assert run.status == "failed"
    assert run.failed_step == chain.steps[0].tool
    assert len(run.steps) == 1


# ---------------------------------------------------------------- YAML / 推荐

def test_load_chain_from_yaml():
    yml = """
name: demo
steps:
  - tool: a.one
    in: {x: "{{y}}"}
    out: r
retry: {max: 1, backoff: 1}
"""
    c = load_chain(yml)
    assert c.name == "demo"
    assert c.max_retry == 1
    assert c.steps[0].service == "a" and c.steps[0].tool_name == "one"


def test_step_parsing_defaults():
    s = ChainStep.from_dict({"service": "svc"})
    assert s.service == "svc" and s.tool_name == "" and s.out == ""


def test_suggest_and_cooccurrence():
    stats = {
        "fast_tool": {"calls": 100, "error_rate": 0.0, "p95_ms": 10},
        "slow_tool": {"calls": 10, "error_rate": 0.5, "p95_ms": 900},
    }
    sug = suggest_chains(stats, top_n=2)
    assert sug[0]["tool"] == "fast_tool"       # 高频低失败排前
    pairs = cooccurrence_pairs([("c1", "A"), ("c1", "B"), ("c1", "B"),
                                ("c2", "A"), ("c2", "B")])
    assert pairs[0] == {"from": "A", "to": "B", "count": 2}


def test_run_registry_keeps_history():
    ex = _mk_executor({})
    run = asyncio.run(ex.run(get_chain("spectrum_scan"), {"source": "s"}))
    assert ex.get_run(run.run_id) is run
    assert ex.get_run("nope") is None


def test_seed_chains_count():
    assert len(seed_chains()) == 3
