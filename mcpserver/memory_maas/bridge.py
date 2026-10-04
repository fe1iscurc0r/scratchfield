"""记忆 MaaS MCP 桥 — MemoryMaasBridge（agent-manifest.json entryPoint）。

工具（4 个）：
- memory_search(query, limit, with_lineage)：混合检索，命中附会话血统链。
  优先走 HTTP sidecar（MEMORY_MAAS_URL，默认 http://127.0.0.1:48919），
  不通则进程内直连五件套降级（via 字段标明来源）。
- memory_lineage(session_id)：会话血统链 + 根下分支树。
- memory_write(session_id, turns)：写索引卡（后台写入+检索索引同步）。
- memory_status()：五件套状态（数据目录/计数/后台写统计）。

fail-fast：查询为空/会话不存在返回 {"status":"error"}，不静默空返回。
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from mcpserver.memory_maas.entities import MemoryEntity
from mcpserver.memory_maas.guard import FlowPolicy, pre_write_check
from mcpserver.memory_maas.maintenance import consolidate, retention_sweep

logger = logging.getLogger(__name__)

_DEFAULT_SIDECAR = "http://127.0.0.1:48919"
_SIDECAR_TIMEOUT = 2.0


def _sidecar_url() -> str:
    return os.environ.get("MEMORY_MAAS_URL", _DEFAULT_SIDECAR).rstrip("/")


def _sidecar_post(path: str, payload: dict[str, Any]) -> dict[str, Any] | None:
    """POST 到 sidecar；不通（连接失败/超时/5xx）返回 None 走降级。"""
    import httpx
    try:
        resp = httpx.post(f"{_sidecar_url()}{path}", json=payload,
                          timeout=_SIDECAR_TIMEOUT)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        logger.debug("[memory_maas] sidecar %s 不通（%s），进程内降级",
                     path, e)
    return None


def _sidecar_get(path: str) -> dict[str, Any] | None:
    import httpx
    try:
        resp = httpx.get(f"{_sidecar_url()}{path}", timeout=_SIDECAR_TIMEOUT)
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        logger.debug("[memory_maas] sidecar %s 不通（%s），进程内降级",
                     path, e)
    return None


class MemoryMaasBridge:
    """记忆 MaaS MCP 服务实例（HTTP sidecar 优先，进程内降级兜底）。"""

    # ---- 工具实现 ----
    def tool_search(self, query: str, limit: int = 10,
                    with_lineage: bool = True) -> dict[str, Any]:
        if not (query or "").strip():
            return {"status": "error", "error": "query 不能为空"}
        via_http = _sidecar_post("/memory/search", {
            "query": query, "limit": limit, "with_lineage": with_lineage})
        if via_http is not None:
            return {"status": "ok", "via": "http-sidecar", **via_http}
        from mcpserver.memory_maas.core import MemoryMaasError, get_core
        try:
            result = get_core().search(query, limit=limit,
                                       with_lineage=with_lineage)
            return {"status": "ok", "via": "in-process", **result}
        except MemoryMaasError as e:
            return {"status": "error", "error": str(e)}

    def tool_lineage(self, session_id: str) -> dict[str, Any]:
        if not session_id:
            return {"status": "error", "error": "session_id 不能为空"}
        via_http = _sidecar_get(f"/memory/lineage/trace/{session_id}")
        if via_http is not None and via_http.get("ok"):
            branches = _sidecar_get(
                f"/memory/lineage/branches/{via_http['lineage'][0]['session_id']}")
            return {"status": "ok", "via": "http-sidecar", **via_http,
                    "branches": (branches or {}).get("branches", {})}
        from mcpserver.memory_maas.core import get_core
        core = get_core()
        try:
            chain = core.trace(session_id)
        except Exception as e:
            return {"status": "error",
                    "error": f"会话血统查询失败: {session_id}: {e}"}
        if not chain:
            return {"status": "error",
                    "error": f"会话不存在或无血统记录: {session_id}"}
        root_id = chain[0]["session_id"]
        try:
            branches = core.branches_under(root_id)
        except Exception:
            branches = {}
        return {"status": "ok", "via": "in-process", "session_id": session_id,
                "lineage": chain, "depth": len(chain), "branches": branches}

    def tool_write(self, session_id: str,
                   turns: list[dict[str, Any]]) -> dict[str, Any]:
        if not session_id:
            return {"status": "error", "error": "session_id 不能为空"}
        via_http = _sidecar_post("/memory/cards",
                                 {"session_id": session_id, "turns": turns})
        if via_http is not None:
            return {"status": "ok", "via": "http-sidecar", **via_http}
        from mcpserver.memory_maas.core import MemoryMaasError, get_core
        try:
            result = get_core().write_card(session_id, turns)
            return {"status": "ok", "via": "in-process", **result}
        except MemoryMaasError as e:
            return {"status": "error", "error": str(e)}

    def tool_status(self) -> dict[str, Any]:
        via_http = _sidecar_get("/status")
        if via_http is not None:
            return {"status": "ok", "via": "http-sidecar", **via_http}
        from mcpserver.memory_maas.core import get_core
        return {"status": "ok", "via": "in-process",
                **get_core().status()}

    # ---- typed 实体 + 维护 + 防护（X-01~X-03 新工具） ----

    def tool_typed_add(self, content: str, type: str = "note",
                       tags: list[str] | None = None, pinned: bool = False,
                       source_rank: int = 0,
                       relations: list[str] | None = None,
                       platform: str = "local") -> dict[str, Any]:
        if not (content or "").strip():
            return {"status": "error", "error": "content 不能为空"}
        decision = pre_write_check(content, source_rank=source_rank)
        if decision.blocked:
            return {"status": "error", "error": decision.reason}
        via_http = _sidecar_post("/memory/typed", {
            "content": content, "type": type, "tags": tags or [],
            "pinned": bool(pinned), "source_rank": int(source_rank),
            "relations": relations or [], "platform": platform})
        if via_http is not None:
            return {"status": "ok", "via": "http-sidecar", **via_http}
        from mcpserver.memory_maas.core import MemoryMaasError, get_core
        try:
            result = get_core().add_memory(
                content, type=type, tags=tags, pinned=pinned,
                relations=relations, source_rank=source_rank,
                platform=platform)
            return {"status": "ok", "via": "in-process", **result}
        except MemoryMaasError as e:
            return {"status": "error", "error": str(e)}

    def tool_capture_observation(self, memory_session_id: str, title: str = "",
                                 narrative: str = "", type: str = "note",
                                 tags: list[str] | None = None,
                                 pinned: bool = False,
                                 source_rank: int = 0,
                                 platform: str = "local") -> dict[str, Any]:
        """观察捕获（03-01 内容哈希去重）：同观察幂等只留一条。03-04 platform 打标。"""
        if not (memory_session_id or "").strip():
            return {"status": "error", "error": "memory_session_id 不能为空"}
        via_http = _sidecar_post("/memory/capture/observation", {
            "memory_session_id": memory_session_id, "title": title,
            "narrative": narrative, "type": type, "tags": tags or [],
            "pinned": bool(pinned), "source_rank": int(source_rank),
            "platform": platform})
        if via_http is not None:
            return {"status": "ok", "via": "http-sidecar", **via_http}
        from mcpserver.memory_maas.core import MemoryMaasError, get_core
        try:
            result = get_core().capture_observation(
                memory_session_id, title, narrative, type=type, tags=tags,
                pinned=pinned, source_rank=source_rank, platform=platform)
            return {"status": "ok", "via": "in-process", **result}
        except MemoryMaasError as e:
            return {"status": "error", "error": str(e)}

    def tool_typed_query(self, type: str | None = None,
                         tags: list[str] | None = None,
                         pinned: bool | None = None,
                         include_isolation: bool = False,
                         limit: int | None = None,
                         path: str | None = None,
                         platform: str | None = None) -> dict[str, Any]:
        via_http = _sidecar_post("/memory/typed/query", {
            "type": type, "tags": tags, "pinned": pinned,
            "include_isolation": bool(include_isolation), "limit": limit,
            "path": path, "platform": platform})
        if via_http is not None:
            return {"status": "ok", "via": "http-sidecar", **via_http}
        from mcpserver.memory_maas.core import get_core
        result = get_core().query(type=type, tags=tags, pinned=pinned,
                                  limit=limit,
                                  include_isolation=include_isolation,
                                  path=path, platform=platform)
        return {"status": "ok", "via": "in-process", **result}

    def tool_maintenance(self, action: str = "status",
                         max_age_days: float = 30.0,
                         min_group: int = 2,
                         template_mode: str = "default",
                         dry_run: bool = False) -> dict[str, Any]:
        """action: status | sweep | consolidate | snapshot。"""
        if action == "sweep":
            via_http = _sidecar_post("/memory/maintenance/sweep",
                                     {"max_age_days": max_age_days,
                                      "dry_run": bool(dry_run)})
            if via_http is not None:
                return {"status": "ok", "via": "http-sidecar", **via_http}
            from mcpserver.memory_maas.core import get_core
            core = get_core()
            result = retention_sweep(
                core.typed_store, max_age_days=max_age_days, dry_run=dry_run,
                snapshots_dir=str(core.data_dir / "snapshots"))
            return {"status": "ok", "via": "in-process", **result}
        if action == "consolidate":
            via_http = _sidecar_post("/memory/maintenance/consolidate",
                                     {"min_group": min_group,
                                      "template_mode": template_mode,
                                      "dry_run": bool(dry_run)})
            if via_http is not None:
                return {"status": "ok", "via": "http-sidecar", **via_http}
            from mcpserver.memory_maas.core import get_core
            core = get_core()
            result = consolidate(
                core.typed_store, min_group=min_group,
                template_mode=template_mode, dry_run=dry_run,
                snapshots_dir=str(core.data_dir / "snapshots"))
            return {"status": "ok", "via": "in-process", **result}
        if action == "status":
            via_http = _sidecar_get("/memory/maintenance/status")
            if via_http is not None:
                return {"status": "ok", "via": "http-sidecar", **via_http}
            from mcpserver.memory_maas.core import get_core
            return {"status": "ok", "via": "in-process",
                    **get_core().maintenance_status()}
        return {"status": "error",
                "error": f"不支持的 maintenance action: {action!r}（sweep/consolidate/status/snapshot）"}

    def tool_guard_status(self) -> dict[str, Any]:
        via_http = _sidecar_get("/memory/guard/status")
        if via_http is not None:
            return {"status": "ok", "via": "http-sidecar", **via_http}
        from mcpserver.memory_maas.core import get_core
        return {"status": "ok", "via": "in-process",
                **get_core().guard_status()}

    # ---- MCP 分发 ----
    async def handle_handoff(self, tool_call: dict[str, Any]) -> str:
        tool_name = str(tool_call.get("tool_name") or "").strip()
        params = {k: v for k, v in tool_call.items()
                  if k not in ("service_name", "tool_name", "message",
                               "session_id", "callback_url")}
        try:
            if tool_name == "memory_search":
                result = self.tool_search(
                    str(params.get("query") or ""),
                    limit=int(params.get("limit", 10) or 10),
                    with_lineage=bool(params.get("with_lineage", True)))
            elif tool_name == "memory_lineage":
                result = self.tool_lineage(
                    str(tool_call.get("session_id")
                        or params.get("session_id") or ""))
            elif tool_name == "memory_write":
                result = self.tool_write(
                    str(tool_call.get("session_id")
                        or params.get("session_id") or ""),
                    turns=params.get("turns") or [])
            elif tool_name == "memory_status":
                result = self.tool_status()
            elif tool_name == "memory_add_typed":
                result = self.tool_typed_add(
                    str(params.get("content") or ""),
                    type=str(params.get("type") or "note"),
                    tags=params.get("tags") or [],
                    pinned=bool(params.get("pinned", False)),
                    source_rank=int(params.get("source_rank", 0) or 0),
                    relations=params.get("relations") or [],
                    platform=str(params.get("platform") or "local"))
            elif tool_name == "memory_capture_observation":
                result = self.tool_capture_observation(
                    str(params.get("memory_session_id")
                        or tool_call.get("session_id") or ""),
                    title=str(params.get("title") or ""),
                    narrative=str(params.get("narrative") or ""),
                    type=str(params.get("type") or "note"),
                    tags=params.get("tags") or [],
                    pinned=bool(params.get("pinned", False)),
                    source_rank=int(params.get("source_rank", 0) or 0),
                    platform=str(params.get("platform") or "local"))
            elif tool_name == "memory_query_filtered":
                result = self.tool_typed_query(
                    type=params.get("type"),
                    tags=params.get("tags"),
                    pinned=params.get("pinned"),
                    include_isolation=bool(params.get("include_isolation", False)),
                    limit=params.get("limit"),
                    path=params.get("path"),
                    platform=params.get("platform"))
            elif tool_name == "memory_maintenance":
                result = self.tool_maintenance(
                    action=str(params.get("action") or "status"),
                    max_age_days=float(params.get("max_age_days", 30.0) or 30.0),
                    min_group=int(params.get("min_group", 2) or 2),
                    template_mode=str(params.get("template_mode") or "default"),
                    dry_run=bool(params.get("dry_run", False)))
            elif tool_name == "memory_guard_status":
                result = self.tool_guard_status()
            else:
                raise ValueError(
                    f"memory_maas 不支持的工具: {tool_name!r}（可用: "
                    "memory_search/memory_lineage/memory_write/memory_status/"
                    "memory_capture_observation/memory_add_typed/"
                    "memory_query_filtered/memory_maintenance/"
                    "memory_guard_status）")
        except Exception as e:
            logger.exception("[memory_maas] %s 未预期异常", tool_name)
            return json.dumps({"status": "error", "service": "memory_maas",
                               "tool": tool_name, "error": str(e)},
                              ensure_ascii=False)
        return json.dumps({"service": "memory_maas", "tool": tool_name,
                           **result}, ensure_ascii=False)
