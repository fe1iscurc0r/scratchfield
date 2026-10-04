"""pylabrobot_probe 验收硬线（88号 M1）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pylabrobot_probe import probe  # noqa: E402

_REPORT = Path(__file__).resolve().parents[1] / "docs" / "pylabrobot-实验自动化评估-2026-09-04.md"


def test_probe_output_structure():
    """探针输出操作日志结构合法。"""
    out = probe()
    assert out["status"] in ("success", "degraded")
    assert isinstance(out["board_layout"], list) and out["board_layout"]
    assert isinstance(out["steps"], list) and out["steps"]
    assert any(s["op"] == "transfer" for s in out["steps"])


def test_report_exists():
    """评估报告落盘且含接入结论 + 模拟路径验证。"""
    assert _REPORT.exists(), f"评估报告缺失：{_REPORT}"
    text = _REPORT.read_text(encoding="utf-8")
    assert "接入" in text
    assert "虚拟" in text or "模拟" in text


def test_abstraction_layer():
    """验证探针调用的是硬件无关 API（不硬编码具体设备型号）。"""
    out = probe()
    assert out["device_specific"] is False
    blob = str(out)
    for brand in ("Tecan", "Hamilton", "Eppendorf", "Opentrons"):
        assert brand not in blob, f"硬编码了具体设备型号：{brand}"
