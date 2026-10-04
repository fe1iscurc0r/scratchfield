"""领域包路由 — /api/domains。

卷162 交付。暴露 `domains/` 下所有领域包的声明式配置，供前端：
- 动态注册领域路由（替代 main.ts 中的硬编码）
- 渲染领域专属 ELN 表单字段
- 展示来源徽章与版权说明
- 领域切换器

本模块只做只读暴露，不引入任何核心领域分支（无 `if domain == "law"`）。
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from ..domain_pack import DEFAULT_PACK_NAME, get_pack, list_packs, reload_packs
from ..naga_auth import require_local_auth

router = APIRouter(prefix="/api/domains", tags=["domains"])
logger = logging.getLogger(__name__)


@router.get("")
async def get_domains(
    refresh: bool = Query(False, description="是否强制重扫 domains/ 目录"),
    _auth: Annotated[dict | None, Depends(require_local_auth)] = None,
) -> dict:
    """返回全部领域包及其 schema。

    加载失败的包不会出现在结果中（加载器已降级为 warning）。
    `default` 包缺失时会带 `warnings` 字段提示，但不影响接口成功返回。
    """
    if refresh:
        reload_packs()

    packs = list_packs()
    names = [p.name for p in packs]

    warnings: list[str] = []
    if DEFAULT_PACK_NAME not in names:
        warnings.append(
            f"默认领域包 {DEFAULT_PACK_NAME!r} 缺失，前端将回退到核心路由"
        )
    if not packs:
        warnings.append("未发现任何领域包，domains/ 目录可能缺失或全部加载失败")

    return {
        "ok": True,
        "default": DEFAULT_PACK_NAME,
        "domains": [p.to_dict() for p in packs],
        **({"warnings": warnings} if warnings else {}),
    }


@router.get("/{name}")
async def get_domain(
    name: str,
    _auth: Annotated[dict | None, Depends(require_local_auth)] = None,
) -> dict:
    """返回单个领域包 schema。"""
    pack = get_pack(name)
    if pack is None:
        raise HTTPException(status_code=404, detail=f"未找到领域包: {name}")
    return {"ok": True, "domain": pack.to_dict()}
