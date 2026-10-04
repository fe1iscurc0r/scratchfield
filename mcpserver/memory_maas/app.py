"""记忆 MaaS sidecar — FastAPI HTTP 面（默认 127.0.0.1:48919）。

端点清单与错误映射见 docs/Memory-MaaS-Research-v1.md 第四节。
硬约束落实：不改 apiserver/NEKO 一行，独立进程独立端口。
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from mcpserver.memory_maas.core import (
    MemoryMaasCore,
    MemoryMaasError,
    ensure_neko_path,
    get_core,
)
from mcpserver.memory_maas.entities import (
    EntityValidationError,
    MemoryEntity,
    normalize_platform,
)
from mcpserver.memory_maas.guard import pre_write_check
from mcpserver.memory_maas.maintenance import (
    consolidate,
    list_snapshots,
    retention_sweep,
    snapshot,
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


class TypedAddRequest(BaseModel):
    content: str = Field(min_length=1, description="记忆内容")
    type: str = Field(default="note", description="decision|insight|handoff|note")
    tags: list[str] = Field(default_factory=list, description="标签")
    pinned: bool = Field(default=False, description="标星（永不清理）")
    relations: list[str] = Field(default_factory=list, description="关联实体 id")
    source_rank: int = Field(default=0, ge=0, le=3,
                             description="来源分级：0 用户 / 1 agent / 2 外部 / 3 未验证")
    platform: str = Field(
        default="local",
        description="平台来源（03-04）：weixin|qqbot|cli|local，别名 qq/wechat/wx 自动归一")

    @field_validator("type")
    @classmethod
    def _valid_type(cls, v: str) -> str:
        try:
            MemoryEntity(id="preview", type=v, content="")  # 非法 type 抛 EntityValidationError
        except EntityValidationError as e:
            raise ValueError(str(e)) from e
        return v

    @field_validator("platform")
    @classmethod
    def _valid_platform(cls, v: str) -> str:
        try:
            return normalize_platform(v)
        except EntityValidationError as e:
            raise ValueError(str(e)) from e


class TypedQueryRequest(BaseModel):
    type: str | None = None
    tags: list[str] | None = None
    pinned: bool | None = None
    limit: int | None = Field(default=None, ge=1, le=1000)
    include_isolation: bool = Field(default=False,
                                    description="是否含隔离区条目")
    path: str | None = Field(
        default=None,
        description="路径过滤（03-02）：绝对/项目根相对/cwd 相对三种写法等价匹配")
    platform: str | None = Field(
        default=None,
        description="平台来源过滤（03-04）：weixin|qqbot|cli|local，别名自动归一")


class ObservationCaptureRequest(BaseModel):
    """03-01 观察捕获：内容哈希去重（同观察幂等只留一条）。"""
    memory_session_id: str = Field(min_length=1, description="观察所属会话")
    title: str = Field(default="", description="观察标题")
    narrative: str = Field(default="", description="观察叙述")
    type: str = Field(default="note", description="decision|insight|handoff|note")
    tags: list[str] = Field(default_factory=list, description="标签")
    pinned: bool = Field(default=False, description="标星（永不清理）")
    source_rank: int = Field(default=0, ge=0, le=3,
                             description="来源分级：0 用户 / 1 agent / 2 外部 / 3 未验证")
    platform: str = Field(
        default="local",
        description="平台来源（03-04）：weixin|qqbot|cli|local，别名自动归一")


class GuardCheckRequest(BaseModel):
    content: str = Field(min_length=1)
    source_rank: int = Field(default=0, ge=0, le=3)


class SweepRequest(BaseModel):
    max_age_days: float = Field(default=30.0, ge=0.0)
    dry_run: bool = Field(default=False)


class ConsolidateRequest(BaseModel):
    min_group: int = Field(default=2, ge=2)
    template_mode: str = Field(default="default",
                               description="压缩块模板模式（03-03）：default|compact")
    dry_run: bool = Field(default=False)


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


# ------------------------------------------------------------------ typed 实体（X-01/X-03）

@app.post("/memory/typed")
async def typed_add(req: TypedAddRequest):
    """新增 typed 记忆实体（内部自动走 pre_write_check 注入校验 + 来源分级隔离）。

    03-04：platform 写时打标平台来源，随 provenance 必填投影返回。
    """
    try:
        return _core().add_memory(req.content, type=req.type, tags=req.tags,
                                  pinned=req.pinned, relations=req.relations,
                                  source_rank=req.source_rank,
                                  platform=req.platform)
    except MemoryMaasError as e:
        raise _maas_error(e, 422)


@app.post("/memory/typed/query")
async def typed_query(req: TypedQueryRequest):
    """按 type/tags/pinned/path/platform 过滤（默认排除隔离区）。"""
    return _core().query(type=req.type, tags=req.tags, pinned=req.pinned,
                         limit=req.limit,
                         include_isolation=req.include_isolation,
                         path=req.path, platform=req.platform)


@app.post("/memory/capture/observation")
async def capture_observation(req: ObservationCaptureRequest):
    """观察捕获（03-01 内容哈希去重）：来源分级 → 哈希去重 → 入库（幂等）。"""
    try:
        return _core().capture_observation(
            req.memory_session_id, req.title, req.narrative, type=req.type,
            tags=req.tags, pinned=req.pinned, source_rank=req.source_rank,
            platform=req.platform)
    except MemoryMaasError as e:
        raise _maas_error(e, 422)


@app.post("/memory/typed/{entity_id}/promote")
async def typed_promote(entity_id: str):
    """隔离条目升级为可信来源（source_rank=1，解除隔离）。"""
    try:
        return _core().promote_memory(entity_id)
    except MemoryMaasError as e:
        raise _maas_error(e, 404)


@app.post("/memory/typed/{entity_id}/pin")
async def typed_pin(entity_id: str):
    return _core().pin_memory(entity_id)


@app.post("/memory/typed/{entity_id}/unpin")
async def typed_unpin(entity_id: str):
    return _core().unpin_memory(entity_id)


# ------------------------------------------------------------------ 注入防护（X-03）

@app.post("/memory/guard/check")
async def guard_check(req: GuardCheckRequest):
    """写前校验 dry-run：返回 blocked/isolation/source_rank 结论（不落盘）。"""
    return pre_write_check(req.content, source_rank=req.source_rank).to_dict()


@app.get("/memory/guard/status")
async def guard_status():
    return _core().guard_status()


# ------------------------------------------------------------------ 维护（X-02）

@app.post("/memory/maintenance/sweep")
async def maintenance_sweep(req: SweepRequest):
    """遗忘调度：低价值/过期记忆清理（执行前自动快照，pinned 永不删）。"""
    core = _core()
    return retention_sweep(core.typed_store, max_age_days=req.max_age_days,
                           dry_run=req.dry_run,
                           snapshots_dir=str(core.data_dir / "snapshots"))


@app.post("/memory/maintenance/consolidate")
async def maintenance_consolidate(req: ConsolidateRequest):
    """相似记忆合并：同 tags 短 note 合并（执行前自动快照）。

    03-03：组员全为可解析压缩块时按 XML 模板渲染合并块，否则整段降级。
    """
    core = _core()
    return consolidate(core.typed_store, min_group=req.min_group,
                       template_mode=req.template_mode,
                       dry_run=req.dry_run,
                       snapshots_dir=str(core.data_dir / "snapshots"))


@app.get("/memory/maintenance/status")
async def maintenance_status():
    return _core().maintenance_status()


@app.get("/memory/maintenance/snapshots")
async def maintenance_snapshots():
    """已创建快照列表（回滚保护点）。"""
    return {"ok": True, "snapshots": list_snapshots(
        _core().data_dir / "snapshots")}


@app.post("/memory/maintenance/snapshot")
async def maintenance_snapshot():
    """手动创建快照（不执行 sweep/consolidate）。"""
    core = _core()
    return snapshot(core.typed_store,
                    snapshots_dir=str(core.data_dir / "snapshots"))
