"""工单227 任务一 · trace 诊断器测试（合成轨迹：单因果跳/无因果跳/多跳注入）。

⚠️ 关键前提：hop.out 必须是"该步函数在该 hop.inp 下的真实产出"（自洽）——
否则诊断器比较的是手写值与重放值之差，那是数据错误不是归因结论。
本测试用 `_run()`（真跑注册函数）生成轨迹，杜绝手写 out。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from tools.trace_diagnose import _REGISTRY, Hop, delta_score, diagnose, replay_from  # noqa: E402


def _run(names: list[str], inputs: list[dict], det: list[bool] | None = None) -> list[Hop]:
    """按注册函数真跑一遍，产出自洽轨迹（out = fn(inp with _prev)）。"""
    det = det or [True] * len(names)
    hops: list[Hop] = []
    outs: list = []
    for n, inp, d in zip(names, inputs, det):
        out = _REGISTRY[n]({**inp, "_prev": outs[-1] if outs else None})
        outs.append(out)
        hops.append(Hop(n, inp, out, d))
    return hops


NAMES = ["fetch", "transform", "report"]


class TestSingleCausal:
    def test_causal_hop_is_first_significant(self):
        """注入点=跳2（transform 的 drop_first）→ 因果跳=2。"""
        good = _run(NAMES, [{"rows": [1, 2]}, {}, {"label": "r"}])
        bad = _run(NAMES, [{"rows": [1, 2]}, {"drop_first": True}, {"label": "r"}])
        assert good[-1].out != bad[-1].out, "合成轨迹必须先造出真实差异"
        res = diagnose(bad, good)
        assert res.causal_hop == 2, f"delta={res.hop_deltas}"
        assert res.hop_deltas[0] == pytest.approx(0.0), "跳1 与参考一致 → 冻结无差异"


class TestNoCausal:
    def test_identical_trajectories_no_cause(self):
        """失败=成功（无病）→ 全 delta=0 → 因果跳=None。"""
        chain = _run(NAMES, [{"rows": [1]}, {}, {"label": "r"}])
        res = diagnose(chain, _run(NAMES, [{"rows": [1]}, {}, {"label": "r"}]))
        assert res.causal_hop is None
        assert all(d == pytest.approx(0.0) for d in res.hop_deltas), res.hop_deltas


class TestMultiHop:
    def test_first_hop_injection(self):
        """注入点=跳1（fetch 数据坏）→ 因果跳=1。"""
        good = _run(NAMES, [{"rows": [10]}, {}, {"label": "r"}])
        bad = _run(NAMES, [{"rows": [5]}, {}, {"label": "r"}])
        res = diagnose(bad, good)
        assert res.causal_hop == 1, f"delta={res.hop_deltas}"

    def test_llm_hop_marked_low_confidence(self):
        """非确定跳（LLM 采样）置信标注为低。"""
        names = ["fetch", "report"]
        good = _run(names, [{"rows": [1]}, {"label": "r"}])
        bad = _run(names, [{"rows": [1]}, {"label": "r"}], det=[True, False])
        res = diagnose(bad, good)
        assert "低" in res.confidences[1]
        assert "高" in res.confidences[0]


class TestReplay:
    def test_replay_from_prefix(self):
        """重放引擎：从指定跳起用给定前置输出续跑。"""
        hops = _run(NAMES, [{"rows": [1, 2, 3]}, {}, {"label": "r"}])
        out = replay_from(hops, [{"rows": [7]}], start=1)   # 换掉 fetch 输出，重放后两跳
        assert out == {"total": 7, "label": "r"}

    def test_unregistered_step_raises(self):
        with pytest.raises(KeyError):
            replay_from([Hop("nope", {}, None)], [], start=0)


class TestDelta:
    def test_equal_zero(self):
        assert delta_score({"a": 1}, {"a": 1}) == 0.0

    def test_partial(self):
        d = delta_score({"a": 1, "b": 2}, {"a": 1, "b": 3})
        assert 0 < d < 1

    def test_disjoint_keys(self):
        assert delta_score({"a": 1}, {"b": 1}) == 1.0


def test_registry_ready():
    assert all(n in _REGISTRY for n in NAMES)
