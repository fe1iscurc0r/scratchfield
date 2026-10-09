"""
服务健康检查和连通性诊断系统
检查所有服务的端口、API连接、依赖等
"""

import asyncio
import logging
import socket
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
import threading

logger = logging.getLogger(__name__)


class ServiceStatus(Enum):
    """服务状态"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class HealthCheckResult:
    """健康检查结果"""
    service_name: str
    status: ServiceStatus
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    checks: list[dict[str, Any]] = field(default_factory=list)
    latency_ms: float | None = None


class HealthChecker:
    """健康检查器"""

    def __init__(self):
        from system.config import get_config, get_server_port

        self.ports = {
            "api_server": get_server_port("api_server"),
            "agent_server": get_server_port("agent_server"),
            "mcp_server": get_server_port("mcp_server"),
            "tts_server": get_server_port("tts_server"),
            "asr_server": get_server_port("asr_server"),
        }
        cfg = get_config()
        self.api_enabled = bool(getattr(cfg.api_server, "enabled", True) and getattr(cfg.api_server, "auto_start", True))

    async def check_all(self) -> dict[str, HealthCheckResult]:
        """检查所有服务"""
        results = {}

        # 并发检查所有服务
        tasks = {
            "api_server": self.check_api_server(),
            "agent_server": self.check_agent_server(),
            "mcp_server": self.check_mcp_server(),
            "screen_vision_mcp": self.check_screen_vision_mcp(),
            "proactive_vision": self.check_proactive_vision(),
            "websocket": self.check_websocket(),
        }

        for service_name, task in tasks.items():
            try:
                results[service_name] = await task
            except Exception as e:
                logger.error(f"[HealthCheck] 检查 {service_name} 失败: {e}")
                results[service_name] = HealthCheckResult(
                    service_name=service_name,
                    status=ServiceStatus.UNKNOWN,
                    message=f"检查失败: {e}",
                )

        return results

    async def check_port(self, host: str, port: int, timeout: float = 2.0) -> bool:
        """检查端口是否可连接"""
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port),
                timeout=timeout
            )
            writer.close()
            await writer.wait_closed()
            return True
        except (TimeoutError, ConnectionRefusedError, OSError):
            return False

    async def wait_port_ready(
        self,
        host: str,
        port: int,
        retries: int = 6,
        interval_seconds: float = 0.5,
        timeout: float = 2.0,
    ) -> bool:
        """等待端口就绪（用于虚拟机/慢机器上的启动抖动）"""
        for i in range(max(1, retries)):
            if await self.check_port(host, port, timeout=timeout):
                return True
            if i < retries - 1:
                await asyncio.sleep(interval_seconds)
        return False

    async def check_http_endpoint(self, url: str, timeout: float = 5.0) -> dict[str, Any]:
        """检查HTTP端点"""
        import time

        import httpx

        start = time.time()
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.get(url)
                latency_ms = (time.time() - start) * 1000

                return {
                    "success": True,
                    "status_code": resp.status_code,
                    "latency_ms": round(latency_ms, 2),
                    "ok": 200 <= resp.status_code < 300,
                }
        except httpx.ConnectError:
            return {
                "success": False,
                "error": "无法连接",
                "error_type": "connection_refused",
            }
        except httpx.TimeoutException:
            return {
                "success": False,
                "error": "连接超时",
                "error_type": "timeout",
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "error_type": "unknown",
            }

    async def check_api_server(self) -> HealthCheckResult:
        """检查API Server"""
        if not self.api_enabled:
            return HealthCheckResult(
                service_name="api_server",
                status=ServiceStatus.HEALTHY,
                message="API Server 已禁用，跳过检查",
                details={"enabled": False},
            )

        port = self.ports["api_server"]
        checks = []

        # 1. 检查端口
        port_ok = await self.wait_port_ready("127.0.0.1", port, retries=8, interval_seconds=0.5, timeout=1.5)
        checks.append({
            "name": "port_connectivity",
            "passed": port_ok,
            "message": f"端口 {port} {'可连接' if port_ok else '不可连接（可能仍在启动）'}",
        })

        if not port_ok:
            return HealthCheckResult(
                service_name="api_server",
                status=ServiceStatus.UNHEALTHY,
                message=f"API Server 端口 {port} 不可用",
                checks=checks,
            )

        # 2. 检查健康端点（假设有/health）
        health_check = await self.check_http_endpoint(f"http://127.0.0.1:{port}/health")
        checks.append({
            "name": "health_endpoint",
            "passed": health_check.get("success") and health_check.get("ok"),
            "details": health_check,
        })

        # 3. 检查WebSocket统计端点
        ws_stats_check = await self.check_http_endpoint(f"http://127.0.0.1:{port}/ws/stats")
        checks.append({
            "name": "websocket_stats",
            "passed": ws_stats_check.get("success") and ws_stats_check.get("ok"),
            "details": ws_stats_check,
        })

        # 判断整体状态
        passed_count = sum(1 for c in checks if c.get("passed"))
        total_count = len(checks)

        if passed_count == total_count:
            status = ServiceStatus.HEALTHY
            message = f"API Server 健康 ({port})"
        elif passed_count > 0:
            status = ServiceStatus.DEGRADED
            message = f"API Server 部分功能可用 ({passed_count}/{total_count})"
        else:
            status = ServiceStatus.UNHEALTHY
            message = "API Server 不健康"

        return HealthCheckResult(
            service_name="api_server",
            status=status,
            message=message,
            checks=checks,
            details={"port": port},
            latency_ms=health_check.get("latency_ms"),
        )

    async def check_agent_server(self) -> HealthCheckResult:
        """检查Agent Server"""
        port = self.ports["agent_server"]
        checks = []

        # 1. 检查端口
        port_ok = await self.check_port("127.0.0.1", port)
        checks.append({
            "name": "port_connectivity",
            "passed": port_ok,
            "message": f"端口 {port} {'可连接' if port_ok else '不可连接'}",
        })

        if not port_ok:
            return HealthCheckResult(
                service_name="agent_server",
                status=ServiceStatus.UNHEALTHY,
                message=f"Agent Server 端口 {port} 不可用",
                checks=checks,
            )

        # 2. 检查健康端点
        health_check = await self.check_http_endpoint(f"http://127.0.0.1:{port}/health")
        checks.append({
            "name": "health_endpoint",
            "passed": health_check.get("success") and health_check.get("ok"),
            "details": health_check,
        })

        passed_count = sum(1 for c in checks if c.get("passed"))

        if passed_count == len(checks):
            status = ServiceStatus.HEALTHY
            message = f"Agent Server 健康 ({port})"
        elif passed_count > 0:
            status = ServiceStatus.DEGRADED
            message = "Agent Server 部分功能可用"
        else:
            status = ServiceStatus.UNHEALTHY
            message = "Agent Server 不健康"

        return HealthCheckResult(
            service_name="agent_server",
            status=status,
            message=message,
            checks=checks,
            details={"port": port},
            latency_ms=health_check.get("latency_ms"),
        )

    async def check_mcp_server(self) -> HealthCheckResult:
        """检查MCP Server"""
        port = self.ports["mcp_server"]
        checks = []

        # 1. 检查端口
        port_ok = await self.check_port("127.0.0.1", port)
        checks.append({
            "name": "port_connectivity",
            "passed": port_ok,
            "message": f"端口 {port} {'可连接' if port_ok else '不可连接'}",
        })

        if not port_ok:
            return HealthCheckResult(
                service_name="mcp_server",
                status=ServiceStatus.UNHEALTHY,
                message=f"MCP Server 端口 {port} 不可用",
                checks=checks,
            )

        # 2. 检查服务列表端点
        services_check = await self.check_http_endpoint(f"http://127.0.0.1:{port}/services")
        checks.append({
            "name": "services_endpoint",
            "passed": services_check.get("success") and services_check.get("ok"),
            "details": services_check,
        })

        # 3. 检查状态端点
        status_check = await self.check_http_endpoint(f"http://127.0.0.1:{port}/status")
        checks.append({
            "name": "status_endpoint",
            "passed": status_check.get("success") and status_check.get("ok"),
            "details": status_check,
        })

        passed_count = sum(1 for c in checks if c.get("passed"))

        if passed_count == len(checks):
            status = ServiceStatus.HEALTHY
            message = f"MCP Server 健康 ({port})"
        elif passed_count > 0:
            status = ServiceStatus.DEGRADED
            message = "MCP Server 部分功能可用"
        else:
            status = ServiceStatus.UNHEALTHY
            message = "MCP Server 不健康"

        return HealthCheckResult(
            service_name="mcp_server",
            status=status,
            message=message,
            checks=checks,
            details={"port": port},
            latency_ms=services_check.get("latency_ms"),
        )

    async def check_screen_vision_mcp(self) -> HealthCheckResult:
        """检查ScreenVision MCP服务"""
        port = self.ports["mcp_server"]
        checks = []

        # 1. 检查screen_vision服务是否注册
        services_check = await self.check_http_endpoint(f"http://127.0.0.1:{port}/services")
        service_registered = False

        if services_check.get("success") and services_check.get("ok"):
            try:
                import httpx
                async with httpx.AsyncClient(timeout=5.0) as client:
                    # 给服务注册一点缓冲时间，避免启动早期误报未注册
                    for i in range(4):
                        resp = await client.get(f"http://127.0.0.1:{port}/services")
                        if resp.status_code == 200:
                            data = resp.json()
                            services = data.get("services", {})
                            service_registered = "screen_vision" in services
                            if service_registered:
                                break
                        if i < 3:
                            await asyncio.sleep(0.5)
            except Exception:
                pass

        checks.append({
            "name": "service_registered",
            "passed": service_registered,
            "message": f"screen_vision 服务 {'已注册' if service_registered else '未注册'}",
        })

        # 2. 如果服务已注册，尝试调用
        if service_registered:
            call_check = await self.check_http_endpoint(
                f"http://127.0.0.1:{port}/call",
            )
            # 注意：这里只检查端点可访问性，不真正调用（避免截图开销）
            checks.append({
                "name": "call_endpoint",
                "passed": call_check.get("success"),
                "details": call_check,
            })

        passed_count = sum(1 for c in checks if c.get("passed"))

        if passed_count == len(checks) and service_registered:
            status = ServiceStatus.HEALTHY
            message = "ScreenVision MCP 服务健康"
        elif service_registered:
            status = ServiceStatus.DEGRADED
            message = "ScreenVision MCP 服务已注册但功能异常"
        else:
            # 屏幕视觉是可选能力（尤其在无图形环境/虚拟机中常不可用），记为降级而非硬失败
            status = ServiceStatus.DEGRADED
            message = "ScreenVision MCP 服务未注册（可选能力）"

        return HealthCheckResult(
            service_name="screen_vision_mcp",
            status=status,
            message=message,
            checks=checks,
        )

    async def check_proactive_vision(self) -> HealthCheckResult:
        """检查ProactiveVision系统"""
        agent_port = self.ports["agent_server"]
        checks = []

        # 1. 检查配置端点
        config_check = await self.check_http_endpoint(f"http://127.0.0.1:{agent_port}/proactive_vision/config")
        checks.append({
            "name": "config_endpoint",
            "passed": config_check.get("success") and config_check.get("ok"),
            "details": config_check,
        })

        # 2. 检查状态端点
        status_check = await self.check_http_endpoint(f"http://127.0.0.1:{agent_port}/proactive_vision/status")
        is_enabled = False
        is_running = False

        if status_check.get("success") and status_check.get("ok"):
            try:
                import httpx

                async with httpx.AsyncClient(timeout=5.0) as client:
                    resp = await client.get(f"http://127.0.0.1:{agent_port}/proactive_vision/status")
                    if resp.status_code == 200:
                        data = resp.json()
                        is_enabled = data.get("enabled", False)
                        is_running = data.get("running", False)
            except Exception:
                pass

        checks.append({
            "name": "status_endpoint",
            "passed": status_check.get("success") and status_check.get("ok"),
            "details": {"enabled": is_enabled, "running": is_running},
        })

        # 3. 检查metrics端点
        metrics_check = await self.check_http_endpoint(f"http://127.0.0.1:{agent_port}/proactive_vision/metrics")
        checks.append({
            "name": "metrics_endpoint",
            "passed": metrics_check.get("success") and metrics_check.get("ok"),
            "details": metrics_check,
        })

        passed_count = sum(1 for c in checks if c.get("passed"))

        if passed_count == len(checks):
            if is_enabled and is_running:
                status = ServiceStatus.HEALTHY
                message = "ProactiveVision 已启用且运行中"
            elif is_enabled:
                status = ServiceStatus.DEGRADED
                message = "ProactiveVision 已启用但未运行"
            else:
                status = ServiceStatus.HEALTHY
                message = "ProactiveVision 未启用（正常）"
        elif passed_count > 0:
            status = ServiceStatus.DEGRADED
            message = "ProactiveVision 部分功能可用"
        else:
            status = ServiceStatus.UNHEALTHY
            message = "ProactiveVision 不可用"

        return HealthCheckResult(
            service_name="proactive_vision",
            status=status,
            message=message,
            checks=checks,
            details={"enabled": is_enabled, "running": is_running},
        )

    async def check_websocket(self) -> HealthCheckResult:
        """检查WebSocket功能"""
        if not self.api_enabled:
            return HealthCheckResult(
                service_name="websocket",
                status=ServiceStatus.HEALTHY,
                message="WebSocket 依赖 API Server，API 已禁用，跳过检查",
                details={"enabled": False},
            )

        api_port = self.ports["api_server"]
        checks = []

        # API 端口未就绪时，WebSocket检查没有意义，标记为降级避免误报硬失败
        api_ready = await self.check_port("127.0.0.1", api_port, timeout=1.0)
        if not api_ready:
            checks.append({
                "name": "api_dependency",
                "passed": False,
                "message": f"API端口 {api_port} 未就绪，跳过WebSocket检查",
            })
            return HealthCheckResult(
                service_name="websocket",
                status=ServiceStatus.DEGRADED,
                message="WebSocket 依赖 API 服务，当前 API 未就绪",
                checks=checks,
            )

        # 1. 检查WebSocket统计端点
        stats_check = await self.check_http_endpoint(f"http://127.0.0.1:{api_port}/ws/stats")
        checks.append({
            "name": "ws_stats_endpoint",
            "passed": stats_check.get("success") and stats_check.get("ok"),
            "details": stats_check,
        })

        # 2. 检查WebSocket广播端点
        broadcast_check = await self.check_http_endpoint(f"http://127.0.0.1:{api_port}/ws/broadcast")
        # 注意：POST端点用GET会返回405，但说明端点存在
        endpoint_exists = broadcast_check.get("success") or broadcast_check.get("status_code") == 405
        checks.append({
            "name": "ws_broadcast_endpoint",
            "passed": endpoint_exists,
            "message": "广播端点存在" if endpoint_exists else "广播端点不存在",
        })

        passed_count = sum(1 for c in checks if c.get("passed"))

        if passed_count == len(checks):
            status = ServiceStatus.HEALTHY
            message = "WebSocket 功能健康"
        elif passed_count > 0:
            status = ServiceStatus.DEGRADED
            message = "WebSocket 部分功能可用"
        else:
            status = ServiceStatus.UNHEALTHY
            message = "WebSocket 功能不可用"

        return HealthCheckResult(
            service_name="websocket",
            status=status,
            message=message,
            checks=checks,
        )

    def get_summary(self, results: dict[str, HealthCheckResult]) -> dict[str, Any]:
        """获取健康检查摘要"""
        healthy_count = sum(1 for r in results.values() if r.status == ServiceStatus.HEALTHY)
        degraded_count = sum(1 for r in results.values() if r.status == ServiceStatus.DEGRADED)
        unhealthy_count = sum(1 for r in results.values() if r.status == ServiceStatus.UNHEALTHY)
        unknown_count = sum(1 for r in results.values() if r.status == ServiceStatus.UNKNOWN)

        total_count = len(results)
        overall_health = (healthy_count / total_count * 100) if total_count > 0 else 0

        if unhealthy_count > 0 or unknown_count > 0:
            overall_status = ServiceStatus.UNHEALTHY
        elif degraded_count > 0:
            overall_status = ServiceStatus.DEGRADED
        else:
            overall_status = ServiceStatus.HEALTHY

        return {
            "overall_status": overall_status.value,
            "overall_health_percent": round(overall_health, 2),
            "total_services": total_count,
            "healthy": healthy_count,
            "degraded": degraded_count,
            "unhealthy": unhealthy_count,
            "unknown": unknown_count,
        }


# 全局单例
_health_checker: HealthChecker | None = None


_health_checker_lock = threading.Lock()


def get_health_checker() -> HealthChecker:
    """获取健康检查器单例"""
    global _health_checker
    if _health_checker is None:
        with _health_checker_lock:
            if _health_checker is None:
                _health_checker = HealthChecker()
    return _health_checker


async def perform_startup_health_check():
    """执行启动时健康检查"""
    logger.info("[HealthCheck] 开始启动时健康检查...")

    checker = get_health_checker()
    results = await checker.check_all()
    summary = checker.get_summary(results)

    logger.info(f"[HealthCheck] 健康检查完成: {summary['overall_status']}")
    logger.info(f"[HealthCheck] 健康度: {summary['overall_health_percent']}%")
    logger.info(f"[HealthCheck] 服务状态: ✓{summary['healthy']} ⚠{summary['degraded']} ✗{summary['unhealthy']}")

    for service_name, result in results.items():
        status_symbol = {
            ServiceStatus.HEALTHY: "✓",
            ServiceStatus.DEGRADED: "⚠",
            ServiceStatus.UNHEALTHY: "✗",
            ServiceStatus.UNKNOWN: "?",
        }[result.status]

        logger.info(f"[HealthCheck]   {status_symbol} {service_name}: {result.message}")

        # 如果有失败的检查，打印详情
        for check in result.checks:
            if not check.get("passed"):
                logger.warning(f"[HealthCheck]     - {check.get('name')}: {check.get('message', '失败')}")

    return results, summary
