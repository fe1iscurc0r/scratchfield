"""dexter 语音链路轻量探针（诚实降级 · Rust 项目静态分析）。

授粉来源：thecodacus/dexter（Apache-2.0，Rust）。本探针输出「ASR→LLM→TTS」组件图
（基于上游公开文档静态分析），不 clone、不 cargo build（环境/时间约束，诚实标注）。
"""
from __future__ import annotations

import json


def probe() -> dict:
    """输出 dexter 组件图（ASR→LLM→TTS 调用链）。

    返回
    ----
    dict：``{"package", "status", "license", "summary", "components"}``。
    """
    return {
        "package": "dexter",
        "status": "degraded",
        "license": "Apache-2.0",
        "summary": (
            "dexter 为 Rust 项目，未浅克隆/未 cargo build（环境约束，诚实标注）；"
            "组件图基于上游公开文档静态分析"
        ),
        "components": [
            {"stage": "wake", "name": "VAD/唤醒", "next": "asr"},
            {"stage": "asr", "name": "Whisper", "next": "llm"},
            {"stage": "llm", "name": "Ollama", "next": "tts"},
            {"stage": "tts", "name": "Chatterbox TTS", "next": "play"},
            {"stage": "play", "name": "音频播放", "next": None},
        ],
    }


def main() -> None:
    print(json.dumps(probe(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
