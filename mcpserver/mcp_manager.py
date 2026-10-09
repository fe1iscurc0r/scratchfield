"""MCP管理器 - 管理MCP服务连接和工具调用"""

import json
import os
import time
from typing import Any, Dict, List, Optional

from mcpserver.mcp_registry import (
    MANIFEST_CACHE,
    MCP_REGISTRY,
    all_service_names,
    ensure_hot,
    get_cold_hot_failure,
    get_service_source,
    list_visible_service_names,
)
from mcpserver.telemetry import get_breaker, record_tool_call
from system.config import logger
import threading

# B5 工具级可观测：{service_name: {calls, latency_sum, errors, last_call}}
_TOOL_METRICS: dict[str, dict[str, Any]] = {}

# B4 声明式鉴权守卫：{service_name: {provider, scopes, env_key}}
_AUTH_GUARD: dict[str, dict[str, Any]] = {}


def register_auth_requirement(service_name: str, provider: str,
                              scopes: list[str] | None = None,
                              env_key: str | None = None) -> None:
    """声明某服务需要凭证（provider + scopes）。env_key 默认 {PROVIDER}_API_KEY。"""
    _AUTH_GUARD[service_name] = {
        "provider": provider,
        "scopes": scopes or [],
        "env_key": env_key or f"{provider.upper()}_API_KEY",
    }


def _auth_blocked(service_name: str) -> str | None:
    """鉴权检查：返回 None=放行；返回字符串=标准错误 JSON。"""
    g = _AUTH_GUARD.get(service_name)
    if not g:
        return None
    if os.environ.get(g["env_key"]):
        return None
    return (
        '{"status": "error", "error_type": "auth_required", '
        f'"message": "请先配置 {g["env_key"]} 凭证（provider: {g["provider"]}）"}}'
    )


class MCPManager:
    """MCP服务管理器 - 管理工具调用路由"""

    def __init__(self):
        self._initialized = False

    async def unified_call(self, service_name: str, tool_call: dict[str, Any]) -> str:
        """统一调用接口 - 路由到注册的agent的handle_handoff方法"""
        # B4 鉴权守卫：声明需凭证且未配置 → 标准错误，不进 LLM
        blocked = _auth_blocked(service_name)
        if blocked:
            return blocked

        # B2 快速失败：熔断中的外部/adapter 工具直接短路（内置核心 agent 不熔断）
        source = get_service_source(service_name)
        breaker = get_breaker()
        if not breaker.allow(service_name, source):
            st = breaker.state(service_name)
            logger.warning("[MCPManager] 熔断短路 %s（fail_rate=%.2f, samples=%d）",
                           service_name, st["fail_rate"], st["samples"])
            return json.dumps({
                "status": "error", "error_type": "tool_circuit_open",
                "tool": service_name,
                "message": f"工具 {service_name} 连续失败已熔断，{int(st['open_until'] - time.time())}s 后半开探测",
                "last_error": st["last_error"],
            }, ensure_ascii=False)

        agent = ensure_hot(service_name)   # 卷189-A1：冷表首次调用转热
        if not agent:
            # B2 快速失败：冷表转热失败给结构化报错（不抛 500 堆栈）
            reason = get_cold_hot_failure(service_name)
            if reason:
                logger.error(f"[MCPManager] 服务 {service_name} 冷表转热失败: {reason}")
                return (
                    '{"status": "error", "error_type": "tool_unavailable", '
                    f'"message": "服务 {service_name} 无法实例化", "detail": {reason!r}}}'
                )
            return f'{{"status": "error", "message": "未找到服务: {service_name}"}}'

        t0 = time.time()
        ok = True
        err_kind = ""
        try:
            result = await agent.handle_handoff(tool_call)
            return result
        except Exception as e:
            ok = False
            err_kind = type(e).__name__
            logger.error(f"[MCPManager] 调用服务 {service_name} 失败: {e}")
            self._record_metric(service_name, t0, error=True)
            return f'{{"status": "error", "message": "调用失败: {e}"}}'
        finally:
            elapsed = time.time() - t0
            if service_name not in _TOOL_METRICS:
                _TOOL_METRICS[service_name] = {"calls": 0, "latency_sum": 0.0, "errors": 0, "last_call": 0.0}
            # 成功路径在 finally 里也累计 calls/latency（错误路径上面已 +errors）
            _TOOL_METRICS[service_name]["calls"] += 1
            _TOOL_METRICS[service_name]["latency_sum"] += elapsed
            _TOOL_METRICS[service_name]["last_call"] = time.time()
            # B1 画像 + 熔断：入后台队列，不阻塞调用路径
            try:
                record_tool_call(service_name, agent="mcp_manager",
                                 caller=str(tool_call.get("tool_name") or ""),
                                 duration_ms=elapsed * 1000, ok=ok,
                                 error_kind=err_kind, source=source)
            except Exception:
                pass

    def _record_metric(self, service_name: str, t0: float, error: bool = False) -> None:
        """错误路径指标记录（调用方已在 except 中调用）。"""
        if service_name not in _TOOL_METRICS:
            _TOOL_METRICS[service_name] = {"calls": 0, "latency_sum": 0.0, "errors": 0, "last_call": 0.0}
        if error:
            _TOOL_METRICS[service_name]["errors"] += 1

    def get_tool_metrics(self) -> dict[str, dict[str, Any]]:
        """导出工具级指标（供 GET /metrics/tools）。"""
        out = {}
        for name, m in _TOOL_METRICS.items():
            calls = max(m["calls"], 1)
            out[name] = {
                "calls": m["calls"],
                "avg_latency_ms": round(m["latency_sum"] / calls * 1000, 2),
                "errors": m["errors"],
                "error_rate": round(m["errors"] / calls, 4),
                "last_call_ts": m["last_call"],
            }
        return out

    def get_available_services(self) -> list[str]:
        """获取可用服务列表（懒加载下含尚未实例化的冷表项）。"""
        return all_service_names()

    def get_available_services_filtered(self) -> dict[str, Any]:
        """获取服务详情（冷热合并：冷表项也返回，供前端/提示词展示）。"""
        result = {}
        for name in all_service_names():
            manifest = MANIFEST_CACHE.get(name, {})
            caps = manifest.get("capabilities", {})
            tools = caps.get("invocationCommands", []) if isinstance(caps, dict) else []
            result[name] = {
                "displayName": manifest.get("displayName") or manifest.get("name") or name,
                "description": manifest.get("description", ""),
                "tools": tools,
            }
        return result

    def format_available_services(self) -> str:
        """格式化服务列表为字符串，供提示词注入"""
        lines = []
        for name, manifest in MANIFEST_CACHE.items():
            self._format_single_service(name, manifest, lines)
        return "\n".join(lines)

    def format_available_services_for_agent(self, agent_id: str | None = None) -> str:
        """按干员可见范围格式化 MCP 服务列表。"""
        return self.format_services_by_names(list_visible_service_names(agent_id))

    def format_services_by_names(self, names: list) -> str:
        """只格式化指定名称的 MCP 服务文档"""
        lines = []
        for name in names:
            manifest = MANIFEST_CACHE.get(name)
            if not manifest:
                continue
            self._format_single_service(name, manifest, lines)
        return "\n".join(lines)

    @staticmethod
    def _format_single_service(name: str, manifest: dict, lines: list):
        """格式化单个 MCP 服务的文档（内部共享方法）"""
        display_name = manifest.get("displayName") or manifest.get("name") or name
        desc = manifest.get("description", "")
        # capabilities 可能是 dict（标准格式）或 list（标签格式），仅 dict 含 invocationCommands
        caps = manifest.get("capabilities", {})
        tools = caps.get("invocationCommands", []) if isinstance(caps, dict) else []
        lines.append(f"- 服务名(service_name): {name}")
        lines.append(f"  显示名: {display_name}")
        lines.append(f"  描述: {desc}")
        for tool in tools:
            if not isinstance(tool, dict):
                continue
            cmd = tool.get("command", "")
            tool_desc = tool.get("description", "").split("\n")[0]
            example = tool.get("example", "")
            lines.append(f"  工具: {cmd} - {tool_desc}")
            if example:
                lines.append(f"  示例: {example}")
        lines.append("")

    async def cleanup(self):
        """清理资源"""
        pass


# 全局单例
_MCP_MANAGER: MCPManager | None = None


_MCP_MANAGER_lock = threading.Lock()


def get_mcp_manager() -> MCPManager:
    global _MCP_MANAGER
    if _MCP_MANAGER is None:
        with _MCP_MANAGER_lock:
            if _MCP_MANAGER is None:
                _MCP_MANAGER = MCPManager()
    return _MCP_MANAGER
