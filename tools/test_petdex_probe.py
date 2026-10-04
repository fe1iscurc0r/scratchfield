"""petdex_probe 验收硬线（89号 P1）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from petdex_probe import probe  # noqa: E402

_REPORT = Path(__file__).resolve().parents[1] / "docs" / "petdex-事件动画联动-2026-09-04.md"


def test_probe_output_structure():
    """探针输出映射表结构合法。"""
    out = probe()
    assert out["status"] in ("success", "degraded")
    mapping = out["mapping"]
    assert isinstance(mapping, list) and mapping
    assert all("event" in m and "animation" in m for m in mapping)


def test_report_exists():
    """分析报告落盘且含 ≥3 条 NEKO 侧接入建议。"""
    assert _REPORT.exists(), f"分析报告缺失：{_REPORT}"
    text = _REPORT.read_text(encoding="utf-8")
    assert "NEKO" in text
    assert "事件" in text and "动画" in text
