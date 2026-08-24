"""
H-01: yjs CRDT 同步端点生产化 — /api/sync 三端点（v2 施工图）

职责：
  - POST /api/sync/update   增量 upsert（append-only，同 (doc_id, instance_id, clock) 重发幂等）
  - GET  /api/sync/updates  按自增 seq(rowid) 水位拉取他人增量（升序，水位语义稳定）
  - POST /api/sync/compact  手动合并旧增量（pycrdt.merge_updates 变参展开）

存储：SQLite `sync_updates(seq, doc_id, instance_id, clock, update_blob)`。
唯一键 (doc_id, instance_id, clock)——clock 是实例内逻辑时钟，多实例会碰撞，
必须带 instance_id 分键，否则跨实例同 clock 增量会被 OR REPLACE 覆盖丢失。

同步水位：since=<seq>（自增主键，语义稳定不受 clock 碰撞/compact 影响）。
客户端把已应用的最大 seq 存为水位，下次拉取 seq > 水位的增量。

compact：pycrdt.merge_updates(*blobs) 为可变参数，传 list 会 PanicException，
必须 * 展开。合并后整表删除并回写单条 merged 行（instance_id='__merged__'），
获得新 seq，客户端重复拉取由 CRDT 幂等保证无害。

CRDT 收敛语义交给 pycrdt 现成实现（与 yjs 同算法、update 字节格式互通），
本层只做传输与存储，不引入自定义墙钟语义——同 key 并发写由 CRDT
逻辑时钟 LWW 收敛，服务端不额外排序。

设计依据：WO-04 yjs 原型（scripts/yjs_sync_prototype.py）+ BATCH-WORKORDERS-2026-08-24-SPEC10.md H-01 v2 施工图。
"""

from __future__ import annotations

import base64
import binascii
import logging
import os
import sqlite3
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from system.config import get_data_dir

try:
    import pycrdt
except ImportError:  # pragma: no cover - 依赖缺失时启动降级
    pycrdt = None

from ..naga_auth import require_local_auth

router = APIRouter(prefix="/api/sync", tags=["sync"])
logger = logging.getLogger(__name__)

_MAX_UPDATE_B64_LEN = 16 * 1024 * 1024  # 单条增量 base64 上限（防超大 payload）
_DEFAULT_PAGE_SIZE = 1024
_MERGED_INSTANCE_ID = "__merged__"  # compact 合并行的 instance_id 占位


# ============ 存储 ============


def _db_path() -> str:
    """返回 SQLite 文件路径（数据目录下 sync/sync.db）。"""
    return str(get_data_dir() / "sync" / "sync.db")


_SCHEMA = """
CREATE TABLE IF NOT EXISTS sync_updates (
    seq         INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_id      TEXT    NOT NULL,
    instance_id TEXT    NOT NULL,
    clock       INTEGER NOT NULL,
    update_blob BLOB    NOT NULL,
    UNIQUE (doc_id, instance_id, clock)
);
"""


def _connect() -> sqlite3.Connection:
    path = _db_path()
    # 确保目录存在（get_data_dir 已 mkdir，但 sync 子目录需自建）
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(_SCHEMA)
    return conn


def _decode_update(update_b64: str) -> bytes:
    """base64 -> bytes，非法则抛 400。"""
    try:
        return base64.b64decode(update_b64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(status_code=400, detail="invalid base64 update") from None


def _encode_update(blob: bytes) -> str:
    return base64.b64encode(blob).decode("ascii")


# ============ 请求模型 ============


class UpdateRequest(BaseModel):
    doc_id: str = Field(..., min_length=1, max_length=128, description="同步文档标识")
    instance_id: str = Field(
        ..., min_length=1, max_length=64, description="客户端实例标识（逻辑时钟命名空间，防跨实例 clock 碰撞）"
    )
    clock: int = Field(..., ge=0, description="客户端实例内逻辑时钟（LWW 排序键）")
    update_b64: str = Field(..., min_length=1, max_length=_MAX_UPDATE_B64_LEN)


class CompactRequest(BaseModel):
    doc_id: str = Field(..., min_length=1, max_length=128)


# ============ 端点 ============


@router.post("/update")
async def post_update(
    body: UpdateRequest,
    _auth: Annotated[dict | None, Depends(require_local_auth)] = None,
) -> dict:
    """增量 upsert：唯一键 (doc_id, instance_id, clock)，重发幂等（seq 不变，内容覆盖）。

    服务端不解析 update 内容、不做 CRDT 运算——只存储增量字节。
    """
    blob = _decode_update(body.update_b64)
    with _connect() as conn:
        conn.execute(
            "INSERT INTO sync_updates (doc_id, instance_id, clock, update_blob) VALUES (?, ?, ?, ?) "
            "ON CONFLICT (doc_id, instance_id, clock) DO UPDATE SET update_blob = excluded.update_blob",
            (body.doc_id, body.instance_id, body.clock, blob),
        )
    logger.debug(
        f"[sync] update doc={body.doc_id[:16]} inst={body.instance_id[:16]} clock={body.clock} bytes={len(blob)}"
    )
    return {
        "ok": True,
        "doc_id": body.doc_id,
        "instance_id": body.instance_id,
        "clock": body.clock,
        "stored": True,
    }


@router.get("/updates")
async def get_updates(
    doc_id: str = Query(..., min_length=1, max_length=128),
    since: int = Query(0, ge=0, description="只拉取 seq > since 的增量（水位 = 已应用的最大 seq）"),
    limit: int = Query(_DEFAULT_PAGE_SIZE, ge=1, le=4096),
    _auth: Annotated[dict | None, Depends(require_local_auth)] = None,
) -> dict:
    """拉取他人增量：按自增 seq 升序，返回 seq/instance_id/clock/base64 列表。

    since 语义为「我已应用到 seq=since 为止」，只返回之后的新增量；
    重复拉取同一行由 CRDT 幂等保证（apply_update 重复应用无害）。
    """
    with _connect() as conn:
        rows = conn.execute(
            "SELECT seq, instance_id, clock, update_blob FROM sync_updates "
            "WHERE doc_id = ? AND seq > ? ORDER BY seq ASC LIMIT ?",
            (doc_id, since, limit),
        ).fetchall()
    updates = [
        {"seq": seq, "instance_id": instance_id, "clock": clock, "update_b64": _encode_update(blob)}
        for seq, instance_id, clock, blob in rows
    ]
    return {
        "ok": True,
        "doc_id": doc_id,
        "since": since,
        "updates": updates,
        "count": len(updates),
    }


@router.post("/compact")
async def compact_doc(
    body: CompactRequest,
    _auth: Annotated[dict | None, Depends(require_local_auth)] = None,
) -> dict:
    """手动合并该 doc 的全部旧增量为单条 merged update（append-only 的显式收敛）。

    pycrdt.merge_updates(*blobs) 把多条增量合成为一条等价 update（变参展开，
    传 list 会 PanicException）。合并后 DELETE 全部旧行、回写单条 merged 行，
    新行获得新的自增 seq——水位单调，客户端按 since 拉取至多重复返回一次
    该 merged 行，由 CRDT 幂等保证无害。
    """
    if pycrdt is None:  # pragma: no cover
        raise HTTPException(status_code=503, detail="pycrdt 依赖缺失")
    with _connect() as conn:
        rows = conn.execute(
            "SELECT seq, clock, update_blob FROM sync_updates WHERE doc_id = ? ORDER BY seq ASC",
            (body.doc_id,),
        ).fetchall()
        if not rows:
            return {"ok": True, "doc_id": body.doc_id, "merged_seq": None, "rows": 0}
        blobs = [blob for _, _, blob in rows]
        max_clock = max(clock for _, clock, _ in rows)
        try:
            merged = pycrdt.merge_updates(*blobs)
        except Exception as e:  # pragma: no cover - 异常路径防御
            logger.error(f"[sync] compact merge 失败 doc={body.doc_id}: {e}")
            raise HTTPException(status_code=500, detail=f"merge failed: {e}") from e
        conn.execute("DELETE FROM sync_updates WHERE doc_id = ?", (body.doc_id,))
        cur = conn.execute(
            "INSERT INTO sync_updates (doc_id, instance_id, clock, update_blob) VALUES (?, ?, ?, ?)",
            (body.doc_id, _MERGED_INSTANCE_ID, max_clock, merged),
        )
        merged_seq = cur.lastrowid
    logger.info(f"[sync] compact doc={body.doc_id[:16]} rows={len(rows)} -> 1 seq={merged_seq} bytes={len(merged)}")
    return {
        "ok": True,
        "doc_id": body.doc_id,
        "merged_seq": merged_seq,
        "rows": len(rows),
    }
