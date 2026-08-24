"""
RAG API 路由 - 材料科研知识检索接口

安全要点:
    - 所有接口受 require_local_auth 保护（仅本地访问）。
    - 文件上传做扩展名白名单 + 路径穿越校验 + 大小限制。
    - 文本直入做长度限制与字段校验。
    - 错误信息统一脱敏：对外只返回"服务器内部错误"，详细原因进日志，不泄露堆栈/路径。
"""
import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field

from apiserver.naga_auth import require_local_auth
from rag import get_rag_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/rag", tags=["RAG"])

# 允许的文件扩展名白名单（防止上传可执行/脚本文件）
ALLOWED_EXTS = {'.pdf', '.docx', '.doc', '.md', '.markdown', '.txt'}
# 最大文件大小（10MB）：防止大文件撑爆解析与存储
MAX_FILE_SIZE = 10 * 1024 * 1024
# 文本直入字符上限：防止超长文本拖垮分块与嵌入
MAX_TEXT_CHARS = 200_000
# Vault 强制重建最小间隔（秒）：防止频繁点击"重建索引"拖垮嵌入引擎
FORCE_MIN_INTERVAL = 60
# 上次强制重建时间戳（模块级，进程内共享）
_last_force_index = 0.0


class QueryRequest(BaseModel):
    """检索请求模型。

    用 pydantic Field 约束边界，越界自动返回 422（客户端错误），
    避免非法 top_k（如 999999）压垮向量库，或负 min_score 造成逻辑混乱。
    """
    query: str = Field(..., min_length=1, max_length=2000, description="检索关键词，非空")
    top_k: int = Field(5, ge=1, le=50, description="返回结果数，1~50")
    tags: list[str] | None = None
    min_score: float = Field(0.6, ge=0.0, le=1.0, description="最低相似度阈值，0~1")
    rerank: bool = True


@router.post("/ingest")
async def ingest_document(
    file: UploadFile = File(...),
    title: str | None = None,
    tags: str | None = None,
    auth: dict = Depends(require_local_auth),
):
    """文档入库

    上传文档并入库到 RAG 知识库。
    流程：类型白名单 → 路径穿越校验 → 大小校验 → 落临时文件 → 解析入库 → 清理临时文件。
    """
    try:
        # HIGH-3修复：文件类型白名单校验
        filename = file.filename or 'unnamed'
        suffix = Path(filename).suffix.lower()

        # 规范化文件名，防止路径穿越（如 ../../etc/passwd）
        safe_name = Path(filename).name  # 仅取文件名，去除路径
        if safe_name != filename:
            logger.warning(f"路径穿越尝试被拦截: {filename}")
            raise HTTPException(status_code=400, detail="文件名包含非法字符")

        if suffix not in ALLOWED_EXTS:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的文件类型: {suffix}。支持: {', '.join(ALLOWED_EXTS)}"
            )

        # 检查文件大小（先读入内存再判断，10MB 内可接受）
        content = await file.read()
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(status_code=400, detail=f"文件过大，最大支持 {MAX_FILE_SIZE // 1024 // 1024}MB")

        # 保存上传的文件到临时目录（用原扩展名，便于 DocumentParser 按类型解析）
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(content)
            temp_path = tmp.name

        try:
            # 解析标签：tags 是前端传来的 JSON 字符串，非法格式应返回 400 而非 500
            tag_list = []
            if tags:
                try:
                    tag_list = json.loads(tags)
                    if not isinstance(tag_list, list):
                        raise ValueError("tags 必须是 JSON 数组")
                except (json.JSONDecodeError, ValueError) as e:
                    # 修复：原实现让 JSON 解析异常落到通用 except 返回 500，应为客户端错误 400
                    logger.warning(f"tags 参数解析失败: {e}; raw={tags!r}")
                    raise HTTPException(
                        status_code=400,
                        detail="tags 必须是合法的 JSON 数组字符串，如 [\\\"锂电池\\\", \\\"正极\\\"]"
                    )

            # 调用 RAG 服务入库
            rag_service = get_rag_service()
            result = rag_service.ingest_document(
                file_path=temp_path,
                title=title or safe_name,
                tags=tag_list,
            )

            if not result.get('success'):
                raise HTTPException(status_code=400, detail=result.get('error', '入库失败'))

            return result
        finally:
            # 清理临时文件：无论入库成功与否都删除，避免磁盘泄漏
            if os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except Exception:
                    # 删除失败仅记录，不影响主流程
                    logger.warning(f"临时文件删除失败: {temp_path}")

    except HTTPException:
        # HTTPException 直接向上抛，不被通用 except 吞掉
        raise
    except Exception as e:
        # 兜底脱敏：不把内部异常细节返回客户端，仅记日志
        logger.error(f"文档入库失败: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.post("/query")
async def query_documents(
    request: QueryRequest,
    auth: dict = Depends(require_local_auth),
):
    """知识检索

    根据查询文本检索相关文档。参数边界由 QueryRequest (pydantic) 强制校验。
    """
    try:
        rag_service = get_rag_service()
        result = rag_service.query(
            query_text=request.query,
            top_k=request.top_k,
            tags=request.tags,
            min_score=request.min_score,
            rerank=request.rerank,
        )
        return result
    except Exception as e:
        # 脱敏：不向客户端暴露内部错误细节
        logger.error(f"检索失败: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.get("/stats")
async def get_stats(auth: dict = Depends(require_local_auth)):
    """获取 RAG 统计信息（文档数、分块数等）。"""
    try:
        rag_service = get_rag_service()
        return rag_service.get_stats()
    except Exception as e:
        logger.error(f"获取统计失败: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.delete("/documents/{doc_id}")
async def delete_document(
    doc_id: str,
    auth: dict = Depends(require_local_auth),
):
    """删除文档

    根据文档 ID 删除文档及其分块。
    """
    try:
        rag_service = get_rag_service()
        result = rag_service.delete_document(doc_id)
        if not result.get('success'):
            # 删除失败通常意味着文档不存在，返回 404
            raise HTTPException(status_code=404, detail="文档不存在")
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除文档失败: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")


# ============= MatChat 一键入库新增接口 =============

class IngestTextRequest(BaseModel):
    """文本直入请求模型。

    用于 MatChat 问答对一键入库：前端把 Q/A 拼成纯文本，复用文档解析链路。
    字段边界校验在 handler 内补充（title/content 非空 + 长度上限）。
    """
    title: str = Field(..., min_length=1, max_length=200, description="文档标题，非空，上限 200 字符")
    content: str = Field(..., min_length=1, description="正文内容，非空")
    tags: list[str] | None = None
    source: str | None = "manual"
    metadata: dict[str, Any] | None = None


@router.post("/document")
async def ingest_document_text(
    req: IngestTextRequest,
    auth: dict = Depends(require_local_auth),
):
    """文本直入知识库（MatChat 问答对一键入库用）

    - 直接拼接 Q/A 文本写入临时 .txt，复用同一 DocumentParser 分块+嵌入链路
    - metadata.source = req.source，前端筛选"来源 MatChat"用

    参数校验：
        - title/content 非空（pydantic min_length 已保证，此处再做 strip 兜底）
        - content 不超过 MAX_TEXT_CHARS，防止超大文本拖垮嵌入
    """
    # 入口诊断日志：确认请求到达路由，记录关键参数（不记录 content 全文，避免日志爆炸）
    logger.info(
        f"[RAG入库] 收到请求: title={req.title!r} | content_len={len(req.content)} | "
        f"source={req.source!r} | tags={req.tags} | metadata_keys={list(req.metadata.keys()) if req.metadata else None}"
    )
    try:
        # 二次校验：pydantic 的 min_length 不拒绝纯空白字符串，这里 strip 后再判
        if not req.title or not req.title.strip():
            raise HTTPException(status_code=400, detail="title 不能为空")
        if not req.content or not req.content.strip():
            raise HTTPException(status_code=400, detail="content 不能为空")
        if len(req.content) > MAX_TEXT_CHARS:
            raise HTTPException(status_code=400, detail=f"内容过长，上限 {MAX_TEXT_CHARS} 字符")

        # 合并 metadata：保证 source 字段一定存在，前端按 source 筛选
        merged_meta = {**(req.metadata or {}), "source": req.source or "manual"}
        # title 截断 200 字符，防止超长标题撑爆展示与索引
        safe_title = req.title.strip()[:200]

        # 写入 UTF-8 临时 .txt：复用文档解析链路（DocumentParser 按 .txt 处理）
        with tempfile.NamedTemporaryFile(
            "w", delete=False, suffix=".txt", encoding="utf-8"
        ) as tmp:
            tmp.write(req.content)
            temp_path = tmp.name

        try:
            rag_service = get_rag_service()
            logger.info(f"[RAG入库] 调用 rag_service.ingest_document: temp_path={temp_path}")
            result = rag_service.ingest_document(
                file_path=temp_path,
                title=safe_title,
                tags=req.tags or [],
                metadata=merged_meta,
            )
            logger.info(f"[RAG入库] rag_service 返回: success={result.get('success')} | error={result.get('error')}")
            if not result.get("success"):
                # 记录详细错误到日志（detail 字段包含 db_path/线程/pid 等诊断信息）
                detail = result.get("detail")
                logger.error(f"[RAG入库] 入库失败: error={result.get('error')} | detail={detail}")
                # 对外只返回通用 error，不暴露 detail（避免泄露路径/进程信息）
                raise HTTPException(status_code=400, detail=result.get("error", "入库失败"))
            # 回填 source 到返回的 doc，便于前端直接展示来源
            doc = result.get("doc") or {}
            doc["source"] = req.source
            result["doc"] = doc
            logger.info(f"[RAG入库] 入库成功: doc_id={result.get('doc_id')} | chunks={result.get('chunk_count')}")
            return result
        finally:
            # 清理临时文件：失败也兜底删除，避免磁盘泄漏
            if os.path.exists(temp_path):
                try:
                    os.unlink(temp_path)
                except Exception:
                    pass
    except HTTPException:
        raise
    except Exception as e:
        # 脱敏：详细堆栈进日志，对外仅返回通用错误
        logger.exception(f"[RAG入库] 文本入库异常: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")


@router.get("/documents")
async def list_documents(
    keyword: str | None = None,
    source: str | None = None,
    limit: int = 50,
    offset: int = 0,
    auth: dict = Depends(require_local_auth),
):
    """文档列表 + 关键词/来源筛选。

    limit/offset 做边界钳制：limit 1~500，offset >=0，防止越界查询。
    """
    try:
        # 钳制分页参数到合理区间，防止 limit=0 或超大值
        limit = max(1, min(500, int(limit)))
        offset = max(0, int(offset))
        rag_service = get_rag_service()
        # 优雅降级：旧版 rag_service 可能未实现 list_documents
        if not hasattr(rag_service, "list_documents"):
            return {"success": False, "error": "list_documents 未实现", "documents": [], "total": 0}
        data = rag_service.list_documents(keyword=keyword, source=source, limit=limit, offset=offset)
        return {
            "success": True,
            "documents": data.get("docs", []),
            "total": data.get("total", 0),
            "error": data.get("error"),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"文档列表失败: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")


# ============= Vault 索引接口 =============


@router.get("/vault/status")
async def vault_status(auth: dict = Depends(require_local_auth)):
    """获取 Vault 索引状态。

    - 通过公开方法 get_indexed_count() 读取已索引文件数，不直接触碰内部状态
    - 路径脱敏：仅返回文件名（.name）与相对计数，不暴露完整绝对路径
    """
    try:
        from rag.vault_indexer import get_vault_indexer

        indexer = get_vault_indexer()
        files = indexer.scan_files()
        return {
            "success": True,
            "vault_dir": indexer.vault_dir.name,
            "indexed_count": indexer.get_indexed_count(),
            "total_files": len(files),
            "sample_files": [f[0].name for f in files[:20]],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取 Vault 状态失败: {e}")
        raise HTTPException(status_code=500, detail="服务器内部错误")
