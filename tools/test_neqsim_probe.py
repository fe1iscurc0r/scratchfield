"""neqsim_probe 验收硬线（93号 T3）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from neqsim_probe import probe  # noqa: E402

_REPORT = Path(__file__).resolve().parents[1] / "docs" / "neqsim-相平衡评估-2026-09-04.md"


def test_probe_output_structure():
    """探针输出结构合法（成功或退化标注）。"""
    out = probe()
    assert out["status"] in ("success", "degraded")
    assert out["capabilities"]
    assert out["api_surface"]
    assert out["conclusion"]


def test_report_exists():
    """评估报告落盘且含三工具分工结论。"""
    assert _REPORT.exists(), f"评估报告缺失：{_REPORT}"
    text = _REPORT.read_text(encoding="utf-8")
    assert "feos" in text and "CEA" in text
    assert "分工" in text or "主" in text
