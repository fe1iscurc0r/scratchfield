"""agent_server_parts.lifecycle —— 自 agentserver/agent_server.py 拆出（工单204 任务一，纯移动）。"""
from __future__ import annotations

from .common import *  # noqa: F401,F403
from .common import Modules, logger  # noqa: F401
from .session import _interrupt_travel_sessions, _resume_open_travel_sessions  # noqa: F401

async def _start_gateway_if_port_free(runtime: EmbeddedRuntime) -> bool:
    """主 Gateway 仅按主端口状态判定是否需要启动。"""
    if runtime.gateway_running:
        logger.info("当前进程中的 OpenClaw Gateway 已在运行，跳过启动")
        return False

    if runtime.is_gateway_port_in_use():
        logger.info(f"端口 {config.openclaw.gateway_port} 已被占用，跳过 Gateway 启动")
        return False

    if runtime.has_gateway_process():
        logger.info("检测到其他 OpenClaw Gateway 进程，但主端口空闲；继续尝试启动 20789 主 Gateway")

    gw_ok = await runtime.start_gateway()
    if gw_ok:
        logger.info("OpenClaw Gateway 启动成功")
    else:
        logger.warning("OpenClaw Gateway 启动失败")
    return gw_ok


def _on_config_changed() -> None:
    """配置变更监听器：自动更新 OpenClaw LLM 配置"""
    try:
        embedded_runtime = get_embedded_runtime()

        if embedded_runtime.is_vendor_ready:
            from agentserver.openclaw.llm_config_bridge import inject_naga_llm_config

            inject_naga_llm_config()
            logger.info("配置变更：已更新 OpenClaw LLM 配置")
    except Exception as e:
        logger.warning(f"配置变更时更新 OpenClaw 配置失败: {e}")


def _is_port_in_use(port: int) -> bool:
    """检测端口是否被占用"""
    import socket

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(("127.0.0.1", port))
        sock.close()
        return result == 0
    except Exception:
        return False


async def _delayed_health_check():
    """延迟健康检查（等待所有服务启动）"""
    await asyncio.sleep(6)  # 虚拟机/低性能环境下启动更慢，适当延长缓冲时间

    try:
        from system.health_check import perform_startup_health_check
        results, _summary = await perform_startup_health_check()

        # API 在慢机器上可能晚于首次检查就绪，做一次延迟复检避免启动早期误报
        api_result = results.get("api_server")
        api_unhealthy = (
            api_result is not None
            and getattr(getattr(api_result, "status", None), "value", "") == "unhealthy"
        )
        if api_unhealthy:
            logger.info("[HealthCheck] 检测到 API 尚未就绪，12 秒后执行一次复检")
            await asyncio.sleep(12)
            await perform_startup_health_check()
    except Exception as e:
        logger.error(f"启动时健康检查失败: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI应用生命周期"""
    # startup
    try:
        # 初始化 OpenClaw 客户端 - 三层回退策略
        try:
            from agentserver.openclaw import OpenClawConfig as ClientOpenClawConfig
            from agentserver.openclaw import detect_openclaw
            from agentserver.openclaw.llm_config_bridge import (
                ensure_gateway_local_mode,
                ensure_gateway_port,
                ensure_hooks_allow_request_session_key,
                ensure_hooks_path,
                ensure_openclaw_config,
                inject_naga_llm_config,
            )

            embedded_runtime = get_embedded_runtime()
            logger.info(f"OpenClaw 运行时模式: {embedded_runtime.runtime_mode}")
            logger.info(f"  vendor_root: {embedded_runtime.vendor_root}")
            logger.info(f"  node_path: {embedded_runtime.node_path}")
            logger.info(f"  is_vendor_ready: {embedded_runtime.is_vendor_ready}")

            # ── Step 1: 确保 vendor 就绪 + 配置 + onboard ──
            if not embedded_runtime.is_vendor_ready:
                await embedded_runtime.ensure_vendor_ready()

            if embedded_runtime.is_vendor_ready:
                ensure_openclaw_config()
                ensure_gateway_port(auto_create=False)
                ensure_gateway_local_mode(auto_create=False)
                ensure_hooks_path(auto_create=False)
                ensure_hooks_allow_request_session_key(auto_create=False)

                await embedded_runtime.ensure_onboarded()
                inject_naga_llm_config()

                # ── Step 1.5: 清理端口范围内的残留进程 ──
                try:
                    from agentserver.openclaw.instance_manager import cleanup_port_range
                    cleaned = cleanup_port_range()
                    if cleaned:
                        await asyncio.sleep(1)  # 等端口释放
                except Exception as e:
                    logger.warning(f"端口清理失败（可忽略）: {e}")

                # ── Step 2: 启动 Gateway（尊重 openclaw.enabled 开关，关闭时不自启） ──
                if config.openclaw.enabled:
                    await _start_gateway_if_port_free(embedded_runtime)
                else:
                    logger.info("openclaw.enabled=False，跳过 Gateway 自启（可在设置界面手动开启）")

            # 检测最终状态并初始化客户端
            openclaw_status = detect_openclaw(check_connection=False)

            if openclaw_status.installed:
                openclaw_config = ClientOpenClawConfig(
                    gateway_url=openclaw_status.gateway_url or config.openclaw.gateway_url,
                    gateway_token=openclaw_status.gateway_token,
                    hooks_token=openclaw_status.hooks_token,
                    hooks_path=getattr(openclaw_status, "hooks_path", "/hooks"),
                    timeout=config.openclaw.timeout,
                )
                logger.info(f"OpenClaw 配置: {openclaw_config.gateway_url}")
                logger.info(
                    f"  - gateway_token: {'***' + openclaw_config.gateway_token[-8:] if openclaw_config.gateway_token else '未配置'}"
                )
                logger.info(
                    f"  - hooks_token: {'***' + openclaw_config.hooks_token[-8:] if openclaw_config.hooks_token else '未配置'}"
                )
            else:
                openclaw_config = ClientOpenClawConfig(
                    gateway_url=config.openclaw.gateway_url,
                    gateway_token=config.openclaw.token,
                    hooks_token=config.openclaw.token,
                    timeout=config.openclaw.timeout,
                )
                logger.info(f"OpenClaw 未检测到安装，使用配置文件: {openclaw_config.gateway_url}")

            Modules.openclaw_client = get_openclaw_client(openclaw_config)
            Modules.openclaw_client.restore_session()
            logger.info(f"OpenClaw客户端初始化完成: {openclaw_config.gateway_url}")
        except Exception as e:
            logger.warning(f"OpenClaw客户端初始化失败（可选功能）: {e}")
            Modules.openclaw_client = None

        # 初始化干员多实例管理器（通讯录模式：只恢复列表，不启动进程）
        try:
            from agentserver.openclaw.instance_manager import InstanceManager
            embedded_runtime = get_embedded_runtime()
            Modules.instance_manager = InstanceManager(embedded_runtime, primary_client=Modules.openclaw_client)
            logger.info("干员多实例管理器已初始化")
            # 从 manifest 恢复通讯录（不启动进程）
            try:
                agents = Modules.instance_manager.restore_from_manifest()
                logger.info(f"通讯录恢复完成，共 {len(agents)} 个干员")
            except Exception as e:
                logger.warning(f"恢复通讯录失败（可忽略）: {e}")
            try:
                await _resume_open_travel_sessions()
            except Exception as e:
                logger.warning(f"恢复探索任务失败（可忽略）: {e}")
        except Exception as e:
            logger.warning(f"干员多实例管理器初始化失败（可选功能）: {e}")
            Modules.instance_manager = None

        # 注册配置变更监听器
        add_config_listener(_on_config_changed)
        logger.debug("已注册 OpenClaw 配置变更监听器")

        # 初始化军牌系统（统一后台任务调度）
        try:
            from agentserver.dogtag import (
                create_dogtag_scheduler,
                create_heartbeat_executor,
                create_proactive_analyzer,
                create_proactive_trigger,
                get_dogtag_registry,
                load_heartbeat_config,
                load_proactive_config,
            )
            from agentserver.dogtag.duties.heartbeat_duty import create_heartbeat_duty
            from agentserver.dogtag.duties.screen_vision_duty import create_screen_vision_duty

            # 1. 初始化子组件
            pv_config = load_proactive_config()
            create_proactive_trigger()
            create_proactive_analyzer(pv_config)

            hb_config = load_heartbeat_config()
            create_heartbeat_executor(hb_config)

            # 2. 创建军牌调度器
            Modules.dogtag_scheduler = create_dogtag_scheduler()
            registry = get_dogtag_registry()

            # 3. 注册职责
            hb_tag, hb_exec = create_heartbeat_duty(hb_config)
            registry.register(hb_tag, hb_exec)

            sv_tag, sv_exec = create_screen_vision_duty(pv_config)
            registry.register(sv_tag, sv_exec)

            # 4. 启动调度器
            await Modules.dogtag_scheduler.start()
            logger.info("[DogTag] 军牌系统已启动")
        except Exception as e:
            logger.warning(f"[DogTag] 军牌系统初始化失败（可选功能）: {e}")
            Modules.dogtag_scheduler = None

        logger.info("陆墨服务初始化完成")

        # 执行启动时健康检查（延迟2秒等待所有服务就绪）
        asyncio.create_task(_delayed_health_check())

    except Exception as e:
        logger.error(f"服务初始化失败: {e}")
        raise

    # 运行期
    yield

    # shutdown
    try:
        # 停止军牌系统
        if Modules.dogtag_scheduler:
            await Modules.dogtag_scheduler.stop()
            logger.info("[DogTag] 军牌系统已停止")

        # 关闭心跳执行器的 HTTP 客户端
        from agentserver.dogtag import get_heartbeat_executor
        hb_executor = get_heartbeat_executor()
        if hb_executor:
            await hb_executor.close()

        # 停止所有干员子实例（主 Gateway 由下方 stop_gateway 处理）
        interrupted_ids = await _interrupt_travel_sessions(reason="shutdown")
        if interrupted_ids:
            logger.info(f"[旅行] 服务关闭前已中断 {len(interrupted_ids)} 个探索任务")

        if Modules.instance_manager:
            await Modules.instance_manager.destroy_all()
            logger.info("干员多实例已全部停止")

        # 停止 Gateway 进程（内嵌模式）
        embedded_runtime = get_embedded_runtime()
        if embedded_runtime.gateway_running:
            await embedded_runtime.stop_gateway()

        logger.info("陆墨服务已关闭")
    except Exception as e:
        logger.error(f"服务关闭失败: {e}")


app = FastAPI(title="陆墨 Server", version="1.0.0", lifespan=lifespan)


apply_local_cors(app)
