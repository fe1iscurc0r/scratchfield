#!/usr/bin/env python3
"""
Agent Server配置文件
OpenClaw 相关配置统一由 system.config.OpenClawConfig 管理（单一来源）。
"""

from dataclasses import dataclass

# ============ 服务器配置 ============

# 从主配置读取端口
try:
    from system.config import get_server_port
    AGENT_SERVER_PORT = get_server_port("agent_server")
except ImportError:
    AGENT_SERVER_PORT = 8001  # 回退默认值

# ============ 全局配置管理 ============

@dataclass
class AgentServerConfig:
    """Agent服务器全局配置"""
    # 服务器配置
    host: str = "0.0.0.0"
    port: int = None

    # 日志配置
    log_level: str = "INFO"
    enable_debug_logs: bool = False

    def __post_init__(self):
        # 设置默认端口
        if self.port is None:
            self.port = AGENT_SERVER_PORT

# 全局配置实例
config = AgentServerConfig()

# ============ 向后兼容 ============

# 保持向后兼容的配置常量
AGENT_SERVER_HOST = config.host
AGENT_SERVER_PORT = config.port
