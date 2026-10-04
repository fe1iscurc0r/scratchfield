"""卷122 验收：天线仿真管线（模型生成 / 执行状态机 / 结果分析）。

覆盖：
- W122-01：三种天线模型生成（语法/元信息/几何）、参数校验、sweep 批量
- W122-02：任务状态机全路径（dry-run / 无后端 / 串行 busy / 路径与 job_id 收敛）
- W122-03：S11 解析（真实 CSV + 合成）、谐振/带宽/阻抗提取、理论对照、归档
"""
from __future__ import annotations

import pytest  # noqa: E402  (卷173 分层标注；与文件既有 import pytest 重复无害)

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.core]

import json

import pytest

from mcpserver.antenna_sim import model_generator as mg
from mcpserver.antenna_sim import result_analyzer as ra
from mcpserver.antenna_sim import sim_runner as sr


@pytest.fixture()
def lab(tmp_path, monkeypatch):
    """实验室根目录重定向到 tmp（不碰用户目录）。"""
    root = tmp_path / "antenna-lab"
    monkeypatch.setattr(sr, "lab_root", lambda: (root.mkdir(parents=True, exist_ok=True), root)[1])
    (root / "models").mkdir(parents=True, exist_ok=True)
    (root / "results").mkdir(parents=True, exist_ok=True)
    sr.reset_for_tests()
    return root


# ---------------------------------------------------------------------------
# W122-01 模型生成
# ---------------------------------------------------------------------------


def test_gen_model_three_types_are_valid_python_and_xml(lab):
    cases = [("moxon", 14.05), ("quad", 28.0), ("helical_yagi", 145.0)]
    for antenna_type, freq in cases:
        result = mg.gen_model(antenna_type, freq, out_dir=lab / "models")
        assert result["ok"] is True, result
        xml = json.dumps(result)  # 供下面断言
        py_text = (lab / "models" / f"{antenna_type}_{int(freq)}mhz.py").read_text(encoding="utf-8")
        xml_text = (lab / "models" / f"{antenna_type}_{int(freq)}mhz.xml").read_text(encoding="utf-8")
        # 元信息头
        assert f"antenna_type={antenna_type}" in py_text and f"antenna_type={antenna_type}" in xml_text
        assert "generated_by=mcpserver.antenna_sim" in py_text
        assert "网格假设" in py_text and "PML" in py_text
        assert "<openEMS>" in xml_text and "<Geometry" not in xml_text
        # Python 语法成立
        import ast

        ast.parse(py_text)
        assert result["wavelength_mm"] > 0 and result["params"], xml
        assert result["wires"], "应列出导体段"


def test_gen_model_rejects_bad_params(lab):
    bad_type = mg.gen_model("moxon", 14.05, out_dir=lab / "models")
    assert bad_type["ok"] is True  # 默认参数合法
    assert mg.gen_model("not_a_type", 14.05, out_dir=lab / "models")["error"] == "invalid_params"
    assert mg.gen_model("sierpinski", 900.0, out_dir=lab / "models")["error"] == "not_implemented"

    neg = mg.gen_model("quad", 28.0, {"side_mm": -5}, out_dir=lab / "models")
    assert neg["ok"] is False and any("正数" in p for p in neg["problems"])

    weird = mg.gen_model("moxon", 14.05, {"driven_len_mm": 100.0}, out_dir=lab / "models")
    assert weird["ok"] is False and any("比例不合理" in p for p in weird["problems"])

    refl_short = mg.gen_model("moxon", 14.05,
                              {"driven_len_mm": 7300, "reflector_len_mm": 7000},
                              out_dir=lab / "models")
    assert refl_short["ok"] is False and any("反射振子" in p for p in refl_short["problems"])


def test_sweep_params_generates_batch(lab):
    result = mg.sweep_params("moxon", 14.05,
                             {"driven_len_mm": [7200, 7300, 7400], "spacing_mm": [1100, 1200]},
                             out_dir=lab / "models" / "sweep")
    assert result["count"] == 6 and result["ok_count"] >= 1
    files = list((lab / "models" / "sweep").glob("*.xml"))
    assert len(files) == result["ok_count"]


def test_antenna_bridge_handoff(lab, monkeypatch):
    import asyncio

    from mcpserver.antenna_sim.tools import AntennaSimBridge

    bridge = AntennaSimBridge()
    monkeypatch.setattr(bridge, "_resolve_out_dir", lambda out_dir: lab / "models")
    payload = json.loads(asyncio.run(bridge.handle_handoff(
        {"tool_name": "gen_model", "antenna_type": "moxon", "freq_mhz": 14.05})))
    assert payload["status"] == "success" and payload["data"]["ok"] is True
    bad = json.loads(asyncio.run(bridge.handle_handoff({"tool_name": "nope"})))
    assert bad["status"] == "error"


# ---------------------------------------------------------------------------
# W122-02 执行状态机
# ---------------------------------------------------------------------------


def test_run_job_dry_run_state_machine(lab, monkeypatch):
    monkeypatch.setattr(sr, "pick_backend", lambda dry_run=False, suffix="": "dry_run")
    model = mg.gen_model("moxon", 14.05, out_dir=lab / "models")
    outcome = sr.run_job(model["xml_path"], job_id="ant-test-001", dry_run=True)
    assert outcome["ok"] is True and outcome["status"] == sr.STATUS_DONE
    assert (lab / "results" / "ant-test-001" / "job.json").is_file()

    status = sr.job_status("ant-test-001")
    assert status["ok"] and status["job"]["status"] == sr.STATUS_DONE
    assert status["job"]["backend"] == "dry_run"
    listing = sr.job_status()
    assert listing["count"] == 1 and listing["recent"][0]["job_id"] == "ant-test-001"


def test_run_job_no_backend_is_explicit(lab, monkeypatch):
    monkeypatch.setattr(sr, "pick_backend", lambda dry_run=False, suffix="": "unavailable")
    model = mg.gen_model("quad", 28.0, out_dir=lab / "models")
    outcome = sr.run_job(model["xml_path"], job_id="ant-test-002")
    assert outcome["ok"] is False and outcome["error"] == "no_backend"
    assert "ANTENNA_SIM_OPENEMS_DIR" in outcome["hint"], "必须给出可操作的指引"
    assert sr.job_status("ant-test-002")["job"]["status"] == sr.STATUS_FAILED


def test_run_job_serial_and_path_guards(lab, monkeypatch, tmp_path):
    monkeypatch.setattr(sr, "pick_backend", lambda dry_run=False: "dry_run")
    model = mg.gen_model("quad", 28.0, out_dir=lab / "models")
    # 串行：手动占用标记
    sr._running = "other-job"
    busy = sr.run_job(model["xml_path"], job_id="ant-test-003")
    assert busy["error"] == "busy" and busy["running"] == "other-job"
    sr.reset_for_tests()

    # 路径穿越 / 越界 / 不存在
    traversal = sr.run_job("../../etc/passwd", job_id="ant-test-004")
    assert traversal["error"] == "path_traversal_denied"
    outside = tmp_path / "outside.xml"
    outside.write_text("<openEMS/>", encoding="utf-8")
    assert sr.run_job(str(outside), job_id="ant-test-005")["error"] == "path_outside_models"
    assert sr.run_job(str(lab / "models" / "nope.xml"), job_id="ant-test-006")["error"] == "model_not_found"

    # job_id 收敛（会被拼进结果目录名）
    for bad in ("../evil", "a/b", "x" * 65, "a b"):
        assert sr.run_job(model["xml_path"], job_id=bad)["error"] == "invalid_job_id"


def test_job_status_rejects_bad_id(lab):
    assert sr.job_status("../etc")["ok"] is False
    assert sr.job_status("missing-job")["error"] == "job_not_found"


def test_openems_backend_detection(lab, monkeypatch, tmp_path):
    fake = tmp_path / "openEMS"
    fake.mkdir()
    (fake / "openEMS.exe").write_bytes(b"")
    monkeypatch.setenv("ANTENNA_SIM_OPENEMS_DIR", str(fake))
    assert sr.openems_available() is True
    assert sr.openems_dir() == fake
    monkeypatch.delenv("ANTENNA_SIM_OPENEMS_DIR")
    monkeypatch.setattr(sr, "_cfg", lambda: None)
    monkeypatch.setattr(sr, "openems_python", lambda: str(fake / "python.exe"))
    assert sr.pick_backend() in ("openems", "openems_py", "kali", "unavailable")


# ---------------------------------------------------------------------------
# W122-03 结果分析
# ---------------------------------------------------------------------------


def _write_csv(path, rows):
    lines = ["freq_hz,s11_db,zin_re,zin_im"]
    lines += [f"{f:.6e},{s:.4f},{zr:.4f},{zi:.4f}" for f, s, zr, zi in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_analyze_real_csv_extracts_resonance_and_bandwidth(lab):
    job_dir = lab / "results" / "ant-ana-001"
    job_dir.mkdir(parents=True)
    rows = [
        (280e6, -3.0, 80, -30), (290e6, -12.0, 60, -10), (300e6, -25.0, 50, 0),
        (310e6, -11.0, 60, 10), (320e6, -2.0, 90, 40),
    ]
    _write_csv(job_dir / "s11.csv", rows)
    out = ra.analyze_result("ant-ana-001", antenna_type="moxon", f0_mhz=300.0)
    assert out["ok"] is True
    assert out["resonance_mhz"] == 300.0 and out["s11_min_db"] == -25.0
    assert out["bandwidth_hz"] == 20e6, out
    assert out["zin_at_resonance"] == {"re": 50.0, "im": 0.0}
    assert out["synthetic"] is False
    assert out["theory"]["theory_gain_dbi"] == 5.5
    assert any("待实测验证" in n for n in out["theory"]["notes"])
    assert (job_dir / "summary.json").is_file() and (job_dir / "report.md").is_file()
    report = (job_dir / "report.md").read_text(encoding="utf-8")
    assert "谐振频率" in report and "S11 最小值" in report and "synthetic" not in report.split("\n")[2]


def test_analyze_synthetic_marks_source(lab):
    out = ra.analyze_result(synthetic=True, f0_mhz=145.0, antenna_type="helical_yagi",
                            gain_dbi=11.5)
    assert out["ok"] is True and out["synthetic"] is True
    assert out["source"] == "synthetic"
    report = (lab / "results" / "adhoc" / "report.md").read_text(encoding="utf-8")
    assert "合成（synthetic）" in report, "合成数据必须在报告里标注"
    assert out["theory"]["gain_delta_dbi"] == 1.5


def test_analyze_no_data_is_explicit(lab):
    out = ra.analyze_result("ant-none-001", antenna_type="moxon")
    assert out["ok"] is False and out["error"] == "no_s11_data"
    assert "synthetic" in out["hint"]


def test_compare_theory_gives_conservative_advice():
    low_gain = ra.compare_theory("moxon", gain_dbi=3.0, resonance_hz=14.2e6, f0_hz=14.05e6)
    joined = " ".join(low_gain["notes"])
    assert low_gain["gain_delta_dbi"] == -2.5
    assert "网格分辨率" in joined and "待实测验证" in joined
    assert low_gain["resonance_offset_ratio"] > 0

    ok_gain = ra.compare_theory("quad", gain_dbi=7.5, resonance_hz=28.0e6, f0_hz=28.0e6)
    assert ok_gain["gain_delta_dbi"] == 0.5
    assert any("典型值附近" in n for n in ok_gain["notes"])


def test_archive_entry_fields(lab):
    out = ra.analyze_result(synthetic=True, f0_mhz=300.0, antenna_type="moxon")
    entry = ra.archive_entry(out)
    assert entry["job_id"] and entry["resonance_mhz"]
    assert entry["synthetic"] is True and entry["status"] == "仿真结果待实测验证"
    assert set(entry) >= {"job_id", "resonance_mhz", "s11_min_db", "bandwidth_hz", "zin"}
