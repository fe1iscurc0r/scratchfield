"""extensions_parts —— 原 extensions.py 按域拆分后的聚合入口（卷190-A1）。

路由路径逐字不变：各子 router 自持完整路径（/travel/...、/mcp/...），此处只做
``include_router`` 聚合，不加重写前缀。

**注意**：`common` 不含任何路由，故意**不参与** include —— 且它不定义 `router`，
否则 `from .common import *` 会把各子模块自建的 router 覆盖掉（实测会导致
9 个子模块共享同一 router、路由被重复注册 9 次）。

薄壳兼容：把各域全部公共名（**含下划线 helper**）提到包级，使
``from apiserver.routes.extensions import X`` 的既有调用方与测试 patch 目标继续可用。

分域依据见 ``docs/extensions-域边界勘察-2026-10-02.md``。
"""
from fastapi import APIRouter

from . import common, market, mcp, memory, openclaw, search, skills, travel, upload

router = APIRouter()
router.include_router(openclaw.router)
router.include_router(mcp.router)
router.include_router(skills.router)
router.include_router(market.router)
router.include_router(upload.router)
router.include_router(travel.router)
router.include_router(memory.router)
router.include_router(search.router)

# ---- re-export：包级可见（薄壳兼容）----
# 用动态 __all__：`import *` 默认不导出下划线名，而原巨石里 `_run_command` /
# `_write_skill_file_to_dir` 等下划线 helper 是对外可见的（既有调用方 + 测试 patch 目标），
# 故把子模块的全部公共名（含下划线）都列入 __all__，保证兼容面与原文件一致。
_SUBMODULES = (common, openclaw, mcp, skills, market, upload, travel, memory, search)
for _m in _SUBMODULES:
    for _name in dir(_m):
        if _name.startswith("__") or _name == "router":
            continue
        globals().setdefault(_name, getattr(_m, _name))

__all__ = ["router"] + sorted(
    n for m in _SUBMODULES for n in dir(m)
    if not n.startswith("__") and n != "router"
)

# ruff: noqa: F405  # 薄壳模式：星号聚合导入的公共名（导出面由 tools/verify_export_parity.py 钉住）
