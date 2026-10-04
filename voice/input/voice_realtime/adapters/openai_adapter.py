#!/usr/bin/env python

"""
OpenAI 实时语音适配器
基于 OpenAI Realtime API（WebSocket）的实时语音交互对接。

对接方式（TB04，第十三期专项工单）：
- 真实模式：使用 websockets 库（requirements 已有 websockets>=17.0.1，未引入新依赖）
  连接 wss://api.openai.com/v1/realtime?model=<model>，
  握手头带 Authorization: Bearer <api_key> 与 OpenAI-Beta: realtime=v1，
  连接成功后发送 session.update 配置语音角色与输入音频转写。
- MOCK 模式（诚实降级）：api_key 缺失/为占位符、websockets 不可用、
  网络或认证失败时，自动降级为本地 mock 模式——接口行为可用，
  但 get_status() 中 mode='mock' 显式标注，绝不冒充真实连接。
"""

import asyncio
import json
import logging
import threading
from typing import Any

from ..core.base_client import BaseVoiceClient

logger = logging.getLogger(__name__)

# api_key 占位符黑名单（与 config.json.example 中的示例值对齐，视为未配置）
_PLACEHOLDER_KEYS = {"", "your-api-key", "your_openai_api_key", "sk-xxx", "sk-..."}


class OpenAIVoiceClientAdapter(BaseVoiceClient):
    """
    OpenAI 语音客户端适配器
    桥接 OpenAI Realtime API 到统一接口

    连接模式（self.mode）：
    - 'realtime'：真实 WebSocket 连接
    - 'mock'：本地 mock（诚实降级，状态中显式标注）
    - 'stub'：尚未调用 connect() 的初始状态
    """

    # 默认配置
    DEFAULT_MODEL = 'gpt-4o-realtime-preview'
    DEFAULT_VOICE = 'alloy'
    # 握手超时（秒）
    HANDSHAKE_TIMEOUT_S = 10.0

    def __init__(
        self,
        api_key: str,
        model: str | None = None,
        voice: str | None = None,
        base_url: str | None = None,
        **kwargs
    ):
        """
        初始化 OpenAI 适配器

        参数:
            api_key: OpenAI API密钥（缺失/占位符时将以 mock 模式运行）
            model: 模型名称（默认: gpt-4o-realtime-preview）
            voice: 语音角色（默认: alloy）
                可选: alloy, echo, fable, onyx, nova, shimmer
            base_url: Realtime WebSocket 端点覆盖（默认官方端点；测试可指向本地服务）
            **kwargs: 其他参数
        """
        super().__init__(api_key, **kwargs)

        self.model = model or self.DEFAULT_MODEL
        self.voice = voice or self.DEFAULT_VOICE
        self.base_url = (
            base_url or f"wss://api.openai.com/v1/realtime?model={self.model}"
        )

        # 连接状态（由 connect()/disconnect() 管理）
        self.mode = 'stub'          # 'realtime' | 'mock' | 'stub'
        self._ws: Any = None        # websockets 客户端连接对象
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None

        logger.info(f"OpenAIVoiceClientAdapter initialized: model={self.model}, voice={self.voice}")

    # ---------- 内部工具 ----------

    def _api_key_configured(self) -> bool:
        """api_key 是否已真实配置（非空且非占位符）"""
        key = (self.api_key or "").strip()
        return key not in _PLACEHOLDER_KEYS

    def _enter_mock(self, reason: str) -> None:
        """诚实降级：进入 mock 模式并显式标注原因"""
        self.mode = 'mock'
        logger.warning(
            "OpenAI adapter 降级为 MOCK 模式（诚实降级）：真实 Realtime API 不可用。"
            f"原因: {reason}"
        )

    def _run_async(self, coro) -> Any:
        """在独立事件循环中同步执行异步协程（带握手超时）"""
        async def _with_timeout():
            return await asyncio.wait_for(coro, timeout=self.HANDSHAKE_TIMEOUT_S)

        loop = asyncio.new_event_loop()
        self._loop = loop
        try:
            return loop.run_until_complete(_with_timeout())
        finally:
            loop.close()
            self._loop = None

    async def _open_realtime_ws(self):
        """
        打开 OpenAI Realtime WebSocket 连接。
        独立成方法便于测试打桩（monkeypatch _open_realtime_ws）。
        """
        import websockets  # requirements 已有，运行时才导入以便优雅降级

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "OpenAI-Beta": "realtime=v1",
        }
        # websockets>=14 起 extra_headers 更名为 additional_headers（旧名已从 connect() 签名移除）。
        # 根 pyproject 现约束 websockets>=14.0,<17.0，故此处必须用新名，否则 realtime 连接会 TypeError。
        ws = await websockets.connect(self.base_url, additional_headers=headers)

        # 连接成功后发送 session.update：配置语音角色与输入音频转写
        session_update = {
            "type": "session.update",
            "session": {
                "voice": self.voice,
                "input_audio_transcription": {"model": "whisper-1"},
            },
        }
        await ws.send(json.dumps(session_update))
        return ws

    # ---------- BaseVoiceClient 接口 ----------

    def connect(self) -> bool:
        """
        建立连接

        真实模式：握手 OpenAI Realtime API（超时 10s）。
        以下情况诚实降级为 mock 模式（connect 返回 True，状态标注 mode='mock'）：
        - api_key 缺失或为占位符
        - websockets 库不可用
        - 网络不通 / 握手超时 / 认证失败

        返回:
            bool: 连接是否成功（realtime 或 mock 模式均视为可用）
        """
        if self.mode == 'realtime' and self.is_active():
            logger.debug("OpenAI adapter 已处于连接状态，跳过重复连接")
            return True

        # 1) api_key 未配置 → 直接 mock
        if not self._api_key_configured():
            self._enter_mock("api_key 未配置或为占位符")
            self._trigger_status('connected')
            return True

        # 2) 真实握手
        try:
            self._ws = self._run_async(self._open_realtime_ws())
            self.mode = 'realtime'
            logger.info(f"OpenAI Realtime 已连接: {self.base_url}")
            self._trigger_status('connected')
            return True
        except ImportError as e:
            self._ws = None
            self._enter_mock(f"websockets 库不可用: {e}")
            self._trigger_error(e)
            self._trigger_status('connected')
            return True
        except Exception as e:
            # 网络/认证/超时 → 诚实降级为 mock，记录原始错误
            self._ws = None
            self._enter_mock(f"Realtime 握手失败: {type(e).__name__}: {e}")
            self._trigger_error(e)
            self._trigger_status('connected')
            return True

    def disconnect(self):
        """断开连接（realtime 模式关闭 WebSocket，mock 模式清理状态）"""
        if self.mode == 'realtime' and self._ws is not None:
            ws, self._ws = self._ws, None

            async def _close():
                await ws.close()

            try:
                loop = asyncio.new_event_loop()
                try:
                    loop.run_until_complete(asyncio.wait_for(_close(), timeout=5.0))
                finally:
                    loop.close()
                logger.info("OpenAI Realtime 已断开")
            except Exception as e:
                self._trigger_error(e)
        else:
            logger.info("OpenAI adapter（mock 模式）断开连接")

        self.mode = 'stub'
        self._trigger_status('disconnected')

    def is_active(self) -> bool:
        """检查客户端是否活跃（realtime 模式看 WebSocket 存活，mock 模式看连接标记）"""
        if self.mode == 'realtime':
            if self._ws is None:
                return False
            # websockets 连接对象 open 属性反映底层存活状态
            closed = getattr(self._ws, "close_code", None)
            return closed is None
        if self.mode == 'mock':
            # mock 模式：connect 之后视为可用，disconnect 后置 stub 即不活跃
            return True
        return False

    def manual_interrupt(self) -> bool:
        """手动打断 AI 说话（realtime 模式发送 response.cancel 事件）"""
        if self.mode == 'realtime' and self._ws is not None:
            ws = self._ws

            async def _cancel():
                await ws.send(json.dumps({"type": "response.cancel"}))

            try:
                loop = asyncio.new_event_loop()
                try:
                    loop.run_until_complete(asyncio.wait_for(_cancel(), timeout=5.0))
                finally:
                    loop.close()
                return True
            except Exception as e:
                self._trigger_error(e)
                return False
        logger.warning("OpenAI manual_interrupt()：mock 模式无真实会话可打断")
        return False

    def get_status(self) -> dict:
        """获取客户端状态（mode 字段区分 realtime / mock，mock 显式标注）"""
        notes = {
            'realtime': 'OpenAI Realtime API 真实连接',
            'mock': 'MOCK 模式（诚实降级）：未对接真实 API，接口行为可用',
            'stub': 'Stub：尚未调用 connect()',
        }
        return {
            'active': self.is_active(),
            'provider': 'openai',
            'model': self.model,
            'voice': self.voice,
            'mode': self.mode,
            'note': notes.get(self.mode, '未知状态'),
        }
