"""rtl_tcp_probe 验收硬线（92号 A1）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from rtl_tcp_probe import probe  # noqa: E402

_REPORT = Path(__file__).resolve().parents[1] / "docs" / "rtl_tcp_andro-安卓SDR源-2026-09-04.md"


def test_probe_output_structure():
    """探针输出协议交互日志结构合法（成功或退化标注）。"""
    out = probe()
    assert out["status"] in ("success", "degraded")
    assert out["greeting"]["magic"] == "RTL0"
    assert isinstance(out["commands"], list) and out["commands"]


def test_report_exists():
    """勘察报告落盘且含「源→目标→方式→收益」映射表 + 许可边界。"""
    assert _REPORT.exists(), f"勘察报告缺失：{_REPORT}"
    text = _REPORT.read_text(encoding="utf-8")
    assert "源" in text and "目标" in text and "方式" in text and "收益" in text
    assert "GPL" in text


def test_protocol_fields():
    """解析出的 rtl_tcp 协议字段完整（dummy/freq/gain 等）。"""
    out = probe()
    fields = out["protocol_fields"]
    for f in ("dummy", "freq", "gain", "sample_rate"):
        assert f in fields, f"缺协议字段：{f}"
    cmds = out["commands"]
    assert any("freq" in c for c in cmds)
    assert any("gain" in c for c in cmds)
    assert any("sample_rate" in c for c in cmds)
