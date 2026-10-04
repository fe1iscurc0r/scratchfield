"""caal_probe 验收硬线（87号 T1）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from caal_probe import probe  # noqa: E402

_REPORT = Path(__file__).resolve().parents[1] / "docs" / "caal-动态工具发现-2026-09-04.md"


def test_probe_output_structure():
    """探针输出机制图结构合法。"""
    out = probe()
    assert out["status"] in ("success", "degraded")
    mech = out["mechanism"]
    assert isinstance(mech, list) and len(mech) >= 3
    layers = [m["layer"] for m in mech]
    assert "discover" in layers and "register" in layers and "dispatch" in layers


def test_report_exists():
    """架构建议报告落盘且含「源→目标→方式→收益」映射表。"""
    assert _REPORT.exists(), f"架构建议报告缺失：{_REPORT}"
    text = _REPORT.read_text(encoding="utf-8")
    assert "源" in text and "目标" in text and "方式" in text and "收益" in text
