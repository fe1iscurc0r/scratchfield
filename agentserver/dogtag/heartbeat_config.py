"""
军牌系统 — 心跳配置模型与加载器
"""

import json
import logging
from pathlib import Path

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class HeartbeatConfig(BaseModel):
    """心跳系统配置"""

    enabled: bool = Field(default=False, description="总开关")
    interval_minutes: int = Field(default=30, ge=1, le=1440, description="心跳间隔（分钟）")
    ack_max_chars: int = Field(default=300, ge=50, le=2000, description="静默阈值：响应 ≤ 此长度且含 HEARTBEAT_OK 则不推送")
    active_hours_start: str = Field(default="08:00", description="活跃时段开始，如 '08:00'")
    active_hours_end: str = Field(default="23:00", description="活跃时段结束，如 '23:00'")
    prompt: str = Field(default="", description="自定义心跳 prompt（空则使用默认检查清单）")
    post_conversation_delay_minutes: int = Field(
        default=5, ge=1, le=60,
        description="对话结束后延迟多少分钟执行心跳（事件驱动模式）"
    )


# ── 配置文件加载/保存 ──


def get_config_path() -> Path:
    """获取配置文件路径"""
    from system.config import get_data_dir

    return get_data_dir() / "heartbeat_config.json"


def load_heartbeat_config() -> HeartbeatConfig:
    """加载配置文件，不存在则创建默认配置"""
    config_path = get_config_path()

    if not config_path.exists():
        logger.info(f"[Heartbeat] 配置文件不存在，创建默认配置: {config_path}")
        default_config = HeartbeatConfig()
        save_heartbeat_config(default_config)
        return default_config

    try:
        with open(config_path, encoding="utf-8") as f:
            config_data = json.load(f)
        cfg = HeartbeatConfig(**config_data)
        logger.info(f"[Heartbeat] 配置加载成功: enabled={cfg.enabled}")
        return cfg
    except Exception as e:
        logger.error(f"[Heartbeat] 配置加载失败: {e}，使用默认配置")
        return HeartbeatConfig()


def save_heartbeat_config(cfg: HeartbeatConfig) -> bool:
    """保存配置到文件"""
    config_path = get_config_path()

    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(cfg.model_dump(), f, ensure_ascii=False, indent=2)
        logger.info(f"[Heartbeat] 配置保存成功: {config_path}")
        return True
    except Exception as e:
        logger.error(f"[Heartbeat] 配置保存失败: {e}")
        return False
