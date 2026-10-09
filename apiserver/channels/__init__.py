"""Lumo 渠道网关层 —— 多渠道消息统一入口。

对标 OpenClaw channels 架构（调研 2026-09-20）：
OpenClaw 的 12+ 渠道接入是其 320 万月活的地基；Lumo 此前零渠道入口
（NEKO 插件侧有 bilibili/qq/wechat，但 Lumo apiserver 无统一入口）。

本层设计（自研，语义参考 OpenClaw 的 channel 概念，不整抄）：
- BaseChannel：渠道适配器抽象——normalize（外部格式→标准消息）→
  ACL（准入检查）→ message_queue.push（进 Lumo 对话流）→
  send_reply（回复回投到来源渠道）
- WebhookChannel：通用 webhook 渠道（任何能 POST JSON 的外部系统）
- TelegramChannel：Telegram Bot 渠道（getUpdates 长轮询，纯 HTTP 零本地依赖）
- 挂点：message_queue.push()（agentic_tool_loop 每轮自动 drain 注入对话——
  现成机制，渠道层零侵入）

消息流向：
  外部渠道 → 适配器.normalize → ACL → message_queue.push
  → agentic loop drain → LLM 处理 → send_reply 回投
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

# 渠道回复回投的默认 HTTP 参数
_REPLY_TIMEOUT = 15.0


@dataclass
class ChannelMessage:
    """标准化渠道消息（任何外部渠道 normalize 后的统一形态）。"""
    channel: str              # 渠道标识："telegram" / "webhook" / ...
    sender: str               # 发送者标识（user_id / chat_id / 自定义）
    content: str              # 正文
    reply_to: str = ""        # 回投地址（渠道相关的回信目标：chat_id / callback URL）
    metadata: dict = field(default_factory=dict)  # 渠道原始字段（脱敏后）


class BaseChannel(ABC):
    """渠道适配器基类。

    子类实现三件事：
    1. normalize(raw) → ChannelMessage | None（None=丢弃，如命令回声）
    2. send_reply(msg, reply_text) → bool（回复回投到来源渠道）
    3. （可选）poll_loop() 长轮询拉取（主动型渠道：Telegram）
    """

    name: str = "base"

    def __init__(self, allowed_senders: set[str] | None = None):
        self.allowed_senders = allowed_senders  # None=不限制（ACL 关闭）
        self.received_count = 0
        self.rejected_count = 0
        self.last_activity = 0.0

    # ---------- 准入控制 ----------
    def acl_check(self, msg: ChannelMessage) -> bool:
        """ACL：allowed_senders 为 None 时全放行；配置了则白名单制。"""
        if self.allowed_senders is None:
            return True
        ok = msg.sender in self.allowed_senders
        if not ok:
            self.rejected_count += 1
            logger.warning("[channels] %s 拒绝未授权发送者 %s", self.name, msg.sender[:16])
        return ok

    # ---------- 投递进 Lumo ----------
    def deliver(self, raw: Any) -> bool:
        """完整投递链：normalize → ACL → message_queue.push。"""
        try:
            msg = self.normalize(raw)
        except Exception as e:
            logger.warning("[channels] %s normalize 失败: %s", self.name, e)
            self.rejected_count += 1
            return False
        if msg is None or not msg.content.strip():
            return False
        if not self.acl_check(msg):
            return False
        # 挂点：进消息队列（agentic loop 每轮 drain 注入对话）
        from apiserver.message_queue import get_message_queue
        get_message_queue().push(
            content=msg.content,
            source=f"channel:{self.name}",
            metadata={"sender": msg.sender[:32], "reply_to": msg.reply_to[:128],
                      **({k: str(v)[:64] for k, v in list(msg.metadata.items())[:4]}
                         if msg.metadata else {})},
        )
        self.received_count += 1
        self.last_activity = time.time()
        return True

    @abstractmethod
    def normalize(self, raw: Any) -> ChannelMessage | None:
        """外部原始格式 → ChannelMessage；返回 None 丢弃。"""

    @abstractmethod
    def send_reply(self, msg: ChannelMessage, reply_text: str) -> bool:
        """把 Lumo 的回复回投到来源渠道。"""


# ---------------- 通用 Webhook 渠道 ----------------

class WebhookChannel(BaseChannel):
    """通用 webhook 渠道：外部系统 POST JSON 进来。

    请求体约定（宽松）：
      {"sender": "...", "content": "...", "reply_url": "https://..."}
    reply_url 可选——不提供则只进对话不回投。
    """

    name = "webhook"

    def normalize(self, raw: Any) -> ChannelMessage | None:
        if not isinstance(raw, dict):
            return None
        content = str(raw.get("content", "")).strip()
        if not content:
            return None
        sender = str(raw.get("sender") or "anonymous")[:64]
        # 内容长度闸门（防滥用：单条 4KB）
        if len(content) > 4096:
            content = content[:4096] + "...[截断]"
        return ChannelMessage(
            channel=self.name, sender=sender, content=content,
            reply_to=str(raw.get("reply_url", ""))[:512],
            metadata={},
        )

    def send_reply(self, msg: ChannelMessage, reply_text: str) -> bool:
        if not msg.reply_to:
            return False  # 无回投地址（消息仍已进对话）
        try:
            data = __import__("json").dumps(
                {"reply": reply_text, "channel": self.name,
                 "sender": msg.sender}).encode()
            req = urllib.request.Request(
                msg.reply_to, data=data, method="POST",
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=_REPLY_TIMEOUT) as r:
                return 200 <= r.status < 300
        except Exception as e:
            logger.warning("[channels] webhook 回投失败: %s", e)
            return False


# ---------------- Telegram 渠道 ----------------

class TelegramChannel(BaseChannel):
    """Telegram Bot 渠道（getUpdates 长轮询；纯 HTTP，零本地依赖）。

    配置（config 的 channels.telegram 段）：
      bot_token: BotFather 发的 token
      allowed_chat_ids: ["12345"] 白名单（强烈建议配置——OpenClaw 的
        Shodan 暴露事故教训：公网渠道必须 ACL）
      poll_interval: 轮询间隔秒（默认 3）
    """

    name = "telegram"
    _API = "https://api.telegram.org/bot{token}/{method}"

    def __init__(self, bot_token: str, allowed_chat_ids: list[str] | None = None,
                 allowed_senders: set[str] | None = None,
                 poll_interval: float = 3.0):
        super().__init__(allowed_senders=allowed_senders)
        self.bot_token = bot_token
        self.allowed_chat_ids = set(str(c) for c in allowed_chat_ids) if allowed_chat_ids else None
        self.poll_interval = poll_interval
        self._offset = 0            # getUpdates 游标（确认过的 update_id+1）
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # ---- Telegram API 封装 ----
    def _tg(self, method: str, payload: dict | None = None) -> dict | None:
        try:
            data = __import__("json").dumps(payload or {}).encode()
            req = urllib.request.Request(
                self._API.format(token=self.bot_token, method=method),
                data=data, method="POST",
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as r:
                out = __import__("json").loads(r.read().decode())
                return out if out.get("ok") else None
        except Exception as e:
            logger.debug("[channels] telegram %s 失败: %s", method, e)
            return None

    def normalize(self, raw: Any) -> ChannelMessage | None:
        """Telegram update → ChannelMessage（只取 text 消息）。"""
        if not isinstance(raw, dict):
            return None
        msg = raw.get("message") or raw.get("edited_message") or {}
        text = (msg.get("text") or "").strip()
        if not text:
            return None  # 贴纸/图片/语音暂不处理（进对话无文本可注）
        chat_id = str(msg.get("chat", {}).get("id", ""))
        # chat 白名单（与 sender ACL 双层：chat 是会话级，更符合 TG 习惯）
        if self.allowed_chat_ids is not None and chat_id not in self.allowed_chat_ids:
            self.rejected_count += 1
            logger.warning("[channels] telegram 拒绝未授权 chat %s", chat_id[:16])
            return None
        sender = str((msg.get("from") or {}).get("id", chat_id))
        return ChannelMessage(
            channel=self.name, sender=sender, content=text[:4096],
            reply_to=chat_id,  # 回投目标=chat_id
            metadata={"username": (msg.get("from") or {}).get("username", "")},
        )

    def send_reply(self, msg: ChannelMessage, reply_text: str) -> bool:
        out = self._tg("sendMessage", {
            "chat_id": msg.reply_to,
            "text": reply_text[:4096],  # TG 单条上限
        })
        return out is not None

    # ---- 长轮询 ----
    def _poll_once(self) -> int:
        """拉一批 updates，逐条 deliver。返回处理条数。"""
        out = self._tg("getUpdates", {
            "offset": self._offset, "timeout": 0,
            "limit": 10, "allowed_updates": ["message"]})
        if not out:
            return 0
        n = 0
        for upd in out.get("result", []):
            self._offset = max(self._offset, int(upd.get("update_id", 0)) + 1)
            if self.deliver(upd):
                n += 1
        return n

    def _run(self) -> None:
        """轮询主循环（线程内跑；异常不退出，退避重试）。"""
        fail_streak = 0
        while not self._stop.is_set():
            try:
                self._poll_once()
                fail_streak = 0
            except Exception as e:
                fail_streak += 1
                logger.warning("[channels] telegram 轮询异常(%d): %s", fail_streak, e)
            # 退避：连续失败最多 60s
            wait = min(self.poll_interval * (1 + fail_streak), 60.0)
            self._stop.wait(wait)

    def start(self) -> None:
        """启动轮询线程（幂等）。"""
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name=f"channel-{self.name}", daemon=True)
        self._thread.start()
        logger.info("[channels] telegram 轮询已启动")

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None


# ---------------- 渠道注册表 ----------------

class ChannelRegistry:
    """渠道注册表：路由层注册/查询；渠道实例进程级管理。"""

    def __init__(self):
        self._channels: dict[str, BaseChannel] = {}

    def register(self, channel: BaseChannel) -> None:
        self._channels[channel.name] = channel

    def get(self, name: str) -> BaseChannel | None:
        return self._channels.get(name)

    def status(self) -> list[dict]:
        return [
            {"name": c.name, "received": c.received_count,
             "rejected": c.rejected_count,
             "last_activity": c.last_activity,
             "acl": "on" if c.allowed_senders is not None or
                    getattr(c, "allowed_chat_ids", None) is not None else "off"}
            for c in self._channels.values()
        ]

    def reply_to(self, source: str, reply_text: str,
                 metadata: dict | None = None) -> bool:
        """loop 侧回投入口：按 source（"channel:<name>"）找到渠道回信。"""
        if not source.startswith("channel:"):
            return False
        name = source.split(":", 1)[1]
        ch = self._channels.get(name)
        if ch is None:
            return False
        msg = ChannelMessage(
            channel=name,
            sender=str((metadata or {}).get("sender", "")),
            content="",
            reply_to=str((metadata or {}).get("reply_to", "")),
        )
        if not msg.reply_to:
            return False
        try:
            return ch.send_reply(msg, reply_text)
        except Exception as e:
            logger.warning("[channels] 回投 %s 失败: %s", name, e)
            return False


# 进程级单例
_registry: ChannelRegistry | None = None


_registry_lock = threading.Lock()


def get_channel_registry() -> ChannelRegistry:
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = ChannelRegistry()
    return _registry


def init_channels_from_config(cfg: dict) -> ChannelRegistry:
    """按配置初始化渠道（api_server 启动时调一次）。

    cfg 形如（config 的 channels 段）：
      {"webhook": {"enabled": true, "allowed_senders": [...]},
       "telegram": {"enabled": true, "bot_token": "...", "allowed_chat_ids": [...]}}
    """
    reg = get_channel_registry()
    # webhook（默认启用——本地 API 生态零风险）
    wh_cfg = (cfg or {}).get("webhook") or {}
    if wh_cfg.get("enabled", True):
        reg.register(WebhookChannel(
            allowed_senders=set(wh_cfg.get("allowed_senders", [])) or None))
    # telegram（显式启用才开——要 token）
    tg_cfg = (cfg or {}).get("telegram") or {}
    if tg_cfg.get("enabled") and tg_cfg.get("bot_token"):
        tg = TelegramChannel(
            bot_token=str(tg_cfg["bot_token"]),
            allowed_chat_ids=tg_cfg.get("allowed_chat_ids"),
            poll_interval=float(tg_cfg.get("poll_interval", 3.0)))
        reg.register(tg)
        if tg_cfg.get("autostart", True):
            tg.start()
    return reg
