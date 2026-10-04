"""chatterbox_probe 验收硬线（86号 V1）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from chatterbox_probe import probe  # noqa: E402

_REPORT = Path(__file__).resolve().parents[1] / "docs" / "chatterbox-tts选型-2026-09-04.md"


def test_probe_output_structure():
    """探针输出结构合法（成功或退化标注）。"""
    out = probe()
    assert out["status"] in ("success", "degraded")
    assert out["license"].startswith("MIT")
    assert out["summary"]
    assert out["conclusion"]


def test_report_exists():
    """选型报告落盘且含能力矩阵 + 许可结论。"""
    assert _REPORT.exists(), f"选型报告缺失：{_REPORT}"
    text = _REPORT.read_text(encoding="utf-8")
    assert "能力矩阵" in text
    assert "许可" in text
    assert "接入" in text or "暂缓" in text
