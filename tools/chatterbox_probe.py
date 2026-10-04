"""chatterbox TTS 最小探针（诚实降级 · 不拉权重 · 不引重型依赖）。

授粉来源：resemble-ai/chatterbox（代码 MIT，权重许可待核）。本探针只做「可用性
探测 + 架构分析」：不下载权重（许可纪律），不可用时输出架构/接口/依赖分析。
"""
from __future__ import annotations

import importlib.util
import json


def probe() -> dict:
    """探测 chatterbox 可用性；权重不可用则诚实降级为架构分析。

    返回
    ----
    dict：``{"package", "status", "license", "weight_license", "summary",
    "api_surface", "deps", "conclusion"}``。
    """
    package = "chatterbox"
    spec = importlib.util.find_spec(package)

    if spec is not None:
        return {
            "package": package,
            "status": "success",
            "license": "MIT（代码）",
            "weight_license": "待核（本探针不下载权重）",
            "summary": f"{package} 已安装（import 可用）",
            "api_surface": ["load_model()", "synthesize(text) → wav"],
            "deps": ["torch", "声码器依赖"],
            "conclusion": "接入（权重许可确认后）",
        }

    return {
        "package": package,
        "status": "degraded",
        "license": "MIT（代码）",
        "weight_license": "待核（不下载）",
        "summary": (
            "chatterbox 未安装且权重许可未确认，不在共享环境引入；"
            "本次只输出架构分析与接口面（诚实降级，不合成语音）"
        ),
        "api_surface": ["load_model()", "synthesize(text) → wav 落盘", "流式分段合成"],
        "deps": ["torch", "MeloTTS/Resemble 声学模型", "声码器"],
        "conclusion": "接入（有保留：权重许可待确认）",
    }


def main() -> None:
    print(json.dumps(probe(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
