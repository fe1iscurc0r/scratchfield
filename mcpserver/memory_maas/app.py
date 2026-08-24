"""记忆 MaaS sidecar — FastAPI HTTP 面（默认 127.0.0.1:48919）。

端点清单与错误映射见 docs/Memory-MaaS-Research-v1.md 第四节。
硬约束落实：不改 apiserver/NEKO 一行，独立进程独立端口。
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field

from mcpserver.memory_maas.core import (
    MemoryMaasCore,
    MemoryMaasError,
    ensure_neko_path,
    get_core,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    ensure_neko_path()
    core = get_core()
    logger.info("[memory_maas] 启动完成，数据目录: %s", core.data_dir)
    yield
    get_core().close()
    logger.info("[memory_maas] 已关闭")


app = FastAPI(title="记忆 MaaS API", version="0.1.0",
              description="NEKO 记忆五件套 sidecar：会话血统 / 混合检索 / "
                          "索引卡后台写入 / 衰减过期（W-06）",
              lifespan=lifespan)


# ------------------------------------------------------------------ 模型

class SearchRequest(BaseModel):
    query: str = Field(min_length=1, description="检索词")
    limit: int = Field(default=10, ge=1, le=50)
    query_vec: list[float] | None = Field(
        default=None, description="可选稠密向量（提供则叠加向量路 RRF）")
    with_lineage: bool = Field(default=True, description="命中附带会话血统链")


class CardWriteRequest(BaseModel):
    session_id: str = Field(min_length=1)
    turns: list[dict[str, Any]] = Field(
        description="对话轮次 [{role, content}]；后台启发式摘要建卡")
    drain_timeout: float = Field(default=5.0, ge=0.1, le=30.0)


class LineageRegisterRequest(BaseModel):
    session_id: str = Field(min_length=1)
    parent_id: str | None = None
    branch_label: str = "main"
    summary: str = ""


class EnrichRequest(BaseModel):
    records: list[dict[str, Any]] = Field(
        min_length=1,
        description='外部记录 [{"last_access": unix秒, "confidence": 0~1}]')


def _core() -> MemoryMaasCore:
    return get_core()


def _maas_error(e: Exception, status: int = 500) -> HTTPException:
    return HTTPException(status_code=status,
                         detail=f"[memory_maas] {e}")


# ------------------------------------------------------------------ 端点

@app.get("/health")
async def health():
    return {"status": "ok", "service": "memory_maas"}


@app.get("/status")
async def status():
    try:
        return _core().status()
    except MemoryMaasError as e:
        raise _maas_error(e, 503)


@app.post("/memory/search")
async def memory_search(req: SearchRequest):
    """混合检索（FTS5 关键词 + 可选向量，RRF 融合），命中附带会话血统。"""
    try:
        return _core().search(req.query, limit=req.limit,
                              query_vec=req.query_vec,
                              with_lineage=req.with_lineage)
    except MemoryMaasError as e:
        raise _maas_error(e, 422)


@app.post("/memory/cards")
async def write_card(req: CardWriteRequest):
    """写索引卡：BackgroundWriter 后台写入 + 检索索引同步（drain 保证同步语义）。"""
    try:
        return _core().write_card(req.session_id, req.turns,
                                  drain_timeout=req.drain_timeout)
    except MemoryMaasError as e:
        raise _maas_error(e, 422)


@app.get("/memory/cards/{session_id}")
async def cards_for_session(session_id: str):
    return {"ok": True, "session_id": session_id,
            "cards": _core().cards_for_session(session_id)}


@app.get("/memory/cards")
async def search_cards(keyword: str = Query(min_length=0),
                       limit: int = Query(default=10, ge=1, le=200)):
    return {"ok": True, "keyword": keyword,
            "cards": _core().search_cards(keyword, limit=limit)}


@app.post("/memory/cards/{card_id}/touch")
async def touch_card(card_id: int):
    """访问续命：刷新 last_access，对抗 lifecycle 衰减。"""
    _core().touch_card(card_id)
    return {"ok": True, "card_id": card_id, "touched": True}


@app.post("/memory/lineage/register")
async def register_session(req: LineageRegisterRequest):
    """登记会话（fork 守卫：父不存在/血统环/上下文超限 → 409）。"""
    core = _core()
    try:
        return core.register_session(req.session_id, parent_id=req.parent_id,
                                     branch_label=req.branch_label,
                                     summary=req.summary)
    except MemoryMaasError as e:
        raise _maas_error(e, 422)
    except Exception as e:  # LineageError 等五件套异常 → 血统冲突语义
        raise _maas_error(e, 409)


@app.get("/memory/lineage/trace/{session_id}")
async def lineage_trace(session_id: str):
    """会话血统链：[根 .. 自身]，每项含 parent_id/branch_label/summary。"""
    try:
        chain = _core().trace(session_id)
        return {"ok": True, "session_id": session_id, "lineage": chain,
                "depth": len(chain)}
    except Exception as e:
        raise _maas_error(e, 404)


@app.get("/memory/lineage/children/{session_id}")
async def lineage_children(session_id: str):
    return {"ok": True, "session_id": session_id,
            "children": _core().children(session_id)}


@app.get("/memory/lineage/branches/{root_id}")
async def lineage_branches(root_id: str):
    return {"ok": True, "root_id": root_id,
            "branches": _core().branches_under(root_id)}


@app.get("/memory/lifecycle/report")
async def lifecycle_report(limit: int = Query(default=500, ge=1, le=5000)):
    return _core().lifecycle_report(limit=limit)


@app.post("/memory/lifecycle/enrich")
async def lifecycle_enrich(req: EnrichRequest):
    """纯函数：外部记录批量附 keep/decay/expire 决策（无落盘副作用）。"""
    try:
        return _core().enrich_records(req.records)
    except MemoryMaasError as e:
        raise _maas_error(e, 422)
