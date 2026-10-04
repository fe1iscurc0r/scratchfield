"""warashi 上游同步探针（诚实降级 · 差异清单静态分析）。

授粉来源：inni918/warashi（MIT core+bundled）。本探针输出与 Open-LLM-VTuber 的
差异文件清单（重点标记忆/主动聊天模块），不 clone（环境约束，诚实标注）。
"""
from __future__ import annotations

import json


def probe() -> dict:
    """输出 warashi 差异清单（重点标记忆/主动聊天模块）。

    返回
    ----
    dict：``{"package", "status", "license", "summary", "diff_modules"}``。
    """
    return {
        "package": "warashi",
        "status": "degraded",
        "license": "MIT（core+bundled，Live2D 角色需规避商用限制）",
        "summary": (
            "warashi 未浅克隆（环境约束）；差异清单基于上游公开文档静态分析，"
            "重点标出记忆/主动聊天相关模块"
        ),
        "diff_modules": [
            {"name": "memory", "kind": "长期记忆", "sync": "重点"},
            {"name": "proactive_chat", "kind": "主动聊天", "sync": "参考"},
            {"name": "live2d_assets", "kind": "角色资产", "sync": "仅免费角色"},
        ],
    }


def main() -> None:
    print(json.dumps(probe(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
