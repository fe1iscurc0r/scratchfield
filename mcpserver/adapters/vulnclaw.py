"""VulnClaw MCP 适配层。

上游 vendor: vendor/top5/VulnClaw (MIT)
MCP 入口: vulnclaw/mcp/lifecycle.py — MCPLifecycleManager 管理 MCP 服务注册/生命周期
MCP Registry: vulnclaw/mcp/registry.py — 管理工具 schema 和实例状态（schema-only，无 FastMCP 可调用）

适配策略：
- 凭证 fail-fast: 健康检查阶段校验 VULNCLAW_OPENAI_API_KEY 或 OPENAI_API_KEY
- ⚠️ 安全红线：使用前必须获得合法授权。当前仅暴露 vulnclaw_status（列出工具 schema）+ vulnclaw_invoke（诚实说明需完整运行时）
"""
from __future__ import annotations

import asyncio
import logging
import os
import shlex
import sys
import time
from typing import Any

from mcpserver.adapters._common import (
    get_vendor_top5_root,
    inject_vendor_path,
    register_capability_safe,
)

logger = logging.getLogger(__name__)
_VULNCLAW_SRC = get_vendor_top5_root() / "VulnClaw"

# 调用开关：默认关闭，避免模型静默发起扫描/攻击（用户自行在 .env.local 里开）
_INVOKE_ENV_FLAG = "VULNCLAW_ENABLE_INVOKE"
_EXPLOIT_ENV_FLAG = "VULNCLAW_ALLOW_EXPLOIT"
_EXPLOIT_COMMANDS = frozenset({"exploit", "persistent"})
_KNOWN_COMMANDS = frozenset({
    "doctor", "manual", "man", "init", "login", "logout", "report",
    "recon", "scan", "network-scan", "solve", "run", "repl", "tui", "web",
    "exploit", "persistent",
})

CAPABILITY: dict = {
    "name": "vulnclaw",
    "displayName": "渗透测试编排",
    "description": "AI 渗透测试 MCP 服务（信息收集→扫描→利用→报告）。⚠️ 使用前必须合法授权。",
    "version": "0.3.7",
    "license": "MIT",
    "vendor": "VulnClaw",
    "security_notice": "使用前必须获得合法授权",
    "_from_adapter": "vulnclaw",
}


def _llm_api_key() -> str:
    """VulnClaw 的 LLM key：优先 vendor 自己的变量名，再兼容旧的 OPENAI_* 命名。

    注意命名错配：vendor（vulnclaw/config/settings.py）读的是 VULNCLAW_LLM_API_KEY /
    VULNCLAW_LLM_API_KEYS，而本适配器早期只认 VULNCLAW_OPENAI_API_KEY / OPENAI_API_KEY
    → 按 vendor 文档配好 key 也会被判"未配置"。这里把两套名字都认。
    """
    return (
        os.environ.get("VULNCLAW_LLM_API_KEY", "").strip()
        or os.environ.get("VULNCLAW_LLM_API_KEYS", "").strip()
        or os.environ.get("VULNCLAW_OPENAI_API_KEY", "").strip()
        or os.environ.get("OPENAI_API_KEY", "").strip()
    )


def _llm_summary() -> dict:
    """脱敏后的 LLM 配置摘要（不含 key 明文）。"""
    key = _llm_api_key()
    return {
        "provider": os.environ.get("VULNCLAW_LLM_PROVIDER", "").strip() or "(默认 preset)",
        "base_url": os.environ.get("VULNCLAW_LLM_BASE_URL", "").strip() or "(默认)",
        "model": os.environ.get("VULNCLAW_LLM_MODEL", "").strip() or "(默认)",
        "api_key_present": bool(key),
        "api_key_hint": f"len={len(key)}" if key else "",
    }


def healthcheck() -> bool:
    """VulnClaw 健康检查。

    必须条件：
    - 目录存在
    - LLM API key 可用（VULNCLAW_LLM_API_KEY 优先，兼容 VULNCLAW_OPENAI_API_KEY /
      OPENAI_API_KEY，禁止任何默认值）
    """
    if not _VULNCLAW_SRC.is_dir():
        logger.warning("[adapter:vulnclaw] %s 不存在", _VULNCLAW_SRC)
        return False
    inject_vendor_path("VulnClaw")
    if not _llm_api_key():
        logger.warning(
            "[adapter:vulnclaw] 未配置 VULNCLAW_LLM_API_KEY / VULNCLAW_OPENAI_API_KEY / "
            "OPENAI_API_KEY，跳过。⚠️ 渗透功能使用前必须获得合法授权。"
        )
        return False
    try:
        import vulnclaw  # noqa: F401
        from vulnclaw.mcp import registry as _vc_reg  # noqa: F401
    except Exception as e:
        logger.warning("[adapter:vulnclaw] 导入 vulnclaw MCP 模块失败: %s", e)
        return False
    return True


def register(mcp_server: Any, mcp_registry: Any = None) -> None:
    """把 VulnClaw MCP 工具合并到主 mcp_server。

    VulnClaw 使用 MCPRegistry 管理工具 schema（无 FastMCP 实例），这里暴露两个外壳工具：
    - vulnclaw_status: 列出可用工具 schema
    - vulnclaw_invoke: 诚实说明需完整 MCP server 运行时
    """
    inject_vendor_path("VulnClaw")
    from vulnclaw.mcp import registry as vc_registry  # type: ignore

    logger.info("[adapter:vulnclaw] 暴露 vulnclaw_status + vulnclaw_invoke 外壳")

    async def vulnclaw_status() -> dict:
        """VulnClaw MCP 服务状态（LLM 配置摘要 + 可用工具 schema）。"""
        summary = _llm_summary()
        try:
            reg = vc_registry.MCPRegistry()
            schemas = reg.get_all_tool_schemas() if hasattr(reg, "get_all_tool_schemas") else []
            return {
                "ok": True,
                "llm": summary,
                "available_tools": [s.get("name", "?") for s in schemas],
                "tool_count": len(schemas),
                "runtime_note": (
                    "VulnClaw 的完整渗透能力跑在它自己的 MCP server / CLI 运行时里"
                    "（vendor/top5/VulnClaw），本适配器只暴露 schema 与状态；"
                    "⚠️ 任何渗透动作前必须确认对目标有合法授权。"
                ),
            }
        except Exception as e:
            return {"ok": False, "llm": summary, "error": str(e)}

    async def vulnclaw_invoke(
        command: str,
        target: str = "",
        extra_args: str = "",
        timeout_s: int = 600,
    ) -> dict:
        """调用 VulnClaw CLI 执行任务（**默认关闭**，需显式开关）。⚠️ 使用前必须获得合法授权。

        Args:
            command: 子命令（doctor/manual/report/recon/scan/network-scan/solve/run/exploit/persistent）
            target: 目标（URL / IP / CIDR）；只读命令可留空
            extra_args: 追加参数（按 shell 词法切分后逐个传给 CLI，不经 shell）
            timeout_s: 超时秒数（上限 1800）

        安全设计：默认不执行任何动作——需要 VULNCLAW_ENABLE_INVOKE=1 才开放侦察/扫描类命令，
        而 exploit / persistent 还需要第二个开关 VULNCLAW_ALLOW_EXPLOIT=1。两层开关都在
        .env.local（已 gitignore）里由用户自己控制，避免模型静默发起攻击性动作。
        """
        if os.environ.get(_INVOKE_ENV_FLAG, "").strip() != "1":
            return {
                "ok": False,
                "error": (
                    f"vulnclaw_invoke 默认关闭。要在授权范围内使用，请在 .env.local 设置 "
                    f"{_INVOKE_ENV_FLAG}=1（攻击性命令还需 {_EXPLOIT_ENV_FLAG}=1）后重启栈。"
                ),
                "command": command,
                "target": target,
                "authorization_notice": "⚠️ 仅限自有资产或书面授权目标；未授权使用可能违法。",
            }

        cmd = str(command or "").strip().lower()
        if cmd in _EXPLOIT_COMMANDS and os.environ.get(_EXPLOIT_ENV_FLAG, "").strip() != "1":
            return {
                "ok": False,
                "error": f"{cmd} 属攻击性命令，需 {_EXPLOIT_ENV_FLAG}=1 单独放行",
                "command": cmd,
            }
        if cmd not in _KNOWN_COMMANDS:
            return {
                "ok": False,
                "error": f"未知子命令 {cmd}，可用: {', '.join(sorted(_KNOWN_COMMANDS))}",
                "command": cmd,
            }

        argv = [sys.executable, "-m", "vulnclaw.cli.main", cmd]
        if str(target or "").strip():
            argv.append(str(target).strip())
        if str(extra_args or "").strip():
            argv.extend(shlex.split(extra_args))
        env = {**os.environ, "PYTHONPATH": str(_VULNCLAW_SRC) + os.pathsep + os.environ.get("PYTHONPATH", "")}
        logger.warning(
            "[adapter:vulnclaw] ⚠️ 调用 %s（目标=%s）——请确认已获得合法授权", cmd, target or "(空)"
        )
        limit = max(10, min(int(timeout_s or 600), 1800))
        started = time.time()
        try:
            proc = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(_VULNCLAW_SRC),
                env=env,
            )
            try:
                out_b, err_b = await asyncio.wait_for(proc.communicate(), timeout=limit)
            except asyncio.TimeoutError:
                proc.kill()
                return {
                    "ok": False,
                    "error": f"命令超时（>{limit}s），已终止",
                    "command": cmd,
                    "target": target,
                }
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": f"启动失败: {type(e).__name__}: {e}", "command": cmd}

        def _tail(raw: bytes) -> str:
            text = raw.decode("utf-8", errors="replace").strip()
            return text[-8000:] if len(text) > 8000 else text

        return {
            "ok": proc.returncode == 0,
            "command": cmd,
            "target": target or None,
            "exit_code": proc.returncode,
            "duration_s": round(time.time() - started, 1),
            "stdout": _tail(out_b),
            "stderr": _tail(err_b),
            "authorization_notice": "⚠️ 仅限自有资产或书面授权目标。",
        }

    if hasattr(mcp_server, "add_tool"):
        mcp_server.add_tool(vulnclaw_status, name="vulnclaw_status")
        mcp_server.add_tool(vulnclaw_invoke, name="vulnclaw_invoke")

    register_capability_safe(mcp_registry, CAPABILITY)
