"""MCP Server - 独立FastAPI服务，提供统一的MCP工具调度HTTP API

外部用户/服务可通过 POST /schedule 调用已注册的MCP工具。
"""

import asyncio
import json
from contextlib import asynccontextmanager
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from system.config import logger
from system.cors_config import apply_local_cors
import threading


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan - 启动时初始化MCP服务"""
    logger.info("[MCP Server] 正在初始化...")

    from mcpserver.mcp_manager import get_mcp_manager
    get_mcp_manager()

    from mcpserver.mcp_registry import auto_register_mcp
    auto_register_mcp()

    logger.info("[MCP Server] 初始化完成")
    yield

    from mcpserver.mcp_manager import get_mcp_manager
    await get_mcp_manager().cleanup()
    logger.info("[MCP Server] 已关闭")


app = FastAPI(title="陆墨 MCP Server", lifespan=lifespan)

# 统一 CORS 配置
apply_local_cors(app)

# 后台回调任务引用集，避免 fire-and-forget 任务被 GC 中途回收
_BACKGROUND_TASKS: set[asyncio.Task] = set()


class ScheduleRequest(BaseModel):
    query: str = ""
    tool_calls: list = []
    session_id: str = ""
    callback_url: str = ""


class ToolCallRequest(BaseModel):
    """单个工具调用请求"""
    service_name: str
    tool_name: str = ""
    message: str = ""
    # 允许透传任意额外参数
    params: dict[str, Any] = {}


@app.post("/schedule")
async def schedule_task(req: ScheduleRequest):
    """调度MCP任务 - 并行执行所有 tool_calls，同步返回结果

    外部调用统一入口。多个 tool_calls 并行执行，全部完成后一次性返回结果。
    如果指定了 callback_url，也会异步回调。
    """
    from mcpserver.mcp_manager import get_mcp_manager
    manager = get_mcp_manager()

    if not req.tool_calls:
        return {"status": "ok", "results": [], "message": "无工具调用"}

    async def _execute_one(call: dict[str, Any]) -> dict[str, Any]:
        service_name = call.get("service_name", "")
        tool_name = call.get("tool_name", "")
        try:
            result = await manager.unified_call(service_name, call)
            return {"service_name": service_name, "tool_name": tool_name, "status": "ok", "result": result}
        except Exception as e:
            logger.error(f"[MCP Server] 工具调用失败: service={service_name}, error={e}")
            return {"service_name": service_name, "tool_name": tool_name, "status": "error", "error": str(e)}

    # 并行执行所有工具调用
    results = await asyncio.gather(*[_execute_one(call) for call in req.tool_calls], return_exceptions=False)

    response = {"status": "ok", "results": list(results)}

    # 如果有回调地址，先做安全校验再异步发送（不阻塞返回）
    # 拦截私网/链路本地/云元数据地址（SSRF），loopback 本地回调放行
    if req.callback_url:
        from urllib.parse import urlparse

        from mcpserver.security_utils import is_private_url
        parsed_cb = urlparse(req.callback_url)
        host_cb = (parsed_cb.hostname or "").lower()
        if parsed_cb.scheme not in ("http", "https") or not host_cb:
            return {"status": "error", "message": "callback_url 协议或主机不合法"}
        if host_cb not in ("localhost", "127.0.0.1", "::1") and is_private_url(req.callback_url):
            return {"status": "error", "message": f"callback_url 不安全：不允许私有/内部地址 ({host_cb})"}
        # 持有引用避免回调任务被 GC 中途回收
        task = asyncio.create_task(_send_callback(req.callback_url, req.session_id, results))
        _BACKGROUND_TASKS.add(task)
        task.add_done_callback(_BACKGROUND_TASKS.discard)

    return response


@app.post("/call")
async def call_tool(req: ToolCallRequest):
    """调用单个MCP工具 - 同步返回结果

    简化接口，直接指定 service_name 和参数。
    """
    from mcpserver.mcp_manager import get_mcp_manager
    manager = get_mcp_manager()

    tool_call = {"service_name": req.service_name, "tool_name": req.tool_name, "message": req.message, **req.params}

    try:
        result = await manager.unified_call(req.service_name, tool_call)

        # 如果调用的是screen_vision，通知ProactiveVision重置计时器
        # 避免AI刚用过screen_vision，ProactiveVision又立即触发重复分析
        if req.service_name == "screen_vision":
            asyncio.create_task(_notify_proactive_vision_reset())

        return {"status": "ok", "result": result}
    except Exception as e:
        logger.error(f"[MCP Server] 工具调用失败: service={req.service_name}, error={e}")
        raise HTTPException(status_code=500, detail="工具调用失败")


@app.get("/services")
async def list_services():
    """列出已注册的MCP服务"""
    from mcpserver.mcp_registry import get_all_services_info, get_service_statistics
    return {
        "services": get_all_services_info(),
        "statistics": get_service_statistics(),
    }


@app.get("/status")
async def server_status():
    """服务器状态"""
    from mcpserver.mcp_registry import get_service_statistics
    stats = get_service_statistics()
    return {
        "status": "running",
        "registered_services": stats["total_services"],
        "total_tools": stats["total_tools"],
    }


@app.get("/metrics/tools")
async def tool_metrics():
    """工具级可观测指标（B5）：调用次数/平均延迟/错误率"""
    from mcpserver.mcp_manager import get_mcp_manager
    return get_mcp_manager().get_tool_metrics()


# ── 卷189-B：调用画像 + 熔断 ──

@app.get("/tools/stats")
async def tools_stats(window: str = "7d"):
    """调用画像：按工具聚合 调用数/P50/P95/失败率/最近错误（window=7d/24h/30m）。"""
    from mcpserver.telemetry import get_recorder
    rec = get_recorder()
    rec.flush()  # 让刚入队的数据可见（读端点容忍一次同步 flush）
    return {"window": window, "stats": rec.stats(window)}


@app.get("/tools/circuit")
async def tools_circuit():
    """熔断状态：非 closed 的工具及窗口样本/失败率/冷却截止。"""
    from mcpserver.telemetry import get_breaker
    return {"circuits": get_breaker().states()}


# ── 卷189-C：声明式工具链 ──

class ChainRunRequest(BaseModel):
    chain: str                      # 链名（种子链之一或注册的链）
    inputs: dict[str, Any] = {}


@app.get("/chains")
async def chains_list():
    """列出可用链（当前 = 三条种子链）。"""
    from mcpserver.workflow.chains import seed_chains
    return {"chains": [c.to_dict() for c in seed_chains()]}


@app.post("/chains/run")
async def chains_run(req: ChainRunRequest):
    """执行一条链：顺序 + 插值 + 重试 + 失败短路（返回含部分结果）。"""
    from mcpserver.mcp_manager import get_mcp_manager
    from mcpserver.workflow.chains import ChainExecutor, get_chain

    chain = get_chain(req.chain)
    if chain is None:
        raise HTTPException(status_code=404, detail=f"未找到链: {req.chain}")

    manager = get_mcp_manager()

    async def _call(service: str, tool_call: dict[str, Any]) -> Any:
        return await manager.unified_call(service, tool_call)

    executor = _get_chain_executor(ChainExecutor, _call)
    run = await executor.run(chain, req.inputs)
    return run.to_dict()


@app.get("/chains/runs/{run_id}")
async def chains_run_status(run_id: str):
    """查询链执行进度/结果。"""
    ex = _CHAIN_EXECUTOR
    if ex is None:
        raise HTTPException(status_code=404, detail="尚无链执行记录")
    run = ex.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"未找到 run: {run_id}")
    return run.to_dict()


@app.get("/chains/suggest")
async def chains_suggest(window: str = "7d", top_n: int = 5):
    """链推荐（轻量）：基于调用画像给「高频低失败」的候选种子工具。"""
    from mcpserver.telemetry import get_recorder
    from mcpserver.workflow.chains import suggest_chains
    rec = get_recorder()
    rec.flush()
    return {"window": window, "suggestions": suggest_chains(rec.stats(window), top_n=top_n)}


_CHAIN_EXECUTOR = None


_CHAIN_EXECUTOR_lock = threading.Lock()


def _get_chain_executor(cls, call_fn):
    """复用一个执行器实例（保持 run 历史可查）。"""
    global _CHAIN_EXECUTOR
    if _CHAIN_EXECUTOR is None:
        with _CHAIN_EXECUTOR_lock:
            if _CHAIN_EXECUTOR is None:
                _CHAIN_EXECUTOR = cls(call_fn)
    return _CHAIN_EXECUTOR


# ── ②-1 认知免疫层：内容源信任评分（低信任进隔离区）──

class TrustScoreRequest(BaseModel):
    """信任评分请求体"""
    name: str
    source: str = ""
    signature: bool = False
    lineage: str = ""
    reviewed: bool = False
    force: bool = False


@app.post("/trust/assess")
async def trust_assess(req: TrustScoreRequest):
    """评估对象信任分并落盘（评分表可回溯）"""
    from mcpserver.trust_layer import get_trust_scorer
    a = get_trust_scorer().assess(
        req.name, source=req.source, signature=req.signature,
        lineage=req.lineage, reviewed=req.reviewed, force=req.force,
    )
    return {"ok": True, **a.to_dict()}


@app.get("/trust/status")
async def trust_status():
    """信任评分表 + 隔离区清单"""
    from mcpserver.trust_layer import get_trust_scorer
    scorer = get_trust_scorer()
    return {
        "assessments": scorer.all(),
        "quarantined": scorer.quarantine_list(),
        "thresholds": {
            "trust_high": 2,
            "trust_low": 1,
        },
    }


async def _send_callback(callback_url: str, session_id: str, results: list[dict[str, Any]]):
    """异步回调通知"""
    try:
        import httpx

        payload = {
            "session_id": session_id,
            "action": "show_mcp_result",
            "results": [r for r in results if isinstance(r, dict)],
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            for attempt in range(3):
                try:
                    resp = await client.post(callback_url, json=payload)
                    if resp.status_code == 200:
                        logger.info(f"[MCP Server] 回调成功: {callback_url}")
                        return
                except Exception as e:
                    logger.warning(f"[MCP Server] 回调重试 {attempt + 1}/3: {e}")
                    await asyncio.sleep(1)
    except Exception as e:
        logger.error(f"[MCP Server] 回调失败: {e}")


async def _notify_proactive_vision_reset():
    """通知ProactiveVision重置检查计时器

    当AI主动调用screen_vision时，通知ProactiveVision延迟下次检查，
    避免短时间内重复分析同一屏幕。
    """
    try:
        import httpx

        from system.config import get_server_port

        agent_port = get_server_port("agent_server")
        url = f"http://127.0.0.1:{agent_port}/proactive_vision/reset_timer"

        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.post(url, json={"reason": "mcp_call_screen_vision"})
            if resp.status_code == 200:
                result = resp.json()
                if result.get("success"):
                    logger.debug("[MCP Server] 已通知ProactiveVision重置计时器")
                else:
                    logger.debug(f"[MCP Server] ProactiveVision重置失败: {result.get('error')}")
            else:
                logger.debug(f"[MCP Server] ProactiveVision通知失败: HTTP {resp.status_code}")
    except Exception as e:
        # 静默失败，不影响主流程
        logger.debug(f"[MCP Server] ProactiveVision通知异常（忽略）: {e}")
