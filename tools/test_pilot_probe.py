"""pilot_probe 验收硬线（87号 T2）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pilot_probe import probe  # noqa: E402

_REPORT = Path(__file__).resolve().parents[1] / "docs" / "pilot-浏览器控制评估-2026-09-04.md"


def test_probe_output_structure():
    """探针输出接口调用链结构合法。"""
    out = probe()
    assert out["status"] in ("success", "degraded")
    assert isinstance(out["interfaces"], list) and out["interfaces"]
    names = [i["name"] for i in out["interfaces"]]
    assert "list_tabs" in names or "click" in names


def test_report_exists():
    """评估报告落盘且含与 browser-use 对比表。"""
    assert _REPORT.exists(), f"评估报告缺失：{_REPORT}"
    text = _REPORT.read_text(encoding="utf-8")
    assert "browser-use" in text
    assert "接入" in text or "补充" in text
