from __future__ import annotations

import logging
from typing import Any

import httpx

from apiserver import naga_auth
from system.config import get_config

logger = logging.getLogger(__name__)


class QQNotifyDeliveryError(RuntimeError):
    def __init__(self, message: str, *, status_code: int):
        super().__init__(message)
        self.status_code = status_code


def build_travel_summary_message(session: Any) -> str:
    base_summary = (getattr(session, "summary", None) or "").strip()
    if not base_summary:
        base_summary = f"旅行完成，共发现 {len(getattr(session, 'discoveries', []) or [])} 个内容。"

    lines = [
        base_summary,
        "",
        f"发现条目：{len(getattr(session, 'discoveries', []) or [])}",
        f"唯一来源：{getattr(session, 'unique_sources', 0) or 0}",
    ]

    agent_name = getattr(session, "agent_name", None)
    if agent_name:
        lines.append(f"执行干员：{agent_name}")

    forum_post_id = getattr(session, "forum_post_id", None)
    if forum_post_id:
        lines.append(f"论坛精华帖：{forum_post_id}")

    return "\n".join(lines).strip()


def build_travel_full_report_message(session: Any) -> str:
    summary_text = (getattr(session, "summary", None) or "").strip() or "旅行已完成"
    lines = [
        "🌍 探索完整报告",
        summary_text,
        "",
        f"发现条目：{len(getattr(session, 'discoveries', []) or [])}",
        f"唯一来源：{getattr(session, 'unique_sources', 0) or 0}",
        f"工具统计：{getattr(session, 'tool_stats', None) or {}}",
    ]
    forum_post_id = getattr(session, "forum_post_id", None)
    if forum_post_id:
        lines.extend(["", f"论坛精华帖已发布，post_id={forum_post_id}"])
    return "\n".join(lines)


def _resolve_feishu_target() -> str | None:
    cfg = get_config()
    notifications = cfg.notifications.feishu
    openclaw_feishu = cfg.openclaw.feishu
    has_app = bool(openclaw_feishu.app_id.strip()) and bool(openclaw_feishu.app_secret.strip())
    if not notifications.enabled or not openclaw_feishu.enabled or not has_app:
        return None

    target = (
        notifications.recipient_chat_id.strip()
        if notifications.recipient_type == "chat_id"
        else notifications.recipient_open_id.strip()
    )
    return target or None


def _render_qq_message(session: Any) -> str:
    return build_travel_summary_message(session)


async def _resolve_naga_user_id_strict() -> str:
    user_info = naga_auth.get_user_info()
    username = str((user_info or {}).get("username") or "").strip()
    if username:
        return username

    token = naga_auth.get_access_token()
    if not token:
        await naga_auth.ensure_access_token()
        token = naga_auth.get_access_token()
    if not token:
        raise RuntimeError("缺少当前登录 access_token，无法确定 naga_user_id")

    user_info = await naga_auth.get_me(token)
    username = str((user_info or {}).get("username") or "").strip()
    if not username:
        raise RuntimeError("当前登录态缺少 username，无法确定 naga_user_id")
    return username


def _resolve_qq_notify_url() -> str:
    return ""


async def _build_qq_notify_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}

    token = naga_auth.get_access_token()
    if not token:
        await naga_auth.ensure_access_token()
        token = naga_auth.get_access_token()
    if not token:
        raise RuntimeError("缺少 access_token，无法发送 QQ notify")
    headers["Authorization"] = f"Bearer {token}"
    return headers


async def _build_qq_payload(session: Any) -> dict[str, Any]:
    cfg = get_config()
    qq_cfg = cfg.notifications.qq

    naga_user_id = await _resolve_naga_user_id_strict()
    qq_user_id = qq_cfg.user_qq.strip()
    if not qq_user_id.isdigit():
        raise RuntimeError(f"QQ 绑定信息无效: user_qq={qq_user_id!r}")

    payload: dict[str, Any] = {
        "event": "explore.completed",
        "trace_id": f"travel:{session.session_id}",
        "idempotency_key": f"travel:{session.session_id}:qq:{qq_user_id}",
        "naga_user_id": naga_user_id,
        "message": _render_qq_message(session),
        "channel": "qq",
        "qq_user_id": int(qq_user_id),
        "metadata": {
            "session_id": session.session_id,
            "agent_name": getattr(session, "agent_name", None),
            "result_count": len(getattr(session, "discoveries", []) or []),
            "forum_post_id": getattr(session, "forum_post_id", None),
            "naga_user_id": naga_user_id,
        },
    }
    return payload


async def _deliver_qq_payload(payload: dict[str, Any]) -> str:
    notify_url = _resolve_qq_notify_url()
    headers = await _build_qq_notify_headers()

    logger.info(
        "[旅行] QQ notify request: event=%s naga_user_id=%s qq_user_id=%s trace_id=%s url=%s",
        payload.get("event"),
        payload.get("naga_user_id"),
        payload.get("qq_user_id"),
        payload.get("trace_id"),
        notify_url,
    )

    async with httpx.AsyncClient(timeout=httpx.Timeout(15.0), trust_env=False) as client:
        response = await client.post(notify_url, json=payload, headers=headers)

    response_text = response.text.strip()
    response_json: dict[str, Any] | None = None
    try:
        response_json = response.json()
    except Exception:
        response_json = None

    if response.status_code >= 400:
        detail = (
            (response_json or {}).get("error")
            or (response_json or {}).get("detail")
            or response_text
            or f"HTTP {response.status_code}"
        )
        if response.status_code == 401:
            auth_mode = "X-Internal-Secret" if "X-Internal-Secret" in headers else "Bearer token"
            detail = f"{detail}（QQ notify 鉴权失败，当前使用 {auth_mode} 调用 {notify_url}）"
        raise QQNotifyDeliveryError(detail, status_code=response.status_code)

    if response_json and response_json.get("ok") is False:
        raise QQNotifyDeliveryError(
            response_json.get("error")
            or response_json.get("message")
            or "通知服务返回失败",
            status_code=502,
        )

    delivery_id = (response_json or {}).get("delivery_id")
    logger.info(
        "[旅行] QQ notify accepted: event=%s trace_id=%s delivery_id=%s",
        payload.get("event"),
        payload.get("trace_id"),
        delivery_id,
    )
    return f"accepted:{delivery_id}" if delivery_id else "accepted"


async def send_test_qq_notification(
    qq_user_id: str,
    message: str | None = None,
    naga_user_id: str | None = None,
) -> str:
    qq_value = str(qq_user_id or "").strip()
    if not qq_value:
        raise ValueError("缺少 QQ 号")
    if not qq_value.isdigit():
        raise ValueError("QQ 号必须是纯数字")

    normalized_naga_user_id = str(naga_user_id or "").strip()
    if not normalized_naga_user_id:
        normalized_naga_user_id = await _resolve_naga_user_id_strict()
    message_content = (message or "这是一条来自 Naga 的 QQ 通知测试消息，用于验证机器人回调链路是否可用。").strip()

    payload: dict[str, Any] = {
        "event": "explore.test",
        "trace_id": f"travel:test:qq:{qq_value}",
        "idempotency_key": f"travel:test:qq:{qq_value}",
        "naga_user_id": normalized_naga_user_id,
        "message": message_content,
        "channel": "qq",
        "qq_user_id": int(qq_value),
        "metadata": {
            "test": True,
            "qq_user_id": qq_value,
            "naga_user_id": normalized_naga_user_id,
        },
    }
    return await _deliver_qq_payload(payload)


async def deliver_travel_completion_notifications(session: Any, travel_client: Any | None) -> dict[str, str]:
    cfg = get_config()
    statuses: dict[str, str] = dict(getattr(session, "notification_delivery_statuses", {}) or {})

    feishu_target = _resolve_feishu_target()
    if cfg.notifications.feishu.enabled:
        if session.deliver_channel == "feishu" and session.full_report_delivery_status == "delivered":
            statuses["feishu"] = "delivered_full_report"
        elif feishu_target and travel_client is not None:
            try:
                await travel_client.send_message(
                    message=build_travel_summary_message(session),
                    deliver=True,
                    session_key=getattr(session, "openclaw_session_key", None),
                    name="NagaTravel",
                    channel="feishu",
                    to=feishu_target,
                    timeout_seconds=30,
                )
                statuses["feishu"] = "delivered_summary"
            except Exception as exc:
                statuses["feishu"] = f"failed:{exc}"
                logger.warning("[旅行] 飞书完成通知发送失败: %s", exc)
        else:
            statuses["feishu"] = "skipped:incomplete_config"

    qq_cfg = cfg.notifications.qq
    if qq_cfg.enabled:
        qq_user_id = qq_cfg.user_qq.strip()
        if not qq_user_id:
            statuses["qq"] = "skipped:incomplete_config"
        elif not qq_user_id.isdigit():
                statuses["qq"] = "skipped:invalid_qq"
        else:
            try:
                payload = await _build_qq_payload(session)
                statuses["qq"] = await _deliver_qq_payload(payload)
            except Exception as exc:
                statuses["qq"] = f"failed:{exc}"
                logger.warning("[旅行] QQ 完成通知发送失败: %s", exc)

    return statuses
