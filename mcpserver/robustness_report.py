"""鲁棒性回归报告生成器（E-02）。

跑一遍全故障类型的故障注入回归，输出：
各故障类型下的成功率 / 平均重试次数 / 恢复时长 / 重连次数 / 降级次数。

用法：
    python -m mcpserver.robustness_report
    或 python mcpserver/robustness_report.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcpserver.fault_inject.robustness import run_robustness_suite  # noqa: E402

_HEADERS = ["故障类型", "试验数", "成功率", "平均重试次数", "恢复时长(s)", "重连次数", "降级次数"]
_KEYS = ["fault_type", "trials", "success_rate", "avg_retries", "avg_recovery_s", "reconnects", "degraded"]


def _fmt_table(rows: list[dict]) -> str:
    col_widths = [
        max(len(_HEADERS[i]), max(len(str(row[_KEYS[i]])) for row in rows))
        for i in range(len(_HEADERS))
    ]
    lines = []
    lines.append("  ".join(h.ljust(col_widths[i]) for i, h in enumerate(_HEADERS)))
    lines.append("  ".join("-" * w for w in col_widths))
    for row in rows:
        lines.append("  ".join(str(row[_KEYS[i]]).ljust(col_widths[i]) for i in range(len(_HEADERS))))
    return "\n".join(lines)


def main() -> int:
    rows = asyncio.run(run_robustness_suite(trials=20))
    print("鲁棒性回归报告（mock MCP server，无真实网络）")
    print()
    print(_fmt_table(rows))
    print()
    print("说明：成功率=成功调用占比；平均重试次数=每次调用的重试次数（尝试次数-1）；")
    print("恢复时长=成功调用（含重试/重连）的耗时；重连次数=断连后重连回调次数；")
    print("降级次数=错误走降级路径的次数。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
