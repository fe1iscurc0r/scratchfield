"""
agent_nuclei.py - MCP Agent wrapper for nuclei vulnerability scanner.

Independently importable. Stdlib only.
"""

import asyncio
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

NUCLEI_BIN = shutil.which("nuclei")
DEFAULT_TIMEOUT = 300  # 5 minutes for vulnerability scans


class AgentNuclei:
    """MCP Agent that wraps nuclei CLI for vulnerability scanning."""

    def __init__(self):
        if not NUCLEI_BIN:
            raise RuntimeError("nuclei not found on PATH. Install: go install -v github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest")

    async def _run(
        self,
        args: list,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> Dict[str, Any]:
        """Run nuclei subprocess with timeout and return structured result."""
        cmd = [NUCLEI_BIN] + args
        try:
            proc = await asyncio.wait_for(
                asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                ),
                timeout=timeout,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout,
            )
            stdout_str = stdout.decode("utf-8", errors="replace").strip()
            stderr_str = stderr.decode("utf-8", errors="replace").strip()

            if proc.returncode != 0:
                return {
                    "status": "error",
                    "message": f"nuclei exited with code {proc.returncode}",
                    "data": {"stderr": stderr_str, "cmd": " ".join(shlex.quote(a) for a in cmd)},
                }

            # Parse JSON-lines output
            results = []
            for line in stdout_str.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    results.append(json.loads(line))
                except json.JSONDecodeError:
                    results.append({"raw": line})

            return {
                "status": "ok",
                "message": f"Scan completed: {len(results)} finding(s)",
                "data": {"findings": results, "count": len(results)},
            }

        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return {
                "status": "error",
                "message": f"nuclei command timed out after {timeout}s",
                "data": None,
            }
        except FileNotFoundError:
            return {
                "status": "error",
                "message": f"nuclei binary not found at {NUCLEI_BIN}",
                "data": None,
            }
        except Exception as exc:
            return {
                "status": "error",
                "message": f"Unexpected error: {exc}",
                "data": None,
            }

    async def scan_url(
        self,
        url: str,
        templates: str | None = None,
    ) -> Dict[str, Any]:
        """Scan a single URL with optional template filter."""
        args = ["-u", url, "-json", "-silent"]
        if templates:
            args.extend(["-t", templates])
        return await self._run(args)

    async def scan_list(self, file_path: str) -> Dict[str, Any]:
        """Batch-scan targets from a file (one URL per line)."""
        target_file = Path(file_path)
        if not target_file.is_file():
            return {
                "status": "error",
                "message": f"Target file not found: {file_path}",
                "data": None,
            }
        return await self._run(["-l", str(target_file.resolve()), "-json", "-silent"])

    async def list_templates(
        self,
        severity: str | None = None,
    ) -> Dict[str, Any]:
        """List available templates, optionally filtered by severity."""
        args = ["-tl", "-silent"]
        if severity:
            valid = {"info", "low", "medium", "high", "critical"}
            sev_lower = severity.lower()
            if sev_lower not in valid:
                return {
                    "status": "error",
                    "message": f"Invalid severity: {severity}. Must be one of: {', '.join(sorted(valid))}",
                    "data": None,
                }
            args.extend(["-s", sev_lower])

        result = await self._run(args, timeout=60)
        return result
    async def handle_handoff(self, task: dict) -> dict:
        """类方法入口（对齐主仓 agent 约定）：委托模块级 handle_handoff。

        主仓既有 agent（agent_frida 等）的 MCP 入口均为类方法；
        tool_registry/meta.py:119 亦要求 entryPoint 为 {module, class}。
        返回值与模块级实现一致（JSON 字符串）。
        """
        return await handle_handoff(task)




async def handle_handoff(task: Dict[str, Any]) -> str:
    """Entry point: receive a task dict, dispatch to tool, return JSON string.

    Task format:
        {"tool": "scan_url|scan_list|list_templates", "params": {...}}
    """
    # tier=offensive 闸门：默认关闭，需显式开启（先例 mcpserver/adapters/vulnclaw.py）
    _gate_flag = "NUCLEI_ENABLE_INVOKE"
    if os.environ.get(_gate_flag, "").strip().lower() not in ("1", "true", "yes"):
        return json.dumps({
            "status": "error",
            "message": (
                "disabled: agent_nuclei 属 tier=offensive（主动攻击性），默认关闭。"
                f"确认目标已获授权后设 {_gate_flag}=1 开启。"
            ),
            "data": {"tier": "offensive", "enable_flag": _gate_flag},
        }, ensure_ascii=False)
    agent = AgentNuclei()
    tool = task.get("tool", "")
    params = task.get("params", {})

    dispatcher = {
        "scan_url": lambda: agent.scan_url(
            url=params.get("url", ""),
            templates=params.get("templates"),
        ),
        "scan_list": lambda: agent.scan_list(
            file_path=params.get("file_path", ""),
        ),
        "list_templates": lambda: agent.list_templates(
            severity=params.get("severity"),
        ),
    }

    handler = dispatcher.get(tool)
    if handler is None:
        result = {
            "status": "error",
            "message": f"Unknown tool: {tool}. Available: {list(dispatcher.keys())}",
            "data": None,
        }
    else:
        result = await handler()

    return json.dumps(result, ensure_ascii=False)
