"""CAAL 动态工具发现机制探针（诚实降级 · n8n 环境约束）。

授粉来源：CoreWorxLab/CAAL（MIT，★439）。本探针输出「发现→注册→调用」三层
机制图（基于上游公开文档静态分析）；n8n 未部署，退化为机制分析（诚实标注）。
"""
from __future__ import annotations

import json


def probe() -> dict:
    """输出 CAAL 工具发现机制的三层调用图。

    返回
    ----
    dict：``{"package", "status", "license", "summary", "mechanism"}``。
    """
    return {
        "package": "caal",
        "status": "degraded",
        "license": "MIT",
        "summary": (
            "CAAL 需 n8n 部署才能真实验证，环境不允许 n8n；"
            "本次输出「发现→注册→调用」三层机制图（诚实降级，未真实验证）"
        ),
        "mechanism": [
            {"layer": "discover", "desc": "扫描 n8n workflow 列表"},
            {"layer": "register", "desc": "提取入/出参 schema，注册为 MCP 工具"},
            {"layer": "dispatch", "desc": "工具调用路由到对应 workflow 执行"},
        ],
    }


def main() -> None:
    print(json.dumps(probe(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
