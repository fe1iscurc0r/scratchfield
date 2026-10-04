"""lumo_gateway 入口：asyncio 事件循环 + adapters + 队列消费者 + 健康检查。

启动方式：
  python -m agentserver.lumo_gateway

硬约束：
  - gateway 绑定 127.0.0.1，不对外暴露
  - 密钥只走环境变量（LUMO_PROXY_TOKEN / QQ_APP_ID / QQ_CLIENT_SECRET）
  - 凭据缺失 fail-fast 日志，但进程仍起、/health 可用（qqbot: down）
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from .adapters.base import PlatformAdapter
from .adapters.qqbot import QQBotAdapter
from .config import GatewayConfig
from .health import HealthServer
from .lumo_client import LumoClient, build_lumo_client, split_reply
from .models import InboundMessage, OutboundMessage
from .queue import MessageQueue
from .session_router import SessionRouter

logger = logging.getLogger("lumo_gateway")


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def build_consumer(
    router: SessionRouter,
    lumo: LumoClient,
    adapters_by_platform: dict[str, PlatformAdapter],
    reply_segment_limit: int,
):
    """构造队列消费者：消息 → 会话路由 → 陆墨对话 → 分段回复回投平台。"""

    async def handle(msg: InboundMessage) -> None:
        adapter = adapters_by_platform.get(msg.platform)
        if adapter is None:
            logger.error("[main] 无 %s 平台适配器，丢弃消息 %s", msg.platform, msg.msg_id)
            return
        session = router.get_or_create(msg.platform, msg.user_id)
        reply = await lumo.chat(msg.content, session.session_id)
        segments = split_reply(reply, reply_segment_limit)
        if not segments:
            logger.warning("[main] 陆墨返回空回复，不回投（msg_id=%s）", msg.msg_id)
            return
        for seg in segments:
            outbound = OutboundMessage(
                platform=msg.platform,
                user_id=msg.user_id,
                content=seg,
                msg_id=msg.msg_id,
                group_id=msg.group_id,
            )
            await adapter.send(outbound)

    return handle


async def main(cfg: GatewayConfig | None = None) -> None:
    cfg = cfg or GatewayConfig.from_env()

    # 铁律7：fail-fast 凭证日志（进程仍起，/health 可用）
    missing = cfg.missing_credentials()
    if missing:
        logger.error(
            "[main] fail-fast：缺失密钥 %s —— lumo 对话通道与 QQ 出站不可用，补齐后重启",
            ", ".join(missing),
        )

    router = SessionRouter(cfg.db_path)
    lumo = build_lumo_client(cfg)
    queue = MessageQueue(maxsize=cfg.queue_maxsize)

    qqbot = QQBotAdapter(
        cfg.qq_app_id,
        cfg.qq_client_secret,
        bot_token=cfg.qq_bot_token,
        dedup_cache=cfg.msg_dedup_cache,
        retry_base=cfg.ws_retry_base,
        retry_max=cfg.ws_retry_max,
    )

    # 全凭据齐备才启动完整链路（QQ 收 → 陆墨 → 回投）
    if cfg.qq_ready() and cfg.lumo_ready():
        qqbot.set_on_message(queue.put)
        queue.start_consumer(
            build_consumer(router, lumo, {"qq": qqbot}, cfg.reply_segment_limit)
        )
        asyncio.create_task(qqbot.run(), name="lumo-gateway-qqbot")
        logger.info("[main] 完整链路已启动（QQ 私聊 → 陆墨 /persona）")
    else:
        logger.error(
            "[main] 凭据缺失：qqbot 保持 down（/health 可见）。"
            "需设置 LUMO_PROXY_TOKEN / QQ_APP_ID / QQ_CLIENT_SECRET",
        )

    # 健康检查：仅绑定 127.0.0.1（不对外暴露）
    health = HealthServer("127.0.0.1", cfg.gateway_port, {"qqbot": qqbot})
    health.start()
    logger.info(
        "[main] gateway 启动完成：health=http://127.0.0.1:%d/health 队列上限=%d",
        health.port, cfg.queue_maxsize,
    )

    try:
        while True:
            await asyncio.sleep(3600)
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("[main] 收到退出信号，正在关闭…")
    finally:
        health.stop()
        await qqbot.close()
        await queue.stop()
        await lumo.aclose()
        router.close()
        logger.info("[main] 已关闭")


if __name__ == "__main__":
    setup_logging()
    asyncio.run(main())
