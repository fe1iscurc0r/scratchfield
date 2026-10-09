#!/usr/bin/env python3
"""
OpenClaw 状态检测器
自动检测 OpenClaw 安装状态、配置和 Gateway 连接
"""

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional

from .state_paths import get_openclaw_config_path, get_openclaw_state_dir
import threading

logger = logging.getLogger("openclaw.detector")


def _get_gateway_port() -> int:
    """从 system.config 读取 Gateway 端口（单一来源）。"""
    try:
        from system.config import config as _cfg
        return _cfg.openclaw.gateway_port
    except Exception:
        return 20789


@dataclass
class OpenClawStatus:
    """OpenClaw 状态信息"""
    # 安装状态
    installed: bool = False
    source_mode: bool = False
    config_path: str | None = None

    # Gateway 配置
    gateway_url: str | None = None
    gateway_port: int = 0  # 0 表示尚未初始化，运行时从 config 读
    gateway_token: str | None = None
    gateway_enabled: bool = False

    # Hooks 配置
    hooks_enabled: bool = False
    hooks_token: str | None = None
    hooks_path: str = "/hooks"

    # 连接状态
    gateway_reachable: bool = False

    # 其他信息
    version: str | None = None
    workspace: str | None = None
    primary_model: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "installed": self.installed,
            "source_mode": self.source_mode,
            "config_path": self.config_path,
            "gateway_url": self.gateway_url,
            "gateway_port": self.gateway_port,
            "gateway_token": self.gateway_token,
            "gateway_enabled": self.gateway_enabled,
            "hooks_enabled": self.hooks_enabled,
            "hooks_token": self.hooks_token,
            "hooks_path": self.hooks_path,
            "gateway_reachable": self.gateway_reachable,
            "version": self.version,
            "workspace": self.workspace,
            "primary_model": self.primary_model
        }


class OpenClawDetector:
    """OpenClaw 状态检测器"""

    @property
    def OPENCLAW_DIR(self):
        return get_openclaw_state_dir()

    @property
    def OPENCLAW_CONFIG(self):
        return get_openclaw_config_path()

    def __init__(self):
        self._cached_status: OpenClawStatus | None = None

    def detect(self, check_connection: bool = False) -> OpenClawStatus:
        """
        检测 OpenClaw 状态

        Args:
            check_connection: 是否检查 Gateway 连接状态

        Returns:
            OpenClawStatus 对象
        """
        status = OpenClawStatus()
        status.gateway_port = _get_gateway_port()

        # 1. 检查是否安装（目录是否存在）
        if self.OPENCLAW_DIR.exists():
            status.installed = True
            status.config_path = str(self.OPENCLAW_CONFIG)

            # 2. 读取配置文件
            if self.OPENCLAW_CONFIG.exists():
                try:
                    config = self._read_config()
                    if config:
                        self._parse_config(config, status)
                except Exception as e:
                    logger.warning(f"读取 OpenClaw 配置失败: {e}")

        # 打包环境下，即使 ~/.naga/openclaw 不存在，只要内嵌运行时可用也标记为已安装
        from .embedded_runtime import get_embedded_runtime
        runtime = get_embedded_runtime()
        if not status.installed:
            if runtime.is_vendor_ready:
                status.installed = True
                logger.info(f"vendor 模式可用（{runtime.runtime_mode}），标记 OpenClaw 为已安装")

        # 3. 检查 Gateway 连接（可选）
        if check_connection and status.gateway_url:
            status.gateway_reachable = self._check_gateway_connection(status.gateway_url)

        self._cached_status = status
        return status

    def _read_config(self) -> dict[str, Any] | None:
        """读取 OpenClaw 配置文件"""
        try:
            with open(self.OPENCLAW_CONFIG, encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"读取 OpenClaw 配置文件失败: {e}")
            return None

    def _parse_config(self, config: dict[str, Any], status: OpenClawStatus):
        """解析配置文件"""
        # Gateway 配置
        gateway = config.get("gateway", {})
        status.gateway_enabled = gateway.get("enabled", False)
        status.gateway_port = gateway.get("port", _get_gateway_port())

        # 构建 Gateway URL
        host = gateway.get("host", "127.0.0.1")
        bind = gateway.get("bind", "loopback")
        if bind == "loopback":
            host = "127.0.0.1"
        status.gateway_url = f"http://{host}:{status.gateway_port}"

        # 认证 token
        auth = gateway.get("auth", {})
        if auth.get("mode") == "token":
            status.gateway_token = auth.get("token")
        elif auth.get("mode") == "password":
            # password 模式使用 password 作为 token
            status.gateway_token = auth.get("password")

        # Hooks 配置
        hooks = config.get("hooks", {})
        status.hooks_enabled = hooks.get("enabled", False)
        status.hooks_token = hooks.get("token")
        hooks_path = hooks.get("path", "/hooks")
        if isinstance(hooks_path, str) and hooks_path.strip():
            status.hooks_path = hooks_path
        else:
            status.hooks_path = "/hooks"

        # 版本信息
        meta = config.get("meta", {})
        status.version = meta.get("lastTouchedVersion")

        # Agent 配置
        agents = config.get("agents", {})
        defaults = agents.get("defaults", {})
        status.workspace = defaults.get("workspace")

        # 主模型
        model_config = defaults.get("model", {})
        status.primary_model = model_config.get("primary")

    def _check_gateway_connection(self, url: str) -> bool:
        """检查 Gateway 连接状态"""
        try:
            import socket
            from urllib.parse import urlparse

            parsed = urlparse(url)
            host = parsed.hostname or "127.0.0.1"
            port = parsed.port or _get_gateway_port()

            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex((host, port))
            sock.close()

            return result == 0
        except Exception as e:
            logger.debug(f"Gateway 连接检查失败: {e}")
            return False

    async def check_gateway_health_async(self, url: str, token: str | None = None) -> dict[str, Any]:
        """异步检查 Gateway 健康状态"""
        acceptable_statuses = {200, 401, 403, 404, 405, 426}
        try:
            import httpx

            headers = {"Content-Type": "application/json"}
            if token:
                headers["Authorization"] = f"Bearer {token}"

            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{url}/", headers=headers)

                if response.status_code in acceptable_statuses:
                    result = {
                        "status": "healthy",
                        "reachable": True,
                        "url": url,
                    }
                    if response.status_code != 200:
                        result["probe_status"] = response.status_code
                    return result
                else:
                    return {
                        "status": "unhealthy",
                        "reachable": True,
                        "url": url,
                        "error": f"HTTP {response.status_code}"
                    }
        except Exception as e:
            return {
                "status": "unreachable",
                "reachable": False,
                "url": url,
                "error": str(e)
            }

    def get_cached_status(self) -> OpenClawStatus | None:
        """获取缓存的状态"""
        return self._cached_status

    def get_token(self) -> str | None:
        """快速获取 gateway token"""
        if self._cached_status:
            return self._cached_status.gateway_token

        status = self.detect()
        return status.gateway_token

    def get_hooks_token(self) -> str | None:
        """快速获取 hooks token"""
        if self._cached_status:
            return self._cached_status.hooks_token

        status = self.detect()
        return status.hooks_token

    def get_gateway_url(self) -> str | None:
        """快速获取 Gateway URL"""
        if self._cached_status:
            return self._cached_status.gateway_url

        status = self.detect()
        return status.gateway_url

    def is_installed(self) -> bool:
        """检查是否安装"""
        return self.OPENCLAW_DIR.exists()


# 全局检测器实例
_detector: OpenClawDetector | None = None


_detector_lock = threading.Lock()


def get_openclaw_detector() -> OpenClawDetector:
    """获取全局检测器实例"""
    global _detector
    if _detector is None:
        with _detector_lock:
            if _detector is None:
                _detector = OpenClawDetector()
    return _detector


def detect_openclaw(check_connection: bool = False) -> OpenClawStatus:
    """快速检测 OpenClaw 状态"""
    return get_openclaw_detector().detect(check_connection)


def get_openclaw_token() -> str | None:
    """快速获取 OpenClaw gateway token"""
    return get_openclaw_detector().get_token()


def get_openclaw_hooks_token() -> str | None:
    """快速获取 OpenClaw hooks token"""
    return get_openclaw_detector().get_hooks_token()


def get_openclaw_gateway_url() -> str | None:
    """快速获取 OpenClaw Gateway URL"""
    return get_openclaw_detector().get_gateway_url()
