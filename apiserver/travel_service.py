#!/usr/bin/env python3
"""
旅行服务 — 状态管理、持久化、提示词构建、结果解析
"""

import ast
import json
import logging
import math
import re
import uuid
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ── 数据目录 ────────────────────────────────────

from system.config import get_data_dir

TRAVEL_DIR = get_data_dir() / "travel"
TRAVEL_DIR.mkdir(parents=True, exist_ok=True)

WRAPPED_CONTENT_RE = re.compile(
    r"<<<EXTERNAL_UNTRUSTED_CONTENT[^>]*>>>\s*(?:Source:[^\n]*\n)?(?:---\n)?(?P<body>.*?)<<<END_EXTERNAL_UNTRUSTED_CONTENT[^>]*>>>",
    re.DOTALL,
)
DISCOVERY_TAG_RE = re.compile(
    r"\[DISCOVERY\]\s*"
    r"url:\s*(?P<url>.+?)\s*"
    r"title:\s*(?P<title>.+?)\s*"
    r"summary:\s*(?P<summary>.+?)\s*"
    r"(?:tags:\s*(?P<tags>.+?)\s*)?"
    r"\[/DISCOVERY\]",
    re.DOTALL,
)
SOCIAL_TAG_RE = re.compile(
    r"\[SOCIAL\]\s*"
    r"type:\s*(?P<type>.+?)\s*"
    r"(?:post_id:\s*(?P<post_id>.+?)\s*)?"
    r"content_preview:\s*(?P<content_preview>.+?)\s*"
    r"\[/SOCIAL\]",
    re.DOTALL,
)

BROWSER_ACTION_COSTS: dict[str, int] = {
    "status": 1,
    "start": 3,
    "profiles": 1,
    "tabs": 2,
    "open": 6,
    "focus": 1,
    "close": 1,
    "snapshot": 8,
    "screenshot": 6,
    "navigate": 6,
    "console": 5,
    "pdf": 5,
    "upload": 4,
    "dialog": 2,
    "act": 10,
}
TOOL_BASE_COSTS: dict[str, int] = {
    "web_search": 24,
    "web_fetch": 12,
    "browser": 8,
}


# ── 数据模型 ────────────────────────────────────


class TravelStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    INTERRUPTED = "interrupted"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TravelDiscovery(BaseModel):
    url: str
    title: str
    summary: str
    found_at: str  # ISO 8601
    tags: list[str] = Field(default_factory=list)
    source: str | None = None
    site_name: str | None = None


class SocialInteraction(BaseModel):
    type: str  # "post_created", "reply_sent", "friend_request"
    post_id: str | None = None
    content_preview: str
    timestamp: str


class TravelProgressEvent(BaseModel):
    timestamp: str
    type: str
    message: str
    level: str = "info"
    meta: dict[str, Any] = Field(default_factory=dict)


class TravelSession(BaseModel):
    session_id: str
    status: TravelStatus = TravelStatus.PENDING
    phase: str = "pending"
    created_at: str
    phase_started_at: str | None = None
    last_checkpoint_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    interrupted_at: str | None = None
    interrupted_reason: str | None = None
    agent_id: str | None = None
    agent_name: str | None = None
    # 用户配置
    time_limit_minutes: int = 300
    credit_limit: int = 1000
    want_friends: bool = True
    friend_description: str | None = None
    goal_prompt: str | None = None
    post_to_forum: bool = True
    deliver_full_report: bool = True
    deliver_channel: str | None = None
    deliver_to: str | None = None
    browser_visible: bool = False
    browser_keep_open: bool = False
    browser_idle_timeout_seconds: int = 300
    # 运行时跟踪
    openclaw_session_key: str | None = None
    last_heartbeat_at: str | None = None
    resume_count: int = 0
    tokens_used: int = 0
    credits_used: int = 0
    elapsed_minutes: float = 0.0
    tool_stats: dict[str, int] = Field(default_factory=dict)
    unique_sources: int = 0
    sources: list[str] = Field(default_factory=list)
    summary_report_path: str | None = None
    summary_report_title: str | None = None
    wrap_up_sent: bool = False
    idle_polls: int = 0
    time_warning_sent: bool = False
    credit_warning_sent: bool = False
    progress_events: list[TravelProgressEvent] = Field(default_factory=list)
    # 结果
    discoveries: list[TravelDiscovery] = Field(default_factory=list)
    social_interactions: list[SocialInteraction] = Field(default_factory=list)
    summary: str | None = None
    forum_digest: str | None = None
    forum_post_id: str | None = None
    forum_post_status: str | None = None
    full_report_delivery_status: str | None = None
    notification_delivery_statuses: dict[str, str] = Field(default_factory=dict)
    error: str | None = None


class TravelHistoryAnalysis(BaseModel):
    discoveries: list[TravelDiscovery] = Field(default_factory=list)
    social_interactions: list[SocialInteraction] = Field(default_factory=list)
    credits_used: int = 0
    tool_stats: dict[str, int] = Field(default_factory=dict)
    sources: list[str] = Field(default_factory=list)
    activity_events: list[TravelProgressEvent] = Field(default_factory=list)
    summary_report_path: str | None = None
    summary_report_title: str | None = None


TERMINAL_TRAVEL_STATUSES = {
    TravelStatus.COMPLETED,
    TravelStatus.FAILED,
    TravelStatus.CANCELLED,
}
ACTIVE_TRAVEL_STATUSES = {TravelStatus.RUNNING}
OPEN_TRAVEL_STATUSES = {
    TravelStatus.PENDING,
    TravelStatus.RUNNING,
    TravelStatus.INTERRUPTED,
}
INTERRUPTIBLE_TRAVEL_STATUSES = {
    TravelStatus.PENDING,
    TravelStatus.RUNNING,
}


# ── 持久化 ──────────────────────────────────────


def _session_path(session_id: str) -> Path:
    # 安全：session_id 来自 URL/body 并拼入文件路径，限制字符集防路径穿越（../），
    # 规则与 lumo_proxy 的 session_id 校验一致；非法 ID 视同不存在（调用方已有 FileNotFoundError → 404 处理）
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", session_id or ""):
        raise FileNotFoundError(f"旅行 session 不存在: {session_id}")
    return TRAVEL_DIR / f"{session_id}.json"


def create_session(
    agent_id: str | None = None,
    agent_name: str | None = None,
    time_limit_minutes: int = 300,
    credit_limit: int = 1000,
    want_friends: bool = True,
    friend_description: str | None = None,
    goal_prompt: str | None = None,
    post_to_forum: bool = True,
    deliver_full_report: bool = True,
    deliver_channel: str | None = None,
    deliver_to: str | None = None,
    browser_visible: bool = False,
    browser_keep_open: bool = False,
    browser_idle_timeout_seconds: int = 300,
) -> TravelSession:
    """创建并持久化一个新的旅行 session"""
    session = TravelSession(
        session_id=uuid.uuid4().hex[:16],
        created_at=datetime.now().isoformat(),
        phase_started_at=datetime.now().isoformat(),
        last_checkpoint_at=datetime.now().isoformat(),
        agent_id=agent_id,
        agent_name=agent_name,
        time_limit_minutes=time_limit_minutes,
        credit_limit=credit_limit,
        want_friends=want_friends,
        friend_description=friend_description,
        goal_prompt=goal_prompt,
        post_to_forum=post_to_forum,
        deliver_full_report=deliver_full_report,
        deliver_channel=deliver_channel,
        deliver_to=deliver_to,
        browser_visible=browser_visible,
        browser_keep_open=browser_keep_open,
        browser_idle_timeout_seconds=max(30, int(browser_idle_timeout_seconds or 300)),
    )
    append_progress_event(
        session,
        "created",
        "探索任务已创建，等待后端调度执行。",
        meta={
            "agent_id": session.agent_id,
            "time_limit_minutes": session.time_limit_minutes,
            "credit_limit": session.credit_limit,
            "browser_visible": session.browser_visible,
            "browser_keep_open": session.browser_keep_open,
        },
    )
    save_session(session)
    logger.info(f"旅行 session 已创建: {session.session_id}")
    return session


def save_session(session: TravelSession) -> None:
    """将 session 写入 JSON 文件"""
    session.last_checkpoint_at = datetime.now().isoformat()
    path = _session_path(session.session_id)
    path.write_text(session.model_dump_json(indent=2), encoding="utf-8")


def set_session_phase(
    session: TravelSession,
    phase: str,
    *,
    message: str | None = None,
    level: str = "info",
    meta: dict[str, Any] | None = None,
    save: bool = True,
) -> TravelSession:
    now = datetime.now().isoformat()
    session.phase = phase
    session.phase_started_at = now
    session.last_checkpoint_at = now
    if message:
        append_progress_event(
            session,
            "phase_changed",
            message,
            level=level,
            meta={"phase": phase, **(meta or {})},
            timestamp=now,
        )
    if save:
        save_session(session)
    return session


def append_progress_event(
    session: TravelSession,
    event_type: str,
    message: str,
    *,
    level: str = "info",
    meta: dict[str, Any] | None = None,
    timestamp: str | None = None,
    save: bool = False,
) -> TravelSession:
    session.progress_events.append(
        TravelProgressEvent(
            timestamp=timestamp or datetime.now().isoformat(),
            type=event_type,
            message=message,
            level=level,
            meta=meta or {},
        )
    )
    if len(session.progress_events) > 40:
        session.progress_events = session.progress_events[-40:]
    if save:
        save_session(session)
    return session


def get_browser_policy_path() -> Path:
    return TRAVEL_DIR / "browser-policies.json"


def _load_browser_policy_map() -> dict[str, Any]:
    path = get_browser_policy_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def _save_browser_policy_map(data: dict[str, Any]) -> None:
    path = get_browser_policy_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def sync_session_browser_policy(session: TravelSession) -> None:
    session_key = (session.openclaw_session_key or "").strip()
    if not session_key:
        return
    data = _load_browser_policy_map()
    data[session_key] = {
        "keepOpen": bool(session.browser_keep_open),
        "idleTimeoutSeconds": max(30, int(session.browser_idle_timeout_seconds or 300)),
        "visible": bool(session.browser_visible),
        "agentId": session.agent_id,
        "sessionId": session.session_id,
        "updatedAt": datetime.now().isoformat(),
    }
    _save_browser_policy_map(data)


def remove_session_browser_policy(session_key: str | None) -> None:
    key = (session_key or "").strip()
    if not key:
        return
    data = _load_browser_policy_map()
    if key not in data:
        return
    data.pop(key, None)
    _save_browser_policy_map(data)


def load_session(session_id: str) -> TravelSession:
    """从文件读取 session"""
    path = _session_path(session_id)
    if not path.exists():
        raise FileNotFoundError(f"旅行 session 不存在: {session_id}")
    return TravelSession.model_validate_json(path.read_text(encoding="utf-8"))


def get_session_or_none(session_id: str) -> TravelSession | None:
    path = _session_path(session_id)
    if not path.exists():
        return None
    try:
        return TravelSession.model_validate_json(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def get_active_session() -> TravelSession | None:
    """兼容旧逻辑：返回最近创建的 running session。"""
    sessions = list_sessions(statuses={TravelStatus.RUNNING})
    return sessions[0] if sessions else None


_ANY_AGENT = object()


def list_sessions(
    *,
    agent_id: Any = _ANY_AGENT,
    statuses: set[TravelStatus] | None = None,
) -> list[TravelSession]:
    """列出 session，支持按 agent/status 过滤，按 created_at 倒序。"""
    sessions: list[TravelSession] = []
    for path in TRAVEL_DIR.glob("*.json"):
        try:
            session = TravelSession.model_validate_json(path.read_text(encoding="utf-8"))
            if agent_id is not _ANY_AGENT and session.agent_id != agent_id:
                continue
            if statuses is not None and session.status not in statuses:
                continue
            sessions.append(session)
        except Exception:
            continue
    sessions.sort(key=lambda s: s.created_at, reverse=True)
    return sessions


def list_active_sessions(*, agent_id: Any = _ANY_AGENT) -> list[TravelSession]:
    return list_sessions(agent_id=agent_id, statuses=ACTIVE_TRAVEL_STATUSES)


def list_open_sessions(*, agent_id: Any = _ANY_AGENT) -> list[TravelSession]:
    return list_sessions(agent_id=agent_id, statuses=OPEN_TRAVEL_STATUSES)


def list_interruptible_sessions(*, agent_id: Any = _ANY_AGENT) -> list[TravelSession]:
    return list_sessions(agent_id=agent_id, statuses=INTERRUPTIBLE_TRAVEL_STATUSES)


def get_open_session_for_agent(agent_id: str | None) -> TravelSession | None:
    sessions = list_open_sessions(agent_id=agent_id)
    return sessions[0] if sessions else None


def get_latest_session(*, agent_id: Any = _ANY_AGENT) -> TravelSession | None:
    sessions = list_sessions(agent_id=agent_id)
    return sessions[0] if sessions else None


def mark_session_interrupted(
    session: TravelSession,
    *,
    reason: str | None = None,
    interrupted_at: str | None = None,
) -> TravelSession:
    if session.status in TERMINAL_TRAVEL_STATUSES:
        return session
    ts = interrupted_at or datetime.now().isoformat()
    session.status = TravelStatus.INTERRUPTED
    session.interrupted_at = ts
    if reason:
        session.interrupted_reason = reason
    session.last_heartbeat_at = ts
    interrupt_message = "探索已中断，当前进度已落盘，可在重新登录或重启后恢复。"
    if reason == "auth_expired":
        interrupt_message = "当前登录态已过期，探索已挂起，进度已落盘。请重新登录后恢复。"
    append_progress_event(
        session,
        "interrupted",
        interrupt_message,
        level="warn",
        meta={"reason": reason or "interrupted"},
        timestamp=ts,
    )
    save_session(session)
    return session


def interrupt_open_sessions(
    *,
    agent_id: Any = _ANY_AGENT,
    reason: str | None = None,
) -> list[TravelSession]:
    interrupted: list[TravelSession] = []
    for session in list_interruptible_sessions(agent_id=agent_id):
        interrupted.append(mark_session_interrupted(session, reason=reason))
    return interrupted


# ── Prompt 构建 ─────────────────────────────────


def build_travel_prompt(session: TravelSession) -> str:
    """生成给 OpenClaw 的探索指令"""
    goal = session.goal_prompt or "自由探索互联网，优先了解最新热点、值得持续追踪的话题和高质量来源"
    agent_line = f"- 当前执行干员：{session.agent_name or session.agent_id}\n" if session.agent_id or session.agent_name else ""
    browser_mode = "可见浏览器窗口" if session.browser_visible else "无头浏览器"
    browser_keep_open = "浏览器页面会保持打开直到任务主动关闭" if session.browser_keep_open else f"浏览器页面空闲 {session.browser_idle_timeout_seconds} 秒会自动关闭"
    return f"""你正在执行一次长期网络探索任务，运行环境是 OpenClaw。

核心目标：
{agent_line}- 围绕这个方向探索：{goal}
- 优先获取“最新、仍在发展、值得继续追踪”的内容，而不是泛泛百科知识
- 产出结构化发现，并在预算接近上限时主动收束并准备报告

预算约束：
- 时间上限：{session.time_limit_minutes} 分钟
- 积分预算：{session.credit_limit} 积分（后端会按工具调用做近似计费）
- 浏览器模式：{browser_mode}
- 浏览器页面策略：{browser_keep_open}

工具策略：
1. 先用 web_search 获取最新线索、热点主题和高价值来源
2. 再用 browser 打开、导航、快照、验证页面内容
3. web_search 默认使用压缩结果；只有确实需要原始结果时才显式 raw=true
4. browser 只允许这些 action：
   status, start, profiles, tabs, open, focus, close, snapshot, screenshot, navigate, console, pdf, upload, dialog, act
5. browser 支持 keepopen=true；只有确实需要后续连续操作同一页面时才使用它
6. 不要编造不存在的 browser action，例如 extract、getText
7. 每完成一个有意义的步骤（开始搜索、切换方向、遇到阻塞、准备收束），优先调用 travel_progress 记录最近进展
8. 每确认一个值得保留的发现，优先调用 travel_discovery 写入结构化发现；只有工具不可用时，再退回输出 [DISCOVERY] 块
9. 当你需要查看当前累计发现、来源和最近进展时，调用 travel_state，不要靠记忆猜测
10. 进入最终总结阶段后，优先调用 travel_summary 将完整成果写入 markdown 文件，再返回简要结论

探索纪律：
- 每一轮继续探索前，都必须有明确的新信息目标
- 如果连续两次结果高度重复，停止扩搜并开始总结
- 优先保留一手来源、官方来源、原始页面，而不是反复引用二手摘要
- 如果已经掌握足够证据，直接收束，不要为了“看起来更努力”而空转

输出规则：
- 每当形成一个值得保留的发现时，优先使用 travel_discovery 工具；只有在工具不可用时，才追加一个 [DISCOVERY] 块：
[DISCOVERY]
url: <网页URL>
title: <标题>
summary: <一句话总结，说明它为什么重要>
tags: <标签1>, <标签2>
[/DISCOVERY]

- 阶段性总结时，简要说明：
  1. 当前热点/趋势
  2. 你最值得追踪的 3-5 个来源
  3. 接下来还缺什么信息

现在开始探索。先广搜，再聚焦高价值页面，保持节制但保留发现。"""


def build_social_prompt(session: TravelSession) -> str:
    """生成社交指令"""
    desc = session.friend_description or "任何有趣的 AI Agent"
    return f"""补充社交目标：
- 在合适的时候浏览陆墨网络论坛，与其他 AI 互动
- 你希望结识的对象：{desc}
- 只有当探索已经有阶段性成果时，再进行社交；不要让社交打断主探索任务

若有社交互动，用以下格式记录：
[SOCIAL]
type: <post_created|reply_sent|friend_request>
post_id: <帖子ID，如有>
content_preview: <互动内容预览>
[/SOCIAL]"""


def build_wrap_up_prompt(session: TravelSession) -> str:
    goal = session.goal_prompt or "自由探索最新热点"
    return f"""请停止扩展探索，开始收束并输出最终旅行报告。

报告要求：
1. 先给出本次探索的总判断，回答目标：{goal}
2. 总结 3-7 条最有价值的发现，按重要性排序
3. 每条发现尽量点出来源/页面，以及它为什么值得继续追踪
4. 说明哪些信息已经足够，哪些仍存在不确定性
5. 如果有社交互动，再单独附一段社交总结
6. 开始写最终报告前，先调用 travel_state 查看当前累计发现、来源和最近进展
7. 生成完整 markdown 报告后，调用 travel_summary 写入成果文件
8. 在 travel_summary 成功后，再用简短 plain text 回复一句已完成总结，概括最重要的结论

不要再继续盲目搜索或重复访问页面，直接完成报告。"""


def build_quota_warning_prompt(
    session: TravelSession,
    *,
    remaining_minutes: float,
    remaining_credits: int,
    trigger: str,
) -> str:
    parts: list[str] = []
    if trigger in {"time", "both"}:
        parts.append(f"- 剩余时间约 {max(0.0, remaining_minutes):.1f} 分钟")
    if trigger in {"credit", "both"}:
        parts.append(f"- 剩余积分约 {max(0, remaining_credits)}")
    lines = "\n".join(parts) if parts else "- 预算已非常接近上限"
    return f"""注意：本次探索预算已进入最后 10%，请立刻开始收束并减少新的搜索/打开页面动作。

当前剩余额度：
{lines}

现在的要求：
1. 不要再扩张探索范围
2. 只补最后必要的确认信息
3. 立刻整理已经拿到的发现
4. 准备输出最终报告，避免预算耗尽
5. 开始收束前，先调用 travel_state 查看当前累计发现和最近进展，再决定最终报告结构

如果已经足够回答目标，就直接开始最终总结。"""


def build_travel_instruction_prompt(message: str) -> str:
    clean_message = message.strip()
    return f"""这是用户对当前探索任务的补充指令，请在不丢失现有上下文的前提下吸收执行。

补充要求：
- 不要重置已经完成的探索和已有发现
- 优先基于当前线索调整方向，而不是从头开始
- 如补充指令与当前计划冲突，以用户最新要求为准
- 执行过程中仍然遵守时间/积分预算和收束纪律
- 如补充指令会影响探索方向、重点或当前阻塞，请用 travel_progress 记录这次调整

用户补充指令：
{clean_message}"""


def _compact_text(text: str | None, limit: int = 220) -> str:
    if not text:
        return ""
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: max(1, limit - 1)] + "…"


def build_forum_post_payload(session: TravelSession) -> dict[str, Any]:
    """根据旅行结果构建论坛精华帖。"""
    title_seed = _compact_text(session.goal_prompt, 36) or "最新热点探索"
    summary = _compact_text(session.summary, 700) or "本轮探索已完成，但暂未生成完整总结。"
    top_discoveries = session.discoveries[:5]
    top_tags: list[str] = []
    for item in top_discoveries:
        for tag in item.tags:
            if tag and tag not in top_tags:
                top_tags.append(tag)
            if len(top_tags) >= 5:
                break
    lines = [
        f"【探索方向】{title_seed}",
        "",
        "【精华总结】",
        summary,
    ]
    if top_discoveries:
        lines.extend(["", "【本轮值得继续追踪】"])
        for idx, item in enumerate(top_discoveries, start=1):
            source = item.site_name or urlparse(item.url).netloc or item.url
            lines.append(
                f"{idx}. {item.title}\n"
                f"来源：{source}\n"
                f"摘要：{_compact_text(item.summary, 140)}\n"
                f"链接：{item.url}"
            )
    if session.social_interactions:
        lines.extend(["", f"【社交互动】本轮记录 {len(session.social_interactions)} 次互动"])
    content = "\n".join(lines).strip()
    return {
        "title": f"探索速报｜{title_seed}"[:60],
        "content": content[:4000],
        "tags": top_tags[:5],
        "source": "openclaw-travel",
    }


# ── 结果解析 ─────────────────────────────────────


def _clean_wrapped_text(text: str) -> str:
    if not text:
        return ""

    def _replace(match: re.Match[str]) -> str:
        return match.group("body")

    text = WRAPPED_CONTENT_RE.sub(_replace, text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _parse_maybe_serialized(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text:
        return value
    try:
        return json.loads(text)
    except Exception:
        pass
    try:
        return ast.literal_eval(text)
    except Exception:
        return value


def _extract_text_items(payload: Any) -> list[str]:
    payload = _parse_maybe_serialized(payload)
    texts: list[str] = []
    if isinstance(payload, dict):
        content = payload.get("content")
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    text = item.get("text")
                    if isinstance(text, str) and text.strip():
                        texts.append(_clean_wrapped_text(text))
        result = payload.get("result")
        if result is not None and result is not payload:
            texts.extend(_extract_text_items(result))
    elif isinstance(payload, list):
        for item in payload:
            texts.extend(_extract_text_items(item))
    elif isinstance(payload, str) and payload.strip():
        texts.append(_clean_wrapped_text(payload))
    return [text for text in texts if text]


def _guess_title_from_url(url: str) -> str:
    try:
        parsed = urlparse(url)
        host = parsed.netloc or url
        path = parsed.path.rstrip("/").split("/")[-1]
        if path:
            return f"{host} / {path}"
        return host
    except Exception:
        return url


def _safe_summary(text: str, max_len: int = 220) -> str:
    text = _clean_wrapped_text(text)
    if len(text) <= max_len:
        return text
    return f"{text[: max_len - 1].rstrip()}…"


def _looks_like_placeholder(value: str) -> bool:
    text = _clean_wrapped_text(value)
    if not text:
        return True
    return bool(re.fullmatch(r"<[^>\n]+>", text))


def _normalize_discovery_tags(tags_str: str) -> list[str]:
    tags: list[str] = []
    for raw_tag in tags_str.split(","):
        tag = _clean_wrapped_text(raw_tag)
        if not tag or _looks_like_placeholder(tag):
            continue
        tags.append(tag)
    return tags


def _build_assistant_discovery(
    *,
    url: str,
    title: str,
    summary: str,
    tags: list[str],
    now: str,
) -> TravelDiscovery | None:
    cleaned_url = _clean_wrapped_text(url)
    cleaned_title = _clean_wrapped_text(title)
    cleaned_summary = _clean_wrapped_text(summary)
    if (
        not cleaned_url
        or _looks_like_placeholder(cleaned_url)
        or _looks_like_placeholder(cleaned_title)
        or _looks_like_placeholder(cleaned_summary)
    ):
        return None

    site_name = urlparse(cleaned_url).netloc or None
    return TravelDiscovery(
        url=cleaned_url,
        title=cleaned_title,
        summary=cleaned_summary,
        found_at=now,
        tags=tags,
        source="assistant",
        site_name=site_name,
    )


def parse_discoveries_from_text(text: str, *, now: str | None = None) -> list[TravelDiscovery]:
    if not text:
        return []
    timestamp = now or datetime.now().isoformat()
    discoveries: list[TravelDiscovery] = []
    seen_urls: set[str] = set()
    for match in DISCOVERY_TAG_RE.finditer(text):
        discovery = _build_assistant_discovery(
            url=match.group("url"),
            title=match.group("title"),
            summary=match.group("summary"),
            tags=_normalize_discovery_tags(match.group("tags") or ""),
            now=timestamp,
        )
        if discovery is None or discovery.url in seen_urls:
            continue
        seen_urls.add(discovery.url)
        discoveries.append(discovery)
    return discoveries


def _discovery_from_search_item(item: dict[str, Any], *, query: str, now: str) -> TravelDiscovery | None:
    url = str(item.get("url") or "").strip()
    if not url:
        return None

    title = _clean_wrapped_text(str(item.get("title") or "").strip()) or _guess_title_from_url(url)
    summary = (
        _clean_wrapped_text(str(item.get("description") or "").strip())
        or _clean_wrapped_text(str(item.get("snippet") or "").strip())
        or f"搜索命中：{query}"
    )
    site_name = str(item.get("siteName") or item.get("site_name") or "").strip() or None
    tags = ["web_search"]
    if site_name:
        tags.append(site_name)
    return TravelDiscovery(
        url=url,
        title=_safe_summary(title, 120),
        summary=_safe_summary(summary),
        found_at=now,
        tags=tags,
        source="web_search",
        site_name=site_name,
    )


def _discoveries_from_web_search_result(result: Any, now: str) -> list[TravelDiscovery]:
    payload = _parse_maybe_serialized(result)
    if not isinstance(payload, dict):
        return []
    details = payload.get("details") if isinstance(payload.get("details"), dict) else None
    value = details or payload.get("value", payload)
    if not isinstance(value, dict):
        return []

    query = str(value.get("query") or "").strip() or "未命名搜索"
    discoveries: list[TravelDiscovery] = []
    for item in value.get("results", [])[:5]:
        if not isinstance(item, dict):
            continue
        discovery = _discovery_from_search_item(item, query=query, now=now)
        if discovery is not None:
            discoveries.append(discovery)
    return discoveries


def _discovery_from_browser_result(args: dict[str, Any], result: Any, now: str) -> TravelDiscovery | None:
    payload = _parse_maybe_serialized(result)
    details = payload.get("details", {}) if isinstance(payload, dict) else {}
    if not isinstance(details, dict):
        details = {}

    url = str(details.get("url") or "").strip()
    if not url:
        return None

    action = str(args.get("action") or "browser").strip() or "browser"
    text_parts = _extract_text_items(payload)
    summary = text_parts[0] if text_parts else f"通过 browser.{action} 访问并检查页面"
    title = str(details.get("title") or "").strip() or _guess_title_from_url(url)
    tags = ["browser", action]
    site_name = urlparse(url).netloc or None
    if site_name:
        tags.append(site_name)
    return TravelDiscovery(
        url=url,
        title=_safe_summary(title, 120),
        summary=_safe_summary(summary),
        found_at=now,
        tags=tags,
        source="browser",
        site_name=site_name,
    )


def _discovery_from_web_fetch_result(args: dict[str, Any], result: Any, now: str) -> TravelDiscovery | None:
    url = str(args.get("url") or "").strip()
    if not url:
        return None

    payload = _parse_maybe_serialized(result)
    details = payload.get("details", {}) if isinstance(payload, dict) else {}
    if not isinstance(details, dict):
        details = {}
    text_parts = _extract_text_items(payload)
    summary = text_parts[0] if text_parts else "通过 web_fetch 获取了页面内容"
    title = _guess_title_from_url(url)
    site_name = urlparse(url).netloc or None
    tags = ["web_fetch"]
    if site_name:
        tags.append(site_name)
    return TravelDiscovery(
        url=url,
        title=_safe_summary(title, 120),
        summary=_safe_summary(summary),
        found_at=now,
        tags=tags,
        source="web_fetch",
        site_name=site_name,
    )


def _estimate_event_cost(name: str, args: dict[str, Any], is_error: bool) -> tuple[str, int]:
    if name == "browser":
        action = str(args.get("action") or "").strip() or "unknown"
        cost = BROWSER_ACTION_COSTS.get(action, TOOL_BASE_COSTS["browser"])
        return f"browser.{action}", max(1, cost if not is_error else max(1, cost // 2))

    cost = TOOL_BASE_COSTS.get(name, 6)
    return name, max(1, cost if not is_error else max(1, cost // 2))


def _extract_message_text(msg: dict[str, Any]) -> str:
    content = msg.get("content", "")
    if isinstance(content, str):
        return _clean_wrapped_text(content)
    return "\n".join(_extract_text_items(content)).strip()


def _extract_tool_events_from_message(msg: dict[str, Any]) -> list[dict[str, Any]]:
    tool_events = msg.get("toolEvents") or msg.get("tool_events") or []
    if isinstance(tool_events, list) and tool_events:
        return [event for event in tool_events if isinstance(event, dict)]

    role = str(msg.get("role") or "").strip().lower().replace("-", "_")
    derived: list[dict[str, Any]] = []
    if role in {"tool_result", "toolresult"}:
        tool_call_id = str(
            msg.get("toolCallId")
            or msg.get("tool_call_id")
            or msg.get("toolUseId")
            or msg.get("tool_use_id")
            or ""
        ).strip()
        tool_name = str(msg.get("toolName") or msg.get("tool_name") or "").strip()
        if tool_call_id:
            derived.append(
                {
                    "type": "tool_result",
                    "name": tool_name,
                    "toolCallId": tool_call_id,
                    "isError": bool(msg.get("isError") or msg.get("is_error")),
                    "result": {
                        "content": msg.get("content"),
                        "details": msg.get("details"),
                    },
                }
            )
            return derived

    content = msg.get("content", [])
    if isinstance(content, list):
        for block in content:
            if not isinstance(block, dict):
                continue
            block_type = str(block.get("type") or "").strip().lower().replace("-", "_")
            if block_type in {"tool_use", "toolcall", "tool_call"}:
                derived.append(
                    {
                        "type": "tool_call",
                        "name": block.get("name") or block.get("tool_name") or "",
                        "toolCallId": block.get("id") or block.get("tool_use_id") or "",
                        "args": block.get("input") or block.get("args") or block.get("arguments"),
                    }
                )
            elif block_type in {"tool_result", "toolresult", "tool_result_error", "tool_resulterror"}:
                derived.append(
                    {
                        "type": "tool_result",
                        "name": block.get("name") or block.get("tool_name") or "",
                        "toolCallId": block.get("toolCallId") or block.get("tool_call_id") or block.get("tool_use_id") or block.get("id") or "",
                        "isError": bool(block.get("isError") or block.get("is_error") or "error" in block_type),
                        "result": {
                            "content": _extract_text_items(block.get("content")),
                            "details": block.get("details"),
                        },
                    }
                )
    return derived


def _collect_sources_from_discoveries(discoveries: list[TravelDiscovery]) -> list[str]:
    seen: set[str] = set()
    sources: list[str] = []
    for discovery in discoveries:
        source = (discovery.site_name or urlparse(discovery.url).netloc or discovery.url).strip()
        if not source or source in seen:
            continue
        seen.add(source)
        sources.append(source)
    return sources


def _safe_parse_json_dict(value: Any) -> dict[str, Any] | None:
    parsed = _parse_maybe_serialized(value)
    return parsed if isinstance(parsed, dict) else None


def _estimate_message_credit_cost(msg: dict[str, Any]) -> int:
    usage = msg.get("usage")
    if isinstance(usage, dict):
        total_tokens = usage.get("totalTokens", usage.get("total_tokens", usage.get("total")))
        if isinstance(total_tokens, (int, float)) and total_tokens > 0:
            return max(1, math.ceil(float(total_tokens) / 100.0))

    text = _extract_message_text(msg)
    tool_events = _extract_tool_events_from_message(msg)
    if not text and not tool_events:
        return 0

    estimate_tokens = 0
    if text:
        try:
            from apiserver.context_compressor import count_tokens

            role = str(msg.get("role") or "assistant")
            estimate_tokens += count_tokens([{"role": role, "content": text}])
        except Exception:
            estimate_tokens += max(1, int(len(text) * 1.2))
    if tool_events:
        estimate_tokens += 60 * len(tool_events)
    return max(1, math.ceil(estimate_tokens / 100.0))


def _progress_event_from_tool_result(
    *,
    name: str,
    args: dict[str, Any],
    result: Any,
    is_error: bool,
    tool_call_id: str,
    now: str,
) -> TravelProgressEvent | None:
    payload = _safe_parse_json_dict(result) or {}
    details = payload.get("details") if isinstance(payload.get("details"), dict) else {}
    level = "error" if is_error else "info"

    if name == "web_search":
        query = str(details.get("query") or "").strip() or str(args.get("query") or "").strip() or "未命名搜索"
        total_results = details.get("totalResults", details.get("total_results"))
        results_text = f"{int(total_results)} 条结果" if isinstance(total_results, (int, float)) else "已返回结果"
        return TravelProgressEvent(
            timestamp=now,
            type="tool.web_search",
            message=(
                f"搜索失败：{query}" if is_error else f"已搜索：{query}（{results_text}）"
            ),
            level=level,
            meta={"travel_tool_call_id": tool_call_id, "tool": name, "query": query},
        )

    if name == "browser":
        action = str(args.get("action") or "browser").strip() or "browser"
        url = str(details.get("url") or "").strip() or str(args.get("url") or "").strip()
        summary = f"浏览器 {action}"
        if url:
            summary += f"：{url}"
        if is_error and isinstance(details, dict) and details.get("error"):
            summary = f"{summary} 失败：{details.get('error')}"
        return TravelProgressEvent(
            timestamp=now,
            type=f"tool.browser.{action}",
            message=summary,
            level=level,
            meta={"travel_tool_call_id": tool_call_id, "tool": name, "action": action, "url": url},
        )

    if name == "web_fetch":
        url = str(args.get("url") or "").strip()
        summary = f"已抓取页面：{url}" if url else "已抓取页面内容"
        if is_error and isinstance(details, dict) and details.get("error"):
            summary = f"{summary} 失败：{details.get('error')}"
        return TravelProgressEvent(
            timestamp=now,
            type="tool.web_fetch",
            message=summary,
            level=level,
            meta={"travel_tool_call_id": tool_call_id, "tool": name, "url": url},
        )

    if name == "travel_progress":
        details_payload = details if details else payload
        message = _clean_wrapped_text(str(details_payload.get("message") or "")) if isinstance(details_payload, dict) else ""
        event_level = str(details_payload.get("level") or level) if isinstance(details_payload, dict) else level
        if not message:
            return None
        return TravelProgressEvent(
            timestamp=now,
            type="travel_progress",
            message=message,
            level=event_level,
            meta={"travel_tool_call_id": tool_call_id, "tool": name},
        )

    if name == "travel_summary":
        details_payload = details if details else payload
        file_path = _clean_wrapped_text(str(details_payload.get("file_path") or "")) if isinstance(details_payload, dict) else ""
        title = _clean_wrapped_text(str(details_payload.get("title") or "")) if isinstance(details_payload, dict) else ""
        if not file_path:
            return None
        file_name = Path(file_path).name
        message = f"已写入探索成果文件：{file_name}"
        if title:
            message = f"已写入探索成果文件：{title}（{file_name}）"
        return TravelProgressEvent(
            timestamp=now,
            type="travel_summary",
            message=message,
            level=level,
            meta={
                "travel_tool_call_id": tool_call_id,
                "tool": name,
                "file_path": file_path,
                "title": title,
            },
        )

    return None


def _discovery_from_travel_tool_result(result: Any, now: str) -> TravelDiscovery | None:
    payload = _safe_parse_json_dict(result) or {}
    details = payload.get("details") if isinstance(payload.get("details"), dict) else payload
    if not isinstance(details, dict):
        return None
    url = str(details.get("url") or "").strip()
    title = str(details.get("title") or "").strip()
    summary = str(details.get("summary") or "").strip()
    tags = details.get("tags") or []
    if isinstance(tags, str):
        tags = _normalize_discovery_tags(tags)
    elif isinstance(tags, list):
        tags = [str(tag).strip() for tag in tags if str(tag).strip()]
    else:
        tags = []
    discovery = _build_assistant_discovery(
        url=url,
        title=title,
        summary=summary,
        tags=tags,
        now=now,
    )
    if discovery is None:
        return None
    if isinstance(details.get("source"), str) and details.get("source").strip():
        discovery.source = details.get("source").strip()
    if isinstance(details.get("site_name"), str) and details.get("site_name").strip():
        discovery.site_name = details.get("site_name").strip()
    return discovery


def _summary_report_from_travel_tool_result(result: Any) -> tuple[str | None, str | None]:
    payload = _safe_parse_json_dict(result) or {}
    details = payload.get("details") if isinstance(payload.get("details"), dict) else payload
    if not isinstance(details, dict):
        return None, None
    file_path = str(details.get("file_path") or "").strip() or None
    title = str(details.get("title") or "").strip() or None
    return file_path, title


def analyze_history(history_messages: list[dict]) -> TravelHistoryAnalysis:
    """从 OpenClaw 历史中提炼发现、社交互动和近似预算消耗。"""
    now = datetime.now().isoformat()
    analysis = TravelHistoryAnalysis()
    seen_urls: set[str] = set()
    seen_tool_results: set[str] = set()
    call_args: dict[str, dict[str, Any]] = {}
    seen_progress_ids: set[str] = set()

    for msg in history_messages:
        text_content = _extract_message_text(msg)
        role = str(msg.get("role") or "").strip().lower().replace("-", "_")
        if role in {"user", "assistant"}:
            analysis.credits_used += _estimate_message_credit_cost(msg)
            analysis.tool_stats["llm.turn"] = analysis.tool_stats.get("llm.turn", 0) + 1

        if text_content:
            for discovery in parse_discoveries_from_text(text_content, now=now):
                if discovery.url in seen_urls:
                    continue
                seen_urls.add(discovery.url)
                analysis.discoveries.append(discovery)

        tool_events = _extract_tool_events_from_message(msg)
        if not tool_events:
            continue

        for event in tool_events:
            if not isinstance(event, dict):
                continue
            event_type = str(event.get("type") or "").strip()
            tool_call_id = str(event.get("toolCallId") or "").strip()
            if event_type == "tool_call" and tool_call_id:
                args = event.get("args")
                if isinstance(args, dict):
                    call_args[tool_call_id] = args
                else:
                    parsed = _parse_maybe_serialized(args)
                    call_args[tool_call_id] = parsed if isinstance(parsed, dict) else {}
                continue

            if event_type != "tool_result" or not tool_call_id or tool_call_id in seen_tool_results:
                continue

            seen_tool_results.add(tool_call_id)
            name = str(event.get("name") or "").strip()
            args = call_args.get(tool_call_id, {})
            is_error = bool(event.get("isError"))
            stat_key, cost = _estimate_event_cost(name, args, is_error)
            analysis.credits_used += cost
            analysis.tool_stats[stat_key] = analysis.tool_stats.get(stat_key, 0) + 1

            progress_event = _progress_event_from_tool_result(
                name=name,
                args=args,
                result=event.get("result"),
                is_error=is_error,
                tool_call_id=tool_call_id,
                now=now,
            )
            if progress_event and tool_call_id not in seen_progress_ids:
                seen_progress_ids.add(tool_call_id)
                analysis.activity_events.append(progress_event)

            if is_error:
                continue

            result = event.get("result")
            if name == "web_search":
                for discovery in _discoveries_from_web_search_result(result, now):
                    if discovery.url in seen_urls:
                        continue
                    seen_urls.add(discovery.url)
                    analysis.discoveries.append(discovery)
                continue

            if name == "travel_discovery":
                discovery = _discovery_from_travel_tool_result(result, now)
                if discovery is not None and discovery.url not in seen_urls:
                    seen_urls.add(discovery.url)
                    analysis.discoveries.append(discovery)
                continue

            if name == "travel_summary":
                report_path, report_title = _summary_report_from_travel_tool_result(result)
                if report_path:
                    analysis.summary_report_path = report_path
                if report_title:
                    analysis.summary_report_title = report_title
                continue

            if name == "browser":
                discovery = _discovery_from_browser_result(args, result, now)
                if discovery is not None and discovery.url not in seen_urls:
                    seen_urls.add(discovery.url)
                    analysis.discoveries.append(discovery)
                continue

            if name == "web_fetch":
                discovery = _discovery_from_web_fetch_result(args, result, now)
                if discovery is not None and discovery.url not in seen_urls:
                    seen_urls.add(discovery.url)
                    analysis.discoveries.append(discovery)

    analysis.social_interactions = parse_social(history_messages)
    analysis.sources = _collect_sources_from_discoveries(analysis.discoveries)
    return analysis


def parse_discoveries(history_messages: list[dict]) -> list[TravelDiscovery]:
    """从 OpenClaw 回复和工具结果中提炼发现。"""
    return analyze_history(history_messages).discoveries


def estimate_travel_credits(history_messages: list[dict]) -> tuple[int, dict[str, int]]:
    analysis = analyze_history(history_messages)
    return analysis.credits_used, analysis.tool_stats


def parse_social(history_messages: list[dict]) -> list[SocialInteraction]:
    """解析 [SOCIAL]...[/SOCIAL] 格式"""
    interactions: list[SocialInteraction] = []
    now = datetime.now().isoformat()
    for msg in history_messages:
        content = _extract_message_text(msg)
        if not content:
            continue
        for match in SOCIAL_TAG_RE.finditer(content):
            post_id = match.group("post_id")
            if post_id:
                post_id = post_id.strip()
                if post_id.lower() in ("none", "null", ""):
                    post_id = None
            interactions.append(
                SocialInteraction(
                    type=match.group("type").strip(),
                    post_id=post_id,
                    content_preview=match.group("content_preview").strip(),
                    timestamp=now,
                )
            )
    return interactions
