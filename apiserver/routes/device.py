"""设备状态路由（卷131 W131-05）+ 知识摄取路由（W131-04）+ loop 快照路由（W131-03）。

三个新路由面，全部挂 apiserver 既有鉴权（require_local_auth）。
"""
from __future__ import annotations

from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from apiserver.device_state import get_device_state_store

router = APIRouter(prefix="/device", tags=["device"])


# ============ W131-05: 设备状态 ============


@router.get("/state")
async def get_device_states(
    name: str | None = None,
    _auth: Annotated[dict | None, Depends(_get_auth())] = None,
) -> dict:
    """全部/单个设备感知状态（在线离线 + 关键指标摘要）。"""
    store = get_device_state_store()
    if name:
        st = store.get_state(name)
        if st is None:
            raise HTTPException(status_code=404, detail=f"未注册设备: {name}")
        return {"ok": True, "device": st.name, "online": st.online,
                "last_seen": st.last_seen, "key_metrics": st.key_metrics,
                "offline_reason": st.offline_reason}
    return {"ok": True, "devices": store.list_devices(),
            "perception": store.perception_snapshot()}


@router.post("/state/{name}")
async def update_device_state(
    name: str,
    body: dict,
    _auth: Annotated[dict | None, Depends(_get_auth())] = None,
) -> dict:
    """设备上报状态（设备侧主动推送 metrics → 感知层）。"""
    store = get_device_state_store()
    store.update_state(name, body if isinstance(body, dict) else {})
    st = store.get_state(name)
    return {"ok": True, "device": name, "online": st.online}


@router.post("/heartbeat/{name}")
async def device_heartbeat(
    name: str,
    _auth: Annotated[dict | None, Depends(_get_auth())] = None,
) -> dict:
    """设备心跳（无指标，只刷新在线时间；超时会自动标 offline）。"""
    get_device_state_store().heartbeat(name)
    return {"ok": True}


# ============ W131-04: 知识摄取（cron → knowledge 管道入口） ============


class IngestRequest(BaseModel):
    source_type: str = Field(..., description="daily_brief / rss / paper_digest")
    title: str = Field(..., max_length=200)
    content: str = Field(..., max_length=4000)
    tags: list[str] = Field(default_factory=list, max_length=16)


knowledge_router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@knowledge_router.post("/ingest")
async def ingest_knowledge(
    body: IngestRequest,
    _auth: Annotated[dict | None, Depends(_get_auth())] = None,
) -> dict:
    """cron 任务（日报/RSS/论文 digest）完成后写入知识库（W131-04.4）。"""
    from apiserver.knowledge_driver import get_knowledge_driver
    item_id = get_knowledge_driver().ingest(
        source_type=body.source_type, title=body.title,
        content=body.content, tags=body.tags)
    return {"ok": True, "item_id": item_id}


@knowledge_router.get("/stats")
async def knowledge_stats(
    _auth: Annotated[dict | None, Depends(_get_auth())] = None,
) -> dict:
    """知识库统计（条目数/工具评分数）。"""
    from apiserver.knowledge_driver import get_knowledge_driver
    return {"ok": True, **get_knowledge_driver().stats()}


@knowledge_router.get("/recommend")
async def tool_recommendation(
    task: str = "",
    _auth: Annotated[dict | None, Depends(_get_auth())] = None,
) -> dict:
    """按当前任务查工具推荐（W131-04.1 / W131-07.2）。"""
    from apiserver.knowledge_driver import get_knowledge_driver
    recs = get_knowledge_driver().get_tool_recommendation(task)
    return {"ok": True, "task": task,
            "recommendations": [vars(r) for r in recs]}


# ============ W131-03: loop 快照（checkpoint/resume） ============


class CheckpointRequest(BaseModel):
    session_id: str = Field(..., max_length=64)
    messages: list[dict] = Field(default_factory=list)
    round_num: int = Field(0, ge=0)
    tool_results: list[dict] = Field(default_factory=list)
    meta: dict = Field(default_factory=dict)


checkpoint_router = APIRouter(prefix="/agent", tags=["agent-loop"])


@checkpoint_router.post("/checkpoint")
async def save_checkpoint(
    body: CheckpointRequest,
    _auth: Annotated[dict | None, Depends(_get_auth())] = None,
) -> dict:
    """手动保存 loop 快照（自动快照之外的手动触发点）。"""
    from apiserver.loop_checkpoint import get_loop_checkpoint
    get_loop_checkpoint().save(
        body.session_id, body.messages, body.round_num,
        body.tool_results, meta=body.meta)
    return {"ok": True, "session_id": body.session_id, "round_num": body.round_num}


@checkpoint_router.get("/checkpoint/{session_id}")
async def load_checkpoint(
    session_id: str,
    _auth: Annotated[dict | None, Depends(_get_auth())] = None,
) -> dict:
    """读最新快照（恢复前检查：无快照返回 empty=True）。"""
    from apiserver.loop_checkpoint import get_loop_checkpoint
    st = get_loop_checkpoint().load(session_id)
    if st is None:
        return {"ok": True, "empty": True, "session_id": session_id}
    return {"ok": True, "empty": False, "session_id": st.session_id,
            "round_num": st.round_num, "timestamp": st.timestamp,
            "messages_summary": st.messages_summary,
            "tool_results_digest": st.tool_results_digest, "meta": st.meta}


@checkpoint_router.post("/resume")
async def resume_loop(
    body: dict,
    _auth: Annotated[dict | None, Depends(_get_auth())] = None,
) -> dict:
    """从快照恢复 agentic loop（W131-03.3：从断点继续，不是从头）。

    恢复语义：返回快照状态给调用方（chat 路由拿去重建上下文后继续 loop）。
    若 session 正在运行则拒绝（防双跑）。
    """
    session_id = str(body.get("session_id", ""))[:64]
    if not session_id:
        raise HTTPException(status_code=422, detail="session_id 必填")
    from apiserver.loop_checkpoint import get_loop_checkpoint
    cp = get_loop_checkpoint()
    if body.get("is_running"):
        return {"ok": False, "reason": "session_running", "detail": "会话运行中，拒绝 resume"}
    st = cp.load(session_id)
    if st is None:
        return {"ok": False, "reason": "no_checkpoint",
                "detail": "无快照可恢复，请从头开始"}
    # 恢复成功后不删快照（等任务成功再 clear——工单 W131-03.1）
    return {"ok": True, "resumed": True, "session_id": st.session_id,
            "round_num": st.round_num, "messages_summary": st.messages_summary,
            "tool_results_digest": st.tool_results_digest}


@checkpoint_router.delete("/checkpoint/{session_id}")
async def clear_checkpoint(
    session_id: str,
    _auth: Annotated[dict | None, Depends(_get_auth())] = None,
) -> dict:
    """任务成功后清理快照（安全擦除）。"""
    from apiserver.loop_checkpoint import get_loop_checkpoint
    get_loop_checkpoint().clear(session_id)
    return {"ok": True}


def _get_auth():
    """延迟导入鉴权（与 radio.py 等既有路由同源：apiserver.naga_auth）。"""
    from apiserver.naga_auth import require_local_auth
    return require_local_auth
