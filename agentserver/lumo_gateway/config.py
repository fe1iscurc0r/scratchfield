"""lumo_gateway 配置：环境变量优先，默认值兜底。

密钥只走环境变量，不落盘明文：
  LUMO_PROXY_TOKEN / QQ_APP_ID / QQ_CLIENT_SECRET（铁律7 fail-fast 凭证）
"""

from __future__ import annotations

import os
from dataclasses import dataclass

_DEFAULT_API_BASE = "http://127.0.0.1:8000"  # apiserver 默认监听


@dataclass(frozen=True)
class GatewayConfig:
    gateway_port: int = 19090  # 健康检查端口（绑定 127.0.0.1，不对外）
    lumo_api_base: str = _DEFAULT_API_BASE  # 陆墨 apiserver 基地址
    lumo_proxy_token: str = ""  # /persona/v1/chat/completions 的 Bearer 密钥
    qq_app_id: str = ""  # QQ 开放平台机器人 appid
    qq_client_secret: str = ""  # QQ 开放平台机器人 appsecret
    qq_bot_token: str = ""  # 可选：机器人 token（缺省用 client_secret 拼 Bot 头）
    db_path: str = ""  # 会话映射 SQLite 路径（gateway/data/sessions.db）
    queue_maxsize: int = 1024  # 队列上限（背压阈值）
    lumo_timeout: float = 120.0  # lumo 对话超时（秒）
    msg_dedup_cache: int = 1024  # msg_id 去重 LRU 容量
    ws_retry_base: float = 1.0  # WS 断线退避初始（秒）
    ws_retry_max: float = 60.0  # WS 断线退避上限（秒）
    reply_segment_limit: int = 2000  # 回复超长分段上限（字）

    @classmethod
    def from_env(cls) -> "GatewayConfig":
        pkg_dir = os.path.dirname(os.path.abspath(__file__))
        data_dir = os.environ.get("GATEWAY_DATA_DIR", "").strip() or os.path.join(pkg_dir, "data")
        return cls(
            gateway_port=int(os.environ.get("GATEWAY_PORT", "19090")),
            lumo_api_base=os.environ.get("LUMO_API_BASE", _DEFAULT_API_BASE).rstrip("/"),
            lumo_proxy_token=os.environ.get("LUMO_PROXY_TOKEN", "").strip(),
            qq_app_id=os.environ.get("QQ_APP_ID", "").strip(),
            qq_client_secret=os.environ.get("QQ_CLIENT_SECRET", "").strip(),
            qq_bot_token=os.environ.get("QQ_BOT_TOKEN", "").strip(),
            db_path=os.environ.get("GATEWAY_DB_PATH", os.path.join(data_dir, "sessions.db")),
            queue_maxsize=int(os.environ.get("GATEWAY_QUEUE_MAX", "1024")),
            lumo_timeout=float(os.environ.get("LUMO_TIMEOUT", "120.0")),
            msg_dedup_cache=int(os.environ.get("GATEWAY_DEDUP_CACHE", "1024")),
            ws_retry_base=float(os.environ.get("GATEWAY_WS_RETRY_BASE", "1.0")),
            ws_retry_max=float(os.environ.get("GATEWAY_WS_RETRY_MAX", "60.0")),
            reply_segment_limit=int(os.environ.get("GATEWAY_REPLY_LIMIT", "2000")),
        )

    def missing_credentials(self) -> list[str]:
        """缺失的密钥列表（fail-fast 用）。"""
        missing = []
        if not self.lumo_proxy_token:
            missing.append("LUMO_PROXY_TOKEN")
        if not self.qq_app_id:
            missing.append("QQ_APP_ID")
        if not self.qq_client_secret:
            missing.append("QQ_CLIENT_SECRET")
        return missing

    def qq_ready(self) -> bool:
        """QQ adapter 可启动条件：全部 QQ 凭据就绪。"""
        return bool(self.qq_app_id and self.qq_client_secret)

    def lumo_ready(self) -> bool:
        return bool(self.lumo_proxy_token)
