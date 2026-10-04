"""bluetts_probe 验收硬线（86号 V2）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bluetts_probe import probe  # noqa: E402

_REPORT = Path(__file__).resolve().parents[1] / "docs" / "bluetts-轻量评估-2026-09-04.md"


def test_probe_runs():
    """探针可运行（成功或明确退化标注）。"""
    out = probe()
    assert out["status"] in ("success", "degraded")
    assert out["chinese_support"] is False
    assert out["languages"]
    assert out["conclusion"]


def test_report_exists():
    """评估报告落盘且含中文支持结论。"""
    assert _REPORT.exists(), f"评估报告缺失：{_REPORT}"
    text = _REPORT.read_text(encoding="utf-8")
    assert "中文" in text
    assert "仅参考" in text or "备选" in text
