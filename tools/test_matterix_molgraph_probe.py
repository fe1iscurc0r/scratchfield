"""matterix_molgraph_probe 验收硬线（88号 M2）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from matterix_molgraph_probe import probe  # noqa: E402

_REPORT = Path(__file__).resolve().parents[1] / "docs" / "matterix-molgraph-评估-2026-09-04.md"


def test_probe_runs():
    """探针可运行（成功或明确退化标注）。"""
    out = probe()
    assert out["molgraph"]["status"] in ("success", "degraded")
    assert out["matterix"]["status"] in ("success", "degraded")
    assert out["molgraph"]["conclusion"]
    assert out["matterix"]["conclusion"]


def test_report_exists():
    """评估报告落盘且含 Matterix/molgraph 结论 + ChemLint 对比附注。"""
    assert _REPORT.exists(), f"评估报告缺失：{_REPORT}"
    text = _REPORT.read_text(encoding="utf-8")
    assert "Matterix" in text and "molgraph" in text and "ChemLint" in text
    assert "仅参考" in text and "不重复接入" in text
