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

"""voice_pipeline 内置后端：Edge TTS / ASR 会话封装 + 显式降级路径。

授粉纪律：上游（achatbot BSD-3-Clause）仅作只读参照，本文件为按接口
描述重写的 NEKO 本地实现。所有外部依赖（edge_tts / asr_client /
voice_turn）均延迟 import，保证顶层导入零副作用、测试可离线 mock。
"""

from __future__ import annotations

import math
from typing import Any

from .base import (
    ASRStage,
    LLMStage,
    PipelineBackendUnavailable,
    TurnStage,
    TTSStage,
    VADStage,
)


def _rms(audio: bytes) -> float:
    """计算 16-bit 小端 PCM 音频的归一化 RMS（0.0 ~ 1.0）。"""
    n = len(audio) // 2
    if n == 0:
        return 0.0
    total = 0
    for i in range(n):
        value = int.from_bytes(audio[i * 2 : i * 2 + 2], "little", signed=True)
        total += value * value
    return math.sqrt(total / n) / 32768.0


class FallbackVADStage(VADStage):
    """VAD 降级后端：能量阈值判定，离线可测，零外部依赖。

    silero_vad 未安装时由注册表降级到此实现；产出事件名与
    ``voice_turn.SpeechActivityEvent`` 对齐。
    """

    name = "fallback_vad"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._threshold = float(self.config.get("threshold", 0.02))

    async def detect(self, audio: bytes, **kwargs: Any) -> str:
        if not audio:
            return "none"
        return "speech_started" if _rms(audio) >= self._threshold else "none"


class SileroVADStage(VADStage):
    """silero_vad 后端（可选依赖）。

    依赖未安装时 ``available=False``，注册表构建失败并显式降级到
    ``FallbackVADStage``（硬约束：不引新重依赖）。
    """

    name = "silero_vad"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._iterator = None
        try:
            import silero_vad  # noqa: F401
            from silero_vad import load_silero_vad

            self._iterator = load_silero_vad().get_iterator()
        except Exception:
            self._iterator = None

    @property
    def available(self) -> bool:
        return self._iterator is not None

    async def detect(self, audio: bytes, **kwargs: Any) -> str:
        if self._iterator is None:
            raise RuntimeError("VAD_BACKEND_UNAVAILABLE: silero_vad 未安装")
        # TODO(voice): 当前为 RMS 能量占位实现（阈值默认 0.5 为模型概率尺度，
        # 与能量尺度不匹配）；依赖就绪后的流式状态机接入点，接入时替换本分支。
        return "speech_started" if _rms(audio) >= float(self.config.get("threshold", 0.5)) else "none"


class EnergyThresholdTurnStage(TurnStage):
    """Turn 默认后端：能量阈值端点。

    尾部音频能量低于 ``energy_floor``（即静音）判定 COMPLETE；
    高于阈值判定 INCOMPLETE。返回 NEKO ``voice_turn`` 标准
    ``TurnEvaluation``。
    """

    name = "energy_threshold"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._silence_timeout_ms = int(self.config.get("silence_timeout_ms", 800))
        self._energy_floor = float(self.config.get("energy_floor", 0.02))

    async def evaluate(self, audio_tail: bytes, **kwargs: Any) -> Any:
        from main_logic.voice_turn.contracts import (
            EvaluationStatus,
            TurnDecision,
            TurnEvaluation,
        )

        if not audio_tail or _rms(audio_tail) < self._energy_floor:
            return TurnEvaluation(
                status=EvaluationStatus.OK,
                decision=TurnDecision.COMPLETE,
                probability=1.0,
                generation=0,
                activity_seq=0,
            )
        return TurnEvaluation(
            status=EvaluationStatus.OK,
            decision=TurnDecision.INCOMPLETE,
            probability=0.2,
            generation=0,
            activity_seq=0,
        )


class SemanticTurnStage(TurnStage):
    """Turn 语义端点后端：包装 ``voice_turn.TurnDetector``（复用现有契约）。

    detector 实例通过 config["detector"] 注入（不引新调用路径）；
    未注入时显式报不可用。
    """

    name = "semantic"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._detector = self.config.get("detector")

    @property
    def available(self) -> bool:
        return self._detector is not None

    async def evaluate(self, audio_tail: bytes, **kwargs: Any) -> Any:
        if self._detector is None:
            raise RuntimeError("TURN_BACKEND_UNAVAILABLE: 未注入 TurnDetector")
        return await self._detector.evaluate(audio_tail)


class AsrSessionASRStage(ASRStage):
    """ASR 后端：包装 ``asr_client.create_asr_session``。

    ``session_factory`` 可通过 config 注入（默认 ``asr_client.create_asr_session``），
    测试用 mock 替换即离线。``build_session`` 保留现有直调路径，不破坏
    ``create_asr_session`` 的既有调用契约。
    """

    name = "asr_session"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._core_type = str(self.config.get("core_type", "") or "").strip()
        self._language = str(self.config.get("language", "auto") or "auto").strip()
        self._user_region = self.config.get("user_region")
        self._session_factory = self.config.get("session_factory")
        if not self._core_type:
            # 配置缺失：显式标记不可用，由注册表降级到 fallback（如 dummy），
            # 避免构建成功但 transcribe 运行时才抛 ASR_UNKNOWN_CORE。
            self._core_type_error = "PIPELINE_CONFIG_INVALID: asr 段缺少 core_type"
        else:
            self._core_type_error = None

    @property
    def available(self) -> bool:
        return self._core_type_error is None

    def _resolve_session_factory(self) -> Any:
        if self._session_factory is not None:
            return self._session_factory
        from main_logic.asr_client import create_asr_session

        return create_asr_session

    def build_session(
        self,
        *,
        on_input_transcript: Any,
        on_connection_error: Any,
        on_status_message: Any | None = None,
        on_speech_activity: Any | None = None,
        on_turn_endpointed: Any | None = None,
    ) -> Any:
        """按 ``create_asr_session`` 既有签名转发，保留直调路径。"""
        return self._resolve_session_factory()(
            self._core_type,
            on_input_transcript=on_input_transcript,
            on_connection_error=on_connection_error,
            on_status_message=on_status_message,
            on_speech_activity=on_speech_activity,
            on_turn_endpointed=on_turn_endpointed,
            user_region=self._user_region,
            user_language=self._language,
        )

    async def transcribe(self, audio: bytes, *, language: str | None = None) -> str:
        if self._core_type_error is not None:
            raise PipelineBackendUnavailable(self._core_type_error)
        texts: list[str] = []

        async def _on_input_transcript(text: str) -> None:
            texts.append(text)

        async def _on_connection_error(error: str) -> None:
            raise RuntimeError(f"ASR_CONNECTION_ERROR: {error}")

        session = self.build_session(
            on_input_transcript=_on_input_transcript,
            on_connection_error=_on_connection_error,
        )
        try:
            await session.connect()
            await session.stream_audio(audio)
            await session.signal_user_activity_end()
        finally:
            await session.close()
        return "".join(texts).strip()


class DummyASRStage(ASRStage):
    """ASR 降级后端（fallback.asr = "dummy"）：离线空实现，不联网。"""

    name = "dummy"

    async def transcribe(self, audio: bytes, *, language: str | None = None) -> str:
        return ""


class PlaceholderLLMStage(LLMStage):
    """LLM 段占位后端（openai 等）：接口占位，不引新调用路径。

    对齐 R-01 差距清单第 5 条：LLM 段空白本轮以接口描述占位，
    不新建任何调用路径。
    """

    name = "placeholder_llm"

    async def complete(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        return str(
            self.config.get("echo")
            or "[voice_pipeline] LLM 段为接口占位，未配置真实后端"
        )


class EdgeTTSTTSStage(TTSStage):
    """TTS 后端：Edge TTS 封装（edge_tts 7.x，lazy import）。

    未安装 edge_tts 时 ``available=False``，注册表走 fallback（dummy_tts）。
    测试通过注入 communicate 类或 mock 注册表即可离线验证。
    """

    name = "edge_tts"

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        super().__init__(config)
        self._voice = str(self.config.get("voice", "zh-CN-XiaoxiaoNeural"))
        self._rate = str(self.config.get("rate", "+0%"))
        self._communicate_cls = self.config.get("communicate_cls")
        if self._communicate_cls is None:
            try:
                import edge_tts

                self._communicate_cls = edge_tts.Communicate
            except ImportError:
                self._communicate_cls = None

    @property
    def available(self) -> bool:
        return self._communicate_cls is not None

    async def synthesize(self, text: str, **kwargs: Any) -> bytes:
        if self._communicate_cls is None:
            raise RuntimeError("TTS_BACKEND_UNAVAILABLE: edge_tts 未安装")
        communicate = self._communicate_cls(text, voice=self._voice, rate=self._rate)
        audio = bytearray()
        async for chunk in communicate.stream():
            if chunk.get("type") == "audio":
                audio.extend(chunk.get("data") or b"")
        return bytes(audio)


class DummyTTSStage(TTSStage):
    """TTS 降级后端（fallback.tts = "dummy"）：离线空实现，不联网。"""

    name = "dummy_tts"

    async def synthesize(self, text: str, **kwargs: Any) -> bytes:
        return b""
