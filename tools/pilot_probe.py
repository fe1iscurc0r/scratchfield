"""Pilot 浏览器控制轻量探针（诚实降级 · 无需真实安装 Chrome 扩展）。

授粉来源：TacosyHorchata/Pilot（MIT，★32）。本探针输出「标签页列表/当前 URL/
点击」核心接口调用链（基于上游公开文档静态分析），不安装 Chrome 扩展。
"""
from __future__ import annotations

import json


def probe() -> dict:
    """输出 Pilot 核心接口调用链。

    返回
    ----
    dict：``{"package", "status", "license", "summary", "interfaces"}``。
    """
    return {
        "package": "pilot",
        "status": "degraded",
        "license": "MIT",
        "summary": (
            "Pilot 需真实 Chrome 扩展 + MCP server，本环境未安装；"
            "本次输出核心接口调用链（诚实降级，静态分析）"
        ),
        "interfaces": [
            {"name": "list_tabs", "desc": "列出浏览器标签页"},
            {"name": "get_url", "desc": "获取当前标签页 URL"},
            {"name": "click", "desc": "点击页面元素"},
            {"name": "fill", "desc": "填表输入"},
        ],
    }


def main() -> None:
    print(json.dumps(probe(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
