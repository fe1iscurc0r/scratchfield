# Copyright 2025-2026 Project N.E.K.O. Team
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""voice_pipeline 五段抽象基类（VAD / Turn / ASR / LLM / TTS）。

R-02 落地：上游参照 ai-bot-pro/achatbot（BSD-3-Clause）的 Frame-Processor
五段契约，按授粉纪律重写为接口描述——只写契约，不 copy 上游源码。

统一契约：
- config 声明式注入（构造时接收 dict，换后端只改配置）
- ``run()`` 为统一执行入口（各段基类将其转发到领域方法）
- ``close()`` 释放资源（幂等，默认空操作）

领域抽象方法（子类必须实现）：
- VADStage.detect(audio)        → 语音活动事件名（对齐 SpeechActivityEvent）
- TurnStage.evaluate(audio_tail) → TurnEvaluation（复用 voice_turn 契约）
- ASRStage.transcribe(audio)     → 识别文本
- LLMStage.complete(messages)    → 模型回复（本轮接口占位）
- TTSStage.synthesize(text)      → 音频字节
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class PipelineConfigError(ValueError):
    """pipeline 配置非法（版本 / 缺段 / 类型错误）。"""


class PipelineBackendNotFound(LookupError):
    """注册表中不存在该后端名。"""


class PipelineBackendUnavailable(RuntimeError):
    """后端依赖缺失或运行时不可用（应显式降级）。"""


class VoicePipelineStage(ABC):
    """五段统一基类：config 声明式注入，``run()`` 为统一执行入口。"""

    name: str = ""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config: dict[str, Any] = dict(config or {})
        self._closed = False

    @abstractmethod
    async def run(self, *args: Any, **kwargs: Any) -> Any:
        """统一执行入口；具体语义由各段基类转接到领域方法。"""

    def close(self) -> None:
        """释放子类持有的资源；幂等，默认空操作。"""
        self._closed = True

    @property
    def is_closed(self) -> bool:
        return self._closed


class VADStage(VoicePipelineStage):
    """VAD 段抽象：帧级语音活动检测。

    ``run(audio)`` 转接 ``detect(audio)``，返回语音活动事件名
    （与 NEKO ``voice_turn.SpeechActivityEvent`` 对齐：
    NONE / SPEECH_STARTED / CANDIDATE_PAUSE / SPEECH_RESUMED）。
    """

    async def run(self, audio: bytes, **kwargs: Any) -> str:
        return await self.detect(audio, **kwargs)

    @abstractmethod
    async def detect(self, audio: bytes, **kwargs: Any) -> str:
        """返回当前帧的语音活动事件名。"""


class TurnStage(VoicePipelineStage):
    """Turn 段抽象：语义 / 能量端点检测。

    复用 NEKO ``voice_turn.contracts.TurnDetector`` 契约：
    ``evaluate(audio_tail)`` 返回 ``TurnEvaluation``
    （decision=INCOMPLETE/COMPLETE + probability + generation 防重放）。
    """

    async def run(self, audio_tail: bytes, **kwargs: Any) -> Any:
        return await self.evaluate(audio_tail, **kwargs)

    @abstractmethod
    async def evaluate(self, audio_tail: bytes, **kwargs: Any) -> Any:
        """评估一段音频尾部是否构成语义 / 能量端点。"""


class ASRStage(VoicePipelineStage):
    """ASR 段抽象：语音转文本。

    包装 ``asr_client.create_asr_session``（回调会话直调路径保留）；
    ``transcribe()`` 为简化同步接口（会话 + 回调收集）。
    """

    async def run(self, audio: bytes, **kwargs: Any) -> str:
        return await self.transcribe(audio, **kwargs)

    @abstractmethod
    async def transcribe(self, audio: bytes, *, language: str | None = None) -> str:
        """返回一段音频的最终识别文本。"""


class LLMStage(VoicePipelineStage):
    """LLM 段抽象：文本补全（本轮接口占位，不引新调用路径）。

    对齐 achatbot ``LLMProcessor``：输入对话消息列表 → 模型回复文本。
    """

    async def run(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        return await self.complete(messages, **kwargs)

    @abstractmethod
    async def complete(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        """输入对话消息列表，返回模型回复文本。"""


class TTSStage(VoicePipelineStage):
    """TTS 段抽象：文本转语音。

    对齐 achatbot ``TTSProcessorBase.run_tts(text)``：文本 → 音频字节
    （16kHz PCM/WAV，与 NEKO 现有 worker 输出一致）。
    """

    async def run(self, text: str, **kwargs: Any) -> bytes:
        return await self.synthesize(text, **kwargs)

    @abstractmethod
    async def synthesize(self, text: str, **kwargs: Any) -> bytes:
        """返回文本合成的音频字节。"""
