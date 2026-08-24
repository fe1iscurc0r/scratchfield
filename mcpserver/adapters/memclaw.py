"""MemClaw MCP 适配层（跨 Agent 共享记忆总线）。

上游 vendor: vendor/top5/caura-memclaw (Apache-2.0)
MCP 入口: core-api/src/core_api/mcp_server.py — FastMCP，暴露 12 个 MCP 工具（write/list/recall/evolve/keystones/insights/stats 等）
standalone 支持：IS_STANDALONE=true + providers/sqlite_backend.py → 无需 PostgreSQL+pgvector+Redis

适配策略：
- 默认启用（ENABLE_ADAPTER_MEMCLAW=1）
- healthcheck: STANDALONE 路径可达（SqliteBackend 可导入）
- register: 合并 core_api.mcp_server FastMCP 工具；失败退化到 memclaw_write / memclaw_list 外壳
- 注：vendor Python 源码用了 PEP 695 泛型语法（async def _call_gated[T]），需 Python 3.12+ 才能导入 SqliteBackend；
  在 3.11 下 register 会退化为"仅登记能力卡片，不注册工具"，诚实登记 description
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from mcpserver.adapters._common import (
    inject_vendor_path,
    merge_tools,
    register_capability_safe,
)

logger = logging.getLogger(__name__)

# 模块级 CAPABILITY（正常版描述；退化时 register 会覆盖 description 说明未注册工具原因）
CAPABILITY: dict = {
    "name": "memclaw",
    "displayName": "跨 Agent 共享记忆总线",
    "description": "多 Agent 共享记忆总线（12 个 MCP 工具：write/list/recall/evolve/keystones/insights/stats 等）。桌面端走 SQLite standalone 路径，云服部署可选 PostgreSQL+pgvector+Redis。",
    "version": "2.27.0",
    "license": "Apache-2.0",
    "vendor": "caura-memclaw",
    "deployment_mode": "sqlite_standalone",
    "security_notice": "SQLite standalone 模式：本地存储无加密/无 ACL，多用户场景需隔离 db 文件路径（MEMCLAW_DB_PATH）",
    "_from_adapter": "memclaw",
}


def healthcheck() -> bool:
    """MemClaw standalone 健康检查。"""
    # memclaw 需要注入 3 个路径：根目录 + core-api/src + common
    inject_vendor_path("caura-memclaw", "core-api/src", "common")
    # 提前设置 env，让 core_api.config.settings 在 import 时就是 standalone 路径
    if not os.environ.get("IS_STANDALONE"):
        os.environ["IS_STANDALONE"] = "true"
    if not os.environ.get("ENVIRONMENT"):
        os.environ["ENVIRONMENT"] = "development"
    if not os.environ.get("MEMCLAW_DB_PATH"):
        try:
            from system.config import get_data_dir
            db_dir = get_data_dir() / "memclaw"
            db_dir.mkdir(parents=True, exist_ok=True)
            os.environ["MEMCLAW_DB_PATH"] = str(db_dir / "memclaw.db")
        except Exception as e:
            logger.debug("[adapter:memclaw] system.config 不可用，用默认 ~/.memclaw: %s", e)
    # LLM key：不给也能运行 write/list，但 enrich/embed 降级
    api_key = (
        os.environ.get("MEMCLAW_OPENAI_API_KEY", "").strip()
        or os.environ.get("OPENAI_API_KEY", "").strip()
    )
    if not api_key:
        logger.info(
            "[adapter:memclaw] 未配置 MEMCLAW_OPENAI_API_KEY/OPENAI_API_KEY，"
            "将以纯存储模式运行（不做 enrich/embed/知识图谱，write/list 正常）。"
        )
    try:
        from core_api.providers.sqlite_backend import SqliteBackend  # noqa: F401
    except Exception as e:
        logger.warning("[adapter:memclaw] 导入 SqliteBackend 失败（standalone 路径不可用）: %s", e)
        return False
    return True


def register(mcp_server: Any, mcp_registry: Any = None) -> None:
    """把 MemClaw MCP 工具合并到主 mcp_server。

    core_api/mcp_server.py 暴露 FastMCP 实例的工具；失败退化到外壳。
    """
    inject_vendor_path("caura-memclaw", "core-api/src", "common")
    try:
        from core_api.standalone import init_standalone  # type: ignore
        init_standalone()  # 注入 tenant_id
    except Exception as e:
        logger.warning("[adapter:memclaw] init_standalone 失败: %s，仍尝试注册", e)

    merged = 0
    try:
        from core_api import mcp_server as mc_mcp_mod  # type: ignore
        merged += merge_tools(mc_mcp_mod, mcp_server, prefix="memclaw")
    except Exception as e:
        logger.warning("[adapter:memclaw] mcp tools 合并失败，退化为外壳工具: %s", e)

    if not merged:
        logger.info("[adapter:memclaw] 未直接合并 tools，暴露 memclaw_write / memclaw_list 外壳")
        try:
            from core_api.providers.sqlite_backend import SqliteBackend  # type: ignore
            from core_api.standalone import get_standalone_tenant_id  # type: ignore
        except Exception as e:
            logger.warning("[adapter:memclaw] SqliteBackend 导入失败（如 vendor PEP 695 语法需 Python 3.12+），外壳工具跳过: %s", e)
            degraded_cap = {
                **CAPABILITY,
                "description": (
                    "vendor 导入失败（Python 版本不兼容或缺依赖），当前未注册工具。"
                    "升级到 Python 3.12+ 或补全 core_api/common 依赖后可启用。"
                ),
                "security_notice": "失败模式：仅能力登记可见，不暴露工具；无数据写入。",
            }
            register_capability_safe(mcp_registry, degraded_cap)
            return

        _backend: SqliteBackend | None = None

        def _get_backend() -> SqliteBackend:
            """adapter 内部工厂：惰性创建 SqliteBackend 实例（和 vendor 私有方法 _get_db 同名易混淆，故改名）"""
            nonlocal _backend
            if _backend is None:
                path = os.path.expanduser(os.environ.get("MEMCLAW_DB_PATH", "~/.memclaw/memclaw.db"))
                _backend = SqliteBackend(db_path=path)
            return _backend

        async def memclaw_write(content: str, metadata: dict | None = None) -> dict:
            """写入一条记忆到 MemClaw（SQLite standalone 模式）。"""
            db = _get_backend()
            tid = get_standalone_tenant_id()
            try:
                mid = await db.store(tenant_id=tid, content=content, metadata=metadata or {})
                return {"ok": True, "memory_id": mid}
            except Exception as e:
                return {"ok": False, "error": str(e)}

        async def memclaw_list(limit: int = 20, keyword: str = "") -> dict:
            """列出最近的记忆（SQLite standalone 模式，非向量版）。

            vendor SqliteBackend 未暴露 public list 方法，这里用 getattr 探测：
            ① 优先探测未来可能新增的 public list_memories API
            ② 退化到 vendor 私有 _get_db + 裸 SQL（参数化 ? 占位符，无注入）
            ③ vendor 升级删除/改名 _get_db 时 graceful 返回 error，不抛 AttributeError
            """
            if limit < 1:
                return {"ok": False, "error": f"limit 必须为正整数，收到 {limit}"}
            db = _get_backend()
            tid = get_standalone_tenant_id()
            try:
                # ① 优先探测 public API
                list_fn = getattr(db, "list_memories", None)
                if callable(list_fn):
                    rows = await list_fn(tenant_id=tid, limit=limit, keyword=keyword)
                    return {"ok": True, "memories": rows}
                # ② 退化到 vendor 私有 _get_db（getattr 探测，签名变了不抛 AttributeError）
                get_conn = getattr(db, "_get_db", None)
                if not callable(get_conn):
                    return {"ok": False, "error": "vendor SqliteBackend 无 _get_db 方法，可能已升级 API；仅能力卡片可用"}
                conn = await get_conn()
                cursor = await conn.execute(
                    "SELECT id, content, metadata, created_at FROM memories "
                    "WHERE tenant_id = ? AND deleted_at IS NULL "
                    "ORDER BY created_at DESC LIMIT ?",
                    (tid, int(limit)),
                )
                rows = await cursor.fetchall()
                data = []
                for r in rows:
                    d = dict(r)
                    meta_raw = d.get("metadata")
                    try:
                        d["metadata"] = json.loads(meta_raw) if meta_raw else None
                    except Exception:
                        d["metadata"] = meta_raw
                    if keyword and keyword.lower() not in (d.get("content") or "").lower():
                        continue
                    data.append(d)
                return {"ok": True, "memories": data}
            except Exception as e:
                return {"ok": False, "error": str(e)}

        if hasattr(mcp_server, "add_tool"):
            mcp_server.add_tool(memclaw_write, name="memclaw_write")
            mcp_server.add_tool(memclaw_list, name="memclaw_list")

    register_capability_safe(mcp_registry, CAPABILITY)
