#!/usr/bin/env python3
"""
陆墨 API服务器
提供RESTful API接口访问陆墨功能
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
import threading
import time
import traceback
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from urllib.error import URLError
from urllib.request import Request as UrlRequest
from urllib.request import urlopen

# 在导入其他模块前先设置HTTP库日志级别
logging.getLogger("httpcore.http11").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore.connection").setLevel(logging.WARNING)

# 创建logger实例
logger = logging.getLogger(__name__)

# 卷191-B3：启动计时起点。模块开始加载的瞬间打点，lifespan 结束时打印摘要行
# [boot] total=X.XXs routes=N lazy=M，便于回归监控冷启动变化。
_BOOT_T0 = time.perf_counter()


def _count_lazy_imports() -> int:
    """统计"已声明懒加载但尚未真正 import"的重依赖数（卷191-B3）。

    目前纳入统计：litellm（首次 import 约 8.9s，见 apiserver/litellm_lazy.py）。
    返回值用于 boot 摘要行的 `lazy=` 字段，方便回归时确认懒加载仍在生效
    （若为 0，说明有模块又把 litellm 提前 import 了）。
    """
    try:
        from apiserver import litellm_lazy
        return 0 if litellm_lazy._litellm_module is not None else 1
    except Exception:
        return 0

import shutil
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 流式文本处理模块（仅用于TTS）
from . import naga_auth  # NagaCAS 认证模块
from .llm_service import get_llm_service  # 导入LLM服务
from .message_manager import message_manager  # 导入统一的消息管理器

# 记录哪些会话曾发送过图片，后续消息继续走 VLM 直到新会话
_vlm_sessions: set = set()

# 导入配置系统
try:
    from system.config import (  # 使用新的配置系统  # 导入提示词仓库
        AI_NAME,
        VERSION,  # 版本号（唯一来源：pyproject.toml）
        build_context_supplement,
        build_system_prompt,
        get_config,
        get_prompt,
    )
    from system.config_manager import get_config_snapshot, update_config  # 导入配置管理
except ImportError:
    import os
    import sys

    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from system.config import (  # 导入提示词仓库
        VERSION,  # 版本号（唯一来源：pyproject.toml）
        build_context_supplement,
        build_system_prompt,
        get_config,  # 使用新的配置系统
    )
    from system.config_manager import get_config_snapshot, update_config  # 导入配置管理

# 对话核心功能已集成到apiserver


# 统一保存对话与日志函数 - 已整合到message_manager
def _save_conversation_and_logs(session_id: str, user_message: str, assistant_response: str,
                                assistant_reasoning: str | None = None):
    """统一保存对话历史与日志 - 委托给message_manager

    assistant_reasoning：本轮思考链（可选），随正文落盘供重进会话回显。
    """
    message_manager.save_conversation_and_logs(session_id, user_message, assistant_response,
                                              assistant_reasoning)


async def _notify_conversation_event(event: str):
    """通知 agent_server 对话生命周期事件"""
    try:
        import httpx

        from system.config import get_server_port

        async with httpx.AsyncClient(timeout=3.0, proxy=None) as client:
            await client.post(
                f"http://localhost:{get_server_port('agent_server')}/dogtag/conversation_event",
                json={"event": event},
            )
        logger.info(f"[ConversationEvent] 已通知 agent_server: {event}")
    except Exception as e:
        logger.debug(f"[ConversationEvent] 通知失败: {e}")


def _bg_index_vault() -> None:
    """后台 Vault 索引任务：启动时异步建库，不阻塞 API 服务器。

    索引是 CPU/IO 密集操作，由 lifespan 通过 asyncio.to_thread 丢到
    线程池执行；失败仅告警不阻断启动（索引可后续手动触发）。
    """
    try:
        from rag.vault_indexer import get_vault_indexer

        indexer = get_vault_indexer()
        result = indexer.index_vault()
        logger.info(f"[Vault] 后台索引完成: {result}")
    except Exception as e:
        logger.warning(f"[Vault] 后台索引失败（非致命，可稍后手动重建）: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    try:
        print("[INFO] 正在初始化API服务器...")

        # 异步加载加密的 refresh_token（陆墨定制：安全封坑期）
        try:
            from apiserver.naga_auth import _load_refresh_token as _async_load_token
            await _async_load_token()
        except Exception as e:
            print(f"[WARN] Token加载失败（可忽略首次启动）: {e}")

        # 对话核心功能已集成到apiserver

        # 卷192-C：数据库 schema 版本登记（轻量迁移 runner，幂等；不动现有表）
        # 与卷191 启动优化协同——只做版本表登记，不重复打点。
        try:
            from apiserver.db_migrations.runner import apply_all as _apply_migrations
            _results = await asyncio.to_thread(_apply_migrations)
            _done = [r for r in _results if r.to_version >= 0]
            _failed = [r for r in _results if r.to_version < 0]
            print(f"[INFO] db_migrations: {len(_done)} 库已登记 schema_version"
                  + (f"，{len(_failed)} 库失败" if _failed else ""))
            for _r in _failed:
                print(f"[WARN] db_migrations 失败: {_r.db} — {_r.note}")
        except Exception as e:
            print(f"[WARN] db_migrations 初始化失败（不影响主链路）: {e}")

        # 加载活跃角色配置
        try:
            from system.config import get_config as _gc
            from system.config import set_active_character
            char_name = _gc().system.active_character
            set_active_character(char_name)
        except Exception as e:
            print(f"[WARN] 角色加载失败，使用默认提示词目录: {e}")

        try:
            from apiserver.telemetry import get_telemetry_manager
            await get_telemetry_manager().start()
        except Exception as e:
            print(f"[WARN] Telemetry 初始化失败: {e}")

        # M3.1a EventBus v2 消费者热插拔注册（lumo_state → lumo_proactive 顺序：
        # emit 时 state 先同步更新快照，proactive 再读最新快照触发搭话决策）
        try:
            from apiserver.event_bus import get_bus
            from apiserver.event_bus.handlers import (
                register_proactive_consumer,
                register_state_consumer,
            )
            from apiserver.routes.lumo_proactive import get_decider
            from apiserver.routes.lumo_state import get_state_store

            _bus = get_bus()
            register_state_consumer(_bus, get_state_store())
            register_proactive_consumer(_bus, get_decider())
            print("[INFO] EventBus v2 消费者已注册（lumo_state / lumo_proactive）")

            # W119-03：工具调用安全门（TOOL_PRE_EXECUTE waterfall：审计 / 敏感工具 / 熔断）
            try:
                from apiserver.event_bus.tool_gate import register_tool_gates

                register_tool_gates(_bus)
                print("[INFO] 工具安全门已注册（w119-03）")
            except Exception as gate_err:
                print(f"[WARN] 工具安全门注册失败（可忽略）: {gate_err}")

            # W124-03：工具三段管道的 guard 阶段（参数校验；给不走 loop 的调用方同一套规则）
            try:
                from apiserver.event_bus.tool_pipeline import register_guard

                register_guard(_bus)
            except Exception as guard_err:
                print(f"[WARN] guard 阶段注册失败（可忽略）: {guard_err}")

            # 卷187-D：哨兵占用事件落地（lumo.sentinel.occupation → sentinel_occupation 表）
            # 检测器在网关注入事件，这里只负责把事件写进与 HamLog/记忆同库的记录表。
            try:
                from mcpserver.rf_brain.sentinel_link.occupation import OccupationHandler

                _occ_handler = OccupationHandler()
                _occ_handler.attach(_bus)
                print("[INFO] 哨兵占用事件消费者已注册（卷187-D）")
            except Exception as occ_err:
                print(f"[WARN] 哨兵占用消费者注册失败（可忽略）: {occ_err}")

            # W121-03：写操作确认门（TOOL_PRE_EXECUTE 上再挂一道 handler，先给 diff 再落盘）
            try:
                from apiserver.event_bus.confirm_gate import register_confirm_gate

                register_confirm_gate(_bus)
                print("[INFO] 写操作确认门已注册（w121-03）")
            except Exception as gate_err:
                print(f"[WARN] 写操作确认门注册失败（可忽略）: {gate_err}")

            # W131-06：device_state 消费者（USER_INPUT_RECEIVED → 会话活动追踪）
            try:
                from apiserver.device_state import get_device_state_store
                from apiserver.event_bus.topics import Topics as _BusTopics

                def _track_session_activity(event) -> None:
                    """会话活动痕迹（感知层联动：有交互 → 设备相关性权重微升）。"""
                    try:
                        store = get_device_state_store()
                        store.heartbeat("lumo_session")  # 会话本身作为一个"设备"在线
                    except Exception:
                        pass

                _bus.on(_BusTopics.USER_INPUT_RECEIVED, _track_session_activity)
                get_device_state_store().register("lumo_session")
                print("[INFO] device_state 消费者已注册（w131-06）")
            except Exception as dev_err:
                print(f"[WARN] device_state 消费者注册失败（可忽略）: {dev_err}")

            # 渠道网关层：多渠道消息入口（channels 段配置；默认只开 webhook 零风险）
            try:
                from apiserver.channels import init_channels_from_config
                from system.config import get_config as _get_config

                _ch_cfg = {}
                try:
                    _ch_cfg = dict(getattr(_get_config(), "channels", {}) or {})
                except Exception:
                    _ch_cfg = {}
                _regs = init_channels_from_config(_ch_cfg)
                print(f"[INFO] 渠道网关已初始化（{[s['name'] for s in _regs.status()]}）")
            except Exception as ch_err:
                print(f"[WARN] 渠道网关初始化失败（可忽略）: {ch_err}")

            # 卷123 W123-05：空闲任务提示挂到 SCHEDULER_TICK（默认关，见 task_flow.idle_advance）
            try:
                from apiserver.task_flow import register_scheduler_advice

                if register_scheduler_advice(_bus) is not None:
                    print("[INFO] 空闲任务提示已挂到调度发号器（w123-05）")
            except Exception as task_err:
                print(f"[WARN] 空闲任务提示注册失败（可忽略）: {task_err}")

            # W119-04：跨总线桥（Lumo ↔ mcpserver workflow；命令方向走 NEKO 既有注入路由）
            try:
                from apiserver.event_bus.bridge import NekoHttpTransport, setup_bridges
                from mcpserver.mcp_registry import get_service_instance

                workflow_instance = get_service_instance("workflow")
                workflow_bus = getattr(workflow_instance, "event_bus", None)
                neko_transport = NekoHttpTransport()
                if not neko_transport.available():
                    print("[WARN] LUMO_PROXY_TOKEN 未设置，NEKO 桥命令方向不启用（只挂 workflow 桥）")
                    neko_transport = None
                setup_bridges(_bus, workflow_bus=workflow_bus, neko_transport=neko_transport)
                print(
                    "[INFO] 跨总线桥已挂载（w119-04: Lumo ↔ workflow"
                    + ("; Lumo → NEKO 注入路由" if neko_transport is not None else "")
                    + "）"
                )
            except Exception as bridge_err:
                print(f"[WARN] 跨总线桥挂载失败（可忽略）: {bridge_err}")
            # W120-03：记忆事件化消费者（summer_memory 旁路：统计 + 分层 + 压缩钩子）
            try:
                from apiserver.event_bus.handlers import register_summer_memory_consumer
                from apiserver.event_bus.memory_lifecycle import get_memory_consumer
                from apiserver.event_bus.topics import Topics as _BusTopics

                _memory_consumer = get_memory_consumer(_bus)
                if _memory_consumer is not None:
                    register_summer_memory_consumer(_bus, _memory_consumer)
                    _bus.on(_BusTopics.MEMORY_ARCHIVED, _memory_consumer.on_memory_archived)
                    print("[INFO] 记忆生命周期消费者已注册（w120-03：created/archived + 分层）")
            except Exception as mem_err:
                print(f"[WARN] 记忆消费者注册失败（可忽略）: {mem_err}")
        except Exception as e:
            print(f"[WARN] EventBus v2 消费者注册失败（可忽略）: {e}")

        # M3.1b 主动搭话兜底（W120-02：优先走 SCHEDULER_TICK 总线；关闭或失败时回落原定时器）
        try:
            import asyncio as _asyncio

            from apiserver.routes.lumo_proactive import get_decider

            _use_bus = True
            try:
                from system.config import get_config

                _use_bus = bool(get_config().bus.scheduler.use_bus)
            except Exception as cfg_err:
                print(f"[WARN] 读取 scheduler 配置失败，默认走总线: {cfg_err}")

            if _use_bus:
                from apiserver.event_bus.scheduler import (
                    register_scheduler_subscriber,
                    start_scheduler,
                )

                register_scheduler_subscriber(_bus, get_decider().on_scheduler_tick)
                scheduler = start_scheduler()
                print(
                    "[INFO] 调度已总线化（w120-02：SCHEDULER_TICK 档位 "
                    + ", ".join(scheduler.ticks if scheduler is not None else [])
                    + "）"
                )
            else:
                _asyncio.get_running_loop().create_task(get_decider()._periodic_check())
                print("[INFO] 调度走兜底定时器（bus.scheduler.use_bus=false）")
        except Exception as e:
            print(f"[WARN] 调度总线化失败，回落兜底定时器: {e}")
            try:
                import asyncio as _asyncio2

                from apiserver.routes.lumo_proactive import get_decider as _gd

                _asyncio2.get_running_loop().create_task(_gd()._periodic_check())
                print("[INFO] M3.1b 主动搭话定时器已启动（兜底）")
            except Exception as fallback_err:
                print(f"[WARN] 兜底定时器启动失败（可忽略）: {fallback_err}")

        # Vault 后台索引：启动即异步建库；create_task 挂到 app.state 持有引用防 GC
        try:
            app.state.vault_index_task = asyncio.create_task(
                asyncio.to_thread(_bg_index_vault)
            )
            print("[INFO] Vault 后台索引任务已启动")
        except Exception as e:
            print(f"[WARN] Vault 后台索引启动失败（可忽略）: {e}")

        print("[SUCCESS] API服务器初始化完成")
        # 卷191-B3：启动自检摘要行（total = 模块加载 + lifespan 初始化）
        try:
            _boot_total = time.perf_counter() - _BOOT_T0
            _n_routes = len(getattr(app, "routes", []))
            _lazy = _count_lazy_imports()
            print(f"[boot] total={_boot_total:.2f}s routes={_n_routes} lazy={_lazy}")
        except Exception as e:
            print(f"[WARN] boot 摘要输出失败（可忽略）: {e}")
        yield
    except Exception as e:
        print(f"[ERROR] API服务器初始化失败: {e}")
        traceback.print_exc()
        sys.exit(1)
    finally:
        print("[INFO] 正在清理资源...")
        # MCP服务现在由mcpserver独立管理，无需清理
        try:
            from apiserver.telemetry import get_telemetry_manager
            await get_telemetry_manager().shutdown()
        except Exception as e:
            print(f"[WARN] Telemetry 清理失败: {e}")


# 创建FastAPI应用
app = FastAPI(title="陆墨 API", description="智能对话助手API服务", version=VERSION, lifespan=lifespan)

# 配置CORS — 统一使用 system.cors_config 中的 apply_local_cors
# 说明：原手写配置仅支持 http、缺少 OPTIONS 预检方法，与其他服务不一致。
#       统一后支持 https + 本机 + 任意端口，并补齐 OPTIONS，避免预检请求失败。
from system.cors_config import apply_local_cors

apply_local_cors(app)


# 免本地 token 校验的公开路径前缀（登录类接口、静态资源、文档/健康检查）
_PUBLIC_PATH_PREFIXES = (
    "/auth/login", "/auth/register", "/auth/refresh", "/auth/captcha",
    "/auth/send-verification", "/auth/send-qq-verification", "/auth/qq-email",
    "/characters", "/custom-live2d", "/docs", "/redoc", "/openapi.json",
    "/health", "/api/status/heartbeat", "/api/status/nodes",
)

# 前端引导期（未登录）只读探测路径：仅 GET 放行，写操作仍需 token；
# 路由层会对未登录请求返回的敏感字段做脱敏
_BOOTSTRAP_GET_PREFIXES = ("/system/config", "/system/info")


_TRACE_PATH_PREFIXES = ("/api/chat", "/v1/chat/completions", "/persona/", "/api/lumo/event")


@app.middleware("http")
async def trace_conversation_requests(request: Request, call_next):
    """W120-01：对话链路开启 trace 并把 trace_id 回写响应头（其余路径直通，零开销）。

    说明：BaseHTTPMiddleware 在子任务里执行内层 app，子任务继承 context 的**副本**；
    这里 set 的 TraceContext 对象被子任务共享（span 是往同一对象 append），
    因此中间件结束时归档能拿到端点内记录的全部 span。流式响应下 span 覆盖到「响应对象返回」为止。
    """
    path = request.url.path
    if not path.startswith(_TRACE_PATH_PREFIXES):
        return await call_next(request)

    from apiserver.event_bus import trace as bus_trace

    token = bus_trace.start_trace(
        path=path,
        method=request.method,
        session_id=request.headers.get("x-session-id") or "",
    )
    trace_id = bus_trace.get_or_create_trace_id()
    _started = time.perf_counter()
    try:
        with bus_trace.trace_span(f"http:{request.method} {path}") as span:
            response = await call_next(request)
            span.attributes["status_code"] = response.status_code
        response.headers["X-Lumo-Trace-Id"] = trace_id
        # W120-04：请求指标（O(1) 计数，不阻塞）
        try:
            from apiserver.telemetry import record_request_metric

            record_request_metric(
                path=path,
                method=request.method,
                status=int(response.status_code),
                duration_ms=(time.perf_counter() - _started) * 1000,
            )
        except Exception:  # noqa: BLE001
            pass
        return response
    finally:
        bus_trace.end_trace(token)


@app.middleware("http")
async def sync_auth_token(request: Request, call_next):
    """生产级加固：请求级 token 上下文 + 本地 token 校验

    - 非公开路径必须携带与当前有效全局 token 一致的 Bearer token，否则 401
    - 每个请求独立拥有自己的 token 上下文，请求结束后清除，不再修改全局 token
    """
    try:
        # CORS 预检不携带 Authorization，直接放行
        if request.method == "OPTIONS":
            return await call_next(request)

        # 本地免鉴权模式（require_auth=False）：直接放行，
        # 与 require_local_auth 语义一致——否则未登录时所有接口 401
        if not naga_auth.is_auth_required():
            return await call_next(request)

        auth_header = request.headers.get("authorization", "")
        token = auth_header[7:] if auth_header.startswith("Bearer ") else ""
        path = request.url.path
        is_public = path.startswith(_PUBLIC_PATH_PREFIXES)

        if token:
            # 校验 token 是否与当前有效全局 token 一致
            valid_token = naga_auth.get_access_token()
            if not is_public and (not valid_token or token != valid_token):
                return JSONResponse(status_code=401, content={"detail": "token 无效或已过期，请重新登录"})
            # 从全局 token 中查找用户信息（兼容现有逻辑）
            user = naga_auth.get_user_info()
            naga_auth.set_request_context(token, user)
        elif not is_public:
            if request.method == "GET" and path.startswith(_BOOTSTRAP_GET_PREFIXES):
                # 引导期只读探测放行（路由层已脱敏敏感字段）
                pass
            else:
                return JSONResponse(status_code=401, content={"detail": "缺少认证 token"})

        response = await call_next(request)
        return response
    finally:
        # 确保请求结束后清除上下文，防止内存泄漏
        naga_auth.clear_request_context()


# 挂载静态文件
from fastapi.staticfiles import StaticFiles as _StaticFiles

from system.config import CHARACTERS_DIR as _CHARACTERS_DIR
from system.live2d_assets import CUSTOM_LIVE2D_DIR as _CUSTOM_LIVE2D_DIR

if _CHARACTERS_DIR.exists():
    app.mount("/characters", _StaticFiles(directory=str(_CHARACTERS_DIR)), name="characters")
else:
    # 容错：目录缺失时不阻塞 API 启动，避免打包缺资源导致 8000 端口起不来
    try:
        _CHARACTERS_DIR.mkdir(parents=True, exist_ok=True)
        logger.warning(f"角色目录缺失，已创建空目录: {_CHARACTERS_DIR}")
        app.mount("/characters", _StaticFiles(directory=str(_CHARACTERS_DIR)), name="characters")
    except Exception as e:
        logger.error(f"角色静态目录初始化失败，将跳过 /characters 挂载: {e}")

try:
    _CUSTOM_LIVE2D_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/custom-live2d", _StaticFiles(directory=str(_CUSTOM_LIVE2D_DIR)), name="custom-live2d")
except Exception as e:
    logger.error(f"自定义 Live2D 静态目录初始化失败，将跳过 /custom-live2d 挂载: {e}")

# ============ 运行时状态检查（naga_control） ============


def _is_voice_runtime_paused() -> bool:
    """检查语音是否被 naga_control 运行时暂停"""
    try:
        from apiserver.naga_control import is_voice_paused
        return is_voice_paused()
    except Exception:
        return False


# ============ 内部服务代理 ============


async def _call_agentserver(
    method: str,
    path: str,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
    timeout_seconds: float = 15.0,
) -> Any:
    """调用 agentserver 内部接口（用于透传 OpenClaw 状态查询等能力）"""
    import httpx

    from system.config import get_server_port

    port = get_server_port("agent_server")
    url = f"http://127.0.0.1:{port}{path}"
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds, trust_env=False) as client:
            resp = await client.request(method, url, params=params, json=json_body)
    except Exception as e:
        # M3 修复：不向客户端泄露内部 URL/端口/异常详情
        logger.warning("[agentserver proxy] 不可达: %s", e)
        raise HTTPException(status_code=503, detail="upstream unavailable")
    if resp.status_code >= 400:
        # M3 修复：上游错误体可能含内部信息，用通用消息
        logger.warning("[agentserver proxy] upstream %d: %s", resp.status_code, resp.text[:200])
        raise HTTPException(status_code=resp.status_code, detail="upstream error")
    try:
        return resp.json()
    except Exception:
        return resp.text


# ============ Pydantic 请求/响应模型 ============


class ChatRequest(BaseModel):
    message: str
    stream: bool = False
    session_id: str | None = None
    agent_id: str | None = None
    disable_tts: bool = False  # V17: 支持禁用服务器端TTS
    return_audio: bool = False  # V19: 支持返回音频URL供客户端播放
    skill: str | None = None  # 用户主动选择的技能名称，注入完整指令到系统提示词
    images: list[str] | None = None  # 截屏图片 base64 数据列表（data:image/png;base64,...）
    temporary: bool = False  # 临时会话标记，临时会话不持久化到磁盘


class ChatResponse(BaseModel):
    response: str
    reasoning_content: str | None = None  # COT 思考过程内容
    session_id: str | None = None
    status: str = "success"


class SystemInfoResponse(BaseModel):
    version: str
    status: str
    available_services: list[str]
    api_key_configured: bool


class FileUploadResponse(BaseModel):
    filename: str
    file_path: str
    file_size: int
    file_type: str
    upload_time: str
    status: str = "success"
    message: str = "文件上传成功"


class DocumentProcessRequest(BaseModel):
    file_path: str
    action: str = "read"  # read, analyze, summarize
    session_id: str | None = None


# 挂载LLM服务路由以支持 /llm/chat
from .llm_service import llm_app

app.mount("/llm", llm_app)


# ============ 注册路由模块 ============

from .routes.appearance import router as appearance_router
from .routes.apps import router as apps_router
from .routes.auth import router as auth_router
from .routes.bus_dump import router as bus_dump_router  # W119-01: 总线可观测 dump
from .routes.eda_ingest import router as eda_ingest_router  # 工单217: EDA parasite-export 接收端
from .routes.knowledge_openai import router as knowledge_openai_router  # 工单217-A: 知识检索型 OpenAI 兼容端点
from .routes.channels import router as channels_router  # 渠道网关层：多渠道消息入口
from .routes.chat import router as chat_router
from .routes.data_tools import router as data_tools_router
from .routes.device import (
    checkpoint_router,  # W131-03: loop 快照/resume
    knowledge_router,  # W131-04: 知识摄取/推荐
)
from .routes.device import router as device_router  # W131-05: 设备状态感知
from .routes.domains import router as domains_router  # 卷162: 领域包机制（/api/domains）
from .routes.eln import router as eln_router
from .routes.extensions import router as extensions_router
from .routes.law_cases import router as law_cases_router  # 卷163: 法学判例导入
from .routes.lumo_event import router as lumo_event_router
from .routes.lumo_proxy import router as lumo_proxy_router
from .routes.openai_proxy import router as openai_proxy_router
from .routes.papers import router as papers_router
from .routes.persona import router as persona_router
from .routes.radio import router as radio_router
from .routes.rag import router as rag_router
from .routes.sentinel import router as sentinel_router  # 卷187: 哨兵网格
from .routes.session import router as session_router
from .routes.status_heartbeat import router as status_heartbeat_router
from .routes.sync import router as sync_router
from .routes.system import router as system_router
from .routes.telemetry import router as telemetry_router
from .routes.tools import router as tools_router
from .routes.tools_health import router as tools_health_router  # 卷189-B
from .routes.voice_eln import router as voice_eln_router

app.include_router(auth_router)
app.include_router(session_router)
app.include_router(system_router)
app.include_router(tools_router)
app.include_router(extensions_router)
app.include_router(chat_router)
app.include_router(openai_proxy_router)
app.include_router(lumo_proxy_router)
app.include_router(papers_router)  # W-02: 文献管理器
app.include_router(lumo_event_router)
app.include_router(telemetry_router)
app.include_router(bus_dump_router)  # W119-01: GET /debug/dump/bus[/events]
app.include_router(eda_ingest_router)  # 工单217: POST /api/eda/ingest
app.include_router(knowledge_openai_router)  # 工单217-A: POST /v1/knowledge/chat/completions
app.include_router(rag_router)
app.include_router(radio_router)  # X-01: IC-705 CI-V 串口控制面板 + HamLog 联动
app.include_router(persona_router)
app.include_router(appearance_router)
app.include_router(apps_router)
app.include_router(status_heartbeat_router)  # 战情面板：节点心跳广播
app.include_router(sync_router)  # H-01: yjs CRDT 同步端点
app.include_router(eln_router)  # V-01: ELN 实验记录本（Obsidian-based）
app.include_router(domains_router)  # 卷162: 领域包机制（GET /api/domains）
app.include_router(law_cases_router)  # 卷163: 法学判例导入（/api/domains/law/*）
app.include_router(data_tools_router)  # V-02: 实验数据工具台（TGA/DSC/XRD 导入+绘图）
app.include_router(voice_eln_router)  # X-02: 语音实验记录（ASR → ELN 草稿）
app.include_router(device_router)  # W131-05: 设备状态感知（/api/device/state）
app.include_router(knowledge_router)  # W131-04: 知识摄取（/api/knowledge/ingest）
app.include_router(checkpoint_router)  # W131-03: loop 快照（/api/agent/checkpoint|resume）
app.include_router(channels_router)  # 渠道网关层（/api/channels/webhook|status）
app.include_router(tools_health_router)  # 卷189-B: 工具健康（GET /tools/stats|circuit）
app.include_router(sentinel_router)  # 卷187: 哨兵网格（/sentinel/nodes|spectrum|env）
