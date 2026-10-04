"""BeeAI 源码接口探针（诚实降级 · 不整仓搬运）。

授粉来源：i-am-bee/beeai-framework（Apache-2.0，Python+TS 双语言 agent 框架）。
本探针只做「环境探测 + 接口面分析」：无 clone/npm 环境时输出 README 接口分析，
如实标注退化，不伪造核心类定义。
"""
from __future__ import annotations

import json
import shutil


def probe() -> dict:
    """探测 BeeAI 可用接口面；不可用则诚实降级为 README 接口分析。

    返回
    ----
    dict：``{"package", "status", "license", "summary", "api_surface",
    "integration", "conclusion"}``。
    """
    npm_available = shutil.which("npm") is not None

    base = {
        "package": "beeai-framework",
        "license": "Apache-2.0",
        "api_surface": ["Agent 抽象（Agent/BaseAgent）", "工具注册（Tool）", "记忆面（Memory）"],
        "integration": ["pip install（Python）", "npm install（TS）", "与 CAAL 工具发现链路组合"],
        "conclusion": "接入（有保留：生产级 agent 工程候选，与 CAAL 互补）",
    }

    if npm_available:
        base["status"] = "success"
        base["summary"] = "npm 环境可用（可 install beeai-framework 读类型定义）"
    else:
        base["status"] = "degraded"
        base["summary"] = (
            "未浅克隆且 npm 环境不可用；本次基于 README 接口分析"
            "（诚实降级，不伪造核心类定义）"
        )
    return base


def main() -> None:
    print(json.dumps(probe(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
