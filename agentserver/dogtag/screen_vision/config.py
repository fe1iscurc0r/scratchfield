"""
屏幕感知配置模型
"""

from typing import List, Optional

from pydantic import BaseModel, Field


class TriggerRule(BaseModel):
    """触发规则定义"""
    rule_id: str
    name: str = Field(description="规则名称，如'游戏战斗提醒'")
    enabled: bool = True

    # 检测条件
    keywords: list[str] = Field(default_factory=list, description="屏幕中需要包含的关键词")
    absence_keywords: list[str] = Field(default_factory=list, description="不应出现的关键词")
    scene_description: str = Field(default="", description="场景描述，用于AI匹配")

    # 触发行为
    message_template: str = Field(description="发送给用户的消息模板，支持{context}占位符")
    cooldown_seconds: int = Field(default=300, ge=0, description="冷却时间(秒)，避免重复触发")


class ProactiveVisionConfig(BaseModel):
    """主动视觉系统配置"""
    enabled: bool = Field(default=False, description="总开关")

    # 调度配置
    check_interval_seconds: int = Field(default=30, ge=10, le=600, description="检查间隔(秒)")
    max_fps: float = Field(default=0.5, ge=0.1, le=2.0, description="最大截图频率(帧/秒)")

    # AI分析配置
    analysis_mode: str = Field(
        default="smart",
        pattern="^(always|smart|rule_only)$",
        description="分析模式: always-每次AI分析, smart-规则优先+AI兜底, rule_only-仅规则"
    )

    # 触发规则
    trigger_rules: list[TriggerRule] = Field(default_factory=list, description="触发规则列表")

    # 静默期配置
    quiet_hours_start: str | None = Field(None, description="静默开始时间，如'23:00'")
    quiet_hours_end: str | None = Field(None, description="静默结束时间，如'07:00'")

    # 用户活跃度检测
    pause_on_user_inactive: bool = Field(default=True, description="用户不活跃时暂停")
    inactive_threshold_minutes: int = Field(default=10, ge=1, description="不活跃阈值(分钟)")

    # 前端通知配置
    notification_sound: bool = Field(default=True, description="是否播放通知音效")
    notification_duration: int = Field(default=5, ge=3, le=30, description="通知显示时长(秒)")

    # 差异检测配置
    diff_detection_enabled: bool = Field(default=True, description="启用差异检测（节省AI调用）")
    diff_detection_algorithm: str = Field(
        default="phash",
        pattern="^(phash|dhash|ahash|none)$",
        description="差异检测算法: phash-感知hash(推荐), dhash-差分hash, ahash-平均hash, none-禁用"
    )
    diff_threshold: int = Field(default=8, ge=0, le=64, description="pHash汉明距离阈值，<=此值视为相同")
