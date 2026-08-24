"""lumo_gateway —— 陆墨接入 QQ 的轻量 Gateway（SPEC-11 方案 B，M1：QQ C2C 私聊直连）。

职责：
  QQ 私聊消息 → 归一化 → 消息队列 → 会话路由 → 陆墨 /persona/v1/chat/completions → 回复回投 QQ。

模块拆分（照 SPEC-11 §二）：
  main.py            入口：asyncio 事件循环，加载 adapters，启动队列消费者
  config.py          配置：端口、LUMO_PROXY_TOKEN、平台凭据（环境变量优先）
  models.py          InboundMessage / OutboundMessage / SessionMap 数据类
  queue.py           消息队列（asyncio.Queue + 消费者任务 + 背压）
  session_router.py  platform:user_id → 陆墨 session_id 映射（SQLite 持久化）
  lumo_client.py     调陆墨 /persona/v1/chat/completions（httpx，Bearer LUMO_PROXY_TOKEN）
  adapters/          PlatformAdapter 抽象基类 + QQ Bot API v2（WS 收事件 + REST 出站）
  health.py          /health 健康检查（供 systemd 探活）

硬约束：
  - 不碰 NEKO / apiserver 主流程（lumo_proxy 只读不修改）
  - 不点 OpenClaw gateway（20789 保持空置）
  - 不新增公网端口：gateway 绑定 127.0.0.1
  - 密钥走环境变量，不落盘明文
"""

from .models import InboundMessage, OutboundMessage, SessionMap

__all__ = ["InboundMessage", "OutboundMessage", "SessionMap"]
__version__ = "0.1.0"
