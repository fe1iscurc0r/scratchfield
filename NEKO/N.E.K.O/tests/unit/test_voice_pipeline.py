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

"""voice_pipeline 配置化可插拔层（R-02）单元测试。

覆盖工单验收点：配置加载 / 注册表查找 / 默认后端实例化 / 换后端 mock /
降级路径 / 配置非法报错。
"""

from __future__ import annotations

import asyncio

import pytest

from main_logic.voice_turn.contracts import TurnDecision
from main_logic.voice_pipeline import (
    AsrSessionASRStage,
    DummyASRStage,
    DummyTTSStage,
    EdgeTTSTTSStage,
    EnergyThresholdTurnStage,
    FallbackVADStage,
    PlaceholderLLMStage,
    PipelineBackendNotFound,
    PipelineBackendUnavailable,
    PipelineConfigError,
    VoicePipelineRegistry,
    build_default_registry,
    build_stage_for,
    load_pipeline_config,
)


# ── 1. 配置加载 ────────────────────────────────────────────────────────────


def test_load_default_config() -> None:
    config = load_pipeline_config()
    assert config["version"] == 1
    pipeline = config["pipeline"]
    assert pipeline["vad"] == "silero_vad"
    assert pipeline["turn"] == "energy_threshold"
    assert pipeline["asr"] == "sense_voice"
    assert pipeline["llm"] == "openai"
    assert pipeline["tts"] == "edge_tts"
    # 缺后端显式降级目标
    assert config["fallback"]["asr"] == "dummy"
    assert config["fallback"]["tts"] == "dummy_tts"


# ── 2. 注册表查找 ──────────────────────────────────────────────────────────


def test_registry_lookup_and_build() -> None:
    registry = VoicePipelineRegistry()
    assert not registry.contains("edge_tts")
    registry.register("edge_tts", EdgeTTSTTSStage, available=True)
    assert registry.contains("edge_tts")
    assert registry.lookup("edge_tts") is not None
    assert "edge_tts" in registry.names()

    stage = registry.build_stage("edge_tts", {"voice": "zh-CN-XiaoxiaoNeural"})
    assert isinstance(stage, EdgeTTSTTSStage)
    assert stage.config["voice"] == "zh-CN-XiaoxiaoNeural"
    assert stage.name == "edge_tts"


def test_registry_missing_backend_raises() -> None:
    registry = build_default_registry()
    with pytest.raises(PipelineBackendNotFound):
        registry.build_stage("no_such_backend")


# ── 3. 默认后端实例化 ──────────────────────────────────────────────────────


def test_default_backends_instantiation() -> None:
    config = load_pipeline_config()
    turn = build_stage_for(config, "turn")
    assert isinstance(turn, EnergyThresholdTurnStage)
    asr = build_stage_for(config, "asr")
    assert isinstance(asr, AsrSessionASRStage)
    tts = build_stage_for(config, "tts")
    assert isinstance(tts, EdgeTTSTTSStage)
    llm = build_stage_for(config, "llm")
    assert isinstance(llm, PlaceholderLLMStage)
    # silero_vad 未安装 → 显式降级到内置 fallback_vad
    vad = build_stage_for(config, "vad")
    assert isinstance(vad, FallbackVADStage)


# ── 4. 换后端 mock（改配置换后端） ─────────────────────────────────────────


def test_swap_tts_backend_via_config() -> None:
    config = load_pipeline_config()
    # 只改配置：tts 从 edge_tts 换成 dummy_tts，代码不动
    config["pipeline"]["tts"] = "dummy_tts"
    tts = build_stage_for(config, "tts")
    assert isinstance(tts, DummyTTSStage)


class _FakeSession:
    """离线 fake 会话：按 RealtimeAsrSession 协议记录调用序列。"""

    def __init__(self, on_input_transcript=None) -> None:
        self._on_input_transcript = on_input_transcript
        self.calls: list[str] = []

    async def connect(self, instructions: str = "", native_audio: bool = False) -> None:
        self.calls.append("connect")

    async def stream_audio(self, audio_chunk: bytes, *, sample_rate_hz=None) -> None:
        self.calls.append("stream_audio")
        if self._on_input_transcript is not None:
            await self._on_input_transcript("你好")

    async def signal_user_activity_end(self) -> None:
        self.calls.append("signal_user_activity_end")

    async def close(self) -> None:
        self.calls.append("close")


def _fake_asr_session_factory(core_type: str, **kwargs):
    return _FakeSession(on_input_transcript=kwargs.get("on_input_transcript"))


@pytest.mark.asyncio
async def test_swap_asr_backend_mock() -> None:
    # 改配置：asr 后端注入 mock session_factory（离线，不触网）
    config = load_pipeline_config()
    config["stage_config"]["sense_voice"]["session_factory"] = _fake_asr_session_factory
    asr = build_stage_for(config, "asr")
    assert isinstance(asr, AsrSessionASRStage)

    text = await asr.transcribe(b"\x00" * 1600)
    assert text == "你好"
    # 直调路径保留：create_asr_session 既有调用序列不变
    session = _FakeSession()
    assert session.calls == []


# ── 5. 降级路径 ────────────────────────────────────────────────────────────


def test_fallback_on_missing_backend() -> None:
    registry = build_default_registry()
    # 缺后端 + 提供 fallback → 显式降级
    stage = registry.build_stage_or_fallback("no_such_backend", fallback="dummy")
    assert isinstance(stage, DummyASRStage)
    # 缺后端 + 无 fallback → 抛错
    with pytest.raises(PipelineBackendNotFound):
        registry.build_stage_or_fallback("no_such_backend")


def test_silero_vad_unavailable_falls_back() -> None:
    registry = build_default_registry()
    backend = registry.lookup("silero_vad")
    assert backend is not None
    if backend.available:
        pytest.skip("silero_vad 已安装，跳过降级断言")
    with pytest.raises(PipelineBackendUnavailable):
        registry.build_stage("silero_vad")
    # 显式降级到 fallback_vad，且该后端可离线判定语音活动
    stage = registry.build_stage_or_fallback("silero_vad", fallback="fallback_vad")
    assert isinstance(stage, FallbackVADStage)


@pytest.mark.asyncio
async def test_fallback_vad_offline_detect() -> None:
    stage = FallbackVADStage({"threshold": 0.02})
    assert await stage.run(b"\x00" * 1600) == "none"
    assert await stage.run(b"\xff\x7f" * 800) == "speech_started"


@pytest.mark.asyncio
async def test_energy_turn_evaluate() -> None:
    stage = EnergyThresholdTurnStage({"energy_floor": 0.02})
    # 空尾部 / 静音尾部 → COMPLETE
    assert (await stage.evaluate(b"")).decision is TurnDecision.COMPLETE
    assert (await stage.evaluate(b"\x00" * 1600)).decision is TurnDecision.COMPLETE
    # 有声尾部 → INCOMPLETE
    assert (await stage.evaluate(b"\xff\x7f" * 800)).decision is TurnDecision.INCOMPLETE


class _UnavailableStage(FallbackVADStage):
    """构造期即不可用的 fake 后端（模拟依赖缺失的 edge_tts / silero_vad）。"""

    name = "unavailable_stage"

    @property
    def available(self) -> bool:
        return False


def test_stage_instance_unavailable_falls_back() -> None:
    # 实例级不可用（依赖在构造期才暴露）→ 注册表构建后验证并降级
    registry = build_default_registry()
    registry.register("unavailable_stage", _UnavailableStage, available=True)
    stage = registry.build_stage_or_fallback("unavailable_stage", fallback="fallback_vad")
    assert isinstance(stage, FallbackVADStage)
    # 无法降级时：存在但不可用 → Unavailable（非 NotFound）
    with pytest.raises(PipelineBackendUnavailable):
        registry.build_stage_or_fallback("unavailable_stage")
    # fallback 自身不可用 → Unavailable
    registry.register("unavailable_fb", _UnavailableStage, available=True)
    with pytest.raises(PipelineBackendUnavailable):
        registry.build_stage_or_fallback("no_such_backend", fallback="unavailable_fb")


def test_fallback_config_read_by_fallback_name() -> None:
    # 降级时 fallback 用自己的配置段，不继承原后端的阈值（silero 0.5 → fallback_vad 0.02）
    config = load_pipeline_config()
    vad = build_stage_for(config, "vad")
    assert isinstance(vad, FallbackVADStage)
    assert vad._threshold == 0.02


def test_asr_stage_missing_core_type_unavailable() -> None:
    # 配置缺 core_type → 实例不可用，注册表显式降级 dummy；直调 transcribe 抛 Unavailable
    config = load_pipeline_config()
    config["stage_config"]["sense_voice"] = {"language": "zh"}
    asr = build_stage_for(config, "asr")
    assert isinstance(asr, DummyASRStage)

    raw = AsrSessionASRStage({"language": "zh"})
    assert not raw.available
    with pytest.raises(PipelineBackendUnavailable):
        asyncio.run(raw.transcribe(b"\x00" * 1600))


# ── 6. 配置非法报错 ────────────────────────────────────────────────────────


# 复用 registry 内部校验逻辑（校验失败抛 PipelineConfigError），避免依赖临时文件
def _assert_invalid_config(data) -> None:
    from main_logic.voice_pipeline import registry as _registry

    with pytest.raises(PipelineConfigError):
        _registry._validate_pipeline_config(data)


def test_invalid_config_version_raises() -> None:
    _assert_invalid_config(
        {"version": 2, "pipeline": {"vad": "v", "turn": "t", "asr": "a", "llm": "l", "tts": "x"}}
    )


def test_invalid_config_missing_stage_raises() -> None:
    # 缺 tts 段
    _assert_invalid_config(
        {"version": 1, "pipeline": {"vad": "v", "turn": "t", "asr": "a", "llm": "l"}}
    )
    # 空段名
    _assert_invalid_config(
        {"version": 1, "pipeline": {"vad": "", "turn": "t", "asr": "a", "llm": "l", "tts": "x"}}
    )


def test_invalid_config_stage_config_type_raises() -> None:
    _assert_invalid_config(
        {
            "version": 1,
            "pipeline": {"vad": "v", "turn": "t", "asr": "a", "llm": "l", "tts": "x"},
            "stage_config": "not-a-dict",
        }
    )
