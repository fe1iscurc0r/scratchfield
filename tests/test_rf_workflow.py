"""工单242 验收：Prompt→RF 工程工作流（rf_workflow）。

覆盖：

- 任务一骨架：五接口语义、handoff 契约、manifest entryPoint、错误路径（未知工具/未知 goal/
  非法 id/工作流不存在/无输出/输出不存在）
- 数值正确性：lora_phy 的 Tsym/ToA/标称速率对照 LoRaWAN 公开表；校验边界；dBm↔mW 往返
- 频谱：双边谱口径（回归"只取半边 ⇒ 占用带宽减半"这个坑）
- 任务二 PoC：start → step → explain 全链路真跑（子进程），四件套落盘、全 LF、指标与仓内一致
- 交付纪律：沙箱 vendor 副本字节等同真值源、状态文件无绝对路径、产物无 `null` 字面量
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from mcpserver.rf_workflow import explainer, lora_phy, prompt_to_script, server, sim_runner

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.core]

GOAL = "设计一个 LoRa chirp 在 433 MHz 的发射功率估算器，给定扩频因子 7，输出功率 14 dBm"
PKG_ROOT = Path(server.__file__).resolve().parent
REPO_ROOT = PKG_ROOT.parent.parent


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    """沙箱根重定向到 tmp（不碰仓内 sandbox/），并清掉串行标记。"""
    root = tmp_path / "sandbox"
    monkeypatch.setenv(sim_runner.ENV_SANDBOX, str(root))
    sim_runner.reset_for_tests()
    yield root
    sim_runner.reset_for_tests()


@pytest.fixture()
def bridge(sandbox):
    return server.RfWorkflowBridge()


# ---------------------------------------------------------------------------
# 任务一 · 数值正确性（对照公开的 LoRaWAN 空中时间表）
# ---------------------------------------------------------------------------


def test_lora_phy_matches_reference_values():
    # SF7 / BW125 kHz：Tsym = 128/125k = 1.024 ms，chirp 斜率 = BW^2/2^SF = 122.0703 MHz/s
    assert lora_phy.symbol_duration_s(7, 125e3) == pytest.approx(1.024e-3, rel=1e-9)
    assert lora_phy.chirp_rate_hz_per_s(7, 125e3) == pytest.approx(122.0703e6, rel=1e-5)
    assert lora_phy.chip_rate_chips_per_s(125e3) == pytest.approx(125e3)
    assert lora_phy.symbol_rate_symbols_per_s(7, 125e3) == pytest.approx(976.5625)
    # 标称速率 = SF * BW/2^SF * 4/5
    assert lora_phy.nominal_bitrate_bps(7, 125e3, cr=1) == pytest.approx(5468.75, rel=1e-9)
    # 16 B payload / CRC 开 / 显式头 / CR4-5 → 38 符号 + 12.25 符号前导 = 51.456 ms（公开表同值）
    assert lora_phy.payload_symbol_count(7, 16, cr=1, crc=1) == 38
    assert lora_phy.time_on_air_s(7, 125e3, 16, cr=1, crc=1) == pytest.approx(51.456e-3, rel=1e-6)
    # 已知边界行为：SF11/12 且 BW<=125k 才开低速率优化
    assert lora_phy.low_data_rate_optimize(10, 125e3) == 0
    assert lora_phy.low_data_rate_optimize(11, 125e3) == 1
    assert lora_phy.low_data_rate_optimize(12, 500e3) == 0


def test_lora_phy_energy_and_link_budget():
    metrics = lora_phy.compute_metrics(with_spectrum=False)
    # 14 dBm = 25.1189 mW
    assert metrics["tx_power_mw"] == pytest.approx(25.1189, rel=1e-5)
    assert metrics["energy_per_symbol_uj"] == pytest.approx(
        lora_phy.dbm_to_mw(14.0) * 1e-3 * 1.024e-3 * 1e6, rel=1e-6)
    # FSPL @433.92 MHz / 1 km = 20log10(d) + 20log10(f) - 147.55
    assert lora_phy.free_space_path_loss_db(433.92e6, 1000.0) == pytest.approx(85.20, abs=0.02)
    assert metrics["link_margin_db"] == pytest.approx(
        metrics["rx_power_dbm"] - metrics["sensitivity_dbm"], abs=0.01)
    # EIRP/ERP：0 dBi 天线、0 馈线损耗时 ERP 比 EIRP 低 2.15 dB
    assert lora_phy.erp_dbm(14.0) == pytest.approx(14.0 - lora_phy.DIPOLE_TO_ISOTROPIC_DB, rel=1e-9)
    # 合规化传导功率上限：ERP 恰好顶上限值
    assert lora_phy.max_tx_power_dbm_for_erp() == pytest.approx(
        lora_phy.ERP_LIMIT_DBM + lora_phy.DIPOLE_TO_ISOTROPIC_DB, rel=1e-9)


def test_lora_phy_power_conversion_rejects_non_positive():
    assert lora_phy.mw_to_dbm(lora_phy.dbm_to_mw(14.0)) == pytest.approx(14.0, rel=1e-9)
    with pytest.raises(ValueError):
        lora_phy.mw_to_dbm(0.0)
    with pytest.raises(ValueError):
        lora_phy.free_space_path_loss_db(433.92e6, 0.0)


@pytest.mark.parametrize("bad,keyword", [
    ({"sf": 5}, "sf"),
    ({"sf": 13}, "sf"),
    ({"cr": 9}, "cr"),
    ({"cr": True}, "cr"),
    ({"payload_bytes": 0}, "payload_bytes"),
    ({"payload_bytes": 256}, "payload_bytes"),
    ({"bw_hz": 0}, "bw_hz"),
    ({"sample_rate_hz": 100e3}, "sample_rate_hz"),
])
def test_compute_metrics_rejects_out_of_range(bad, keyword):
    with pytest.raises(ValueError) as info:
        lora_phy.compute_metrics(bad)
    assert keyword in str(info.value)


def test_compute_metrics_reports_regulatory_and_band_fields():
    metrics = lora_phy.compute_metrics()
    assert metrics["duty_cycle_ok"] is True and metrics["duty_cycle_limit_pct"] == 10.0
    # 14 dBm + 0 dBi 天线 → ERP 11.85 dBm > 10 dBm 限值
    assert metrics["erp_ok"] is False and metrics["erp_dbm"] == pytest.approx(11.85, abs=0.01)
    # DEFAULT_SPEC 取子带中心 433.92 MHz（与固件一致）→ 在带内
    assert metrics["in_ism_433"] is True
    assert metrics["ism_433_range_mhz"] == [433.05, 434.79]
    # 而 goal 里字面的「433 MHz」严格说在子带之外 —— 本模块如实报告，不四舍五入糊过去
    offset = lora_phy.compute_metrics({"freq_hz": 433e6}, with_spectrum=False)
    assert offset["in_ism_433"] is False
    assert lora_phy.in_ism_433(433.05e6) is True and lora_phy.in_ism_433(434.79e6) is True
    assert metrics["min_tx_period_s_for_duty_cycle"] == pytest.approx(
        metrics["time_on_air_ms"] / 1e3 / 0.10, abs=1e-3)


# ---------------------------------------------------------------------------
# 任务一 · 频谱口径（回归：只取单边 ⇒ 占用带宽减半）
# ---------------------------------------------------------------------------


def test_spectrum_is_two_sided_and_occupies_full_bandwidth():
    samples = lora_phy.synth_chirp_iq(7, 125e3, 250e3, symbols=1)
    assert len(samples) == 256
    freqs, mags = lora_phy.spectrum_db(samples, 250e3)
    assert len(freqs) == len(mags) and freqs[0] < 0 < freqs[-1], "必须是双边谱"
    obw6 = lora_phy.occupied_bandwidth_hz(freqs, mags, drop_db=-6.0)
    obw99 = lora_phy.occupied_bandwidth_hz(freqs, mags, energy_fraction=0.99)
    # chirp 扫频铺满 BW：-6 dB 带宽应接近 BW（首版只取半边 ⇒ 0.53*BW，本断言锁死该回归）
    assert 0.90 * 125e3 < obw6 < 1.05 * 125e3, obw6
    assert 1.0 * 125e3 < obw99 < 1.15 * 125e3, obw99


def test_spectrum_window_choice_is_documented():
    samples = lora_phy.synth_chirp_iq(7, 125e3, 250e3, symbols=1)
    rect = lora_phy.occupied_bandwidth_hz(*lora_phy.spectrum_db(samples, 250e3, window="rect"),
                                          drop_db=-6.0)
    hann = lora_phy.occupied_bandwidth_hz(*lora_phy.spectrum_db(samples, 250e3, window="hann"),
                                          drop_db=-6.0)
    # chirp 必须等时加权（rect）；加窗会按窗形压掉扫频两端 —— 用数值把这个结论钉住
    assert rect > 1.8 * hann
    with pytest.raises(ValueError):
        lora_phy.spectrum_db(samples, 250e3, window="blackman")


# ---------------------------------------------------------------------------
# 任务一 · prompt 解析 / 脚本生成
# ---------------------------------------------------------------------------


def test_parse_goal_extracts_params_and_records_sources():
    spec = prompt_to_script.parse_goal(GOAL)
    assert spec["freq_hz"] == pytest.approx(433e6)
    assert spec["sf"] == 7
    assert spec["tx_power_dbm"] == pytest.approx(14.0)
    sources = spec["spec_sources"]
    assert sources["freq_hz"] == "goal" and sources["sf"] == "goal"
    assert sources["bw_hz"] == "default" and sources["payload_bytes"] == "default"

    detailed = prompt_to_script.parse_goal("LoRa 功率估算 使用 BW 250 kHz，SF=9，CR 4/8，32 字节，868 MHz")
    assert detailed["bw_hz"] == pytest.approx(250e3)
    assert detailed["sf"] == 9 and detailed["cr"] == 4 and detailed["payload_bytes"] == 32


def test_classify_and_generate_reject_unknown_goal(tmp_path):
    assert prompt_to_script.classify(GOAL) == prompt_to_script.KIND_LORA
    assert prompt_to_script.classify("帮我调一下天线驻波") is None
    result = prompt_to_script.generate("帮我调一下天线驻波", tmp_path)
    assert result["ok"] is False and result["error"] == "unsupported_goal"
    assert result["supported"] == [prompt_to_script.KIND_LORA]


def test_generate_writes_self_contained_sandbox(tmp_path):
    result = prompt_to_script.generate(GOAL, tmp_path, rf_lib="stdlib")
    assert result["ok"] is True
    script = Path(result["script_path"]).read_text(encoding="utf-8")
    compile(script, result["script_path"], "exec")          # 语法必须成立
    assert "null" not in script and "true" not in script and "false" not in script, \
        "规格字面量必须是合法 Python（回归 json.dumps 写出 null 的坑）"
    # 守卫自身的字面量用拼接构造，避免本文件被自己的"无绝对路径"扫描自命中
    posix_home = "/" + "home/"
    drive_letter = "D" + ":"
    assert drive_letter not in script and posix_home not in script, "生成的脚本不得含本机绝对路径"
    vendored = Path(result["vendored_path"])
    assert vendored.read_bytes() == Path(lora_phy.__file__).read_bytes(), "vendor 副本须字节等同真值源"


def test_build_script_validates_rf_lib():
    with pytest.raises(ValueError):
        prompt_to_script.build_script(GOAL, prompt_to_script.parse_goal(GOAL), "julia")


def test_numpy_variant_degrades_explicitly_when_numpy_absent(tmp_path, monkeypatch):
    """rf_lib=numpy 时脚本必须能跑完；numpy 缺失要在产物里留 FALLBACK 标记。"""
    result = prompt_to_script.generate(GOAL, tmp_path, rf_lib="numpy")
    assert result["ok"] is True
    outcome = sim_runner.run_script(result["script_path"], workflow_id="t-numpy")
    assert outcome["ok"] is True, outcome.get("stdout")
    check = outcome["result"]["numpy_cross_check"]
    assert check["backend"] in ("numpy", "stdlib(FALLBACK)")
    if check["backend"] == "numpy":
        assert check["agrees_within_5pct"] is True


# ---------------------------------------------------------------------------
# 任务一 · sim_runner 的收敛与串行
# ---------------------------------------------------------------------------


def test_safe_workflow_id_and_path_convergence(sandbox):
    assert sim_runner.safe_workflow_id("")[1] is None
    assert sim_runner.safe_workflow_id("rfw-1")[0] == "rfw-1"
    for bad in ("../evil", "a/b", "x" * 65, "a b", "点"):
        assert sim_runner.safe_workflow_id(bad)[1] == "invalid_workflow_id"
    with pytest.raises(ValueError):
        sim_runner.workflow_dir("../evil")
    with pytest.raises(ValueError):
        sim_runner.contained_script_path("rfw-1", "../outside.py")
    with pytest.raises(ValueError):
        sim_runner.contained_script_path("rfw-1", "/abs/outside.py")


def test_run_script_patterns_and_failures(tmp_path, sandbox):
    missing = sim_runner.run_script(tmp_path / "nope.py")
    assert missing["error"] == "script_not_found"

    script = tmp_path / "boom.py"
    script.write_text("import sys\nprint('partial')\nsys.exit(3)\n", encoding="utf-8", newline="\n")
    outcome = sim_runner.run_script(script)
    assert outcome["ok"] is False and outcome["exit_code"] == 3
    assert (tmp_path / "log.txt").read_text(encoding="utf-8").strip() == "partial"
    assert sim_runner.parse_metrics(outcome["stdout"]) is None

    assert sim_runner.parse_metrics("noise\n__RF_METRICS__ {\"a\": 1}\n") == {"a": 1}
    assert sim_runner.parse_metrics("__RF_METRICS__ not-json\n") is None
    assert sim_runner.read_result(tmp_path) is None


def test_run_script_serial_guard(tmp_path, sandbox):
    script = tmp_path / "ok.py"
    script.write_text("print('hi')\n", encoding="utf-8", newline="\n")
    outcome = sim_runner.run_script(script, workflow_id="t-serial")
    assert outcome["ok"] is True
    sim_runner._running = "other"                                   # noqa: SLF001 - 显式占位以验证串行
    try:
        busy = sim_runner.run_script(script)
        assert busy["error"] == "busy" and busy["running"] == "other"
    finally:
        sim_runner.reset_for_tests()


def test_run_script_rejects_bad_timeout_and_log_name(tmp_path, sandbox):
    script = tmp_path / "ok.py"
    script.write_text("print('hi')\n", encoding="utf-8", newline="\n")
    assert sim_runner.run_script(script, timeout_s=-1)["error"] == "invalid_timeout"
    assert sim_runner.run_script(script, timeout_s=1e9)["error"] == "invalid_timeout"
    assert sim_runner.run_script(script, log_name="../x.txt")["error"] == "invalid_log_name"


# ---------------------------------------------------------------------------
# 任务二 · 全链路 PoC（真跑子进程）
# ---------------------------------------------------------------------------


def test_full_workflow_poc_produces_four_artifacts(bridge, sandbox):
    started = bridge.start_workflow(GOAL, workflow_id="rfw-test-sf7")
    assert started["ok"] is True and started["kind"] == prompt_to_script.KIND_LORA

    stepped = bridge.step("rfw-test-sf7")
    assert stepped["ok"] is True, stepped
    assert stepped["output_id"] == "out-1"
    assert stepped["metrics_mismatch"] in (None, []), stepped["metrics_mismatch"]

    explained = bridge.explain("rfw-test-sf7", "out-1", allow_llm=False)
    assert explained["ok"] is True and explained["mode"] == "rules"
    assert "ERP" in explained["next_step_suggestion"]

    directory = sandbox / "rfw-test-sf7"
    for name in ("prompt.md", "script.py", "log.txt", "explanation.md", "result.json",
                 "workflow.json", "lora_phy.py"):
        path = directory / name
        assert path.is_file(), name
        assert path.read_bytes().count(b"\r\n") == 0, f"{name} 含 CRLF"
    assert (directory / "lora_phy.py").read_bytes() == Path(lora_phy.__file__).read_bytes()

    status = bridge.workflow_status("rfw-test-sf7")
    assert status["ok"] is True and len(status["workflow"]["steps"]) == 1
    assert "script.py" in status["artifacts"]

    listed = bridge.list_workflows()
    assert listed["ok"] is True and listed["count"] == 1
    assert listed["recent"][0]["workflow_id"] == "rfw-test-sf7"


def test_workflow_metrics_agree_with_in_repo_computation(bridge, sandbox):
    bridge.start_workflow(GOAL, workflow_id="rfw-agree")
    stepped = bridge.step("rfw-agree")
    spec = bridge.workflow_status("rfw-agree")["workflow"]["spec"]
    expected = lora_phy.compute_metrics({k: v for k, v in spec.items() if k != "spec_sources"})
    actual = stepped["metrics"]
    for key, value in expected.items():
        assert key in actual, key
        if isinstance(value, float):
            assert actual[key] == pytest.approx(value, rel=1e-9, abs=1e-9), key
        else:
            assert actual[key] == value, key


def test_step_refines_spec_from_prompt(bridge, sandbox):
    bridge.start_workflow(GOAL, workflow_id="rfw-refine")
    stepped = bridge.step("rfw-refine", prompt="把扩频因子改成 9，功率改成 17 dBm")
    assert stepped["ok"] is True, stepped
    assert Path(stepped["script"]).name == "script.py" and stepped["output_id"] == "out-1"
    state = bridge.workflow_status("rfw-refine")["workflow"]
    assert state["spec"]["sf"] == 9
    assert state["spec"]["tx_power_dbm"] == pytest.approx(17.0)
    assert state["spec"]["spec_sources"]["sf"] == "step"
    assert state["spec"]["spec_sources"]["freq_hz"] == "goal"
    # 第二步的产物不与第一步同名（可追溯）
    stepped2 = bridge.step("rfw-refine")
    assert Path(stepped2["script"]).name == "script_2.py"
    assert Path(stepped2["log"]).name == "log_2.txt"
    explained2 = bridge.explain("rfw-refine")
    assert explained2["ok"] is True and explained2["output_id"] == "out-2"
    assert Path(explained2["explanation_path"]).name == "explanation_out-2.md"


def test_workflow_state_has_no_absolute_paths(bridge, sandbox):
    """状态文件会随沙箱入库 ⇒ 不得出现本机绝对路径（回归 241 交付纪律）。"""
    bridge.start_workflow(GOAL, workflow_id="rfw-clean")
    bridge.step("rfw-clean")
    bridge.explain("rfw-clean")
    two_backslashes = chr(92) * 2
    for artifact in ("prompt.md", "script.py", "log.txt", "explanation.md", "result.json",
                     "workflow.json"):
        text = (sandbox / "rfw-clean" / artifact).read_text(encoding="utf-8")
        assert str(sandbox) not in text, f"{artifact} 泄露沙箱绝对路径"
        assert two_backslashes not in text, f"{artifact} 出现 Windows 绝对路径"
        assert ":/" not in text, f"{artifact} 出现 POSIX 绝对路径"


def test_error_paths_are_explicit(bridge, sandbox):
    assert bridge.start_workflow("")["error"] == "empty_goal"
    assert bridge.start_workflow("随便问点什么")["error"] == "unsupported_goal"
    assert bridge.start_workflow(GOAL, rf_lib="ruby")["error"] == "invalid_rf_lib"
    assert bridge.start_workflow(GOAL, workflow_id="../evil")["error"] == "invalid_workflow_id"

    bridge.start_workflow(GOAL, workflow_id="rfw-twice")
    again = bridge.start_workflow(GOAL, workflow_id="rfw-twice")
    assert again["error"] == "workflow_exists"

    assert bridge.step("nope")["error"] == "workflow_not_found"
    assert bridge.explain("nope")["error"] == "workflow_not_found"
    assert bridge.explain("rfw-twice")["error"] == "no_output"
    bridge.step("rfw-twice")
    assert bridge.explain("rfw-twice", "out-9")["error"] == "output_not_found"
    assert bridge.workflow_status("nope")["error"] == "workflow_not_found"


# ---------------------------------------------------------------------------
# 任务一 · MCP 契约
# ---------------------------------------------------------------------------


def test_handoff_contract(bridge, sandbox):
    import asyncio

    payload = json.loads(asyncio.run(bridge.handle_handoff(
        {"tool_name": "start_workflow", "params": {"goal": GOAL,
                                                  "workflow_id": "rfw-handoff"}})))
    assert payload["status"] == "success" and payload["data"]["workflow_id"] == "rfw-handoff"

    bad = json.loads(asyncio.run(bridge.handle_handoff({"tool_name": "nope"})))
    assert bad["status"] == "error" and "可用" in bad["message"]

    wrong_args = json.loads(asyncio.run(bridge.handle_handoff(
        {"tool_name": "start_workflow", "params": {"nonexistent": 1}})))
    assert wrong_args["status"] == "error"


def test_manifest_entrypoint_and_tool_names_match():
    manifest = json.loads((PKG_ROOT / "agent-manifest.json").read_text(encoding="utf-8"))
    assert manifest["agentType"] == "mcp"
    module_name = manifest["entryPoint"]["module"]
    class_name = manifest["entryPoint"]["class"]
    assert module_name == "mcpserver.rf_workflow.server"
    target = getattr(sys.modules[server.__name__], class_name)
    assert hasattr(target, "handle_handoff")
    commands = [tool["command"] for tool in manifest["capabilities"]["invocationCommands"]]
    assert sorted(commands) == sorted(server.RfWorkflowBridge._TOOLS)   # noqa: SLF001 - 契约对齐
    for tool in manifest["capabilities"]["invocationCommands"]:
        params = tool["parameters"]
        assert params["type"] == "object" and "properties" in params


def test_module_files_exist_and_are_lf():
    expected = {"__init__.py", "server.py", "prompt_to_script.py", "sim_runner.py",
                "explainer.py", "lora_phy.py", "agent-manifest.json", "README.md",
                "requirements.txt"}
    present = {path.name for path in PKG_ROOT.iterdir() if path.is_file()}
    assert expected <= present, sorted(expected - present)
    for name in sorted(expected):
        raw = (PKG_ROOT / name).read_bytes()
        assert raw.count(b"\r\n") == 0, f"{name} 含 CRLF"
    assert (PKG_ROOT / "requirements.txt").read_text(encoding="utf-8").startswith("#")


def test_cli_run_is_reproducible(sandbox):
    """CLI 端到端（不进管道，避免 SIGPIPE 半途而死这套坑）。"""
    proc = subprocess.run(
        [sys.executable, "-m", "mcpserver.rf_workflow.server", "run",
         "--workflow-id", "rfw-cli", "--goal", GOAL, "--no-llm"],
        cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=300, check=False)
    assert proc.returncode == 0, proc.stderr[-2000:]
    payload = json.loads(proc.stdout[proc.stdout.find("{"):])
    assert payload["start"]["ok"] and payload["step"]["ok"] and payload["explain"]["ok"]
    assert payload["explain"]["mode"] == "rules"


def test_explainer_rules_are_self_consistent():
    spec = prompt_to_script.parse_goal(GOAL)
    metrics = lora_phy.compute_metrics({k: v for k, v in spec.items() if k != "spec_sources"})
    notes = explainer.observations(metrics)
    joined = " ".join(notes)
    assert "51.456" in joined and "11.85" in joined and "97.656" in joined
    candidates = explainer.suggest_specs(spec)
    assert len(candidates) == 3
    assert all(item["ok"] for item in candidates)
    compliant = candidates[0]["predicted"]
    assert compliant["erp_ok"] is True, "合规化候选必须真的合规"
    markdown = explainer.render_markdown(
        explainer.explain(spec, metrics, allow_llm=False), spec)
    assert markdown.startswith("# 结果解释") and "候选变体" in markdown
