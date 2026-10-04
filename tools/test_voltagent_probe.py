"""voltagent_probe 验收硬线（94号 T1）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from voltagent_probe import probe  # noqa: E402

_REPORT = Path(__file__).resolve().parents[1] / "docs" / "voltagent-勘察-2026-09-04.md"


def test_probe_output_structure():
    """探针输出结构合法（成功含接口摘要，退化含源码分析）。"""
    out = probe()
    assert out["status"] in ("success", "degraded")
    assert out["license"] == "MIT"
    assert out["api_surface"]
    assert out["conclusion"]


def test_report_exists():
    """勘察报告落盘且含能力矩阵 + 接入结论。"""
    assert _REPORT.exists(), f"勘察报告缺失：{_REPORT}"
    text = _REPORT.read_text(encoding="utf-8")
    assert "能力矩阵" in text
    assert "接入" in text
