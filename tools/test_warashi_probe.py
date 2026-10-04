"""warashi_probe 验收硬线（89号 P2）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from warashi_probe import probe  # noqa: E402

_REPORT = Path(__file__).resolve().parents[1] / "docs" / "warashi-上游同步评估-2026-09-04.md"


def test_probe_output_structure():
    """探针输出差异清单结构合法。"""
    out = probe()
    assert out["status"] in ("success", "degraded")
    diff = out["diff_modules"]
    assert isinstance(diff, list) and diff
    assert all("name" in d and "sync" in d for d in diff)


def test_report_exists():
    """评估报告落盘且含差异评分表。"""
    assert _REPORT.exists(), f"评估报告缺失：{_REPORT}"
    text = _REPORT.read_text(encoding="utf-8")
    assert "差异" in text
    assert "同步" in text and "Live2D" in text
