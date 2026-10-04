"""
agent_sbom.py - MCP Agent wrapper for Syft SBOM generator.

Independently importable. Stdlib only.
"""

import asyncio
import json
import shlex
import shutil
import subprocess
from typing import Any, Dict, Optional

SYFT_BIN = shutil.which("syft")
DEFAULT_TIMEOUT = 300  # 5 minutes for SBOM generation


class AgentSbom:
    """MCP Agent that wraps Syft CLI for SBOM generation and package listing."""

    def __init__(self):
        if not SYFT_BIN:
            raise RuntimeError(
                "syft not found on PATH. Install: https://github.com/anchore/syft#installation"
            )

    async def _run(
        self,
        target: str,
        output_format: str | None = None,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> Dict[str, Any]:
        """Run syft subprocess with timeout and return structured JSON result."""
        cmd = [SYFT_BIN, target]
        fmt = output_format or "syft-json"
        cmd.extend(["-o", fmt, "--quiet"])

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
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
                    "message": f"syft exited with code {proc.returncode}",
                    "data": {
                        "stderr": stderr_str,
                        "cmd": " ".join(shlex.quote(a) for a in cmd),
                    },
                }

            sbom_data = None
            parse_error = None
            if stdout_str:
                try:
                    sbom_data = json.loads(stdout_str)
                except json.JSONDecodeError as e:
                    parse_error = str(e)
                    sbom_data = {"raw": stdout_str}

            name = sbom_data.get("name", target) if isinstance(sbom_data, dict) else target
            artifacts = sbom_data.get("artifacts", []) if isinstance(sbom_data, dict) else []

            return {
                "status": "ok",
                "message": f"SBOM generated for {name}: {len(artifacts)} package(s)",
                "data": {
                    "sbom": sbom_data,
                    "format": fmt,
                    "artifact_count": len(artifacts),
                    "parse_error": parse_error,
                },
            }

        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return {
                "status": "error",
                "message": f"syft command timed out after {timeout}s",
                "data": None,
            }
        except FileNotFoundError:
            return {
                "status": "error",
                "message": f"syft binary not found at {SYFT_BIN}",
                "data": None,
            }
        except Exception as exc:
            return {
                "status": "error",
                "message": f"Unexpected error: {exc}",
                "data": None,
            }

    async def generate_sbom(
        self,
        target: str,
        format: str | None = None,
    ) -> Dict[str, Any]:
        """Generate an SBOM for a container image, directory, or file.

        Args:
            target: Container image name, directory path, or file path
            format: Output format - 'syft-json' (default) or 'cyclonedx-json'
        """
        valid_formats = {None, "syft-json", "cyclonedx-json"}
        if format and format not in valid_formats:
            return {
                "status": "error",
                "message": f"Invalid format: {format}. Use 'syft-json' or 'cyclonedx-json'",
                "data": None,
            }
        return await self._run(target, output_format=format)

    async def list_packages(self, target: str) -> Dict[str, Any]:
        """List all packages found in a target (shorthand for syft-json output)."""
        return await self._run(target, output_format="syft-json")
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
        {"tool": "generate_sbom|list_packages", "params": {...}}
    """
    agent = AgentSbom()
    tool = task.get("tool", "")
    params = task.get("params", {})

    dispatcher = {
        "generate_sbom": lambda: agent.generate_sbom(
            target=params.get("target", ""),
            format=params.get("format"),
        ),
        "list_packages": lambda: agent.list_packages(
            target=params.get("target", ""),
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
