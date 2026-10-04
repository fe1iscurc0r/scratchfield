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

"""voice_pipeline 后端注册表：按配置名查找，缺后端显式降级。

对齐 achatbot「配置 JSON 组装 pipeline」：五段（vad/turn/asr/llm/tts）
各自在后端注册表中按名称查找；未注册 / 不可用的后端在提供 fallback 时
显式降级，否则抛 ``PipelineBackendNotFound`` / ``PipelineBackendUnavailable``。
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .base import (
    PipelineBackendNotFound,
    PipelineBackendUnavailable,
    PipelineConfigError,
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

_STAGE_KEYS: tuple[str, ...] = ("vad", "turn", "asr", "llm", "tts")

# 内置兜底：pipeline 配置未显式声明 fallback 的段，缺后端时降级到这些实现。
_DEFAULT_FALLBACKS: dict[str, str] = {
    "vad": "fallback_vad",
    "turn": "energy_threshold",
    "asr": "dummy",
    "llm": "placeholder_llm",
    "tts": "dummy_tts",
}


@dataclass(frozen=True, slots=True)
class StageBackend:
    """注册表条目：按名称关联工厂与可用性。"""

    name: str
    factory: Callable[[dict[str, Any]], VoicePipelineStage]
    available: bool = True


class VoicePipelineRegistry:
    """五段后端注册表：``register`` 登记、``lookup`` 按名查找、构建时降级。"""

    def __init__(self) -> None:
        self._backends: dict[str, StageBackend] = {}

    def register(
        self,
        name: str,
        factory: Callable[[dict[str, Any]], VoicePipelineStage],
        *,
        available: bool = True,
    ) -> None:
        """登记一个后端（重复登记覆盖旧条目）。"""
        self._backends[name] = StageBackend(
            name=name,
            factory=factory,
            available=available,
        )

    def register_backend(self, backend: StageBackend) -> None:
        """登记一个已构造的 ``StageBackend``。"""
        self._backends[backend.name] = backend

    def lookup(self, name: str) -> StageBackend | None:
        """按名称查找后端；未登记返回 ``None``。"""
        return self._backends.get(name)

    def contains(self, name: str) -> bool:
        return name in self._backends

    def names(self) -> list[str]:
        return sorted(self._backends)

    def build_stage(self, name: str, config: dict[str, Any] | None = None) -> VoicePipelineStage:
        """按名构建后端；未登记 / 构建失败 / 实例不可用分别抛错（调用方自行降级）。"""
        backend = self.lookup(name)
        if backend is None:
            raise PipelineBackendNotFound(f"PIPELINE_BACKEND_NOT_FOUND: {name}")
        try:
            stage = backend.factory(dict(config or {}))
        except PipelineBackendUnavailable:
            raise
        if not getattr(stage, "available", True):
            raise PipelineBackendUnavailable(f"PIPELINE_BACKEND_UNAVAILABLE: {name}")
        return stage

    def build_stage_or_fallback(
        self,
        name: str,
        config: dict[str, Any] | None = None,
        *,
        fallback: str | None = None,
        fallback_config: dict[str, Any] | None = None,
    ) -> VoicePipelineStage:
        """按名构建；缺后端 / 不可用时显式降级到 ``fallback`` 后端名。

        可用性以**构建后实例**为准（``stage.available``），而非注册时静态标记：
        覆盖 silero_vad / edge_tts / semantic 等依赖在构造期才暴露不可用的后端。
        降级配置：``fallback_config`` 显式传入时优先，缺省复用 ``config``。
        无法降级时：未登记抛 ``PipelineBackendNotFound``，存在但不可用抛
        ``PipelineBackendUnavailable``（语义与 ``build_stage`` 一致）。
        """
        stage = self._try_build(name, config)
        if stage is not None:
            return stage
        if fallback is None:
            if self.lookup(name) is None:
                raise PipelineBackendNotFound(f"PIPELINE_BACKEND_NOT_FOUND: {name}")
            raise PipelineBackendUnavailable(f"PIPELINE_BACKEND_UNAVAILABLE: {name}")
        fb_config = fallback_config if fallback_config is not None else dict(config or {})
        fb_stage = self._try_build(fallback, fb_config)
        if fb_stage is not None:
            return fb_stage
        if self.lookup(fallback) is None:
            raise PipelineBackendNotFound(f"PIPELINE_BACKEND_NOT_FOUND: {fallback}")
        raise PipelineBackendUnavailable(f"PIPELINE_BACKEND_UNAVAILABLE: {fallback}")

    def _try_build(
        self,
        name: str,
        config: dict[str, Any] | None,
    ) -> VoicePipelineStage | None:
        """尝试构建：未登记 / 构建失败（Unavailable）/ 实例不可用 → ``None``。"""
        backend = self.lookup(name)
        if backend is None:
            return None
        try:
            stage = backend.factory(dict(config or {}))
        except PipelineBackendUnavailable:
            return None
        if not getattr(stage, "available", True):
            return None
        return stage


def build_default_registry() -> VoicePipelineRegistry:
    """构建含全部内置后端的注册表（silero_vad 依赖未装 → 标记不可用）。"""
    registry = VoicePipelineRegistry()
    registry.register("silero_vad", SileroVADStage, available=_silero_vad_available())
    registry.register("fallback_vad", FallbackVADStage, available=True)
    registry.register("energy_threshold", EnergyThresholdTurnStage, available=True)
    registry.register("semantic", SemanticTurnStage, available=True)
    registry.register("sense_voice", AsrSessionASRStage, available=True)
    registry.register("asr_session", AsrSessionASRStage, available=True)
    registry.register("dummy", DummyASRStage, available=True)
    registry.register("openai", PlaceholderLLMStage, available=True)
    registry.register("placeholder_llm", PlaceholderLLMStage, available=True)
    registry.register("edge_tts", EdgeTTSTTSStage, available=True)
    registry.register("dummy_tts", DummyTTSStage, available=True)
    return registry


def _silero_vad_available() -> bool:
    """silero-vad 未安装时显式标记不可用（硬约束：不引新重依赖）。"""
    try:
        import silero_vad  # noqa: F401

        return True
    except ImportError:
        return False


_default_registry: VoicePipelineRegistry | None = None


def default_registry() -> VoicePipelineRegistry:
    """惰性单例：默认内置后端注册表。"""
    global _default_registry
    if _default_registry is None:
        _default_registry = build_default_registry()
    return _default_registry


# ── pipeline 配置加载与校验 ────────────────────────────────────────────────

_PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH: Path = _PACKAGE_DIR / "pipeline_config.json"


def load_pipeline_config(path: str | Path | None = None) -> dict[str, Any]:
    """加载并校验 pipeline JSON 配置；非法配置抛 ``PipelineConfigError``。"""
    config_path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    if not config_path.exists():
        raise PipelineConfigError(f"PIPELINE_CONFIG_NOT_FOUND: {config_path}")
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise PipelineConfigError(f"PIPELINE_CONFIG_INVALID_JSON: {exc}") from exc
    _validate_pipeline_config(data)
    return data


def _validate_pipeline_config(data: Any) -> None:
    if not isinstance(data, dict):
        raise PipelineConfigError("PIPELINE_CONFIG_INVALID: 顶层必须是 JSON 对象")
    if data.get("version") != 1:
        raise PipelineConfigError("PIPELINE_CONFIG_INVALID: version 必须为 1")
    pipeline = data.get("pipeline")
    if not isinstance(pipeline, dict):
        raise PipelineConfigError("PIPELINE_CONFIG_INVALID: 缺少 pipeline 对象")
    for key in _STAGE_KEYS:
        value = pipeline.get(key)
        if not isinstance(value, str) or not value.strip():
            raise PipelineConfigError(f"PIPELINE_CONFIG_INVALID: pipeline.{key} 必须为非空字符串")
    if "stage_config" in data and not isinstance(data["stage_config"], dict):
        raise PipelineConfigError("PIPELINE_CONFIG_INVALID: stage_config 必须是对象")
    if "fallback" in data and not isinstance(data["fallback"], dict):
        raise PipelineConfigError("PIPELINE_CONFIG_INVALID: fallback 必须是对象")


def build_stage_for(
    config: dict[str, Any],
    stage_key: str,
    *,
    registry: VoicePipelineRegistry | None = None,
) -> VoicePipelineStage:
    """从 pipeline 配置为指定段构建后端。

    - 配置命名优先（``pipeline.{key}`` + ``stage_config[{name}]``）
    - 缺后端按 fallback 降级（配置 ``fallback.{key}`` 优先，内置兜底其次）
    """
    if stage_key not in _STAGE_KEYS:
        raise PipelineConfigError(f"PIPELINE_CONFIG_INVALID: 未知段 {stage_key}")
    pipeline = config.get("pipeline") or {}
    name = pipeline.get(stage_key)
    if not isinstance(name, str) or not name.strip():
        raise PipelineConfigError(f"PIPELINE_CONFIG_INVALID: pipeline.{stage_key} 必须为非空字符串")
    fallback_cfg = config.get("fallback") or {}
    fallback = fallback_cfg.get(stage_key) or _DEFAULT_FALLBACKS.get(stage_key)
    stage_config = (config.get("stage_config") or {}).get(name) or {}
    # 降级时按 fallback 后端自己的名字读配置（各后端取各自参数，避免配置错配）
    fallback_config = (config.get("stage_config") or {}).get(fallback) or {}
    reg = registry if registry is not None else default_registry()
    return reg.build_stage_or_fallback(
        name,
        stage_config,
        fallback=fallback,
        fallback_config=fallback_config,
    )
