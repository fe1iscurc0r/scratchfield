"""CharacterCapability：每角色独立的能力后端绑定（授粉-A3）。

参考 airi CharacterCapability（MIT，
github_haul/fusion/airi/packages/stage-ui/src/types/character.ts）：
每角色按 capability type（llm/tts/vlm/asr）独立绑定后端。

落地形态：
- profile（工作端 work / 宠物端 pet）隔离：两端可绑完全不同的后端，
  切换互不污染（每次解析返回深拷贝实例）
- 铁律7：json 里只存绑定描述与环境变量名（api_key_env），
  真实密钥解析时从环境变量读取，绝不落盘
- provider overlay：绑定可叠加环境变量覆写
  ``LUMO_CAP_<PROFILE>_<TYPE>_MODEL / _BASE_URL / _API_KEY``
  （与 lumo_proxy 的 LUMO_VISION_* overlay 同模式）
"""

from __future__ import annotations

import copy
import json
import logging
import os
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent
CapabilityType = Literal["llm", "tts", "vlm", "asr"]
_CAPABILITY_TYPES = ("llm", "tts", "vlm", "asr")


class CapabilityBinding(BaseModel):
    """单个能力类型的后端绑定（字段语义对齐 airi CharacterCapabilityConfig）。"""

    provider: str = Field(default="", description="后端供应商标识（deepseek/edge-tts/...）。")
    model: str = Field(default="", description="llm/vlm/asr 的模型名。")
    base_url: str = Field(default="", description="API base url；edge-tts 等本地引擎留空。")
    api_key_env: str = Field(
        default="",
        description="存放真实密钥的环境变量名（铁律7：密钥不落盘）。"
        "空串表示该能力无需密钥（如 edge-tts）。",
    )
    temperature: Optional[float] = Field(default=None, description="llm 温度（对应 airi llm.temperature）。")
    voice_id: str = Field(default="", description="tts 音色（对应 airi tts.voiceId）。")
    speed: Optional[float] = Field(default=None, description="tts 语速（对应 airi tts.speed）。")
    pitch: Optional[float] = Field(default=None, description="tts 音调（对应 airi tts.pitch）。")

    def resolve_api_key(self) -> str:
        """从环境变量解析密钥；无 api_key_env 的能力返回空串。"""
        if not self.api_key_env:
            return ""
        return os.environ.get(self.api_key_env, "")


class CapabilityProfile(BaseModel):
    """一个端（工作端/宠物端）的完整能力绑定集。"""

    name: str
    llm: CapabilityBinding = Field(default_factory=CapabilityBinding)
    tts: CapabilityBinding = Field(default_factory=CapabilityBinding)
    vlm: CapabilityBinding = Field(default_factory=CapabilityBinding)
    asr: CapabilityBinding = Field(default_factory=CapabilityBinding)

    def get(self, capability_type: CapabilityType) -> CapabilityBinding:
        return getattr(self, capability_type)


class CharacterCapability(BaseModel):
    """角色能力绑定总表：character_id → 多个 profile。"""

    character_id: str
    default_profile: str = "work"
    profiles: dict[str, CapabilityProfile] = Field(default_factory=dict)


def _capabilities_path(character_id: str) -> Path:
    return REPO_ROOT / "characters" / character_id / "capabilities.json"


def load_capabilities(character_id: str) -> CharacterCapability:
    """加载角色能力绑定表；文件缺失返回空表（fail-fast 由调用方决定）。"""
    path = _capabilities_path(character_id)
    if not path.exists():
        return CharacterCapability(character_id=character_id)
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    payload.setdefault("character_id", character_id)
    return CharacterCapability.model_validate(payload)


def _apply_env_overlay(binding: CapabilityBinding, profile: str, cap_type: str) -> CapabilityBinding:
    """环境变量覆写（同 lumo_proxy LUMO_VISION_* 模式），优先级高于 json。"""
    prefix = f"LUMO_CAP_{profile.upper()}_{cap_type.upper()}"
    overlay = {
        "model": os.environ.get(f"{prefix}_MODEL"),
        "base_url": os.environ.get(f"{prefix}_BASE_URL"),
        "api_key_env": os.environ.get(f"{prefix}_API_KEY_ENV"),
    }
    changed = False
    for field_name, value in overlay.items():
        if value:
            setattr(binding, field_name, value)
            changed = True
    if changed:
        logger.debug("[capability] %s/%s 应用环境变量覆写 %s_*", profile, cap_type, prefix)
    return binding


def resolve_capability(
    character_id: str,
    capability_type: CapabilityType,
    profile: Optional[str] = None,
) -> CapabilityBinding:
    """解析某角色某端某能力的最终后端绑定。

    每次调用返回独立深拷贝——反复切换 profile 不会互相污染。
    profile 缺失或能力未绑定时抛 KeyError（fail-fast）。
    """
    if capability_type not in _CAPABILITY_TYPES:
        raise ValueError(f"未知能力类型: {capability_type}（可选 {_CAPABILITY_TYPES}）")
    caps = load_capabilities(character_id)
    profile_name = profile or caps.default_profile
    if profile_name not in caps.profiles:
        raise KeyError(f"角色 {character_id} 无 profile '{profile_name}'（现有: {list(caps.profiles)}）")
    binding = copy.deepcopy(caps.profiles[profile_name].get(capability_type))
    return _apply_env_overlay(binding, profile_name, capability_type)
