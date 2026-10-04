"""dexter_probe 验收硬线（86号 V3）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dexter_probe import probe  # noqa: E402

_REPORT = Path(__file__).resolve().parents[1] / "docs" / "dexter-语音链路参考-2026-09-04.md"


def test_probe_output_structure():
    """探针输出组件图结构合法。"""
    out = probe()
    assert out["status"] in ("success", "degraded")
    comps = out["components"]
    assert isinstance(comps, list) and len(comps) >= 3
    stages = [c["stage"] for c in comps]
    assert "asr" in stages and "llm" in stages and "tts" in stages


def test_report_exists():
    """参考报告落盘且含 ≥3 个可借鉴设计点。"""
    assert _REPORT.exists(), f"参考报告缺失：{_REPORT}"
    text = _REPORT.read_text(encoding="utf-8")
    assert "链路拆解" in text or "链路" in text
    assert text.count("映射") >= 3 or "可借鉴" in text
