"""beeai_probe 验收硬线（94号 T2）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from beeai_probe import probe  # noqa: E402

_REPORT = Path(__file__).resolve().parents[1] / "docs" / "beeai-评估-2026-09-04.md"


def test_probe_output_structure():
    """探针输出结构合法（成功含接口摘要，退化含文档分析）。"""
    out = probe()
    assert out["status"] in ("success", "degraded")
    assert out["license"] == "Apache-2.0"
    assert out["api_surface"]
    assert out["conclusion"]


def test_report_exists():
    """评估报告落盘且含 AGENT_87 关联分析 + Mastra 对照 + 接入结论。"""
    assert _REPORT.exists(), f"评估报告缺失：{_REPORT}"
    text = _REPORT.read_text(encoding="utf-8")
    assert "CAAL" in text
    assert "Mastra" in text
    assert "接入" in text
