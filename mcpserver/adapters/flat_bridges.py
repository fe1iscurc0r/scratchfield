"""平铺适配器的 manifest 桥（通用实现）。

背景：`mcpserver/adapters/*.py` 这批平铺适配器走 FastMCP `add_tool` 路径，而
Lumo 后端不创建 FastMCP 实例、`register_adapters()` 运行期也无调用点（git 全历史
只有 tests 里 dry-run 调过）——所以它们在运行期是死代码，模型既看不到也调不到。
本模块把它们按**真正生效的 manifest 约定**重挂（同 pdf2md_adapter / semantic_web）。

关键设计：**不抄适配器逻辑**。平铺适配器的工具函数是 `register(mcp_server, ...)` 里
创建的闭包，我们用一个假 server 捕获 `add_tool(fn, name=...)` 传出的函数对象，直接
调用原实现——上游修了 bug、换了实现，这里自动跟着变。
"""
from __future__ import annotations

import asyncio
import importlib
import inspect
import json
import logging
import os
import struct
import threading
from typing import Any, Callable

logger = logging.getLogger(__name__)

# 默认单工具调用硬超时（秒）。阻塞型重活（反编译加载 1.3B 模型）由子类放宽。
TOOL_TIMEOUT_S = 120.0


def _unpack_vector(blob: Any) -> list[float]:
    """把 float32 BLOB 反解成向量（与 vendor `_pack_embedding` 的 struct 打包格式对齐）。"""
    if not isinstance(blob, (bytes, bytearray)):
        return []
    return list(struct.unpack(f"{len(blob) // 4}f", bytes(blob[: len(blob) // 4 * 4])))


class _ToolCapture:
    """假 server：捕获 register() 传出的工具函数（FastMCP add_tool 的最小接口）。"""

    def __init__(self) -> None:
        self.tools: dict[str, Callable[..., Any]] = {}

    def add_tool(self, fn: Callable[..., Any], name: str | None = None, **_kwargs: Any) -> None:
        self.tools[name or getattr(fn, "__name__", "tool")] = fn


class FlatAdapterBridge:
    """把平铺适配器包装成 manifest 桥：handle_handoff 分发到原工具函数。

    子类只需给 `adapter_name`（= mcpserver.adapters.<名> 模块名）与 `name`（= manifest 服务名）。
    """

    adapter_name: str = ""
    name: str = ""
    tool_timeout_s: float = TOOL_TIMEOUT_S

    _tools: dict[str, Callable[..., Any]] | None = None
    _capture_error: str = ""

    # ------------------------------------------------------------------ 工具捕获
    @classmethod
    def _status_tools(cls) -> dict[str, Callable[..., Any]]:
        """子类可补充/覆盖工具（例如依赖缺失时只给一个诚实的 status）。"""
        return {}

    @classmethod
    def _load_tools(cls) -> dict[str, Callable[..., Any]]:
        if cls._tools is not None:
            return cls._tools
        tools: dict[str, Callable[..., Any]] = {}
        try:
            mod = importlib.import_module(f"mcpserver.adapters.{cls.adapter_name}")
            capture = _ToolCapture()
            # mcp_registry=None：能力卡片登记在 register_capability_safe 里按需降级
            mod.register(capture, mcp_registry=None)
            tools.update(capture.tools)
        except Exception as e:  # noqa: BLE001 - 依赖缺失不让整个服务挂掉
            cls._capture_error = f"{type(e).__name__}: {e}"
            logger.warning("[flat_bridge:%s] 工具捕获失败: %s", cls.adapter_name, e)
        tools.update(cls._status_tools())
        cls._tools = tools
        logger.info("[flat_bridge:%s] 捕获工具 %d 个: %s", cls.adapter_name, len(tools), ", ".join(sorted(tools)))
        return tools

    # ------------------------------------------------------------------ 参数与调用
    @staticmethod
    def _arguments_from(task: dict) -> dict[str, Any]:
        """参数平铺在 task 顶层（registry 约定）；兼容嵌套 params/arguments（stdio 直连）。"""
        if isinstance(task.get("params"), dict):
            return task["params"]
        if isinstance(task.get("arguments"), dict):
            return task["arguments"]
        return {
            k: v
            for k, v in task.items()
            if k not in ("tool_name", "agentType", "service_name", "_tool_call_id")
        }

    async def _call_tool(self, fn: Callable[..., Any], arguments: dict[str, Any]) -> Any:
        if inspect.iscoroutinefunction(fn):
            return await fn(**arguments)
        return await asyncio.to_thread(lambda: fn(**arguments))

    @staticmethod
    def _dump(payload: dict[str, Any]) -> str:
        return json.dumps(payload, ensure_ascii=False, default=str)

    # ------------------------------------------------------------------ 分发入口
    async def handle_handoff(self, task: dict) -> str:
        tool_name = str(task.get("tool_name") or "").strip()
        if not tool_name:
            return self._dump({"status": "error", "message": "缺少 tool_name", "data": {}})

        tools = self._load_tools()
        fn = tools.get(tool_name)
        if fn is None:
            detail = f"（工具捕获失败：{self._capture_error}）" if self._capture_error else ""
            return self._dump({
                "status": "error",
                "message": f"未知工具 {tool_name}，可用: {', '.join(sorted(tools)) or '无'}{detail}",
                "data": {},
            })

        arguments = self._arguments_from(task)
        try:
            data = await asyncio.wait_for(self._call_tool(fn, arguments), timeout=self.tool_timeout_s)
        except asyncio.TimeoutError:
            return self._dump({
                "status": "error",
                "message": f"工具 {tool_name} 超时（>{self.tool_timeout_s:.0f}s）",
                "data": {},
            })
        except TypeError as e:
            return self._dump({"status": "error", "message": f"参数错误: {e}", "data": {}})
        except Exception as e:  # noqa: BLE001
            return self._dump({"status": "error", "message": f"{type(e).__name__}: {e}", "data": {}})

        # 工具返回 dict：ok=False 视为业务失败（与 pdf2md/headroom 约定一致）
        if isinstance(data, dict) and data.get("ok") is False:
            return self._dump({
                "status": "error",
                "message": str(data.get("error") or data.get("message") or "工具返回 ok=False"),
                "data": data,
            })
        return self._dump({"status": "success", "message": "ok", "data": data})


# ===========================================================================
# 各适配器桥（子类只声明 adapter_name / name）
# ===========================================================================


class VulnclawBridge(FlatAdapterBridge):
    """渗透编排。工具缺 OPENAI key 时会以明确报错返回，不静默。"""

    adapter_name = "vulnclaw"
    name = "vulnclaw"


class MemclawBridge(FlatAdapterBridge):
    """跨 Agent 共享记忆总线（纯存储模式，写/列可用）。

    为什么不复用平铺模块的 register()：它先尝试合并上游 `core_api.mcp_server` 的
    FastMCP 工具，而 **vendor 快照缺 `core_api/clients/` 整个包**
    （`core_api/mcp_server.py:31` 依赖 core_api.clients.storage_client）——该导入在
    半途失败后会留下副作用，实测把整条工具调用拖到分钟级超时（解释器升级到 3.12 后
    PEP 695 语法已可解析，仍复现）。
    所以本桥不再调 register()，直接用**已验证可用的** SqliteBackend 实现 write/list
    （实测 store() 秒级返回 UUID），不触碰那条坏掉的合并路径。
    未配 MEMCLAW_OPENAI_API_KEY 时不做 enrich/embed/知识图谱，写/列正常。
    """

    adapter_name = "memclaw"
    name = "memclaw"

    _MEMCLAW_BACKEND: Any = None
    _MEMCLAW_TENANT: str | None = None
    _MEMCLAW_EMBEDDER: Any = None
    _MEMCLAW_LOCK = threading.Lock()
    _tool_source: str = ""

    @classmethod
    def _inject(cls) -> None:
        from mcpserver.adapters._common import inject_vendor_path

        inject_vendor_path("caura-memclaw", "core-api/src", "common")

    @classmethod
    def _backend(cls) -> Any:
        """惰性创建 SqliteBackend（standalone 路径）。"""
        if cls._MEMCLAW_BACKEND is not None:
            return cls._MEMCLAW_BACKEND
        with cls._MEMCLAW_LOCK:
            if cls._MEMCLAW_BACKEND is None:
                cls._inject()
                from core_api.providers.sqlite_backend import SqliteBackend  # type: ignore
                from core_api.standalone import init_standalone  # type: ignore

                init_standalone()
                path = os.path.expanduser(os.environ.get("MEMCLAW_DB_PATH", "~/.memclaw/memclaw.db"))
                cls._MEMCLAW_BACKEND = SqliteBackend(db_path=path)
        return cls._MEMCLAW_BACKEND

    @classmethod
    def _tenant(cls) -> str:
        if cls._MEMCLAW_TENANT is None:
            from core_api.standalone import get_standalone_tenant_id  # type: ignore

            cls._MEMCLAW_TENANT = get_standalone_tenant_id()
        return cls._MEMCLAW_TENANT

    @classmethod
    def _prepare_mcp_context(cls) -> None:
        """设置上游处理器需要的认证上下文（等价于 MCPAuthMiddleware 的 standalone 分支）。

        上游 handler 从 contextvars 读租户/凭证（`_tenant_id_var` 无默认值，未设即
        UNAUTHORIZED —— 直接调 handler 时就会撞上这个）。standalone 模式下中间件做的事
        就是「无 key 时把租户设为 standalone tenant」，这里照做。
        """
        from core_api import mcp_server as mod  # type: ignore

        # 必须先 init_standalone：否则 settings.is_standalone 为 False，
        # 上游 handler 直接抛 "Standalone mode not initialised"。
        cls._backend()
        mod._tenant_id_var.set(cls._tenant())
        mod._agent_id_var.set(None)
        mod._via_gateway_var.set(False)
        mod._readable_tenant_ids_var.set(None)
        mod._credential_kind_var.set("user_api_key")
        mod._install_uuid_var.set(None)
        mod._scopes_var.set(None)

    @staticmethod
    def _normalize_upstream_result(result: Any) -> Any:
        """把上游的 str 信封 / CallToolResult 归一化成桥的返回形态。"""
        text = result
        is_error = False
        content = getattr(result, "content", None)
        if content is not None:  # CallToolResult
            is_error = bool(getattr(result, "isError", False))
            if isinstance(content, list) and content:
                first = content[0]
                text = getattr(first, "text", None) or str(first)
        if isinstance(text, str):
            try:
                parsed = json.loads(text)
            except (json.JSONDecodeError, TypeError):
                return {"ok": False, "error": text} if is_error else {"ok": True, "result": text}
            if is_error or (isinstance(parsed, dict) and "error" in parsed):
                err = parsed.get("error") if isinstance(parsed, dict) else parsed
                message = err.get("message") if isinstance(err, dict) else str(err)
                code = err.get("code") if isinstance(err, dict) else ""
                return {"ok": False, "error": f"{code}: {message}".strip(": "), "raw": parsed}
            return {"ok": True, "result": parsed}
        return {"ok": True, "result": text}

    @classmethod
    def _upstream_tools(cls) -> dict[str, Callable[..., Any]]:
        """从 vendor 的 FastMCP 实例里取出 12 个上游工具处理器。

        为什么不走 merge_tools：新版 FastMCP 的 `ToolManager.list_tools()` 是 async，
        而 merge_tools 是同步的，遇到 async 直接 `continue`（还把 `.items()` 兜底一起跳过）
        → 实测合到 0 个工具。这里直接读 `_tool_manager._tools`（Tool 对象）取 `.fn`。
        处理器签名是扁平 kwargs、返回 JSON 字符串信封；调用前必须补认证上下文。
        """
        cls._inject()
        from core_api import mcp_server as core_mcp  # type: ignore

        manager = getattr(getattr(core_mcp, "mcp", None), "_tool_manager", None)
        raw = getattr(manager, "_tools", None)
        if not isinstance(raw, dict) or not raw:
            return {}

        tools: dict[str, Callable[..., Any]] = {}
        for name, tool in raw.items():
            fn = getattr(tool, "fn", None)
            if not callable(fn):
                continue

            def _make(handler: Callable[..., Any]) -> Callable[..., Any]:
                async def _call(**kwargs: Any) -> Any:
                    cls._prepare_mcp_context()
                    return cls._normalize_upstream_result(await handler(**kwargs))

                return _call

            tools[str(name)] = _make(fn)
        return tools

    @classmethod
    def _embedder(cls) -> Any:
        """本地嵌入引擎（项目自带 rag.embedding_engine，bge-small-zh-v1.5，离线可用）。

        语义召回需要向量；本项目已有本地嵌入栈，无需任何云端 key
        （现有 tokenrhythm key 也没有 embedding 模型：/embeddings 返回 MODEL_NOT_AVAILABLE）。
        """
        if cls._MEMCLAW_EMBEDDER is None:
            with cls._MEMCLAW_LOCK:
                if cls._MEMCLAW_EMBEDDER is None:
                    try:
                        from rag.embedding_engine import get_embedding_engine

                        cls._MEMCLAW_EMBEDDER = get_embedding_engine()
                    except Exception as e:  # noqa: BLE001 - 无嵌入时退化为关键词召回
                        logger.warning("[flat_bridge:memclaw] 本地嵌入引擎不可用，退化为关键词召回: %s", e)
                        cls._MEMCLAW_EMBEDDER = False  # 标记为不可用，避免重复尝试
        return cls._MEMCLAW_EMBEDDER or None

    @classmethod
    def _embed(cls, texts: list[str]) -> list[list[float]] | None:
        engine = cls._embedder()
        if engine is None:
            return None
        try:
            vectors = engine.encode(texts)
        except Exception as e:  # noqa: BLE001
            logger.warning("[flat_bridge:memclaw] 嵌入计算失败: %s", e)
            return None
        if vectors is None:
            return None
        return [[float(x) for x in row] for row in vectors]

    @classmethod
    def _direct_tools(cls) -> dict[str, Callable[..., Any]]:
        """上游不可用时的兜底：直连 SqliteBackend 的本地实现（无需任何 API key）。"""

        async def memclaw_write(
            content: str,
            metadata: dict | None = None,
            memory_type: str = "note",
            weight: float = 0.5,
        ) -> dict:
            """写入一条记忆到 MemClaw（SQLite standalone 模式，写入时计算本地向量）。"""
            if not str(content or "").strip():
                return {"ok": False, "error": "content 不能为空"}
            db = cls._backend()
            vectors = cls._embed([content])
            try:
                memory_id = await db.store(
                    tenant_id=cls._tenant(),
                    content=content,
                    embedding=(vectors or [None])[0],
                    metadata={**(metadata or {}), "memory_type": memory_type, "weight": weight},
                )
            except TypeError:
                # 老版本 store() 不接受 embedding 关键字
                memory_id = await db.store(
                    tenant_id=cls._tenant(), content=content, metadata=metadata or {}
                )
            return {
                "ok": True,
                "memory_id": memory_id,
                "embedded": bool(vectors),
                "embedding_note": "" if vectors else "本地嵌入不可用，本条仅支持关键词召回",
            }

        async def memclaw_list(limit: int = 20, keyword: str = "") -> dict:
            """列出最近的记忆（SQLite standalone 模式；keyword 过滤 content）。"""
            if int(limit) < 1:
                return {"ok": False, "error": f"limit 必须为正整数，收到 {limit}"}
            db = cls._backend()
            tenant = cls._tenant()
            list_fn = getattr(db, "list_memories", None)
            if callable(list_fn):
                rows = await list_fn(tenant_id=tenant, limit=int(limit), keyword=keyword)
                return {"ok": True, "memories": rows}
            get_conn = getattr(db, "_get_db", None)
            if not callable(get_conn):
                return {"ok": False, "error": "vendor SqliteBackend 无 _get_db，可能已升级 API"}
            conn = await get_conn()
            if str(keyword or "").strip():
                cursor = await conn.execute(
                    "SELECT id, content, metadata, created_at FROM memories "
                    "WHERE tenant_id = ? AND deleted_at IS NULL AND content LIKE ? "
                    "ORDER BY created_at DESC LIMIT ?",
                    (tenant, f"%{keyword}%", int(limit)),
                )
            else:
                cursor = await conn.execute(
                    "SELECT id, content, metadata, created_at FROM memories "
                    "WHERE tenant_id = ? AND deleted_at IS NULL "
                    "ORDER BY created_at DESC LIMIT ?",
                    (tenant, int(limit)),
                )
            rows = await cursor.fetchall()
            return {
                "ok": True,
                "count": len(rows),
                "memories": [
                    {"id": r[0], "content": r[1], "metadata": r[2], "created_at": r[3]} for r in rows
                ],
            }

        async def memclaw_recall(query: str, limit: int = 5) -> dict:
            """语义召回：本地 bge 向量余弦相似度；无向量的条目用关键词兜底。"""
            text = str(query or "").strip()
            if not text:
                return {"ok": False, "error": "query 不能为空"}
            top_k = max(1, int(limit))
            db = cls._backend()
            get_conn = getattr(db, "_get_db", None)
            if not callable(get_conn):
                return {"ok": False, "error": "vendor SqliteBackend 无 _get_db，可能已升级 API"}
            conn = await get_conn()
            cursor = await conn.execute(
                "SELECT id, content, metadata, created_at, embedding FROM memories "
                "WHERE tenant_id = ? AND deleted_at IS NULL "
                "ORDER BY created_at DESC LIMIT 500",
                (cls._tenant(),),
            )
            rows = await cursor.fetchall()

            query_vec = (cls._embed([text]) or [None])[0]
            scored: list[dict[str, Any]] = []
            for row in rows:
                memory_id, content, metadata, created_at, blob = row
                score = 0.0
                how = "keyword"
                if query_vec and blob:
                    stored = _unpack_vector(blob)
                    if len(stored) == len(query_vec):
                        num = sum(a * b for a, b in zip(stored, query_vec))
                        den = (sum(a * a for a in stored) ** 0.5) * (sum(b * b for b in query_vec) ** 0.5)
                        if den:
                            score = num / den
                            how = "vector"
                if how == "keyword":
                    # 无向量条目：按子串命中给出保守分数（低于任何正向量相似度场景仍可被关键词用户看到）
                    score = 1.0 if text in str(content or "") else 0.0
                if score > 0:
                    scored.append({
                        "id": memory_id,
                        "content": content,
                        "metadata": metadata,
                        "created_at": created_at,
                        "score": round(score, 4),
                        "match": how,
                    })
            scored.sort(key=lambda item: item["score"], reverse=True)
            return {
                "ok": True,
                "query": text,
                "count": len(scored[:top_k]),
                "scanned": len(rows),
                "embedding_backend": "bge-small-zh-v1.5(local)" if query_vec else "unavailable",
                "memories": scored[:top_k],
            }

        async def memclaw_stats() -> dict:
            """记忆总线统计：总数 / 含向量数 / 最近写入。"""
            db = cls._backend()
            get_conn = getattr(db, "_get_db", None)
            if not callable(get_conn):
                return {"ok": False, "error": "无 _get_db"}
            conn = await get_conn()
            total = (await (await conn.execute(
                "SELECT count(*) FROM memories WHERE tenant_id = ? AND deleted_at IS NULL",
                (cls._tenant(),),
            )).fetchone())[0]
            embedded = (await (await conn.execute(
                "SELECT count(*) FROM memories WHERE tenant_id = ? AND deleted_at IS NULL "
                "AND embedding IS NOT NULL",
                (cls._tenant(),),
            )).fetchone())[0]
            latest = (await (await conn.execute(
                "SELECT content, created_at FROM memories WHERE tenant_id = ? AND deleted_at IS NULL "
                "ORDER BY created_at DESC LIMIT 1",
                (cls._tenant(),),
            )).fetchone())
            return {
                "ok": True,
                "total": total,
                "with_embedding": embedded,
                "embedding_backend": "bge-small-zh-v1.5(local)" if cls._embedder() else "unavailable",
                "latest": {"content": (latest or [None])[0], "created_at": (latest or [None, None])[1]},
            }

        return {
            "memclaw_write": memclaw_write,
            "memclaw_list": memclaw_list,
            "memclaw_recall": memclaw_recall,
            "memclaw_stats": memclaw_stats,
        }

    @classmethod
    def _upstream_usable(cls, tools: dict[str, Callable[..., Any]]) -> str:
        """探测上游工具在本环境是否真能干活，返回空串=可用，否则返回不可用原因。

        上游 12 个工具能捕获、认证上下文也能补齐，但它们的 service 层走的是
        `core_api.clients.storage_client.get_storage_client()` —— 那是**指向独立
        core-storage-api 服务的 HTTP 客户端**（2.6k 行，vendored 快照未含），standalone
        下没有 SQLite 分支，因此调用会失败。与其把一排必错的工具暴露给模型，
        不如探测一次再决定：不可用就回落到直连 SqliteBackend 的实现。
        """
        probe = tools.get("memclaw_list")
        if not callable(probe):
            return "上游未提供 memclaw_list"
        try:
            result = asyncio.run(asyncio.wait_for(probe(limit=1), timeout=30))
        except Exception as e:  # noqa: BLE001
            return f"探测调用异常: {type(e).__name__}: {e}"
        if isinstance(result, dict) and result.get("ok") is False:
            return f"探测调用返回错误: {result.get('error')}"
        return ""

    @classmethod
    def _load_tools(cls) -> dict[str, Callable[..., Any]]:
        if cls._tools is not None:
            return cls._tools

        source = "direct"
        tools: dict[str, Callable[..., Any]] = {}
        try:
            upstream = cls._upstream_tools()
            if upstream:
                reason = cls._upstream_usable(upstream)
                if not reason:
                    tools = upstream
                    source = "upstream-fastmcp"
                else:
                    cls._capture_error = reason
                    logger.warning("[flat_bridge:memclaw] 上游工具不可用（%s），回落直连实现", reason)
        except Exception as e:  # noqa: BLE001 - vendor 快照不完整时退回直连实现
            cls._capture_error = f"{type(e).__name__}: {e}"
            logger.warning("[flat_bridge:memclaw] 上游工具不可用，回落直连实现: %s", e)

        if not tools:
            tools = cls._direct_tools()
        tools["memclaw_status"] = cls._make_status()
        cls._tool_source = source

        cls._tools = tools
        logger.info(
            "[flat_bridge:memclaw] 来源=%s，工具 %d 个: %s",
            source,
            len(tools),
            ", ".join(sorted(tools)),
        )
        return cls._tools

    @classmethod
    def _make_status(cls) -> Callable[..., Any]:
        async def memclaw_status() -> dict:
            """memclaw 可用性诊断：工具来源 / 后端 / 已知限制。"""
            import sys as _sys

            backend = None
            backend_error = ""
            try:
                backend = "sqlite-standalone" if cls._backend() is not None else None
            except Exception as e:  # noqa: BLE001
                backend_error = f"{type(e).__name__}: {e}"
            upstream = sorted(k for k in cls._load_tools() if k != "memclaw_status")
            return {
                "ok": backend is not None,
                "python": _sys.version.split()[0],
                "backend": backend,
                "backend_error": backend_error,
                "mode": cls._tool_source or "unknown",
                "tools": upstream,
                "embedding_backend": (
                    "bge-small-zh-v1.5(local)" if cls._embedder() else "unavailable（召回退化为关键词）"
                ),
                "note": (
                    "本地实现（无云端 key 也能跑）：write 写入时算本地向量，recall 走余弦相似度；"
                    "上游 12 工具需要 core-storage-api（云端形态），vendored standalone 下不可用。"
                ),
            }

        return memclaw_status


class MarkitdownBridge(FlatAdapterBridge):
    adapter_name = "markitdown"
    name = "markitdown"


class Llm4decompileBridge(FlatAdapterBridge):
    """反编译：首次调用可能要加载 1.3B 模型，超时放宽。"""

    adapter_name = "llm4decompile"
    name = "llm4decompile"
    tool_timeout_s = 300.0


class PaperMinerBridge(FlatAdapterBridge):
    """论文参数提取：依赖本地 Ollama，未启动时工具会明确报错。"""

    adapter_name = "paper_miner"
    name = "paper_miner"
    tool_timeout_s = 240.0


class Context7Bridge(FlatAdapterBridge):
    adapter_name = "context7"
    name = "context7"


class ChemmcpBridge(FlatAdapterBridge):
    adapter_name = "chemmcp"
    name = "chemmcp"


class AgentReachBridge(FlatAdapterBridge):
    adapter_name = "agent_reach"
    name = "agent_reach"


BRIDGES = {
    "vulnclaw": VulnclawBridge,
    "memclaw": MemclawBridge,
    "markitdown": MarkitdownBridge,
    "llm4decompile": Llm4decompileBridge,
    "paper_miner": PaperMinerBridge,
    "context7": Context7Bridge,
    "chemmcp": ChemmcpBridge,
    "agent_reach": AgentReachBridge,
}
