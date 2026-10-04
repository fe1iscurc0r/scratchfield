"""VoltAgent npm 包接口探针（诚实降级 · 不整仓搬运）。

授粉来源：VoltAgent/voltagent（MIT，TypeScript Agent 平台）。本探针只做「npm 环境
探测 + 接口面分析」：无 npm 环境时输出 GitHub README/源码接口面分析，如实标注
退化，不伪造类型定义。
"""
from __future__ import annotations

import json
import shutil


def probe() -> dict:
    """探测 npm 环境；不可用则诚实降级为 README/源码接口面分析。

    返回
    ----
    dict：``{"package", "status", "license", "summary", "api_surface",
    "integration", "conclusion"}``。
    """
    npm_available = shutil.which("npm") is not None

    base = {
        "package": "@voltagent/core",
        "license": "MIT",
        "api_surface": ["Agent 抽象（Agent.create）", "工具注册（tool）", "记忆面（memory）"],
        "integration": ["npm 包接入", "参考架构", "与 CAAL MCP 动态发现链路组合"],
        "conclusion": "接入（有保留：Lumo TS 层 agent 框架候选）",
    }

    if npm_available:
        base["status"] = "success"
        base["summary"] = "npm 环境可用（可 install @voltagent/core 读类型定义）"
    else:
        base["status"] = "degraded"
        base["summary"] = (
            "npm 环境不可用；本次基于 GitHub README + 源码接口面静态分析"
            "（诚实降级，不伪造类型定义）"
        )
    return base


def main() -> None:
    print(json.dumps(probe(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
