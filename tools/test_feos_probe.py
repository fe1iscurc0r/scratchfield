"""feos_probe 验收硬线（93号 T1）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from feos_probe import probe  # noqa: E402

_REPORT = Path(__file__).resolve().parents[1] / "docs" / "feos-状态方程勘察-2026-09-04.md"


def test_probe_output_structure():
    """探针输出结构合法（成功或退化标注）。"""
    out = probe()
    assert out["status"] in ("success", "degraded")
    assert out["license"] == "Apache-2.0"
    assert out["eos_supported"]
    assert out["api_surface"]
    assert out["conclusion"]


def test_report_exists():
    """勘察报告落盘且含能力矩阵 + 接入结论。"""
    assert _REPORT.exists(), f"勘察报告缺失：{_REPORT}"
    text = _REPORT.read_text(encoding="utf-8")
    assert "能力矩阵" in text
    assert "接入" in text
