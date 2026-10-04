import pytest

# 卷173 测试分层标注：smoke ⊂ core；未标注文件默认 full（pyproject.toml markers）
pytestmark = [pytest.mark.core]
# -*- coding: utf-8 -*-
"""渠道网关层测试：投递链 / ACL / 回复回投 / Telegram normalize。"""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


class TestWebhookChannel(unittest.TestCase):
    def _ch(self):
        from apiserver.channels import WebhookChannel
        return WebhookChannel()

    def test_deliver_normal_flow(self):
        """标准投递：normalize → ACL → message_queue.push 被调。"""
        ch = self._ch()
        with patch("apiserver.message_queue.get_message_queue") as gmq:
            mq = gmq.return_value
            ok = ch.deliver({"sender": "ci-bot", "content": "构建失败：测试 3 例未过",
                             "reply_url": "https://hooks.example.com/cb"})
        self.assertTrue(ok)
        self.assertEqual(ch.received_count, 1)
        # push 参数正确（deliver 用关键字调用）
        kwargs = mq.push.call_args.kwargs
        self.assertEqual(kwargs["content"], "构建失败：测试 3 例未过")
        self.assertEqual(kwargs["source"], "channel:webhook")
        self.assertEqual(kwargs["metadata"]["sender"], "ci-bot")

    def test_acl_whitelist(self):
        from apiserver.channels import WebhookChannel
        ch = WebhookChannel(allowed_senders={"trusted-svc"})
        with patch("apiserver.message_queue.get_message_queue") as gmq:
            ok1 = ch.deliver({"sender": "trusted-svc", "content": "ok"})
            ok2 = ch.deliver({"sender": "attacker", "content": "bad"})
        self.assertTrue(ok1)
        self.assertFalse(ok2, "白名单外的发送者应被拒")
        self.assertEqual(ch.rejected_count, 1)
        self.assertEqual(gmq.return_value.push.call_count, 1)

    def test_garbage_rejected(self):
        ch = self._ch()
        with patch("apiserver.message_queue.get_message_queue") as gmq:
            self.assertFalse(ch.deliver(None))           # 非法类型
            self.assertFalse(ch.deliver({"content": ""}))  # 空内容
            self.assertFalse(ch.deliver({"sender": "x"}))  # 无 content
        self.assertEqual(gmq.return_value.push.call_count, 0)

    def test_content_truncated(self):
        ch = self._ch()
        with patch("apiserver.message_queue.get_message_queue") as gmq:
            ok = ch.deliver({"sender": "s", "content": "A" * 10000})
        self.assertTrue(ok)
        content = gmq.return_value.push.call_args.kwargs["content"]
        # 4096 正文 + "...[截断]" 标记（8 字符）= 上限 4104
        self.assertLessEqual(len(content), 4104)
        self.assertIn("[截断]", content)

    def test_send_reply_to_callback(self):
        ch = self._ch()
        from apiserver.channels import ChannelMessage
        msg = ChannelMessage(channel="webhook", sender="ci",
                             content="x", reply_to="https://hooks.example.com/cb")
        with patch("urllib.request.urlopen") as ur:
            ur.return_value.__enter__.return_value.status = 200
            ok = ch.send_reply(msg, "已收到，正在排查")
        self.assertTrue(ok)
        # 请求体含回复
        req = ur.call_args[0][0]
        self.assertIn("hooks.example.com", req.full_url)


class TestTelegramChannel(unittest.TestCase):
    def _ch(self):
        from apiserver.channels import TelegramChannel
        return TelegramChannel(bot_token="123:ABC",
                               allowed_chat_ids=["10086"])

    def test_normalize_text_message(self):
        ch = self._ch()
        upd = {"update_id": 7, "message": {
            "chat": {"id": 10086}, "from": {"id": 42, "username": "bos"},
            "text": "Lumo，查一下明天的日程"}}
        msg = ch.normalize(upd)
        self.assertIsNotNone(msg)
        self.assertEqual(msg.sender, "42")
        self.assertEqual(msg.reply_to, "10086")
        self.assertEqual(msg.content, "Lumo，查一下明天的日程")

    def test_normalize_rejects_unauthorized_chat(self):
        ch = self._ch()
        upd = {"update_id": 8, "message": {
            "chat": {"id": 999}, "from": {"id": 1}, "text": "hi"}}
        self.assertIsNone(ch.normalize(upd), "非白名单 chat 应被拒")
        self.assertEqual(ch.rejected_count, 1)

    def test_normalize_ignores_non_text(self):
        ch = self._ch()
        upd = {"update_id": 9, "message": {
            "chat": {"id": 10086}, "from": {"id": 42}, "sticker": "👍"}}
        self.assertIsNone(ch.normalize(upd))

    def test_deliver_full_chain(self):
        ch = self._ch()
        with patch("apiserver.message_queue.get_message_queue") as gmq:
            ok = ch.deliver({"update_id": 1, "message": {
                "chat": {"id": 10086}, "from": {"id": 42}, "text": "帮我记一笔"}})
        self.assertTrue(ok)
        kwargs = gmq.return_value.push.call_args.kwargs
        self.assertEqual(kwargs["source"], "channel:telegram")
        self.assertEqual(kwargs["metadata"]["reply_to"], "10086")

    def test_send_reply_calls_tg_api(self):
        ch = self._ch()
        from apiserver.channels import ChannelMessage
        msg = ChannelMessage(channel="telegram", sender="42",
                             content="", reply_to="10086")
        with patch.object(ch, "_tg", return_value={"ok": True}) as tg:
            ok = ch.send_reply(msg, "已记录")
        self.assertTrue(ok)
        tg.assert_called_once_with("sendMessage",
                                   {"chat_id": "10086", "text": "已记录"})

    def test_poll_once_advances_offset(self):
        """轮询游标推进（已确认的 update 不重复处理）。"""
        ch = self._ch()
        with patch.object(ch, "_tg", return_value={
            "ok": True, "result": [
                {"update_id": 100, "message": {"chat": {"id": 10086}, "from": {"id": 42}, "text": "a"}},
                {"update_id": 101, "message": {"chat": {"id": 10086}, "from": {"id": 42}, "text": "b"}},
            ]}):
            with patch("apiserver.message_queue.get_message_queue"):
                n = ch._poll_once()
        self.assertEqual(n, 2)
        self.assertEqual(ch._offset, 102, "游标应到最大 update_id+1")
        # 第二次拉取用新 offset
        with patch.object(ch, "_tg", return_value={"ok": True, "result": []}) as tg:
            ch._poll_once()
        tg.assert_called_once_with("getUpdates", {
            "offset": 102, "timeout": 0, "limit": 10, "allowed_updates": ["message"]})


class TestRegistry(unittest.TestCase):
    def test_init_default_webhook_only(self):
        from apiserver.channels import ChannelRegistry, init_channels_from_config
        reg = init_channels_from_config({})
        names = [s["name"] for s in reg.status()]
        self.assertIn("webhook", names)
        self.assertNotIn("telegram", names, "无 token 不应启动 telegram")

    def test_init_telegram_with_config(self):
        from apiserver.channels import init_channels_from_config
        reg = init_channels_from_config({
            "telegram": {"enabled": True, "bot_token": "123:ABC",
                         "allowed_chat_ids": ["1"], "autostart": False}})
        names = [s["name"] for s in reg.status()]
        self.assertIn("telegram", names)
        tg = reg.get("telegram")
        tg.stop()  # 清理（autostart=False 本不该起线程）

    def test_reply_to_routes_back(self):
        from apiserver.channels import ChannelMessage, WebhookChannel, get_channel_registry
        reg = get_channel_registry()
        reg.register(WebhookChannel())
        ch = reg.get("webhook")
        with patch.object(ch, "send_reply", return_value=True) as sr:
            ok = reg.reply_to("channel:webhook", "回复内容",
                              {"sender": "ci", "reply_to": "https://cb"})
        self.assertTrue(ok)
        sr.assert_called_once()

    def test_reply_to_unknown_source(self):
        from apiserver.channels import get_channel_registry
        reg = get_channel_registry()
        self.assertFalse(reg.reply_to("user", "text"))
        self.assertFalse(reg.reply_to("channel:nope", "text", {}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
