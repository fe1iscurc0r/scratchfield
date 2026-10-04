"""bamboo_probe 验收硬线（85号 M1）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bamboo_probe import probe  # noqa: E402

_REPORT = Path(__file__).resolve().parents[1] / "docs" / "bamboo-力场勘察-2026-09-03.md"


def test_probe_output_structure():
    """探针输出结构合法（成功或退化标注均可）。"""
    out = probe()
    assert out["status"] in ("success", "degraded")
    assert out["package"] == "bamboo"
    assert out["license"] == "GPL-2.0"
    assert out["summary"]
    assert isinstance(out["access_paths"], list) and len(out["access_paths"]) >= 3


def test_report_exists():
    """勘察报告落盘且含能力矩阵。"""
    assert _REPORT.exists(), f"勘察报告缺失：{_REPORT}"
    text = _REPORT.read_text(encoding="utf-8")
    assert "能力矩阵" in text
    assert "接入路径" in text
    assert "GPL-2.0" in text
