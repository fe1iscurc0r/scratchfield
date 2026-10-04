"""BlueTTS 轻量 TTS 探针（诚实降级 · 不引重型依赖）。

授粉来源：maxmelichov/BlueTTS（MIT，ONNX Runtime TTS）。本探针只做「可用性探测
+ 语言面分析」：不可用时输出诚实退化 + 语言/部署分析，不合成语音。
"""
from __future__ import annotations

import importlib.util
import json


def probe() -> dict:
    """探测 BlueTTS 可用性；不可用则诚实降级为语言/部署分析。

    返回
    ----
    dict：``{"package", "status", "license", "summary", "languages",
    "chinese_support", "conclusion"}``。
    """
    package = "bluetts"
    spec = importlib.util.find_spec(package)

    base = {
        "package": package,
        "license": "MIT",
        "languages": ["希腊语", "英语", "西班牙语", "意大利语", "德语"],
        "chinese_support": False,
        "conclusion": "仅参考 / 备选补充（无中文，非主力）",
    }

    if spec is not None:
        base["status"] = "success"
        base["summary"] = f"{package} 已安装（import 可用）"
    else:
        base["status"] = "degraded"
        base["summary"] = (
            "bluetts 未安装（ONNX Runtime 等依赖，不在共享环境引入）；"
            "本次只输出语言面与部署分析（诚实降级，不合成语音）"
        )
    return base


def main() -> None:
    print(json.dumps(probe(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
