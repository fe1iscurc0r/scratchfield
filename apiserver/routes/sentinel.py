"""sentinel.py — 哨兵网格 API（卷187 B2）。

前端 SentinelPanel 消费的四个端点：

- ``GET  /sentinel/nodes``                       在线节点列表 + 最后心跳
- ``GET  /sentinel/spectrum?from=&to=&node=``    时间窗内 RSSI 扫描数据
- ``GET  /sentinel/env?node=&hours=``            环境数据（温湿压/电池）
- ``POST /sentinel/scan_config``                 下发扫描配置（写命令队列）

数据来自 ``mcpserver.rf_brain.sentinel_link.gateway.SqliteSink``（与网关同库）。
网关可能跑在**独立进程**，两者共用同一 SQLite 文件（WAL 模式允许多进程并发
读写），故本端点直接读库，无需转发。

另附 ``GET /sentinel/occupations``（任务 D 的占用事件查询），供面板框选展示。
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sentinel", tags=["sentinel"])

#: 命令帧发往的 Topic（网关/节点侧订阅后下发；本卷只入队不阻塞）
_CMD_TOPIC = "lumo.sentinel.gateway_cmd"


# ── 请求模型 ─────────────────────────────────────────────────────────────

class ScanConfigRequest(BaseModel):
    """`POST /sentinel/scan_config` 请求体。"""

    node_id: str | None = Field(default=None, description="目标节点；None=广播")
    freq_range: list[float] = Field(default_factory=lambda: [433.0, 434.7])
    dwell_ms: int = Field(default=120, ge=10, le=5000)
    sf_set: list[int] = Field(default_factory=lambda: [7, 9, 10, 12])
    step_khz: int = Field(default=200, ge=1, le=10000)


# ── 惰性取库（避免 import 期重依赖 / 库不存在时崩）──────────────────────

def _sink():
    """按需构造 SqliteSink（读同一个库）。"""
    from mcpserver.rf_brain.sentinel_link.gateway import SqliteSink
    return SqliteSink()


# ── 端点 ─────────────────────────────────────────────────────────────────

@router.get("/nodes")
async def list_nodes() -> dict[str, Any]:
    """在线节点列表 + 最后心跳（心跳 >60s 判离线）。"""
    sink = _sink()
    try:
        nodes = sink.list_nodes()
    finally:
        sink.close()
    return {"count": len(nodes),
            "online": sum(1 for n in nodes if n["online"]),
            "offline_after_s": 60,
            "nodes": nodes}


@router.get("/spectrum")
async def get_spectrum(from_: float | None = None, to: float | None = None,
                       node: str | None = None, limit: int = 20000,
                       ) -> dict[str, Any]:
    """时间窗内 RSSI 扫描数据（`from`/`to` 为 Unix 秒；缺省取最近 5 分钟）。"""
    now = time.time()
    frm = from_ if from_ is not None else now - 300.0
    to_v = to if to is not None else now
    if frm > to_v:
        raise HTTPException(status_code=400, detail="from 不能大于 to")
    sink = _sink()
    try:
        rows = sink.query_spectrum(frm=frm, to=to_v, node=node, limit=limit)
    finally:
        sink.close()
    return {"from": frm, "to": to_v, "node": node, "count": len(rows), "rows": rows}


@router.get("/env")
async def get_env(node: str | None = None, hours: float = 24.0,
                  limit: int = 20000) -> dict[str, Any]:
    """环境数据（温湿度/气压/电池/GPS），默认最近 24 小时。"""
    if hours <= 0 or hours > 24 * 30:
        raise HTTPException(status_code=400, detail="hours 需在 (0, 720] 区间")
    sink = _sink()
    try:
        rows = sink.query_env(node=node, hours=hours, limit=limit)
    finally:
        sink.close()
    return {"node": node, "hours": hours, "count": len(rows), "rows": rows}


@router.get("/occupations")
async def get_occupations(node: str | None = None, hours: float = 72.0,
                          limit: int = 500) -> dict[str, Any]:
    """占用事件（任务 D）：同频点持续高 RSSI 超阈值后落地的记录（新→旧）。"""
    from mcpserver.rf_brain.sentinel_link.occupation import query_occupations
    rows = query_occupations(node=node, hours=hours, limit=limit)
    return {"node": node, "hours": hours, "count": len(rows), "rows": rows}


@router.post("/scan_config")
async def post_scan_config(req: ScanConfigRequest) -> dict[str, Any]:
    """下发扫描配置（校验后发 EventBus 命令；节点侧 ack 后生效）。"""
    from mcpserver.rf_brain.sentinel_link.protocol import parse_scan_config
    try:
        cfg = parse_scan_config(req.model_dump(exclude={"node_id"}))
    except Exception as e:                          # noqa: BLE001 - 参数错 → 400
        raise HTTPException(status_code=400, detail=f"scan_config 非法: {e}") from e

    cmd_id = f"c-{int(time.time() * 1000) % 10 ** 9:09d}"
    payload = {"cmd": "scan_config", "cmd_id": cmd_id, "node_id": req.node_id,
               **cfg}
    delivered = False
    try:
        from apiserver.event_bus import get_bus
        get_bus().emit(_CMD_TOPIC, payload)
        delivered = True
    except Exception as e:                          # noqa: BLE001 - 无总线时降级
        logger.warning("[sentinel] 命令入队失败（无总线？）: %s", e)

    return {"ok": True, "cmd_id": cmd_id, "target": req.node_id or "*",
            "config": cfg, "delivered_to_bus": delivered,
            "note": "配置已入队，节点 ack 后生效" if delivered else "总线不可用，未下发"}
