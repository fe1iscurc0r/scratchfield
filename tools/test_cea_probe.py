"""cea_probe 验收硬线（93号 T2）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cea_probe import probe  # noqa: E402

_REPORT = Path(__file__).resolve().parents[1] / "docs" / "cea-平衡组成评估-2026-09-04.md"


def test_probe_output_structure():
    """探针输出结构合法（成功或退化标注）。"""
    out = probe()
    assert out["status"] in ("success", "degraded")
    assert out["inputs"] and out["outputs"]
    assert out["integration"]
    assert out["conclusion"]


def test_report_exists():
    """评估报告落盘且含与 feos 分工矩阵 + 生物质热解适用性判断。"""
    assert _REPORT.exists(), f"评估报告缺失：{_REPORT}"
    text = _REPORT.read_text(encoding="utf-8")
    assert "feos" in text
    assert "分工" in text or "互补" in text
    assert "生物质" in text and "热解" in text
