"""陆墨 persona 对话通道客户端（httpx，Bearer LUMO_PROXY_TOKEN）。

契约（只读参考 apiserver/routes/lumo_proxy.py）：
  POST {LUMO_API_BASE}/persona/v1/chat/completions
  Authorization: Bearer {LUMO_PROXY_TOKEN}
  body: {model:"lumo", messages:[{role:"user",content}], stream:false,
         session_id, task_type:"conversation"}
  响应：OpenAI ChatCompletion 兼容 → choices[0].message.content

鉴权复用 lumo_proxy.require_proxy_token 的 Bearer 模式（密钥在服务端 hmac.compare_digest 校验）。
"""

from __future__ import annotations

import logging

import httpx

from .config import GatewayConfig

logger = logging.getLogger("lumo_gateway.lumo_client")

_MODEL = "lumo"
_CHAT_ENDPOINT = "/persona/v1/chat/completions"


def split_reply(text: str, limit: int = 2000) -> list[str]:
    """回复超长按 limit 字分段（中文安全：按字符切，不按字节）。空文本返回 []。"""
    if not text:
        return []
    if len(text) <= limit:
        return [text]
    return [text[i : i + limit] for i in range(0, len(text), limit)]


class LumoClient:
    """陆墨 /persona/v1/chat/completions 非流式客户端。"""

    def __init__(
        self,
        api_base: str,
        proxy_token: str,
        timeout: float = 120.0,
        reply_segment_limit: int = 2000,
    ) -> None:
        self.api_base = api_base.rstrip("/")
        self.proxy_token = proxy_token
        self.timeout = timeout
        self.reply_segment_limit = reply_segment_limit
        self._client: httpx.AsyncClient | None = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=self.timeout)
        return self._client

    def build_body(self, content: str, session_id: str, *, task_type: str = "conversation") -> dict:
        """构造 /persona/v1/chat/completions 请求体（供测试断言）。"""
        return {
            "model": _MODEL,
            "messages": [{"role": "user", "content": content}],
            "stream": False,
            "session_id": session_id,
            "task_type": task_type,
        }

    async def chat(self, content: str, session_id: str, *, task_type: str = "conversation") -> str:
        """单次对话，返回陆墨回复全文（非流式）。失败返回 ""（降级纪律）。"""
        url = f"{self.api_base}{_CHAT_ENDPOINT}"
        body = self.build_body(content, session_id, task_type=task_type)
        headers = {"Authorization": f"Bearer {self.proxy_token}"}
        client = self._get_client()
        try:
            resp = await client.post(url, json=body, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:  # noqa: BLE001  # 对话通道故障降级，不抛给上层
            logger.error("[lumo] 请求失败: %s", e)
            return ""
        try:
            return str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as e:
            logger.error("[lumo] 响应缺 choices[0].message.content: %s", e)
            return ""

    async def chat_segmented(self, content: str, session_id: str) -> list[str]:
        """单次对话并按 reply_segment_limit 分段（每段直接回投平台）。"""
        reply = await self.chat(content, session_id)
        return split_reply(reply, self.reply_segment_limit)

    async def aclose(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
        self._client = None


def build_lumo_client(cfg: GatewayConfig) -> LumoClient:
    return LumoClient(
        cfg.lumo_api_base,
        cfg.lumo_proxy_token,
        timeout=cfg.lumo_timeout,
        reply_segment_limit=cfg.reply_segment_limit,
    )
