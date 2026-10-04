"""sigmf_probe 验收硬线（90号 S1）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sigmf_probe import probe  # noqa: E402

_REPORT = Path(__file__).resolve().parents[1] / "docs" / "sigmf-频谱数据标准化-2026-09-04.md"


def test_meta_fields():
    """生成的 meta 含 core:datatype/sample_rate/frequency/datetime/hardware 全字段。"""
    out = probe()
    for f in ("datatype", "sample_rate", "frequency", "datetime", "hardware"):
        assert f in out["meta_fields"], f"缺 core:{f}"
    assert out["meta_complete"] is True


def test_roundtrip():
    """写→读回，IQ 数据逐点一致、元数据完整。"""
    out = probe()
    assert out["status"] == "success"
    assert out["roundtrip_ok"] is True


def test_report_exists():
    """勘察报告落盘且含字段对照表 + 接入结论。"""
    assert _REPORT.exists(), f"勘察报告缺失：{_REPORT}"
    text = _REPORT.read_text(encoding="utf-8")
    assert "字段对照表" in text or "对照" in text
    assert "接入" in text
