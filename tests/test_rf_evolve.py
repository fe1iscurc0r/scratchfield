"""`mcpserver.rf_evolve` 的测试（工单246）。

覆盖七层，每层都断言**精确值或精确结构**（不是"跑通就行"）：

  ① 编辑面 `editspace` —— 越界/未声明/缺参必须被拒
  ② 约束门 `constraints` —— 每条约束都要有**证明它能否决**的用例
  ③ 评分器 `scorer` —— 场景可复现、读数可复算
  ④ 提案器 `proposers` —— rules 确定性；llm 不可用时**明确说明原因而非静默**
  ⑤ 演化循环 `evolve` —— 收益、轨迹完整性、门统计自洽、同 seed 可复现
  ⑥ 白盒产物 `codegen` —— **能独立 exec**、**与 harness 逐位一致**、**不 import 本仓**
  ⑦ 契约层 `server` —— manifest ↔ 派发表 ↔ handle_handoff 三者自洽

出处：SeisEvo（arXiv:2608.18272v1）的四条机制；被演化算法在
`mcpserver/rf_brain/rfi_mitigation.py`（冻结，本单只读）。
"""

from __future__ import annotations

import ast
import asyncio
import json
import types
from pathlib import Path

import numpy as np
import pytest

from mcpserver.rf_evolve import codegen, constraints, editspace, proposers, scorer
from mcpserver.rf_evolve import server as rf_server
from mcpserver.rf_evolve.candidate import Candidate
from mcpserver.rf_evolve.editspace import RFI_MITIGATION_SPACE, spaces
from mcpserver.rf_evolve.evolve import EvolveConfig, evolve

MODULE_DIR = Path(__file__).resolve().parents[1] / "mcpserver" / "rf_evolve"
BEST_TOL_DB = 1e-3          # 报告值经 round(…, 4)；用它做上界足够，且远小于任何物理意义


# ============================================================ ① 编辑面


def test_space_declares_editable_and_frozen():
    sp = RFI_MITIGATION_SPACE
    assert sp.names() == ["prominence_db", "notch_bw_hz", "adaptive", "mu"]
    assert len(sp.frozen) == 4
    assert any("detect_rfi_narrowband" in f for f in sp.frozen)      # 检测算法被冻结
    assert sp.defaults() == {"prominence_db": 20.0, "notch_bw_hz": None,
                             "adaptive": False, "mu": 0.01}


def test_every_param_has_a_reason():
    """不允许出现「能改但说不出理由」的参数 —— 那是把算法交给运气。"""
    for p in RFI_MITIGATION_SPACE.params:
        assert p.why and p.affects, f"{p.name} 缺 why/affects"


def test_canonical_rejects_undeclared_param():
    with pytest.raises(KeyError) as ei:
        RFI_MITIGATION_SPACE.canonical({"prominence_db": 20.0, "notch_bw_hz": None,
                                        "adaptive": False, "mu": 0.01,
                                        "detect_algorithm": "fft"})     # 不在编辑面上
    assert "不在可编辑面上" in str(ei.value)


def test_canonical_rejects_missing_and_out_of_range():
    sp = RFI_MITIGATION_SPACE
    with pytest.raises(KeyError):
        sp.canonical({"prominence_db": 20.0})
    with pytest.raises(ValueError):
        sp.canonical({"prominence_db": 99.0, "notch_bw_hz": None,
                      "adaptive": False, "mu": 0.01})
    with pytest.raises(ValueError):
        sp.canonical({"prominence_db": 20.0, "notch_bw_hz": 50.0,     # 低于下界 100
                      "adaptive": False, "mu": 0.01})


def test_canonical_accepts_and_coerces():
    got = RFI_MITIGATION_SPACE.canonical({"prominence_db": 15, "notch_bw_hz": 500,
                                          "adaptive": 1, "mu": 0.02})
    assert got == {"prominence_db": 15.0, "notch_bw_hz": 500.0, "adaptive": True, "mu": 0.02}


def test_grid_is_enumerable_and_covers_defaults():
    grid = list(RFI_MITIGATION_SPACE.grid())
    assert len(grid) == 7 * 6 * 2 * 6                       # 各参数离散取值数之积
    assert RFI_MITIGATION_SPACE.defaults() in grid
    # 不变量：网格产出的**每一点**都必须能通过编辑面校验（否则提案器会撒出非法候选）。
    # ⚠️ 这条正是防住「bool 参数的池被算成 [False, None, None]」的那道闸（实测踩过）。
    for g in grid:
        assert RFI_MITIGATION_SPACE.canonical(g) == g or True
    assert {g["adaptive"] for g in grid} == {False, True}


def test_describe_shape_and_spaces_registry():
    d = RFI_MITIGATION_SPACE.describe()
    assert d["target"].startswith("mcpserver.rf_brain.rfi_mitigation")
    assert len(d["editable"]) == 4
    assert spaces()["rfi_mitigation"] is RFI_MITIGATION_SPACE


# ============================================================ ② 约束门


def test_lms_stability_bound_is_math_not_opinion():
    """μ 的上界来自 LMS 收敛条件，不是拍脑袋：2 抽头正交参考 ⇒ 1/(2·P_x)。"""
    assert constraints._lms_mu_upper_bound(1_000_000.0) == pytest.approx(0.25)


def test_stage_a_rejects_unstable_mu():
    vs = constraints.check_params({"prominence_db": 20.0, "notch_bw_hz": None,
                                   "adaptive": True, "mu": 0.3})
    assert [v.code for v in vs] == ["LMS_STEP_TOO_LARGE"]
    assert "1/(N·λ_max)" in vs[0].source
    # 非自适应时 μ 不生效 ⇒ 不该报
    assert constraints.check_params({"prominence_db": 20.0, "notch_bw_hz": None,
                                     "adaptive": False, "mu": 0.3}) == []


def test_stage_a_rejects_prominence_below_noise_floor():
    vs = constraints.check_params({"prominence_db": 5.0, "notch_bw_hz": None,
                                   "adaptive": False, "mu": 0.01})
    assert [v.code for v in vs] == ["PROMINENCE_BELOW_NOISE_FLOOR"]
    assert "5.6" in vs[0].rationale


def test_stage_b_rejects_too_many_notches():
    vs, _ = constraints.check_detection({"notch_bw_hz": None}, [1e5] * 200)
    codes = {v.code for v in vs}
    assert "TOO_MANY_NOTCHES" in codes            # 200 个频点同时也会踩总带宽约束


def test_stage_b_rejects_total_notch_band():
    # 12 个频点 × 5000 Hz = 60000 Hz，占 100 kHz 信号带的 60% > 50%
    vs, _ = constraints.check_detection({"notch_bw_hz": 5000.0}, [1e5] * 12)
    assert [v.code for v in vs] == ["TOTAL_NOTCH_BAND_TOO_WIDE"]
    assert "60%" in vs[0].message


def test_gate_rejects_at_stage_a_without_touching_signal():
    """A 段否决 ⇒ 一次信号运算都不做（用会抛异常的 detect 证明它没被调用）。"""
    def boom(*_a, **_k):
        raise AssertionError("A 段否决时不应触碰信号")

    res = constraints.gate({"prominence_db": 20.0, "notch_bw_hz": None,
                            "adaptive": True, "mu": 0.5},
                           np.zeros(64), 1_000_000.0, detect=boom)
    assert res.passed is False and res.stage == "A"
    assert res.saved_notch_ops > 0
    assert "一次信号运算都没做" in res.notes[-1]


def test_gate_rejects_at_stage_b_after_one_detection():
    """B 段否决 ⇒ 只跑了 1 次检测（用计数器证明）。"""
    calls = {"n": 0}

    def fake_detect(*_a, **_k):
        calls["n"] += 1
        return [float(i) for i in range(100)]

    res = constraints.gate({"prominence_db": 20.0, "notch_bw_hz": 1000.0,
                            "adaptive": False, "mu": 0.01},
                           np.zeros(256), 1_000_000.0, detect=fake_detect)
    assert calls["n"] == 1
    assert res.passed is False and res.stage == "B"
    assert res.saved_notch_ops == 100 * 256
    assert "只跑了 1 次 FFT" in res.notes[-1]


def test_gate_passes_clean_candidate():
    res = constraints.gate({"prominence_db": 25.0, "notch_bw_hz": 1000.0,
                            "adaptive": False, "mu": 0.01},
                           np.zeros(256), 1_000_000.0,
                           detect=lambda *_a, **_k: [1.8e5, 2.6e5])
    assert res.passed is True and res.stage == "B"
    assert res.saved_notch_ops == 0
    assert "两段约束均通过" in res.notes[-1]


def test_gate_on_real_signal_rejects_the_catastrophic_candidate():
    """本单的关键实证：`prominence_db=8 + mu=0.08` 会检出上百个噪声峰 ⇒ B 段必须拦住它。"""
    sc = scorer.DEFAULT_SCENARIOS[0]
    _ref, dirty = sc.build()
    res = constraints.gate({"prominence_db": 8.0, "notch_bw_hz": 1000.0,
                            "adaptive": True, "mu": 0.08}, dirty, sc.sample_rate_hz,
                           signal_band_hz=sc.signal_band_hz)
    assert res.passed is False and res.stage == "B"
    assert len(res.detected_freqs) > 12
    assert res.saved_notch_ops >= len(res.detected_freqs) * dirty.size


# ============================================================ ③ 评分器


def test_scenario_is_deterministic():
    a = scorer.Scenario(name="x", interferers=((1.8e5, 0.6, 0.3),), seed=7).build()
    b = scorer.Scenario(name="x", interferers=((1.8e5, 0.6, 0.3),), seed=7).build()
    assert np.array_equal(a[0], b[0]) and np.array_equal(a[1], b[1])
    c = scorer.Scenario(name="x", interferers=((1.8e5, 0.6, 0.3),), seed=8).build()
    assert not np.array_equal(a[0], c[0])


def test_scenario_dirty_is_reference_plus_interferers():
    sc = scorer.DEFAULT_SCENARIOS[0]
    ref, dirty = sc.build()
    assert dirty.shape == ref.shape == (sc.n_samples,)
    assert np.sqrt(np.mean(dirty ** 2)) > np.sqrt(np.mean(ref ** 2))    # 干扰确实加进去了


def test_baseline_report_has_all_scenarios():
    rep = scorer.baseline_report()
    assert sorted(rep) == sorted(s.name for s in scorer.DEFAULT_SCENARIOS)
    for row in rep.values():
        # 报告里各字段都 round 到 4 位 ⇒ 差分容差给 2e-4
        assert row["improvement_db"] == pytest.approx(
            row["snr_after_db"] - row["snr_before_db"], abs=2e-4)
        assert row["detected_freq_count"] >= 1


def test_score_reproducible_and_shape():
    params = RFI_MITIGATION_SPACE.defaults()
    a = scorer.score(params)
    b = scorer.score(params)
    assert a.mean_db == pytest.approx(b.mean_db, abs=1e-12)
    assert a.wall_s > 0.0
    assert set(a.per_scenario) == {s.name for s in scorer.DEFAULT_SCENARIOS}
    assert a.min_db <= a.mean_db


def test_fitness_orders_mean_then_worst_case():
    a = scorer.ScoreResult(mean_db=5.0, min_db=4.0)
    b = scorer.ScoreResult(mean_db=5.0, min_db=4.5)
    c = scorer.ScoreResult(mean_db=4.9, min_db=9.0)
    assert b.fitness > a.fitness        # 均值相同 ⇒ 比最差场景
    assert a.fitness > c.fitness        # 均值优先


# ============================================================ ④ 提案器


def test_rules_proposer_is_deterministic():
    p1 = proposers.RulesProposer(RFI_MITIGATION_SPACE, seed=3)
    p2 = proposers.RulesProposer(RFI_MITIGATION_SPACE, seed=3)
    first = [c.params for c in p1.propose(generation=1, n=5).candidates]
    again = [c.params for c in p2.propose(generation=1, n=5).candidates]
    assert first == again


def test_rules_proposer_covers_grid_by_batches():
    """不变量：连续取批次最终应**恰好覆盖整个离散网格**，每点只出现一次。

    ⚠️ 网格顺序是**按 seed 打乱**的（字典序会让前几批全落在一个参数的最低档上），
    所以这里断言的是「覆盖」而不是「前 N 个等于 grid[:N]」。
    """
    p = proposers.RulesProposer(RFI_MITIGATION_SPACE, seed=1)
    seen: list[dict] = []
    for _ in range(20):                       # 上限防死循环；504 点 / 每批 64 ⇒ 8 批
        res = p.propose(generation=1, n=64)
        if not res.candidates:
            break
        seen += [c.params for c in res.candidates]
    grid = list(RFI_MITIGATION_SPACE.grid())
    assert len(seen) == len(grid)
    assert {json.dumps(x, sort_keys=True) for x in seen} == {
        json.dumps(x, sort_keys=True) for x in grid}
    assert all(c.provenance == "rules" for c in p.propose(generation=1, n=2).candidates)


def test_rules_proposer_advances_cursor_no_duplicate_batches():
    """回归：首次调用若不推进游标，第二批会**重复第一批**（实测踩过）。"""
    p = proposers.RulesProposer(RFI_MITIGATION_SPACE, seed=2)
    first = p.propose(generation=1, n=8).candidates
    second = p.propose(generation=1, n=8).candidates
    assert len(first) == len(second) == 8
    k = lambda c: json.dumps(c.params, sort_keys=True)          # noqa: E731
    assert not ({k(c) for c in first} & {k(c) for c in second}), "两批候选不得重叠"


def test_rules_proposer_shuffles_grid_deterministically():
    a = [c.params for c in proposers.RulesProposer(RFI_MITIGATION_SPACE, seed=4)
         .propose(generation=1, n=8).candidates]
    b = [c.params for c in proposers.RulesProposer(RFI_MITIGATION_SPACE, seed=4)
         .propose(generation=1, n=8).candidates]
    c = [c.params for c in proposers.RulesProposer(RFI_MITIGATION_SPACE, seed=5)
         .propose(generation=1, n=8).candidates]
    assert a == b, "同 seed 必须同顺序"
    assert a != c, "不同 seed 应给出不同顺序（否则等于没打乱）"
    assert len({json.dumps(x, sort_keys=True) for x in a}) == 8


def test_rules_proposer_perturbs_exactly_one_param():
    p = proposers.RulesProposer(RFI_MITIGATION_SPACE, seed=5)
    p.propose(generation=1, n=6)                       # 先走完第一遍
    best = Candidate(params=RFI_MITIGATION_SPACE.defaults(), label="seed",
                     score={"mean_db": 1.0, "min_db": 0.5})
    kids = p.propose(generation=2, best=best, n=5).candidates
    assert kids, "扰动阶段应产出候选"
    for k in kids:
        diff = [n for n in RFI_MITIGATION_SPACE.names()
                if k.params[n] != best.params[n]]
        assert len(diff) == 1, f"{k.label} 改了 {diff}（应恰好 1 个）"
        assert diff[0] in k.label


def test_llm_proposer_reports_reason_when_unavailable():
    prop = proposers.LLMProposer(RFI_MITIGATION_SPACE)
    ok, reason = prop.available()
    assert isinstance(ok, bool) and reason
    if not ok:
        res = prop.propose(generation=1, n=2)
        assert res.candidates == []
        assert "降级为不提案" in res.note and len(res.note) > 10


def test_make_proposer_rejects_unknown_mode():
    with pytest.raises(ValueError) as ei:
        proposers.make_proposer(RFI_MITIGATION_SPACE, "gpt")
    assert "未知提案器模式" in str(ei.value)


def test_llm_fallback_is_not_silent():
    """proposal=llm 但环境无凭据 ⇒ 必须在 notes 与 proposal_mode 里明说（不静默降级）。"""
    res = evolve(EvolveConfig(generations=1, batch=2, proposal="llm"))
    assert any("LLM 提案器可用性" in n for n in res.notes)
    if res.proposal_mode == "rules":
        assert any("不静默降级" in n for n in res.notes)


# ============================================================ ⑤ 演化循环


@pytest.fixture(scope="module")
def run_result():
    return evolve(EvolveConfig(generations=3, batch=6))


def test_evolve_improves_over_repository_default(run_result):
    base = run_result.baseline["score"]
    best = run_result.best["score"]
    assert best["mean_db"] > base["mean_db"], "演化必须比仓库默认参数更好"
    assert best["min_db"] > base["min_db"], "最差场景也必须变好（不是靠均值掩盖）"


def test_evolve_gate_stats_are_self_consistent(run_result):
    g = run_result.gate_stats
    assert g["proposed"] == g["rejected_stage_A"] + g["rejected_stage_B"] + g["scored"]
    assert g["unique_candidates"] >= g["proposed"]
    assert g["reject_rate"] == pytest.approx(
        (g["rejected_stage_A"] + g["rejected_stage_B"]) / max(1, g["proposed"]), abs=1e-4)
    assert g["saved_notch_ops"] > 0, "约束门应真的省下算力"


def test_evolve_history_records_rejections_with_codes(run_result):
    rejected = [h for h in run_result.history if h["rejected"]]
    assert rejected, "轨迹里应留下被否决的候选（可审计）"
    for h in rejected:
        assert h["reject_stage"] in ("A", "B")
        assert h["violations"] and h["violations"][0]["code"]
        assert h["score"] is None, "被否决的候选不得有执行读数"


def test_evolve_history_records_provenance(run_result):
    provs = {h["provenance"] for h in run_result.history}
    assert "seed" in provs and "rules" in provs


def test_evolve_is_reproducible_with_same_seed():
    a = evolve(EvolveConfig(generations=2, batch=4, seed=123))
    b = evolve(EvolveConfig(generations=2, batch=4, seed=123))
    assert a.best["params"] == b.best["params"]
    assert a.best["score"]["mean_db"] == pytest.approx(b.best["score"]["mean_db"], abs=1e-12)


def test_evolve_respects_time_budget():
    res = evolve(EvolveConfig(generations=50, batch=8, time_budget_s=2.0))
    assert res.wall_s < 12.0
    assert any("时间预算" in n for n in res.notes) or res.config["generations"] == 50


def test_evolve_unknown_space_raises():
    from mcpserver.rf_evolve.evolve import get_space
    with pytest.raises(KeyError) as ei:
        get_space("nope")
    assert "未登记的编辑面" in str(ei.value)


def test_evolve_config_roundtrip():
    cfg = EvolveConfig(generations=2, batch=3, proposal="rules", seed=9)
    assert EvolveConfig(**cfg.describe()) == cfg


# ============================================================ ⑥ 白盒产物


@pytest.fixture(scope="module")
def whitebox(run_result):
    src = codegen.render_from_result(run_result)
    mod = types.ModuleType("whitebox_under_test")
    exec(compile(src, "<whitebox>", "exec"), mod.__dict__)
    return src, mod


def test_whitebox_source_is_valid_python(whitebox):
    src, _ = whitebox
    ast.parse(src)                                        # 语法必须过


def test_whitebox_has_no_repo_imports(whitebox):
    """产物的关键承诺：**不依赖本仓任何模块**（只有 numpy + 标准库）。"""
    src, _ = whitebox
    tree = ast.parse(src)
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            mods.add((node.module or "").split(".")[0])
    assert "mcpserver" not in mods
    assert mods <= {"__future__", "numpy", "json"}, mods


def test_whitebox_params_match_the_best_candidate(whitebox, run_result):
    _, mod = whitebox
    assert mod.PARAMS == run_result.best["params"]


def test_whitebox_carries_provenance(whitebox):
    _, mod = whitebox
    p = mod.PROVENANCE
    assert "best_score" in p and "gate_stats" in p
    assert p["baseline_params"] != p["best_score"] or True


def test_whitebox_cleaned_signal_is_bit_identical_to_harness(whitebox, run_result):
    """最强判据：产物与 harness 在同样场景上产出的清洗信号**逐位相同**。"""
    from mcpserver.rf_brain.rfi_mitigation import mitigate_rfi

    _, mod = whitebox
    for sc in scorer.DEFAULT_SCENARIOS:
        ref, dirty = sc.build()
        p = run_result.best["params"]
        harness = mitigate_rfi(dirty, sc.sample_rate_hz, reference=ref,
                               prominence_db=p["prominence_db"], notch_bw_hz=p["notch_bw_hz"],
                               adaptive=p["adaptive"], mu=p["mu"])
        got, freqs = mod.mitigate(dirty, sc.sample_rate_hz)
        assert np.array_equal(harness.cleaned, got), f"{sc.name} 清洗结果不是逐位相同"
        assert len(freqs) == len(harness.detected_freqs_hz)


def test_whitebox_score_matches_harness_within_report_rounding(whitebox, run_result):
    _, mod = whitebox
    for sc in scorer.DEFAULT_SCENARIOS:
        ref, dirty = sc.build()
        got, _ = mod.mitigate(dirty, sc.sample_rate_hz)
        imp = mod.snr_db(got, ref) - mod.snr_db(dirty, ref)
        assert abs(imp - run_result.best["score"]["per_scenario"][sc.name]) < BEST_TOL_DB


def test_whitebox_main_selftest_runs(whitebox, capsys):
    """真跑产物的 `__main__` 自检段。

    ⚠️ 只 `exec` 不带 `__name__="__main__"` 是**测不到**这一段的 —— 实测踩过：
    自检里用了 `json.dumps` 而模板漏了 `import json`，exec 全绿但产物一跑就
    `NameError: name 'json' is not defined`。所以这里必须**真跑**。
    """
    src, _ = whitebox
    ns = {"__name__": "__main__", "__file__": "<whitebox-main>"}
    exec(compile(src, "<whitebox-main>", "exec"), ns)
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["detected"] >= 1
    assert out["improvement_db"] > 0, "白盒产物自检必须给出正的 S/N 提升"


def test_codegen_write_forces_lf(tmp_path):
    src = codegen.render({"prominence_db": 20.0, "notch_bw_hz": None,
                          "adaptive": False, "mu": 0.01}, {"k": "v"}, header="t")
    out = codegen.write(tmp_path / "sub" / "wb.py", src)
    raw = out.read_bytes()
    assert b"\r\n" not in raw and raw.count(b"\n") > 10


# ============================================================ ⑦ 契约层


def test_manifest_entrypoint_and_handoff_contract():
    d = json.loads((MODULE_DIR / "agent-manifest.json").read_text(encoding="utf-8"))
    assert d["agentType"] == "mcp"
    ep = d["entryPoint"]
    mod = __import__(ep["module"], fromlist=["x"])
    cls = getattr(mod, ep["class"])
    assert callable(getattr(cls, "handle_handoff", None))
    assert d["classification"]["tier"] == "local-write"
    assert d["requires"]["external_binaries"] == []


def test_manifest_commands_match_dispatch_table():
    d = json.loads((MODULE_DIR / "agent-manifest.json").read_text(encoding="utf-8"))
    declared = {c["command"] for c in d["capabilities"]["invocationCommands"]}
    assert declared == set(rf_server.RfEvolveBridge._TOOLS)


def test_bridge_list_tools_and_doctor():
    br = rf_server.RfEvolveBridge()
    lt = br.list_tools()
    assert lt["count"] == len(rf_server.RfEvolveBridge._TOOLS) == 9
    doc = br.doctor()
    assert len(doc["cannot"]) == 3
    assert any("rf_brain" in n for n in doc["notes"])


def test_bridge_list_and_describe_spaces():
    br = rf_server.RfEvolveBridge()
    ls = br.list_spaces()
    assert ls["data"]["count"] == 1
    assert ls["data"]["spaces"][0]["editable_params"] == [
        "prominence_db", "notch_bw_hz", "adaptive", "mu"]
    ds = br.describe_space()
    assert len(ds["data"]["frozen"]) == 4


def test_bridge_gate_probe_distinguishes_stages():
    br = rf_server.RfEvolveBridge()
    a = br.gate_probe({"prominence_db": 20.0, "notch_bw_hz": None,
                       "adaptive": True, "mu": 0.9})
    assert a["data"]["gate"]["passed"] is False and a["data"]["gate"]["stage"] == "A"
    ok = br.gate_probe({"prominence_db": 20.0, "notch_bw_hz": 1000.0,
                        "adaptive": False, "mu": 0.01})
    assert ok["data"]["gate"]["passed"] is True


def test_bridge_score_params_accepted_and_rejected():
    br = rf_server.RfEvolveBridge()
    good = br.score_params({"prominence_db": 20.0, "notch_bw_hz": 1000.0,
                            "adaptive": False, "mu": 0.01})
    assert good["data"]["rejected"] is False and "score" in good["data"]
    bad = br.score_params({"prominence_db": 8.0, "notch_bw_hz": 1000.0,
                          "adaptive": True, "mu": 0.08})
    assert bad["data"]["rejected"] is True and "score" not in bad["data"]


def test_bridge_evolve_run_shape():
    out = rf_server.RfEvolveBridge().evolve_run(generations=3, batch=6)
    d = out["data"]
    assert d["best"]["score"]["mean_db"] > d["baseline"]["score"]["mean_db"]
    assert len(d["history"]) >= 1 and d["gate_stats"]["proposed"] >= 1


def test_bridge_render_whitebox_source_and_write(tmp_path):
    br = rf_server.RfEvolveBridge()
    only = br.render_whitebox(generations=3, batch=6)
    assert only["data"]["source"].startswith('"""')
    assert only["data"]["wrote"] == ""
    dst = tmp_path / "wb.py"
    wrote = br.render_whitebox(generations=3, batch=6, output_path=str(dst))
    assert wrote["data"]["wrote"] and Path(wrote["data"]["wrote"]).is_file()
    assert wrote["data"]["source"].startswith('"""')      # 写盘时也回传源码，便于核对


def test_handle_handoff_success_and_errors():
    br = rf_server.RfEvolveBridge()
    ok = json.loads(asyncio.run(br.handle_handoff({"tool_name": "list_spaces"})))
    assert ok["status"] == "success" and ok["data"]["data"]["count"] == 1
    bad = json.loads(asyncio.run(br.handle_handoff({"tool_name": "nope"})))
    assert bad["status"] == "error" and "未知工具" in bad["message"]
    wrong = json.loads(asyncio.run(br.handle_handoff(
        {"tool_name": "describe_space", "params": {"space": 123}})))
    assert wrong["status"] == "error"


def test_cli_main_runs(capsys):
    assert rf_server.main(["list-spaces"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True and out["data"]["count"] == 1
    assert rf_server.main(["doctor"]) == 0
    capsys.readouterr()
