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

"""voice_pipeline：NEKO 语音链路配置化可插拔层（R-02）。

五段（VAD/Turn/ASR/LLM/TTS）抽象基类 + 后端注册表 + 默认 pipeline 配置。
换后端只改 ``pipeline_config.json``，不动调用代码；缺后端显式降级。

用法::

    from main_logic.voice_pipeline import load_pipeline_config, build_stage_for

    config = load_pipeline_config()
    asr = build_stage_for(config, "asr")     # sense_voice → asr_session 后端
    tts = build_stage_for(config, "tts")     # edge_tts → Edge TTS 后端
    vad = build_stage_for(config, "vad")     # silero_vad 未装 → fallback_vad 降级
"""

from __future__ import annotations

from .base import (
    ASRStage,
    LLMStage,
    PipelineBackendNotFound,
    PipelineBackendUnavailable,
    PipelineConfigError,
    TurnStage,
    TTSStage,
    VADStage,
    VoicePipelineStage,
)
from .backends import (
    AsrSessionASRStage,
    DummyASRStage,
    DummyTTSStage,
    EdgeTTSTTSStage,
    EnergyThresholdTurnStage,
    FallbackVADStage,
    PlaceholderLLMStage,
    SemanticTurnStage,
    SileroVADStage,
)
from .registry import (
    DEFAULT_CONFIG_PATH,
    StageBackend,
    VoicePipelineRegistry,
    build_default_registry,
    build_stage_for,
    default_registry,
    load_pipeline_config,
)

__all__ = [
    # 统一基类
    "VoicePipelineStage",
    "VADStage",
    "TurnStage",
    "ASRStage",
    "LLMStage",
    "TTSStage",
    # 注册表
    "VoicePipelineRegistry",
    "StageBackend",
    "PipelineBackendNotFound",
    "PipelineBackendUnavailable",
    "build_default_registry",
    "default_registry",
    # 配置
    "DEFAULT_CONFIG_PATH",
    "load_pipeline_config",
    "build_stage_for",
    "PipelineConfigError",
    # 内置后端
    "SileroVADStage",
    "FallbackVADStage",
    "EnergyThresholdTurnStage",
    "SemanticTurnStage",
    "AsrSessionASRStage",
    "DummyASRStage",
    "PlaceholderLLMStage",
    "EdgeTTSTTSStage",
    "DummyTTSStage",
]
