"""工单217 任务一 · 嘉立创 EDA parasite-export 接收端。

EDA→scratchpad 双向适配的第一条实链：parasite-export 扩展（.eext，见
docs/easyeda-custom-extensions.md §1）把当前文档源码（.esch/.epcb JSON）POST 到
可配置 URL（默认 http://127.0.0.1:8765/ingest → 云服改 http://<host>:8000/api/eda/ingest）。

- POST /api/eda/ingest
    信封：{"meta": {"project": str, "page": str, "doc_type": "esch"|"epcb"|str},
           "source": "<文档 JSON 源码>"}
    行为：校验 → 落盘 <user_data>/eda_ingest/<ts>_<project>.json（幂等：同内容 hash 跳过）
          → 发 EventBus 事件 lumo.eda.document_ingested（消费者后续挂：寄生参数提取/RAG 入库）
- 鉴权：静态 token。优先 EDA_INGEST_TOKEN 环境变量；未设时回落 LUMO_PROXY_TOKEN
  （与 /debug/dump 同源的既有约定）；两者都未设 → 拒绝（不裸奔）。
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from apiserver.event_bus import get_bus
from system.config import get_data_dir

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/eda", tags=["eda"])

_SAFE_NAME = re.compile(r"[^0-9A-Za-z_.\-]+")
EVENT_TOPIC = "lumo.eda.document_ingested"


def _safe_project(name: str) -> str:
    """净化工程名：白名单字符 + 压掉路径穿越残留（.. → _）。"""
    s = _SAFE_NAME.sub("_", name).strip("._-") or "unnamed"
    return s.replace("..", "_")


class EdaIngestMeta(BaseModel):
    project: str = Field(..., max_length=200, description="工程名")
    page: str = Field(default="", max_length=200, description="页面/图页名")
    doc_type: str = Field(default="esch", max_length=16, description="esch / epcb / 其他")


class EdaIngestRequest(BaseModel):
    meta: EdaIngestMeta
    source: str = Field(..., min_length=1, description="文档 JSON 源码（getDocumentSource() 产物）")


def _ingest_token() -> str:
    """静态 token：EDA_INGEST_TOKEN 优先，回落 LUMO_PROXY_TOKEN；都空 → 未配置。"""
    return (os.environ.get("EDA_INGEST_TOKEN")
            or os.environ.get("LUMO_PROXY_TOKEN")
            or "").strip()


def _check_token(x_edatoken: str | None) -> None:
    token = _ingest_token()
    if not token:
        raise HTTPException(status_code=503, detail="EDA ingest 未配置 token（设 EDA_INGEST_TOKEN）")
    if not x_edatoken or x_edatoken.strip() != token:
        raise HTTPException(status_code=401, detail="token 无效")


def _ingest_dir() -> Path:
    d = Path(get_data_dir()) / "eda_ingest"
    d.mkdir(parents=True, exist_ok=True)
    return d


@router.post("/ingest")
async def ingest_eda_document(
    body: EdaIngestRequest,
    x_edatoken: str | None = Header(default=None, alias="X-EDA-Token"),
) -> dict:
    """parasite-export 推送端点（工单217 任务一）。"""
    _check_token(x_edatoken)

    project = _safe_project(body.meta.project)
    ts = time.strftime("%Y%m%dT%H%M%S")
    content_hash = hashlib.sha256(body.source.encode("utf-8")).hexdigest()

    # 幂等：同工程 + 同内容 hash → 已存在则跳过落盘（仍发事件，让消费方去重按 hash）
    _ingest_dir().mkdir(parents=True, exist_ok=True)
    target = _ingest_dir() / f"{ts}_{project}.{body.meta.doc_type}.json"
    # 同秒防覆盖：不同内容撞同文件名时加 hash 尾缀（内容不同的两份都要保住）
    if target.exists():
        prev = target.read_text(encoding="utf-8", errors="replace")
        if hashlib.sha256(prev.encode("utf-8")).hexdigest() != content_hash:
            target = _ingest_dir() / f"{ts}_{project}.{content_hash[:8]}.{body.meta.doc_type}.json"
    duplicate = False
    for p in sorted(_ingest_dir().glob(f"*.{body.meta.doc_type}.json")):
        try:
            prev = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if hashlib.sha256(prev.encode("utf-8")).hexdigest() == content_hash:
            duplicate = True
            target = p
            break

    if not duplicate:
        target.write_text(body.source, encoding="utf-8")
        logger.info("[eda_ingest] 落盘 %s (%d B, project=%s)",
                    target.name, len(body.source), project)
    else:
        logger.info("[eda_ingest] 内容 hash 重复，跳过落盘（%s）", target.name)

    event: dict[str, Any] = {
        "project": body.meta.project,
        "page": body.meta.page,
        "doc_type": body.meta.doc_type,
        "path": str(target),
        "content_hash": content_hash,
        "duplicate": duplicate,
        "size": len(body.source),
    }
    get_bus().emit(EVENT_TOPIC, event)
    return {
        "ok": True,
        "stored": not duplicate,
        "path": str(target),
        "content_hash": content_hash,
        "duplicate": duplicate,
    }
