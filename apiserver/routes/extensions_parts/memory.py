"""记忆五元组与图谱（卷190-A1：从 extensions.py 纯搬移）。"""
"""OpenClaw 技能市场、MCP 服务、技能导入、文件上传、旅行、记忆、搜索代理路由"""

import html
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from datetime import datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import URLError
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

import yaml
from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from agentserver.openclaw.state_paths import get_openclaw_config_path, get_openclaw_state_dir
from apiserver import naga_auth
from apiserver.api_server import FileUploadResponse, _call_agentserver
from apiserver.mcp_assembly import (
    KNOWN_FAMILIES,
    KNOWN_TIERS,
)
from apiserver.mcp_assembly import (
    check_requirements as _assembly_check_requirements,
)
from apiserver.mcp_assembly import (
    decide_enabled as _assembly_decide_enabled,
)
from apiserver.mcp_assembly import (
    load_policy as _assembly_load_policy,
)
from apiserver.mcp_assembly import (
    set_agent_override as _assembly_set_override,
)
from apiserver.mcp_assembly import (
    set_policy as _assembly_set_policy,
)
from apiserver.telemetry import emit_telemetry
from system.config import get_config, get_data_dir

from .common import *  # noqa: F401,F403

router = APIRouter()



def _normalize_memory_quintuple_item(item: Any) -> dict[str, str] | None:
    if isinstance(item, dict):
        if isinstance(item.get("quintuple"), (list, tuple)) and len(item["quintuple"]) >= 5:
            q = item["quintuple"]
            return {
                "subject": str(q[0] or ""),
                "subject_type": str(q[1] or ""),
                "predicate": str(q[2] or ""),
                "object": str(q[3] or ""),
                "object_type": str(q[4] or ""),
            }
        return {
            "subject": str(item.get("subject") or ""),
            "subject_type": str(item.get("subject_type") or item.get("subjectType") or ""),
            "predicate": str(item.get("predicate") or item.get("relation") or ""),
            "object": str(item.get("object") or ""),
            "object_type": str(item.get("object_type") or item.get("objectType") or ""),
        }
    if isinstance(item, (list, tuple)) and len(item) >= 5:
        return {
            "subject": str(item[0] or ""),
            "subject_type": str(item[1] or ""),
            "predicate": str(item[2] or ""),
            "object": str(item[3] or ""),
            "object_type": str(item[4] or ""),
        }
    return None



# ============ 记忆 ============


@router.get("/memory/stats")
async def get_memory_stats():
    """获取记忆统计信息"""

    try:
        # 优先使用远程 NagaMemory 服务
        from summer_memory.memory_client import get_remote_memory_client, should_prefer_remote_memory

        remote = get_remote_memory_client()
        if remote is not None:
            try:
                stats = await remote.get_stats()
                if stats.get("success") is not False:
                    return {"status": "success", "memory_stats": stats}
                logger.warning(f"远程记忆统计获取失败: {stats.get('error')}")
            except Exception as e:
                logger.warning(f"远程记忆统计异常: {e}")

        if should_prefer_remote_memory():
            return {
                "status": "success",
                "memory_stats": {"enabled": False, "message": "云端记忆服务暂不可用"},
            }

        # 回退到本地 summer_memory
        try:
            from summer_memory.memory_manager import memory_manager

            if memory_manager and memory_manager.enabled:
                stats = memory_manager.get_memory_stats()
                return {"status": "success", "memory_stats": stats}
            else:
                return {"status": "success", "memory_stats": {"enabled": False, "message": "记忆系统未启用"}}
        except ImportError:
            return {"status": "success", "memory_stats": {"enabled": False, "message": "记忆系统模块未找到"}}
    except Exception as e:
        logger.error(f"获取记忆统计错误: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="获取记忆统计失败")



def _quintuple_degree(rows: list[dict]) -> dict[str, int]:
    """算每个实体（subject/object 名）的连接度数（卷148）。

    度数 = 以该实体为 subject 或 object 的五元组条数。用于：
      - 前端分区布局的 hub 识别（度数 Top-N）
      - graph/summary 概览
    设计为纯函数，便于单测；O(n) 一趟扫描。
    """
    deg: dict[str, int] = {}
    for q in rows:
        for key in ("subject", "object"):
            name = q.get(key)
            if name:
                deg[name] = deg.get(name, 0) + 1
    return deg



def _apply_quintuple_filters(
    rows: list[dict],
    *,
    entity_type: str = "",
    q: str = "",
    order_by: str = "",
) -> list[dict]:
    """对五元组列表做过滤 + 排序（卷148）。不传参时原样返回（向后兼容）。

    - entity_type: 命中 subject_type 或 object_type（大小写不敏感，子串匹配）
    - q: 服务端搜索，命中 subject/predicate/object 任一字段（大小写不敏感）
    - order_by: 'degree' 按两端实体度数和倒序；'time' 保持数据源顺序（无时间字段时
      退化为原序）；空串不排序
    """
    out = rows
    if entity_type:
        needle = entity_type.strip().lower()
        out = [
            r for r in out
            if needle in str(r.get("subject_type", "")).lower()
            or needle in str(r.get("object_type", "")).lower()
        ]
    if q:
        needle = q.strip().lower()
        out = [
            r for r in out
            if needle in str(r.get("subject", "")).lower()
            or needle in str(r.get("predicate", "")).lower()
            or needle in str(r.get("object", "")).lower()
        ]
    if order_by == "degree":
        deg = _quintuple_degree(rows)
        out = sorted(
            out,
            key=lambda r: deg.get(r.get("subject", ""), 0) + deg.get(r.get("object", ""), 0),
            reverse=True,
        )
    return out



async def _fetch_all_quintuples() -> list[dict]:
    """拉取全量五元组（远程优先 + 本地合并去重）——卷148 从端点抽出复用。

    行为与原 get_quintuples 内联逻辑完全一致（含 should_prefer_remote_memory 分支），
    仅做提取以便 /memory/quintuples 与 /memory/graph/summary 两个端点共用同一份取数
    逻辑，避免各写一套导致数据源漂移。必须 async：远程客户端是 awaitable。
    """
    from summer_memory.memory_client import get_remote_memory_client, should_prefer_remote_memory

    remote = get_remote_memory_client()
    remote_quintuples: list[dict] = []
    if remote is not None:
        try:
            result = await remote.get_quintuples(limit=500)
            if result.get("success") is not False:
                quintuples_raw = result.get("quintuples") or result.get("results") or result.get("data") or []
                for q in quintuples_raw:
                    normalized = _normalize_memory_quintuple_item(q)
                    if normalized:
                        remote_quintuples.append(normalized)
            else:
                logger.warning(f"远程五元组获取失败: {result.get('error')}")
        except Exception as e:
            logger.warning(f"远程五元组获取异常: {e}")

    if should_prefer_remote_memory():
        return remote_quintuples

    local_quintuples: list[dict] = []
    try:
        from summer_memory.quintuple_graph import get_all_quintuples
        local_data = get_all_quintuples()  # returns set[tuple]
        local_quintuples = [
            {"subject": q[0], "subject_type": q[1], "predicate": q[2], "object": q[3], "object_type": q[4]}
            for q in local_data
        ]
    except ImportError:
        pass

    seen = set()
    merged = []
    for q in remote_quintuples + local_quintuples:
        key = (q["subject"], q["predicate"], q["object"])
        if key not in seen:
            seen.add(key)
            merged.append(q)
    return merged



@router.get("/memory/quintuples")
async def get_quintuples(
    offset: int = Query(0, ge=0, description="分页起点（卷148）"),
    limit: int = Query(0, ge=0, description="返回条数上限，0=不分页全量（兼容旧行为）"),
    entity_type: str = Query("", description="按实体类型过滤，命中 subject_type/object_type"),
    q: str = Query("", description="服务端搜索，命中 subject/predicate/object"),
    order_by: str = Query("", description="排序：degree=按实体度数倒序；time=原序"),
    with_degree: bool = Query(False, description="是否附带每条五元组两端实体的度数"),
):
    """获取五元组（用于知识图谱可视化）。

    卷148 增量：新增 offset/limit/entity_type/q/order_by/with_degree 查询参数。
    **兼容性**：不传任何新参数时行为与旧版完全一致（全量返回，不做分页/过滤），
    以防旧调用（MindView 老版本、第三方脚本）炸掉。
    """
    try:
        merged = await _fetch_all_quintuples()

        # 过滤 + 排序
        filtered = _apply_quintuple_filters(merged, entity_type=entity_type, q=q, order_by=order_by)

        # 度数下沉：后端算好，前端不再自己数（卷148 任务A.3）
        if with_degree:
            deg = _quintuple_degree(merged)
            filtered = [
                {**r, "subject_degree": deg.get(r.get("subject", ""), 0),
                 "object_degree": deg.get(r.get("object", ""), 0)}
                for r in filtered
            ]

        total = len(filtered)

        # 分页：limit=0 表示不分页（旧行为）
        if limit > 0:
            page = filtered[offset:offset + limit]
        else:
            page = filtered[offset:] if offset else filtered

        return {
            "status": "success",
            "quintuples": page,
            "count": len(page),
            "total": total,
            "offset": offset,
            "limit": limit,
            "has_more": bool(limit > 0 and offset + limit < total),
        }
    except ImportError:
        return {"status": "success", "quintuples": [], "count": 0, "total": 0, "message": "记忆系统模块未找到"}
    except Exception as e:
        logger.error(f"获取五元组错误: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="获取五元组失败")



@router.get("/memory/graph/summary")
async def graph_summary(
    top_n: int = Query(20, ge=1, le=200, description="返回度数 Top-N 实体数"),
):
    """图谱概览聚合（卷148 任务A.2）——给前端分区布局与概览面板用。

    返回：
      - total_quintuples: 五元组总数
      - total_entities: 去重实体数
      - top_entities: 度数 Top-N [{name, degree}]（前端 hub 识别，不用拉全量）
      - subject_types / object_types: 按类型分组计数（前端分区扇区大小 ∝ 该类型实体数）
      - predicate_distribution: 关系类型分布（前端边捆绑粗细参考）

    设计意图：MindView 进图时先拉 summary（小响应）画骨架，
    再按需分页拉五元组填充细节，避免一上来 500 节点全塞。
    """
    try:
        rows = await _fetch_all_quintuples()
        deg = _quintuple_degree(rows)

        top_entities = [
            {"name": name, "degree": d}
            for name, d in sorted(deg.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
        ]

        def _count_by(field: str) -> dict[str, int]:
            acc: dict[str, int] = {}
            for r in rows:
                v = str(r.get(field) or "未分类")
                acc[v] = acc.get(v, 0) + 1
            return dict(sorted(acc.items(), key=lambda kv: kv[1], reverse=True))

        return {
            "status": "success",
            "total_quintuples": len(rows),
            "total_entities": len(deg),
            "top_entities": top_entities,
            "subject_types": _count_by("subject_type"),
            "object_types": _count_by("object_type"),
            "predicate_distribution": _count_by("predicate"),
        }
    except ImportError:
        return {
            "status": "success", "total_quintuples": 0, "total_entities": 0,
            "top_entities": [], "subject_types": {}, "object_types": {},
            "predicate_distribution": {}, "message": "记忆系统模块未找到",
        }
    except Exception as e:
        logger.error(f"图谱概览聚合错误: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="图谱概览聚合失败")



@router.get("/memory/quintuples/search")
async def search_quintuples(keywords: str = ""):
    """按关键词搜索五元组"""
    try:
        keyword_list = [k.strip() for k in keywords.split(",") if k.strip()]
        if not keyword_list:
            raise HTTPException(status_code=400, detail="请提供搜索关键词")

        # 优先使用远程 NagaMemory 服务
        from summer_memory.memory_client import get_remote_memory_client, should_prefer_remote_memory

        remote = get_remote_memory_client()
        if remote is not None:
            try:
                result = await remote.query_by_keywords(keyword_list)
                if result.get("success") is not False:
                    quintuples_raw = result.get("quintuples") or result.get("results") or result.get("data") or []
                    quintuples = []
                    for q in quintuples_raw:
                        normalized = _normalize_memory_quintuple_item(q)
                        if normalized:
                            quintuples.append(normalized)
                    return {"status": "success", "quintuples": quintuples, "count": len(quintuples)}
                else:
                    logger.warning(f"远程五元组搜索失败: {result.get('error')}")
            except Exception as e:
                logger.warning(f"远程五元组搜索异常: {e}")

        if should_prefer_remote_memory():
            return {
                "status": "success",
                "quintuples": [],
                "count": 0,
                "message": "当前为云端记忆模式，远程搜索暂不可用，未再回退本地知识图谱",
            }

        # 回退到本地 summer_memory
        from summer_memory.quintuple_graph import query_graph_by_keywords

        results = query_graph_by_keywords(keyword_list)
        return {
            "status": "success",
            "quintuples": [
                {"subject": q[0], "subject_type": q[1], "predicate": q[2], "object": q[3], "object_type": q[4]}
                for q in results
            ],
            "count": len(results),
        }
    except ImportError:
        return {"status": "success", "quintuples": [], "count": 0, "message": "记忆系统模块未找到"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"搜索五元组错误: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="搜索五元组失败")

# ruff: noqa: F405  # 薄壳模式：星号聚合导入的公共名（导出面由 tools/verify_export_parity.py 钉住）
