"""节点心跳广播路由 —— 战情面板数据源。

职责：
  1) POST /api/status/heartbeat  接收各节点上报，存入内存（TTL 淘汰）并 emit 到 EventBus
  2) GET  /api/status/nodes      查询所有存活节点最新状态

数据流：
  节点定时脚本 → POST heartbeat → 本路由校验+存储 → EventBus.emit(NODE_HEARTBEAT)
                                                          ↓
                                          战情面板 / 告警系统 / 监控脚本订阅

鉴权：免鉴权（节点在内网定向推送，网络层保安全）。
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta
from threading import RLock
from typing import Any, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from apiserver.event_bus import Topics, get_bus

router = APIRouter(prefix="/api/status", tags=["status-heartbeat"])

# ============ 配置 ============
_HEARTBEAT_TTL = 120  # 秒，超过此时间未上报视为离线

# ============ 内存存储 ============
_node_heartbeats: dict[str, dict[str, Any]] = {}
_heartbeat_lock = RLock()


def _purge_expired() -> None:
    """淘汰超过 TTL 的节点记录。调用方须持 _heartbeat_lock。"""
    now = time.time()
    expired = [
        node_id
        for node_id, record in _node_heartbeats.items()
        if now - record.get("_received_at", 0) > _HEARTBEAT_TTL
    ]
    for node_id in expired:
        _node_heartbeats.pop(node_id, None)


# ============ Pydantic 模型 ============
class HeartbeatMetrics(BaseModel):
    cpu_percent: Optional[float] = Field(default=None, ge=0, le=100)
    memory_percent: Optional[float] = Field(default=None, ge=0, le=100)
    disk_percent: Optional[float] = Field(default=None, ge=0, le=100)
    api_quota_percent: Optional[float] = Field(default=None, ge=0, le=100)
    queue_depth: Optional[int] = Field(default=0, ge=0)
    network_rx_mbps: Optional[float] = Field(default=None, ge=0)
    network_tx_mbps: Optional[float] = Field(default=None, ge=0)


class HeartbeatRequest(BaseModel):
    node_id: str = Field(..., description="节点标识，如 'cloud-server' / 'kali' / 'k40' / 'tianxuan7'")
    node_type: Literal["cloud-server", "kali", "k40", "tianxuan7", "other"] = Field(
        default="other", description="节点类型"
    )
    timestamp: Optional[str] = Field(default=None, description="ISO8601 时间戳（可选，缺省则用服务器时间）")
    status: Literal["online", "degraded", "offline"] = Field(default="online")
    metrics: HeartbeatMetrics = Field(default_factory=HeartbeatMetrics)
    alerts: list[str] = Field(default_factory=list, description="告警列表，如 ['rate_limit_near']")

    model_config = {"extra": "forbid"}


class HeartbeatResponse(BaseModel):
    ok: bool
    received: str
    ttl: int


class NodeStatus(BaseModel):
    node_id: str
    node_type: str
    status: str
    metrics: HeartbeatMetrics
    alerts: list[str]
    last_seen: float  # epoch 秒
    # 原始时间戳（上报方提供）
    timestamp: Optional[str] = None


class NodesResponse(BaseModel):
    nodes: dict[str, NodeStatus]
    timestamp: float  # epoch 秒


# ============ 路由实现 ============
@router.post("/heartbeat", response_model=HeartbeatResponse)
async def receive_heartbeat(req: HeartbeatRequest) -> HeartbeatResponse:
    """接收节点心跳：存入内存（TTL 淘汰）并 emit 到 EventBus。"""
    received_at = time.time()
    now_datetime = datetime.now()

    record: dict[str, Any] = {
        "node_id": req.node_id,
        "node_type": req.node_type,
        "status": req.status,
        "metrics": req.metrics.model_dump(),
        "alerts": req.alerts,
        "_received_at": received_at,  # 内部字段，不暴露
        "timestamp": req.timestamp or now_datetime.isoformat(),
    }

    with _heartbeat_lock:
        _purge_expired()
        _node_heartbeats[req.node_id] = record

    # emit 到 EventBus（fire-and-forget，不阻塞响应）
    try:
        bus = get_bus()
        bus.emit(Topics.NODE_HEARTBEAT, record.copy())
    except Exception:
        # EventBus emit 失败不影响心跳接收（总线故障不是节点故障）
        pass

    return HeartbeatResponse(ok=True, received=req.node_id, ttl=_HEARTBEAT_TTL)


@router.get("/nodes", response_model=NodesResponse)
async def get_all_nodes() -> NodesResponse:
    """查询所有存活节点最新状态（TTL 淘汰）。"""
    with _heartbeat_lock:
        _purge_expired()
        nodes: dict[str, NodeStatus] = {}
        for node_id, record in _node_heartbeats.items():
            nodes[node_id] = NodeStatus(
                node_id=record["node_id"],
                node_type=record["node_type"],
                status=record["status"],
                metrics=HeartbeatMetrics(**record.get("metrics", {})),
                alerts=record.get("alerts", []),
                last_seen=record.get("_received_at", 0),
                timestamp=record.get("timestamp"),
            )

    return NodesResponse(nodes=nodes, timestamp=time.time())
