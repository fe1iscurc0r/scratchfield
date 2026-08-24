"""
屏幕感知配置文件加载和保存
"""

import json
import logging
from pathlib import Path
from typing import Optional

from .config import ProactiveVisionConfig, TriggerRule

logger = logging.getLogger(__name__)


def get_config_path() -> Path:
    """获取配置文件路径"""
    from system.config import get_data_dir

    config_path = get_data_dir() / "proactive_vision_config.json"
    return config_path


def get_default_config() -> ProactiveVisionConfig:
    """获取默认配置（包含预设规则）"""
    default_rules = [
        TriggerRule(
            rule_id="game_stage_reminder",
            name="游戏关卡提醒",
            enabled=False,  # 默认关闭，用户手动启用
            keywords=["明日方舟", "开始行动"],
            absence_keywords=[],
            scene_description="明日方舟游戏中进入关卡选择或战斗准备界面",
            message_template="检测到你准备开始新关卡了，需要我提供攻略建议吗？",
            cooldown_seconds=600
        ),
        TriggerRule(
            rule_id="error_detection",
            name="错误检测助手",
            enabled=False,
            keywords=["错误", "Error", "失败", "Warning"],
            absence_keywords=[],
            scene_description="屏幕上出现错误提示或警告弹窗",
            message_template="看起来遇到了问题，需要我帮忙看看吗？",
            cooldown_seconds=300
        ),
        TriggerRule(
            rule_id="long_stay_helper",
            name="长时间停留助手",
            enabled=False,
            keywords=[],
            absence_keywords=[],
            scene_description="用户在同一个界面停留超过5分钟",
            message_template="你在这个界面待了一会儿，需要帮助吗？",
            cooldown_seconds=600
        ),
    ]

    return ProactiveVisionConfig(
        enabled=False,
        check_interval_seconds=30,
        max_fps=0.5,
        analysis_mode="smart",
        trigger_rules=default_rules,
        quiet_hours_start="23:00",
        quiet_hours_end="07:00",
        pause_on_user_inactive=True,
        inactive_threshold_minutes=10,
        notification_sound=True,
        notification_duration=5,
        # 差异检测配置
        diff_detection_enabled=True,
        diff_detection_algorithm="phash",
        diff_threshold=8,
    )


def load_proactive_config() -> ProactiveVisionConfig:
    """加载配置文件，不存在则创建默认配置"""
    config_path = get_config_path()

    if not config_path.exists():
        logger.info(f"[ScreenVision] 配置文件不存在，创建默认配置: {config_path}")
        default_config = get_default_config()
        save_proactive_config(default_config)
        return default_config

    try:
        with open(config_path, encoding="utf-8") as f:
            config_data = json.load(f)
        config = ProactiveVisionConfig(**config_data)
        logger.info(f"[ScreenVision] 配置加载成功: enabled={config.enabled}")
        return config
    except Exception as e:
        logger.error(f"[ScreenVision] 配置加载失败: {e}，使用默认配置")
        return get_default_config()


def save_proactive_config(config: ProactiveVisionConfig) -> bool:
    """保存配置到文件"""
    config_path = get_config_path()

    try:
        # 确保目录存在
        config_path.parent.mkdir(parents=True, exist_ok=True)

        # 保存为格式化的JSON
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config.model_dump(), f, ensure_ascii=False, indent=2)

        logger.info(f"[ScreenVision] 配置保存成功: {config_path}")
        return True
    except Exception as e:
        logger.error(f"[ScreenVision] 配置保存失败: {e}")
        return False


def update_proactive_config(**kwargs) -> ProactiveVisionConfig | None:
    """更新配置项并保存"""
    config = load_proactive_config()

    # 更新字段
    for key, value in kwargs.items():
        if hasattr(config, key):
            setattr(config, key, value)
        else:
            logger.warning(f"[ScreenVision] 未知配置项: {key}")

    # 保存
    if save_proactive_config(config):
        return config
    return None
