"""neqsim 相平衡轻量探针（诚实降级 · Java 只做架构分析）。

授粉来源：equinor/neqsim（Apache-2.0，Java 流体相平衡库）。本探针只做「JVM 桥接
可用性探测 + Java API 面分析」：无 jpype 桥接时输出 API 面/调用路径，如实标注
退化，不编造闪蒸计算结果。
"""
from __future__ import annotations

import importlib.util
import json


def probe() -> dict:
    """探测 JVM/Python 桥（jpype）可用性；不可用则诚实降级为 API 面分析。

    返回
    ----
    dict：``{"package", "status", "license", "summary", "capabilities",
    "api_surface", "conclusion"}``。
    """
    bridge_found = importlib.util.find_spec("jpype") is not None

    base = {
        "package": "neqsim",
        "license": "Apache-2.0",
        "capabilities": ["闪蒸计算", "相包络", "物性模型"],
        "api_surface": ["thermoSystem", "TPflash", "phaseEnvelope"],
        "conclusion": "仅参考（备选：油气/流体相平衡，Java 桥接成本高）",
    }

    if bridge_found:
        base["status"] = "success"
        base["summary"] = "jpype JVM 桥可用（可尝试 Java API 调用）"
    else:
        base["status"] = "degraded"
        base["summary"] = (
            "neqsim 为 Java 库且无 jpype 桥（JVM 依赖，不在共享环境引入）；"
            "本次只输出 Java API 面与调用路径分析（诚实降级，不编造闪蒸结果）"
        )
    return base


def main() -> None:
    print(json.dumps(probe(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
