#!/usr/bin/env python3
"""
OpenClaw 安装器
处理 OpenClaw 的安装、初始化和配置流程
"""

import asyncio
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from .state_paths import get_openclaw_config_path, get_openclaw_state_dir
import threading

logger = logging.getLogger("openclaw.installer")


class InstallMethod(Enum):
    """安装方式"""
    VENDOR = "vendor"
    UNKNOWN = "unknown"


class InstallStatus(Enum):
    """安装状态"""
    NOT_INSTALLED = "not_installed"
    INSTALLED = "installed"
    INSTALLING = "installing"
    FAILED = "failed"
    NEEDS_SETUP = "needs_setup"


@dataclass
class InstallResult:
    """安装结果"""
    success: bool
    status: InstallStatus
    message: str
    version: str | None = None
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "status": self.status.value,
            "message": self.message,
            "version": self.version,
            "details": self.details
        }


class OpenClawInstaller:
    """
    OpenClaw 安装器

    负责检测、安装和初始化 OpenClaw
    打包环境下通过 EmbeddedRuntime 获取路径和环境变量。
    """

    @property
    def OPENCLAW_DIR(self):
        return get_openclaw_state_dir()

    @property
    def OPENCLAW_CONFIG(self):
        return get_openclaw_config_path()

    def _get_runtime(self):
        """获取 EmbeddedRuntime 实例"""
        from .embedded_runtime import get_embedded_runtime
        return get_embedded_runtime()

    @staticmethod
    def _get_gateway_port() -> int:
        try:
            from system.config import config as _cfg
            return _cfg.openclaw.gateway_port
        except Exception:
            return 20789

    # 默认配置模板（使用免费的 GLM 模型作为兜底）
    DEFAULT_CONFIG_TEMPLATE = {
        "agents": {
            "defaults": {
                "model": {
                    "primary": "zai/glm-4.7"
                },
                "models": {
                    "zai/glm-4.7": {
                        "alias": "GLM"
                    }
                },
                "workspace": str(get_openclaw_state_dir() / "workspace"),
                "compaction": {
                    "mode": "safeguard"
                },
                "maxConcurrent": 4
            }
        },
        "tools": {
            "allow": ["*"]
        },
        "hooks": {
            "enabled": True,
            "token": "",  # 将在初始化时生成
        },
        "gateway": {
            "port": 20789,  # 运行时由 _get_gateway_port() 覆盖
            "mode": "local",
            "bind": "loopback",
            "auth": {
                "mode": "token",
                "token": ""  # 将在初始化时生成
            }
        }
    }

    @staticmethod
    def build_config_from_naga() -> dict[str, Any]:
        """从 NagaAgent config.api 构建 OpenClaw 配置"""
        import secrets

        from system.config import config

        token = secrets.token_hex(24)
        api = config.api
        port = config.openclaw.gateway_port
        workspace = str(get_openclaw_state_dir() / "workspace")

        return {
            "meta": {
                "lastTouchedVersion": "naga-generated",
                "lastTouchedAt": "",
            },
            "env": {
                "shellEnv": {"enabled": False},
            },
            "models": {
                "providers": {
                    "naga-provider": {
                        "baseUrl": api.base_url,
                        "apiKey": api.api_key,
                        "auth": "api-key",
                        "api": "openai-completions",
                        "headers": {},
                        "authHeader": False,
                        "models": [{
                            "id": api.model,
                            "name": api.model,
                            "api": "openai-completions",
                            "reasoning": False,
                            "input": ["text"],
                            "cost": {"input": 1, "output": 1, "cacheRead": 1, "cacheWrite": 1},
                            "contextWindow": 128000,
                            "maxTokens": api.max_tokens,
                            "compat": {"maxTokensField": "max_tokens"},
                        }],
                    }
                }
            },
            "agents": {
                "defaults": {
                    "model": {"primary": f"naga-provider/{api.model}"},
                    "models": {f"naga-provider/{api.model}": {"alias": "NAGA"}},
                    "workspace": workspace,
                    "compaction": {"mode": "safeguard"},
                    "maxConcurrent": 4,
                    "subagents": {"maxConcurrent": 8},
                }
            },
            "hooks": {
                "enabled": True,
                "path": "/hooks",
                "token": token,
            },
            "gateway": {
                "port": port,
                "mode": "local",
                "bind": "loopback",
                "auth": {"mode": "token", "token": token},
            },
            "skills": {"install": {"nodeManager": "npm"}},
            "tools": {"allow": ["*"]},
        }

    def __init__(self):
        self._install_status = InstallStatus.NOT_INSTALLED

    # ============ 检测方法 ============

    def check_installation(self) -> tuple[InstallStatus, str | None]:
        """
        检查 OpenClaw 安装状态（基于 vendor 模型）

        Returns:
            (安装状态, 版本号)
        """
        runtime = self._get_runtime()

        # 1. 检查 vendor 是否就绪
        if not runtime.is_vendor_ready:
            return InstallStatus.NOT_INSTALLED, None

        # 2. 尝试从 vendor package.json 读取版本
        version = None
        try:
            import json
            pkg_json = runtime.vendor_root / "package.json"
            if pkg_json.exists():
                pkg = json.loads(pkg_json.read_text(encoding="utf-8"))
                version = pkg.get("version")
        except Exception:
            pass

        # 3. 检查配置是否完成
        if self.OPENCLAW_CONFIG.exists():
            return InstallStatus.INSTALLED, version
        else:
            return InstallStatus.NEEDS_SETUP, version

    def check_node_version(self) -> tuple[bool, str | None]:
        """
        检查 Node.js 版本（需要 Node 22+）

        Returns:
            (是否满足要求, 版本号)
        """
        runtime = self._get_runtime()
        return runtime.get_node_version()

    def check_npm_available(self) -> bool:
        """检查 npm 是否可用"""
        runtime = self._get_runtime()
        return runtime.npm_path is not None

    # ============ 安装方法 ============

    async def install(self, method: InstallMethod = InstallMethod.VENDOR) -> InstallResult:
        """
        安装 OpenClaw（确保 vendor 依赖就绪）

        Returns:
            InstallResult 对象
        """
        # 1. 检查是否已就绪
        status, version = self.check_installation()
        if status == InstallStatus.INSTALLED:
            return InstallResult(
                success=True,
                status=InstallStatus.INSTALLED,
                message=f"OpenClaw 已就绪 (v{version})",
                version=version
            )
        if status == InstallStatus.NEEDS_SETUP:
            return InstallResult(
                success=True,
                status=InstallStatus.NEEDS_SETUP,
                message=f"OpenClaw 已就绪 (v{version})，仅需初始化配置",
                version=version,
            )

        # 2. 检查 Node.js
        node_ok, node_version = self.check_node_version()
        if not node_ok:
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=f"需要 Node.js 22+，当前版本: {node_version or '未安装'}",
                details={"node_version": node_version}
            )

        # 3. 确保 vendor 依赖就绪
        self._install_status = InstallStatus.INSTALLING
        runtime = self._get_runtime()
        try:
            ok = await runtime.ensure_vendor_ready()
            if ok:
                status, version = self.check_installation()
                self._install_status = status
                return InstallResult(
                    success=True,
                    status=status,
                    message=f"OpenClaw vendor 依赖安装成功 (v{version})",
                    version=version,
                )
            else:
                self._install_status = InstallStatus.FAILED
                return InstallResult(
                    success=False,
                    status=InstallStatus.FAILED,
                    message="vendor 依赖安装失败",
                )
        except Exception as e:
            self._install_status = InstallStatus.FAILED
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=f"安装异常: {str(e)}"
            )

    # ============ 初始化方法 ============

    async def setup(self, hooks_token: str | None = None, interactive: bool = False) -> InstallResult:
        """
        初始化 OpenClaw 配置

        使用 `openclaw onboard` 命令进行初始化配置

        Args:
            hooks_token: Hooks 认证 token（不传则自动生成）
            interactive: 是否交互模式（默认非交互）

        Returns:
            InstallResult 对象
        """
        # 检查是否已安装
        status, version = self.check_installation()
        if status == InstallStatus.NOT_INSTALLED:
            return InstallResult(
                success=False,
                status=InstallStatus.NOT_INSTALLED,
                message="OpenClaw 未安装，请先安装"
            )

        try:
            runtime = self._get_runtime()
            cmd = self._build_openclaw_cmd()
            if not cmd:
                return InstallResult(
                    success=False,
                    status=InstallStatus.FAILED,
                    message="openclaw CLI 不可用，无法执行 onboard"
                )
            logger.info("运行 OpenClaw onboard...")

            # 构建命令参数
            onboard_cmd = [*cmd, "onboard"]
            if not interactive:
                onboard_cmd.append("--install-daemon")

            process = await asyncio.create_subprocess_exec(
                *onboard_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.DEVNULL if not interactive else None,
                env=runtime.env,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=120  # 2 分钟超时
            )

            # 配置 hooks token
            if self.OPENCLAW_CONFIG.exists():
                from .config_manager import OpenClawConfigManager
                config_manager = OpenClawConfigManager()
                config_manager.set_hooks_enabled(True)
                config_manager.set_hooks_allow_request_session_key(True)
                if hooks_token:
                    config_manager.set_hooks_token(hooks_token)

            # 检查最终状态
            final_status, final_version = self.check_installation()
            if final_status == InstallStatus.INSTALLED:
                return InstallResult(
                    success=True,
                    status=InstallStatus.INSTALLED,
                    message="OpenClaw 初始化完成",
                    version=final_version,
                    details={"output": stdout.decode() if stdout else ""}
                )
            else:
                return InstallResult(
                    success=False,
                    status=final_status,
                    message="初始化后配置文件未生成，请检查",
                    version=version
                )

        except TimeoutError:
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message="初始化超时（2分钟）"
            )
        except Exception as e:
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=f"初始化失败: {str(e)}"
            )

    # ============ Gateway 管理 ============

    def _build_openclaw_cmd(self) -> list[str] | None:
        """构建 openclaw CLI 命令前缀：[node, openclaw.mjs]"""
        runtime = self._get_runtime()
        node = runtime.node_path
        openclaw_mjs = runtime.openclaw_path  # vendor/openclaw/openclaw.mjs
        if not node or not openclaw_mjs:
            return None
        return [node, openclaw_mjs]

    async def install_gateway_service(self) -> InstallResult:
        """安装 Gateway 为系统服务"""
        status, version = self.check_installation()
        if status != InstallStatus.INSTALLED:
            return InstallResult(
                success=False,
                status=status,
                message="OpenClaw 未正确安装或配置"
            )

        try:
            runtime = self._get_runtime()
            cmd = self._build_openclaw_cmd()
            if not cmd:
                return InstallResult(success=False, status=InstallStatus.FAILED, message="openclaw CLI 不可用")

            process = await asyncio.create_subprocess_exec(
                *cmd, "gateway", "install",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=runtime.env,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=60
            )

            if process.returncode == 0:
                return InstallResult(
                    success=True,
                    status=InstallStatus.INSTALLED,
                    message="Gateway 服务安装成功",
                    details={"output": stdout.decode() if stdout else ""}
                )
            else:
                return InstallResult(
                    success=False,
                    status=InstallStatus.FAILED,
                    message=f"Gateway 服务安装失败: {stderr.decode() if stderr else '未知错误'}"
                )
        except Exception as e:
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=f"安装 Gateway 服务失败: {str(e)}"
            )

    async def start_gateway(self, background: bool = True) -> InstallResult:
        """
        启动 Gateway

        后台模式优先复用进程内 EmbeddedRuntime，避免打包环境下 CLI 二次派生失败。

        Args:
            background: 是否后台运行

        Returns:
            InstallResult 对象
        """
        status, version = self.check_installation()
        if status != InstallStatus.INSTALLED:
            return InstallResult(
                success=False,
                status=status,
                message="OpenClaw 未正确安装或配置"
            )

        try:
            runtime = self._get_runtime()
            if background:
                port = self._get_gateway_port()
                if runtime.gateway_running:
                    logger.info("EmbeddedRuntime 中的 Gateway 已在运行")
                else:
                    logger.info(f"通过 EmbeddedRuntime 启动 Gateway（port={port}）")
                    started = await runtime.start_gateway()
                    if not started and runtime.is_gateway_port_in_use(port=port):
                        logger.info(f"Gateway 端口 {port} 已被外部进程占用，转为连通性校验")

                # 检查是否启动成功
                from .detector import detect_openclaw
                oc_status = detect_openclaw(check_connection=True)

                if oc_status.gateway_reachable:
                    return InstallResult(
                        success=True,
                        status=InstallStatus.INSTALLED,
                        message="Gateway 启动成功",
                        details={
                            "gateway_url": oc_status.gateway_url,
                            "port": port,
                            "mode": "embedded-runtime",
                        }
                    )
                else:
                    return InstallResult(
                        success=False,
                        status=InstallStatus.FAILED,
                        message=f"Gateway 端口 {port} 启动失败"
                    )
            else:
                cmd = self._build_openclaw_cmd()
                if not cmd:
                    return InstallResult(success=False, status=InstallStatus.FAILED, message="openclaw CLI 不可用")
                # 前台运行（用于调试）
                # 审计 LOW L1: PIPE 若不读取会导致子进程写满管道挂起，前台模式直接丢弃输出
                await asyncio.create_subprocess_exec(
                    *cmd, "gateway",
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                    env=runtime.env,
                )
                return InstallResult(
                    success=True,
                    status=InstallStatus.INSTALLED,
                    message="Gateway 已启动（前台模式）"
                )

        except Exception as e:
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=f"启动 Gateway 失败: {str(e)}"
            )

    async def stop_gateway(self) -> InstallResult:
        """停止 Gateway"""
        try:
            runtime = self._get_runtime()
            if runtime.gateway_running:
                await runtime.stop_gateway()
                return InstallResult(
                    success=True,
                    status=InstallStatus.INSTALLED,
                    message="Gateway 已停止",
                )

            cmd = self._build_openclaw_cmd()
            if not cmd:
                return InstallResult(success=False, status=InstallStatus.FAILED, message="openclaw CLI 不可用")

            process = await asyncio.create_subprocess_exec(
                *cmd, "gateway", "stop",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=runtime.env,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=30
            )

            return InstallResult(
                success=process.returncode == 0,
                status=InstallStatus.INSTALLED if process.returncode == 0 else InstallStatus.FAILED,
                message="Gateway 已停止" if process.returncode == 0 else f"停止失败: {stderr.decode() if stderr else '未知错误'}"
            )
        except Exception as e:
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=f"停止 Gateway 失败: {str(e)}"
            )

    async def restart_gateway(self) -> InstallResult:
        """重启 Gateway"""
        try:
            stop_result = await self.stop_gateway()
            if not stop_result.success:
                return stop_result
            return await self.start_gateway(background=True)
        except Exception as e:
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=f"重启 Gateway 失败: {str(e)}"
            )

    async def check_gateway_status(self) -> dict[str, Any]:
        """检查 Gateway 状态"""
        try:
            runtime = self._get_runtime()
            cmd = self._build_openclaw_cmd()
            if not cmd:
                return {"success": False, "running": False, "error": "openclaw CLI 不可用"}

            process = await asyncio.create_subprocess_exec(
                *cmd, "gateway", "status",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=runtime.env,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=10
            )

            return {
                "success": process.returncode == 0,
                "running": process.returncode == 0,
                "output": stdout.decode() if stdout else "",
                "error": stderr.decode() if stderr else ""
            }
        except Exception as e:
            return {
                "success": False,
                "running": False,
                "error": str(e)
            }

    async def run_doctor(self) -> dict[str, Any]:
        """运行 OpenClaw 健康检查"""
        try:
            runtime = self._get_runtime()
            cmd = self._build_openclaw_cmd()
            if not cmd:
                return {"success": False, "healthy": False, "error": "openclaw CLI 不可用"}

            process = await asyncio.create_subprocess_exec(
                *cmd, "doctor",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=runtime.env,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=30
            )

            return {
                "success": process.returncode == 0,
                "healthy": process.returncode == 0,
                "output": stdout.decode() if stdout else "",
                "error": stderr.decode() if stderr else ""
            }
        except Exception as e:
            return {
                "success": False,
                "healthy": False,
                "error": str(e)
            }

    async def check_status(self) -> dict[str, Any]:
        """检查 OpenClaw 运行状态"""
        try:
            runtime = self._get_runtime()
            cmd = self._build_openclaw_cmd()
            if not cmd:
                return {"success": False, "error": "openclaw CLI 不可用"}

            process = await asyncio.create_subprocess_exec(
                *cmd, "status",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=runtime.env,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=10
            )

            return {
                "success": process.returncode == 0,
                "output": stdout.decode() if stdout else "",
                "error": stderr.decode() if stderr else ""
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

    # ============ Skills 管理 ============

    async def install_skill(self, skill_slug: str) -> InstallResult:
        """安装 Skill"""
        try:
            logger.info(f"安装 Skill: {skill_slug}")

            runtime = self._get_runtime()
            cmd = self._build_openclaw_cmd()
            if not cmd:
                return InstallResult(
                    success=False,
                    status=InstallStatus.FAILED,
                    message="openclaw CLI 不可用，无法安装 Skill"
                )

            process = await asyncio.create_subprocess_exec(
                *cmd, "skills", "install", skill_slug,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=runtime.env,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=120
            )

            if process.returncode == 0:
                return InstallResult(
                    success=True,
                    status=InstallStatus.INSTALLED,
                    message=f"Skill '{skill_slug}' 安装成功",
                    details={"output": stdout.decode() if stdout else ""}
                )
            else:
                return InstallResult(
                    success=False,
                    status=InstallStatus.FAILED,
                    message=f"Skill 安装失败: {stderr.decode() if stderr else '未知错误'}"
                )

        except Exception as e:
            return InstallResult(
                success=False,
                status=InstallStatus.FAILED,
                message=f"安装 Skill 异常: {str(e)}"
            )

    async def list_skills(self) -> list[dict[str, Any]]:
        """列出已安装的 Skills"""
        try:
            runtime = self._get_runtime()
            cmd = self._build_openclaw_cmd()
            if not cmd:
                return []

            process = await asyncio.create_subprocess_exec(
                *cmd, "skills", "list",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=runtime.env,
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=30
            )

            if process.returncode == 0:
                # 解析输出（简单解析）
                output = stdout.decode() if stdout else ""
                return [{"raw_output": output}]
            else:
                return []

        except Exception as e:
            logger.error(f"列出 Skills 失败: {e}")
            return []


# 全局安装器实例
_installer: OpenClawInstaller | None = None


_installer_lock = threading.Lock()


def get_openclaw_installer() -> OpenClawInstaller:
    """获取全局安装器实例"""
    global _installer
    if _installer is None:
        with _installer_lock:
            if _installer is None:
                _installer = OpenClawInstaller()
    return _installer
