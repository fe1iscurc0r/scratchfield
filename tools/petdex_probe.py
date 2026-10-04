"""petdex-cc 事件动画联动探针（诚实降级 · 静态分析）。

授粉来源：devnomad-byte/petdex-cc（MIT，★18）。本探针输出「事件类型 → 动画状态」
映射表（基于上游公开文档静态分析），不 clone（环境约束，诚实标注）。
"""
from __future__ import annotations

import json


def probe() -> dict:
    """输出事件→动画映射表。

    返回
    ----
    dict：``{"package", "status", "license", "summary", "mapping"}``。
    """
    return {
        "package": "petdex-cc",
        "status": "degraded",
        "license": "MIT",
        "summary": (
            "petdex-cc 未浅克隆（环境约束）；事件→动画映射表基于上游公开文档静态分析"
        ),
        "mapping": [
            {"event": "compile", "animation": "working"},
            {"event": "success", "animation": "happy"},
            {"event": "error", "animation": "sad"},
        ],
    }


def main() -> None:
    print(json.dumps(probe(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
