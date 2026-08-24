#!/usr/bin/env python3
"""
OpenClaw 客户端适配器
用于与 OpenClaw Gateway 进行通信

官方文档: https://docs.openclaw.ai/

API 端点:
- POST /hooks/agent - 发送消息给 Agent
- POST /hooks/wake - 触发系统事件
- POST /tools/invoke - 直接调用工具
"""

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from .state_paths import get_openclaw_state_dir

logger = logging.getLogger("openclaw.client")


class TaskStatus(Enum):
    """任务状态枚举"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class OpenClawTaskEvent:
    """OpenClaw 任务事件（用于追踪中间过程）"""

    ts: str = field(default_factory=lambda: datetime.now().isoformat())
    kind: str = "info"  # info, request, response, error, state
    message: str = ""
    data: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ts": self.ts,
            "kind": self.kind,
            "message": self.message,
            "data": self.data,
        }


@dataclass
class OpenClawTask:
    """OpenClaw 任务数据结构"""

    task_id: str
    message: str
    status: TaskStatus = TaskStatus.PENDING
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: str | None = None
    completed_at: str | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    session_key: str | None = None
    run_id: str | None = None  # OpenClaw 返回的 runId
    events: list[OpenClawTaskEvent] = field(default_factory=list)

    def add_event(self, kind: str, message: str, data: dict[str, Any] | None = None) -> None:
        self.events.append(OpenClawTaskEvent(kind=kind, message=message, data=data))

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "message": self.message,
            "status": self.status.value,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "result": self.result,
            "error": self.error,
            "session_key": self.session_key,
            "run_id": self.run_id,
            "events": [e.to_dict() for e in self.events],
        }


@dataclass
class OpenClawSessionInfo:
    """OpenClaw 调度终端会话信息"""

    session_key: str
    created_at: str
    last_activity: str
    message_count: int = 0
    last_run_id: str | None = None
    status: str = "active"  # active, idle, error

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_key": self.session_key,
            "created_at": self.created_at,
            "last_activity": self.last_activity,
            "message_count": self.message_count,
            "last_run_id": self.last_run_id,
            "status": self.status,
        }


@dataclass
class OpenClawConfig:
    """OpenClaw 配置"""

    # gateway_url 默认值在 __post_init__ 中从 system.config 动态获取
    gateway_url: str = ""
    # Gateway 认证 token (对应 gateway.auth.token)
    gateway_token: str | None = None
    # Hooks 认证 token (对应 hooks.token)
    hooks_token: str | None = None
    # Hooks API 基础路径 (对应 hooks.path)
    hooks_path: str = "/hooks"
    # 请求超时时间（秒）
    timeout: int = 120
    # 默认参数
    default_model: str | None = None
    default_channel: str = "last"

    # 兼容旧配置
    token: str | None = None

    def __post_init__(self):
        # gateway_url 默认值从 system.config 动态获取
        if not self.gateway_url:
            try:
                from system.config import config as _cfg
                self.gateway_url = _cfg.openclaw.gateway_url
            except Exception:
                self.gateway_url = "http://127.0.0.1:20789"
        # 如果只配置了 token，同时用于 gateway 和 hooks
        if self.token and not self.gateway_token:
            self.gateway_token = self.token
        if self.token and not self.hooks_token:
            self.hooks_token = self.token

        # 规范化 hooks_path，避免出现 "hooks" / "/hooks/" 等差异
        path = (self.hooks_path or "/hooks").strip()
        if not path:
            path = "/hooks"
        if not path.startswith("/"):
            path = f"/{path}"
        path = path.rstrip("/")
        self.hooks_path = path or "/hooks"

    def get_gateway_headers(self) -> dict[str, str]:
        """获取 Gateway 请求头"""
        headers = {"Content-Type": "application/json"}
        if self.gateway_token:
            headers["Authorization"] = f"Bearer {self.gateway_token}"
        return headers

    def get_hooks_headers(self) -> dict[str, str]:
        """获取 Hooks 请求头"""
        headers = {"Content-Type": "application/json"}
        if self.hooks_token:
            headers["Authorization"] = f"Bearer {self.hooks_token}"
        return headers

    def get_headers(self) -> dict[str, str]:
        """获取请求头（兼容旧代码）"""
        return self.get_gateway_headers()

    def get_hooks_agent_url(self) -> str:
        """获取 hooks/agent 端点 URL（支持自定义 hooks.path）"""
        return f"{self.gateway_url}{self.hooks_path}/agent"

    def get_hooks_wake_url(self) -> str:
        """获取 hooks/wake 端点 URL（支持自定义 hooks.path）"""
        return f"{self.gateway_url}{self.hooks_path}/wake"


class OpenClawClient:
    """
    OpenClaw 客户端

    基于官方文档实现:
    - https://docs.openclaw.ai/automation/webhook
    - https://docs.openclaw.ai/gateway/tools-invoke-http-api

    功能：
    1. 发送消息给 Agent (POST /hooks/agent)
    2. 触发系统事件 (POST /hooks/wake)
    3. 直接调用工具 (POST /tools/invoke)
    """

    def __init__(self, config: OpenClawConfig | None = None):
        self.config = config or OpenClawConfig()
        self._tasks: dict[str, OpenClawTask] = {}
        self._http_client: httpx.AsyncClient | None = None

        # 调度终端会话信息 - 首次调用时初始化，保持整个运行期间
        self._session_info: OpenClawSessionInfo | None = None
        self._default_session_key: str | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """获取 HTTP 客户端（懒加载，禁用代理确保 localhost 直连）"""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(
                timeout=self.config.timeout,
                proxy=None,  # localhost 请求不走系统代理
            )
        return self._http_client

    async def close(self):
        """关闭客户端"""
        if self._http_client and not self._http_client.is_closed:
            await self._http_client.aclose()
            self._http_client = None

    def _emit_task_event(
        self, task: OpenClawTask, kind: str, message: str, data: dict[str, Any] | None = None
    ) -> None:
        try:
            task.add_event(kind=kind, message=message, data=data)
        except Exception:
            # 事件记录失败不影响主流程
            return

    # ============ 核心 API ============

    async def send_message(
        self,
        message: str,
        session_key: str | None = None,
        workspace: str | None = None,
        name: str | None = None,
        channel: str | None = None,
        to: str | None = None,
        model: str | None = None,
        wake_mode: str = "now",
        deliver: bool = False,
        timeout_seconds: int = 1200,
        max_retries: int = 5,
        retry_interval: float = 3.0,
        task_id: str | None = None,
    ) -> OpenClawTask:
        """
        发送消息给 OpenClaw Agent

        使用 POST /hooks/agent 端点
        文档: https://docs.openclaw.ai/automation/webhook

        Args:
            message: 消息内容 (必需)
            session_key: 会话标识，用于多轮对话
            workspace: 工作区目录（可选）
            name: hook 名称，用于会话摘要前缀 (如 "GitHub", "Naga")
            channel: 输出通道 (last, whatsapp, telegram, discord, slack 等)
            to: 接收者标识
            model: 模型覆盖 (如 "anthropic/claude-3-5-sonnet")
            wake_mode: 唤醒模式 ("now" 或 "next-heartbeat")
            deliver: 是否投递到通道
            timeout_seconds: 等待结果的超时时间（秒），0表示异步不等待
            max_retries: 最大重试次数，默认5次
            retry_interval: 重试间隔（秒），默认2秒

        Returns:
            OpenClawTask: 任务对象
        """
        import asyncio

        # 首次调用时初始化默认 session_key
        if self._default_session_key is None:
            self._default_session_key = f"naga:{uuid.uuid4().hex[:12]}"
            logger.info(f"[OpenClaw] 初始化调度终端会话: {self._default_session_key}")

        # 使用传入的 session_key 或默认的
        actual_session_key = session_key or self._default_session_key

        use_task_id = task_id or str(uuid.uuid4())
        task = OpenClawTask(task_id=use_task_id, message=message, session_key=actual_session_key)

        self._emit_task_event(
            task,
            kind="state",
            message="task_created",
            data={
                "gateway_url": self.config.gateway_url,
                "session_key": actual_session_key,
                "timeout_seconds": timeout_seconds,
            },
        )

        # 构建请求体
        payload: dict[str, Any] = {"message": message}

        # 可选参数
        payload["sessionKey"] = actual_session_key
        if workspace:
            payload["workspace"] = workspace
        if name:
            payload["name"] = name
        if channel:
            payload["channel"] = channel
        elif self.config.default_channel:
            payload["channel"] = self.config.default_channel
        if to:
            payload["to"] = to
        if model:
            payload["model"] = model
        elif self.config.default_model:
            payload["model"] = self.config.default_model
        if wake_mode:
            payload["wakeMode"] = wake_mode
        if deliver:
            payload["deliver"] = deliver
        # 设置超时时间，>0 表示同步等待结果
        if timeout_seconds > 0:
            payload["timeoutSeconds"] = timeout_seconds

        task.started_at = datetime.now().isoformat()
        task.status = TaskStatus.RUNNING

        # HTTP 超时需要比 OpenClaw 的 timeoutSeconds 更长
        http_timeout = max(timeout_seconds + 30, self.config.timeout)
        hooks_agent_url = self.config.get_hooks_agent_url()
        hooks_agent_path = f"{self.config.hooks_path}/agent"

        last_error = None
        for attempt in range(1, max_retries + 1):
            try:
                client = await self._get_client()

                logger.info(
                    f"[OpenClaw] 发送消息到 {hooks_agent_path} (尝试 {attempt}/{max_retries}): {message[:50]}... (timeout={timeout_seconds}s)"
                )

                self._emit_task_event(
                    task,
                    kind="request",
                    message="hooks_agent_request",
                    data={
                        "attempt": attempt,
                        "max_retries": max_retries,
                        "url": hooks_agent_url,
                        "session_key": actual_session_key,
                        "deliver": deliver,
                        "wake_mode": wake_mode,
                        "timeout_seconds": timeout_seconds,
                    },
                )

                response = await client.post(
                    hooks_agent_url,
                    json=payload,
                    headers=self.config.get_hooks_headers(),
                    timeout=http_timeout,
                )

                self._emit_task_event(
                    task,
                    kind="response",
                    message="hooks_agent_response",
                    data={
                        "status_code": response.status_code,
                    },
                )

                # /hooks/agent 返回 200/202
                # 200 表示同步完成（含 reply），202 表示异步接受（需轮询获取回复）
                if response.status_code in (200, 202):
                    try:
                        result = response.json()
                        task.result = result if isinstance(result, dict) else {}
                        task.run_id = result.get("runId")

                        self._emit_task_event(
                            task,
                            kind="state",
                            message="hooks_agent_accepted",
                            data={
                                "run_id": task.run_id,
                                "status": result.get("status", "accepted"),
                            },
                        )

                        # 检查返回状态
                        status = result.get("status", "accepted")
                        if status == "ok" and result.get("reply"):
                            # 同步完成，包含 reply
                            task.status = TaskStatus.COMPLETED
                            task.completed_at = datetime.now().isoformat()
                            reply = result.get("reply", "")
                            logger.info(
                                f"[OpenClaw] 任务同步完成: {task.task_id}, reply: {reply[:100] if reply else 'empty'}..."
                            )

                            self._emit_task_event(
                                task,
                                kind="state",
                                message="task_completed",
                                data={
                                    "run_id": task.run_id,
                                    "reply_preview": (reply[:200] if reply else ""),
                                },
                            )
                        elif timeout_seconds <= 0:
                            # 调用方选择异步投递，不等待最终 reply。
                            task.status = TaskStatus.COMPLETED
                            task.completed_at = datetime.now().isoformat()
                            logger.info(f"[OpenClaw] 任务已异步接受: {task.task_id}, runId: {task.run_id}")
                        else:
                            # 202 异步接受，需要轮询 sessions_history 获取回复
                            task.status = TaskStatus.RUNNING
                            logger.info(
                                f"[OpenClaw] 任务已接受(202): {task.task_id}, runId: {task.run_id}, 开始轮询回复..."
                            )

                            replies = await self._poll_for_reply(
                                actual_session_key,
                                timeout_seconds=timeout_seconds,
                            )
                            if replies:
                                task.status = TaskStatus.COMPLETED
                                task.completed_at = datetime.now().isoformat()
                                if task.result is None:
                                    task.result = {}
                                task.result["replies"] = replies
                                task.result["reply"] = replies[0] if len(replies) == 1 else "\n\n---\n\n".join(replies)
                                logger.info(f"[OpenClaw] 轮询获取{len(replies)}条回复成功")

                                self._emit_task_event(
                                    task,
                                    kind="state",
                                    message="task_completed",
                                    data={
                                        "run_id": task.run_id,
                                        "replies_count": len(replies),
                                        "reply_preview": (str(task.result.get("reply", ""))[:200]),
                                    },
                                )
                            else:
                                task.status = TaskStatus.FAILED
                                task.completed_at = datetime.now().isoformat()
                                last_error = f"OpenClaw 在 {timeout_seconds}s 内未返回可用回复"
                                task.error = last_error
                                logger.warning(f"[OpenClaw] {last_error}")

                                self._emit_task_event(
                                    task,
                                    kind="state",
                                    message="task_failed",
                                    data={
                                        "run_id": task.run_id,
                                        "error": last_error,
                                    },
                                )
                    except Exception:
                        task.result = {"raw": response.text}
                        task.status = TaskStatus.RUNNING

                        self._emit_task_event(
                            task,
                            kind="error",
                            message="hooks_agent_parse_failed",
                            data={
                                "status_code": response.status_code,
                                "raw_preview": response.text[:500] if response.text else "",
                            },
                        )

                    # 更新会话信息
                    session_status = "error" if task.status == TaskStatus.FAILED else "active"
                    self._update_session_info(actual_session_key, task.run_id, session_status)
                    # 成功，跳出重试循环
                    break
                else:
                    last_error = f"HTTP {response.status_code}: {response.text}"
                    logger.warning(f"[OpenClaw] 消息发送失败 (尝试 {attempt}/{max_retries}): {last_error}")

                    # OpenClaw 2026.2.17+ 默认禁止外部 hooks 传入 sessionKey。
                    # 命中该错误时不要做无意义重试，尝试补丁配置并给出明确提示。
                    if (
                        response.status_code == 400
                        and "sessionKey is disabled for external /hooks/agent payloads" in (response.text or "")
                    ):
                        patched = False
                        try:
                            from .llm_config_bridge import ensure_hooks_allow_request_session_key

                            patched = ensure_hooks_allow_request_session_key(auto_create=False)
                        except Exception:
                            patched = False

                        if patched:
                            last_error = (
                                "OpenClaw 拒绝外部 sessionKey（已自动写入 hooks.allowRequestSessionKey=true），"
                                "请重启 OpenClaw Gateway 后重试。"
                            )
                        else:
                            last_error = (
                                "OpenClaw 拒绝外部 sessionKey，请在 ~/.naga/openclaw/openclaw.json 设置 "
                                "hooks.allowRequestSessionKey=true 并重启 OpenClaw Gateway。"
                            )

                        task.status = TaskStatus.FAILED
                        task.error = last_error
                        self._update_session_info(actual_session_key, None, "error")
                        self._emit_task_event(
                            task,
                            kind="state",
                            message="task_failed",
                            data={"error": last_error},
                        )
                        logger.error(f"[OpenClaw] {last_error}")
                        break

                    if response.status_code == 405:
                        last_error = (
                            f"HTTP 405: Method Not Allowed (url={hooks_agent_url})。"
                            f"请检查 openclaw.json 的 hooks.path（当前客户端路径: {self.config.hooks_path}）"
                            "是否与 Gateway 一致，并确认 gateway.mode=local 后重启 Gateway。"
                        )
                        task.status = TaskStatus.FAILED
                        task.error = last_error
                        self._update_session_info(actual_session_key, None, "error")
                        self._emit_task_event(
                            task,
                            kind="state",
                            message="task_failed",
                            data={"error": last_error},
                        )
                        logger.error(f"[OpenClaw] {last_error}")
                        break

                    self._emit_task_event(
                        task,
                        kind="error",
                        message="hooks_agent_http_error",
                        data={
                            "attempt": attempt,
                            "status_code": response.status_code,
                            "error_preview": response.text[:500] if response.text else "",
                        },
                    )

                    if attempt < max_retries:
                        logger.info(f"[OpenClaw] {retry_interval}秒后重试...")
                        await asyncio.sleep(retry_interval)
                    else:
                        # 最后一次尝试也失败了
                        task.status = TaskStatus.FAILED
                        task.error = last_error
                        logger.error(f"[OpenClaw] 消息发送失败，已达最大重试次数: {last_error}")
                        self._update_session_info(actual_session_key, None, "error")

                        self._emit_task_event(
                            task,
                            kind="state",
                            message="task_failed",
                            data={
                                "error": last_error,
                            },
                        )

            except Exception as e:
                last_error = str(e)
                logger.warning(f"[OpenClaw] 消息发送异常 (尝试 {attempt}/{max_retries}): {e}")

                self._emit_task_event(
                    task,
                    kind="error",
                    message="hooks_agent_exception",
                    data={
                        "attempt": attempt,
                        "error": last_error,
                    },
                )

                if attempt < max_retries:
                    logger.info(f"[OpenClaw] {retry_interval}秒后重试...")
                    await asyncio.sleep(retry_interval)
                else:
                    # 最后一次尝试也失败了
                    task.status = TaskStatus.FAILED
                    task.error = last_error
                    logger.error(f"[OpenClaw] 消息发送异常，已达最大重试次数: {e}")
                    if self._session_info:
                        self._session_info.status = "error"

                    self._emit_task_event(
                        task,
                        kind="state",
                        message="task_failed",
                        data={
                            "error": last_error,
                        },
                    )

        self._tasks[task.task_id] = task
        return task

    def _update_session_info(self, session_key: str, run_id: str | None, status: str):
        """更新调度终端会话信息"""
        now = datetime.now().isoformat()

        if self._session_info is None:
            # 首次创建会话信息
            self._session_info = OpenClawSessionInfo(
                session_key=session_key,
                created_at=now,
                last_activity=now,
                message_count=1,
                last_run_id=run_id,
                status=status,
            )
        else:
            # 更新现有会话信息
            self._session_info.last_activity = now
            self._session_info.message_count += 1
            if run_id:
                self._session_info.last_run_id = run_id
            self._session_info.status = status

        # 持久化会话信息
        self.save_session()

    async def _poll_for_reply(
        self,
        session_key: str,
        timeout_seconds: int = 1200,
        poll_interval: float = 3.0,
        initial_delay: float = 1.0,
    ) -> list[str]:
        """
        轮询 sessions_history 获取 Agent 回复

        /hooks/agent 返回 202 后，通过 /tools/invoke 调用 sessions_history
        持续轮询收集所有 assistant 消息，直到消息不再增加或超时。

        Args:
            session_key: 会话标识
            timeout_seconds: 最大等待时间（秒）
            poll_interval: 轮询间隔（秒）
            initial_delay: 首次轮询前等待时间（秒）

        Returns:
            回复文本列表，超时返回收集到的所有消息
        """
        import asyncio
        import time

        await asyncio.sleep(initial_delay)

        start_time = time.time()
        all_replies: list[str] = []
        last_count = 0
        stable_count = 0

        while time.time() - start_time < timeout_seconds:
            attempt = int(time.time() - start_time)
            try:
                client = await self._get_client()

                response = await client.post(
                    f"{self.config.gateway_url}/tools/invoke",
                    json={
                        "tool": "sessions_history",
                        "args": {
                            "sessionKey": session_key,
                            "limit": 50,
                        },
                    },
                    headers=self.config.get_gateway_headers(),
                    timeout=15,
                )

                if response.status_code == 200:
                    data = response.json()
                    replies = self._extract_all_assistant_replies(data)
                    if not replies:
                        replies = self._extract_local_assistant_replies(session_key)
                    current_count = len(replies)

                    if current_count > last_count:
                        delta = current_count - last_count
                        all_replies = replies
                        last_count = current_count
                        stable_count = 0
                        logger.info(
                            f"[OpenClaw] 轮询第{attempt}次: 发现{current_count}条assistant消息 (新增{delta})"
                        )
                    else:
                        stable_count += 1
                        if stable_count >= 2 and current_count > 0:
                            logger.info(f"[OpenClaw] 消息已稳定{stable_count}次，共{current_count}条，结束轮询")
                            return replies

            except Exception as e:
                logger.warning(f"[OpenClaw] 轮询第{attempt}次异常: {e}")

            await asyncio.sleep(poll_interval)

        logger.warning(f"[OpenClaw] 轮询超时({timeout_seconds}s)，共收集{len(all_replies)}条消息")
        return all_replies

    @staticmethod
    def _extract_all_assistant_replies(data: dict[str, Any]) -> list[str]:
        """
        从 sessions_history 返回值中提取所有 assistant 的文本回复
        """
        replies: list[str] = []
        try:
            result = data.get("result", {})
            details = result.get("details", {})
            messages = details.get("messages", [])

            if not messages:
                content = result.get("content", [])
                if content and isinstance(content, list) and len(content) > 0:
                    text = content[0].get("text", "")
                    if isinstance(text, str) and text.strip():
                        try:
                            inner = json.loads(text)
                            messages = inner.get("messages", [])
                        except json.JSONDecodeError:
                            pass

            for msg in messages:
                if msg.get("role") != "assistant":
                    continue
                content = msg.get("content", [])
                if isinstance(content, str):
                    if content.strip():
                        replies.append(content)
                elif isinstance(content, list):
                    text_parts = [
                        item.get("text", "")
                        for item in content
                        if isinstance(item, dict) and item.get("type") == "text"
                    ]
                    text = "\n".join(text_parts)
                    if text.strip():
                        replies.append(text)
        except Exception:
            pass
        return replies

    def _local_sessions_dir(self) -> Path:
        session_file = getattr(self, "_SESSION_FILE", None)
        if isinstance(session_file, Path):
            session_root = session_file.parent
            state_root = session_root / "state"
            sessions_dir = state_root / "agents" / "main" / "sessions"
            if sessions_dir.exists():
                return sessions_dir
        return get_openclaw_state_dir() / "agents" / "main" / "sessions"

    def _resolve_local_session_file(self, session_key: str) -> Path | None:
        sessions_dir = self._local_sessions_dir()
        sessions_index = sessions_dir / "sessions.json"
        if not sessions_index.exists():
            return None

        try:
            index_data = json.loads(sessions_index.read_text(encoding="utf-8"))
        except Exception:
            return None

        candidate_keys = [session_key]
        if not session_key.startswith("agent:main:"):
            candidate_keys.append(f"agent:main:{session_key}")

        record: dict[str, Any] | None = None
        for key in candidate_keys:
            value = index_data.get(key)
            if isinstance(value, dict):
                record = value
                break
        if not record:
            return None

        session_file = record.get("sessionFile")
        if isinstance(session_file, str) and session_file.strip():
            path = Path(session_file).expanduser()
            if path.exists():
                return path

        session_id = str(record.get("sessionId") or "").strip()
        if not session_id:
            return None

        derived = sessions_dir / f"{session_id}.jsonl"
        return derived if derived.exists() else None

    @staticmethod
    def _extract_local_text_from_message(message: dict[str, Any]) -> str:
        content = message.get("content", "")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if not isinstance(item, dict):
                    continue
                if item.get("type") == "text":
                    text = item.get("text", "")
                    if isinstance(text, str) and text.strip():
                        parts.append(text.strip())
            return "\n".join(parts).strip()
        return ""

    @staticmethod
    def _stringify_tool_payload(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        try:
            return json.dumps(value, ensure_ascii=False, indent=2)
        except Exception:
            return str(value)

    @staticmethod
    def _history_timestamp_seconds(value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            numeric = float(value)
            if numeric > 1_000_000_000_000:
                return numeric / 1000.0
            return numeric
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            try:
                numeric = float(text)
                if numeric > 1_000_000_000_000:
                    return numeric / 1000.0
                return numeric
            except Exception:
                pass
            try:
                return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
            except Exception:
                return None
        return None

    @classmethod
    def _history_sort_key(cls, item: dict[str, Any], index: int) -> tuple[int, float, int]:
        message = item.get("message") if isinstance(item.get("message"), dict) else item
        candidates = [
            item.get("timestamp"),
            message.get("timestamp") if isinstance(message, dict) else None,
            item.get("createdAt"),
            message.get("createdAt") if isinstance(message, dict) else None,
            item.get("updatedAt"),
            message.get("updatedAt") if isinstance(message, dict) else None,
        ]
        for candidate in candidates:
            seconds = cls._history_timestamp_seconds(candidate)
            if seconds is not None:
                return (0, seconds, index)
        return (1, float(index), index)

    @classmethod
    def _extract_history_message(cls, item: dict[str, Any]) -> dict[str, Any]:
        message = item.get("message") if isinstance(item.get("message"), dict) else item
        role = str(message.get("role", "unknown") or "unknown").strip()
        raw_content = message.get("content", "")
        text_parts: list[str] = []
        tool_events: list[dict[str, Any]] = []
        usage = message.get("usage")

        if isinstance(raw_content, str):
            if raw_content.strip():
                text_parts.append(raw_content.strip())
        elif isinstance(raw_content, list):
            for block in raw_content:
                if not isinstance(block, dict):
                    continue
                block_type = str(block.get("type", "")).strip().lower().replace("-", "_")
                if block_type == "text":
                    text = block.get("text", "")
                    if isinstance(text, str) and text.strip():
                        text_parts.append(text.strip())
                    continue

                if block_type in {"tool_use", "toolcall", "tool_call"}:
                    tool_events.append(
                        {
                            "type": "tool_call",
                            "name": block.get("name") or block.get("tool_name") or "",
                            "toolCallId": block.get("id") or block.get("tool_use_id") or "",
                            "args": block.get("input") or block.get("args") or block.get("arguments"),
                        }
                    )
                    continue

                if block_type in {"tool_result", "tool_resulterror", "tool_result_error", "toolresult"}:
                    tool_events.append(
                        {
                            "type": "tool_result",
                            "name": block.get("name") or block.get("tool_name") or "",
                            "toolCallId": block.get("tool_use_id") or block.get("toolCallId") or block.get("id") or "",
                            "isError": bool(block.get("is_error", False) or "error" in block_type),
                            "result": cls._stringify_tool_payload(
                                block.get("content", block.get("result", block.get("output", "")))
                            ),
                        }
                    )
                    continue

        role_key = role.lower().replace("-", "_")
        if role_key in {"toolresult", "tool_result"}:
            details = message.get("details")
            text_payload = "\n".join(part for part in text_parts if part).strip()
            if isinstance(details, dict):
                result_payload: Any = {"details": details}
                if text_payload:
                    result_payload["content"] = text_payload
            else:
                result_payload = cls._stringify_tool_payload(text_payload)
            tool_events.append(
                {
                    "type": "tool_result",
                    "name": message.get("toolName") or message.get("tool_name") or "",
                    "toolCallId": message.get("toolCallId") or message.get("tool_call_id") or "",
                    "isError": bool(
                        message.get("isError", False)
                        or message.get("is_error", False)
                        or (isinstance(details, dict) and str(details.get("status", "")).strip().lower() == "error")
                    ),
                    "result": result_payload,
                }
            )
            text_parts = []

        return {
            "role": role,
            "content": "\n\n".join(part for part in text_parts if part).strip(),
            "toolEvents": tool_events,
            "usage": usage if isinstance(usage, dict) else None,
        }

    @classmethod
    def _normalize_history_messages(cls, raw_messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not raw_messages:
            return []

        ordered = [item for item in raw_messages if isinstance(item, dict)]
        indexed_messages = list(enumerate(ordered))
        indexed_messages.sort(key=lambda pair: cls._history_sort_key(pair[1], pair[0]))

        normalized: list[dict[str, Any]] = []
        current_assistant: dict[str, Any] | None = None

        for _, item in indexed_messages:
            extracted = cls._extract_history_message(item)
            role_key = str(extracted.get("role") or "").strip().lower().replace("-", "_")
            content = str(extracted.get("content") or "").strip()
            tool_events = extracted.get("toolEvents") or []

            if role_key == "user":
                current_assistant = None
                if content:
                    normalized.append(
                        {
                            "role": "user",
                            "content": content,
                            "type": "message",
                            "toolEvents": [],
                            "usage": extracted.get("usage"),
                        }
                    )
                continue

            if role_key in {"assistant", "toolresult", "tool_result"}:
                if current_assistant is None:
                    current_assistant = {
                        "role": "assistant",
                        "content": "",
                        "type": "message",
                        "toolEvents": [],
                        "usage": extracted.get("usage"),
                    }
                    normalized.append(current_assistant)

                if content:
                    current_assistant["content"] = (
                        f"{current_assistant['content']}\n\n{content}".strip()
                        if current_assistant["content"]
                        else content
                    )
                if isinstance(tool_events, list) and tool_events:
                    current_assistant["toolEvents"].extend(tool_events)
                if extracted.get("usage") and not current_assistant.get("usage"):
                    current_assistant["usage"] = extracted.get("usage")
                continue

        cleaned: list[dict[str, Any]] = []
        for message in normalized:
            content = str(message.get("content") or "").strip()
            tool_events = message.get("toolEvents") or []
            if message.get("role") == "assistant" and not content and not tool_events:
                continue
            message["content"] = content
            cleaned.append(message)
        return cleaned

    def _read_local_session_messages(self, session_key: str) -> list[dict[str, Any]]:
        session_file = self._resolve_local_session_file(session_key)
        if not session_file:
            return []

        raw_messages: list[dict[str, Any]] = []
        try:
            for line in session_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                if entry.get("type") != "message":
                    continue
                if not isinstance(entry.get("message"), dict):
                    continue
                raw_messages.append(entry)
        except Exception as e:
            logger.warning(f"[OpenClaw] 读取本地会话历史失败: {e}")
            return []
        return self._normalize_history_messages(raw_messages)

    def _read_local_session_transcript(self, session_key: str) -> list[dict[str, Any]]:
        sessions_dir = self._local_sessions_dir()
        candidate_keys = [session_key.strip()]
        if candidate_keys[0] and not candidate_keys[0].startswith("agent:main:"):
            candidate_keys.append(f"agent:main:{candidate_keys[0]}")
        candidate_keys = [key for key in candidate_keys if key]

        candidate_files: list[Path] = []
        primary_file = self._resolve_local_session_file(session_key)
        if primary_file and primary_file.exists():
            candidate_files.append(primary_file)

        try:
            for session_file in sessions_dir.glob("*.jsonl"):
                if session_file in candidate_files:
                    continue
                try:
                    text = session_file.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue
                if any(key in text for key in candidate_keys):
                    candidate_files.append(session_file)
        except Exception as e:
            logger.warning(f"[OpenClaw] 扫描本地 transcript 片段失败: {e}")

        transcript_entries: list[dict[str, Any]] = []
        seen_keys: set[str] = set()
        try:
            for session_file in candidate_files:
                for line_no, raw_line in enumerate(
                    session_file.read_text(encoding="utf-8", errors="ignore").splitlines(),
                    start=1,
                ):
                    line = raw_line.strip()
                    if not line:
                        continue
                    entry = json.loads(line)
                    entry_id = str(entry.get("id") or "").strip()
                    dedupe_key = f"{session_file.name}:{entry_id or line_no}"
                    if dedupe_key in seen_keys:
                        continue
                    seen_keys.add(dedupe_key)
                    transcript_entries.append(
                        {
                            "entryType": entry.get("type"),
                            "id": entry.get("id"),
                            "parentId": entry.get("parentId"),
                            "timestamp": entry.get("timestamp"),
                            "sourceFile": session_file.name,
                            "message": entry.get("message"),
                            "raw": entry,
                        }
                    )
        except Exception as e:
            logger.warning(f"[OpenClaw] 读取本地 transcript 失败: {e}")
            return []

        def _sort_key(item: dict[str, Any]) -> tuple[str, str]:
            timestamp = str(item.get("timestamp") or "")
            source_file = str(item.get("sourceFile") or "")
            return (timestamp, source_file)

        transcript_entries.sort(key=_sort_key)
        return transcript_entries

    def _extract_local_assistant_replies(self, session_key: str) -> list[str]:
        replies: list[str] = []
        for message in self._read_local_session_messages(session_key):
            if message.get("role") != "assistant":
                continue
            text = str(message.get("content") or "").strip()
            if text:
                replies.append(text)
        return replies

    async def wake(self, text: str, mode: str = "now") -> dict[str, Any]:
        """
        触发系统事件

        使用 POST /hooks/wake 端点
        文档: https://docs.openclaw.ai/automation/webhook

        Args:
            text: 事件描述
            mode: 触发模式 ("now" 或 "next-heartbeat")

        Returns:
            响应结果
        """
        try:
            client = await self._get_client()

            payload = {"text": text, "mode": mode}
            hooks_wake_url = self.config.get_hooks_wake_url()

            logger.info(f"[OpenClaw] 触发系统事件: {text[:50]}...")

            response = await client.post(
                hooks_wake_url, json=payload, headers=self.config.get_hooks_headers()
            )

            if response.status_code == 200:
                logger.info("[OpenClaw] 系统事件触发成功")
                try:
                    return {"success": True, "result": response.json()}
                except Exception:
                    return {"success": True, "result": response.text}
            else:
                logger.error(f"[OpenClaw] 系统事件触发失败: {response.status_code}")
                return {"success": False, "error": response.text}

        except Exception as e:
            logger.error(f"[OpenClaw] 系统事件触发异常: {e}")
            return {"success": False, "error": str(e)}

    async def invoke_tool(
        self,
        tool: str,
        args: dict[str, Any] | None = None,
        action: str | None = None,
        session_key: str | None = None,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """
        直接调用工具

        使用 POST /tools/invoke 端点
        文档: https://docs.openclaw.ai/gateway/tools-invoke-http-api

        Args:
            tool: 工具名称 (必需)
            args: 工具参数
            action: 动作映射到工具参数
            session_key: 目标会话标识
            dry_run: 预留功能

        Returns:
            工具执行结果
        """
        try:
            client = await self._get_client()

            payload: dict[str, Any] = {"tool": tool}

            if args:
                payload["args"] = args
            if action:
                payload["action"] = action
            if session_key:
                payload["sessionKey"] = session_key
            if dry_run:
                payload["dryRun"] = dry_run

            logger.info(f"[OpenClaw] 调用工具: {tool}")

            response = await client.post(
                f"{self.config.gateway_url}/tools/invoke", json=payload, headers=self.config.get_gateway_headers()
            )

            if response.status_code == 200:
                logger.info(f"[OpenClaw] 工具调用成功: {tool}")
                try:
                    return {"success": True, "result": response.json()}
                except Exception:
                    return {"success": True, "result": response.text}
            elif response.status_code == 400:
                logger.error(f"[OpenClaw] 工具调用错误: {response.text}")
                return {"success": False, "error": "invalid_request", "detail": response.text}
            elif response.status_code == 401:
                logger.error("[OpenClaw] 认证失败")
                return {"success": False, "error": "unauthorized"}
            elif response.status_code == 404:
                logger.error(f"[OpenClaw] 工具不可用: {tool}")
                return {"success": False, "error": "tool_not_found", "tool": tool}
            else:
                logger.error(f"[OpenClaw] 工具调用失败: {response.status_code}")
                return {"success": False, "error": response.text}

        except Exception as e:
            logger.error(f"[OpenClaw] 工具调用异常: {e}")
            return {"success": False, "error": str(e)}

    # ============ 任务管理 ============

    def get_task(self, task_id: str) -> OpenClawTask | None:
        """获取本地缓存的任务"""
        return self._tasks.get(task_id)

    def get_all_tasks(self) -> list[OpenClawTask]:
        """获取所有本地缓存的任务"""
        return list(self._tasks.values())

    def get_tasks_by_status(self, status: TaskStatus) -> list[OpenClawTask]:
        """按状态获取任务"""
        return [t for t in self._tasks.values() if t.status == status]

    def clear_completed_tasks(self):
        """清理已完成的任务"""
        self._tasks = {
            k: v
            for k, v in self._tasks.items()
            if v.status not in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]
        }

    # ============ 会话历史查询 ============

    async def get_sessions_history(
        self,
        session_key: str | None = None,
        limit: int = 20,
        include_tools: bool = False,
    ) -> dict[str, Any]:
        """
        获取会话历史消息

        使用 POST /tools/invoke 调用 sessions_history 工具

        Args:
            session_key: 会话标识，必须指定
            limit: 返回消息条数限制

        Returns:
            包含历史消息的结果。此函数只负责调用 OpenClaw 的 sessions_history 工具，
            不再隐式回退到本地 transcript。
        """
        # 如果没有指定 session_key，尝试回退到默认会话
        actual_session_key = session_key or self._default_session_key
        if not actual_session_key:
            return {"success": True, "messages": [], "note": "no_session_key_available"}

        try:
            result = await self.invoke_tool(
                tool="sessions_history",
                args={
                    "sessionKey": actual_session_key,
                    "limit": limit,
                    "includeTools": include_tools,
                },
            )

            if result.get("success"):
                # 解析返回的消息
                raw_result = result.get("result", {})
                messages = self._parse_history_messages(raw_result)
                return {"success": True, "session_key": actual_session_key, "messages": messages, "raw": raw_result}
            else:
                return {"success": False, "error": result.get("error", "unknown"), "messages": []}

        except Exception as e:
            logger.error(f"[OpenClaw] 获取会话历史失败: {e}")
            return {"success": False, "error": str(e), "messages": []}

    async def get_local_session_history(
        self,
        session_key: str | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        """
        从本地 transcript 明确读取会话历史。

        此函数只负责读取本地文件，不调用 OpenClaw tools。
        """
        actual_session_key = session_key or self._default_session_key
        if not actual_session_key:
            return {"success": True, "messages": [], "note": "no_session_key_available"}

        messages = self._read_local_session_messages(actual_session_key)
        if limit > 0:
            messages = messages[-limit:]
        return {"success": True, "session_key": actual_session_key, "messages": messages}

    async def get_local_session_transcript(
        self,
        session_key: str | None = None,
        limit: int = 120,
    ) -> dict[str, Any]:
        """
        从本地 transcript 明确读取原始会话记录（不做 assistant/toolResult 合并）。
        """
        actual_session_key = session_key or self._default_session_key
        if not actual_session_key:
            return {"success": True, "messages": [], "note": "no_session_key_available"}

        messages = self._read_local_session_transcript(actual_session_key)
        if limit > 0:
            messages = messages[-limit:]
        return {"success": True, "session_key": actual_session_key, "messages": messages}

    def _parse_history_messages(self, raw_result: dict[str, Any]) -> list[dict[str, Any]]:
        """
        解析 sessions_history 返回的消息格式

        OpenClaw 返回格式:
        {
          "ok": true,
          "result": {
            "content": [{"type": "text", "text": "{...json...}"}],
            "details": {"sessionKey": "...", "messages": [...]}
          }
        }
        """
        messages: list[dict[str, Any]] = []

        try:
            # 尝试从 result 中提取
            if isinstance(raw_result, dict):
                inner_result = raw_result.get("result", raw_result)

                # 优先从 details.messages 获取
                details = inner_result.get("details", {})
                msg_list = details.get("messages", [])
                if msg_list and isinstance(msg_list, list):
                    return self._normalize_history_messages(msg_list)

                # 备选：从 content[].text 解析 JSON
                content = inner_result.get("content", [])
                if content and isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and "text" in item:
                            text = item.get("text", "")
                            # 尝试解析 JSON
                            try:
                                parsed = json.loads(text)
                                if isinstance(parsed, dict):
                                    msg_list = parsed.get("messages", [])
                                    if isinstance(msg_list, list):
                                        messages.extend(self._normalize_history_messages(msg_list))
                            except json.JSONDecodeError:
                                # 不是 JSON，作为原始文本返回
                                if text.strip():
                                    messages.append({"role": "system", "content": text, "type": "raw"})

        except Exception as e:
            logger.warning(f"[OpenClaw] 解析历史消息失败: {e}")

        return messages

    async def get_session_status(self, session_key: str | None = None) -> dict[str, Any]:
        """
        获取当前会话状态

        使用 POST /tools/invoke 调用 sessions_list 工具获取会话信息

        Args:
            session_key: 会话标识（暂未使用，sessions_list 不需要此参数）

        Returns:
            会话状态信息
        """
        try:
            # sessions_list 不需要 sessionKey 参数，它列出所有会话
            result = await self.invoke_tool(tool="sessions_list")

            if result.get("success"):
                raw_result = result.get("result", {})
                # 提取状态文本
                inner_result = raw_result.get("result", {})
                content = inner_result.get("content", [])

                status_text = ""
                if content and isinstance(content, list) and len(content) > 0:
                    status_text = content[0].get("text", "")

                return {"success": True, "status_text": status_text, "raw": raw_result}
            else:
                return {"success": False, "error": result.get("error", "unknown"), "status_text": ""}

        except Exception as e:
            logger.error(f"[OpenClaw] 获取会话状态失败: {e}")
            return {"success": False, "error": str(e), "status_text": ""}

    async def get_sessions_list(self) -> dict[str, Any]:
        """
        获取所有会话列表

        使用 POST /tools/invoke 调用 sessions_list 工具

        Returns:
            会话列表
        """
        try:
            result = await self.invoke_tool(tool="sessions_list")

            if result.get("success"):
                return {
                    "success": True,
                    "sessions": result.get("result", {}),
                }
            else:
                return {"success": False, "error": result.get("error", "unknown"), "sessions": []}

        except Exception as e:
            logger.error(f"[OpenClaw] 获取会话列表失败: {e}")
            return {"success": False, "error": str(e), "sessions": []}

    # ============ 会话信息 ============

    def get_session_info(self) -> dict[str, Any] | None:
        """
        获取当前调度终端会话信息

        Returns:
            会话信息字典，未交互时返回 None
        """
        if self._session_info is None:
            return None
        return self._session_info.to_dict()

    def has_session(self) -> bool:
        """检查是否已有活跃会话"""
        return self._session_info is not None

    def get_default_session_key(self) -> str | None:
        """获取默认会话标识"""
        return self._default_session_key

    # ============ 会话持久化 ============

    _SESSION_FILE = get_openclaw_state_dir() / "openclaw_session.json"

    def save_session(self) -> None:
        """将当前 session_key 持久化到磁盘，重启后可恢复"""
        if not self._default_session_key:
            return
        try:
            self._SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = {"session_key": self._default_session_key}
            if self._session_info:
                data["last_activity"] = self._session_info.last_activity
                data["message_count"] = self._session_info.message_count
            self._SESSION_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            logger.debug(f"[OpenClaw] 会话已持久化: {self._default_session_key}")
        except Exception as e:
            logger.warning(f"[OpenClaw] 会话持久化失败: {e}")

    def restore_session(self) -> bool:
        """从磁盘恢复之前的 session_key（仅在尚未初始化时生效）"""
        if self._default_session_key is not None:
            return False  # 已有会话，跳过
        try:
            if not self._SESSION_FILE.exists():
                return False
            data = json.loads(self._SESSION_FILE.read_text(encoding="utf-8"))
            session_key = data.get("session_key")
            if session_key:
                self._default_session_key = session_key
                logger.info(f"[OpenClaw] 已恢复持久化会话: {session_key}")
                return True
        except Exception as e:
            logger.warning(f"[OpenClaw] 恢复会话失败: {e}")
        return False

    # ============ 健康检查 ============

    async def health_check(self) -> dict[str, Any]:
        """
        检查 OpenClaw Gateway 健康状态

        Returns:
            健康状态信息
        """
        client = await self._get_client()
        acceptable_statuses = {200, 401, 403, 404, 405, 426}

        try:
            # OpenClaw Gateway 主体是 WebSocket 服务，HTTP 根路径常见返回 404/405/426。
            # 只要端口上返回了受控 HTTP 响应，就说明 Gateway 进程已经起来。
            response = await client.get(
                f"{self.config.gateway_url}/", timeout=10, headers=self.config.get_gateway_headers()
            )

            if response.status_code in acceptable_statuses:
                result = {"status": "healthy", "gateway_url": self.config.gateway_url}
                if response.status_code != 200:
                    result["probe_status"] = response.status_code
                return result
            else:
                return {
                    "status": "unhealthy",
                    "gateway_url": self.config.gateway_url,
                    "error": f"HTTP {response.status_code}",
                }

        except Exception as e:
            return {"status": "unreachable", "gateway_url": self.config.gateway_url, "error": str(e)}


# 全局客户端实例（懒加载）
_openclaw_client: OpenClawClient | None = None


def get_openclaw_client(config: OpenClawConfig | None = None) -> OpenClawClient:
    """获取全局 OpenClaw 客户端实例"""
    global _openclaw_client
    if _openclaw_client is None:
        _openclaw_client = OpenClawClient(config)
    return _openclaw_client


def set_openclaw_config(config: OpenClawConfig):
    """设置 OpenClaw 配置并重新创建客户端"""
    global _openclaw_client
    _openclaw_client = OpenClawClient(config)
