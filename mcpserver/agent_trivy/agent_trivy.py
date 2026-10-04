"""
agent_trivy.py - MCP Agent wrapper for Trivy container/filesystem/repo scanner.

Independently importable. Stdlib only.
"""

import asyncio
import json
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict

TRIVY_BIN = shutil.which("trivy")
DEFAULT_TIMEOUT = 600  # 10 minutes for comprehensive scans


class AgentTrivy:
    """MCP Agent that wraps Trivy CLI for container/image/filesystem/repo scanning."""

    def __init__(self):
        if not TRIVY_BIN:
            raise RuntimeError("trivy not found on PATH. Install: https://aquasecurity.github.io/trivy/latest/getting-started/installation/")

    async def _run(
        self,
        args: list,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> Dict[str, Any]:
        """Run trivy subprocess with timeout and return structured JSON result."""
        cmd = [TRIVY_BIN] + args + ["-f", "json", "--quiet"]
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

            trivy_data = None
            parse_error = None
            if stdout_str:
                try:
                    trivy_data = json.loads(stdout_str)
                except json.JSONDecodeError as e:
                    parse_error = str(e)
                    trivy_data = {"raw": stdout_str}

            if proc.returncode != 0:
                # Trivy returns non-zero when vulnerabilities found, but we still have data
                return {
                    "status": "ok",
                    "message": f"Scan completed with exit code {proc.returncode}",
                    "data": {
                        "results": trivy_data,
                        "exit_code": proc.returncode,
                        "stderr": stderr_str,
                        "parse_error": parse_error,
                    },
                }

            return {
                "status": "ok",
                "message": "Scan completed successfully",
                "data": {"results": trivy_data, "parse_error": parse_error},
            }

        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return {
                "status": "error",
                "message": f"trivy command timed out after {timeout}s",
                "data": None,
            }
        except FileNotFoundError:
            return {
                "status": "error",
                "message": f"trivy binary not found at {TRIVY_BIN}",
                "data": None,
            }
        except Exception as exc:
            return {
                "status": "error",
                "message": f"Unexpected error: {exc}",
                "data": None,
            }

    async def scan_image(self, image: str) -> Dict[str, Any]:
        """Scan a container image for vulnerabilities."""
        return await self._run(["image", image])

    async def scan_filesystem(self, path: str) -> Dict[str, Any]:
        """Scan a local filesystem path."""
        fs_path = Path(path)
        if not fs_path.exists():
            return {
                "status": "error",
                "message": f"Path not found: {path}",
                "data": None,
            }
        return await self._run(["fs", str(fs_path.resolve())])

    async def scan_repo(self, repo_url: str) -> Dict[str, Any]:
        """Scan a remote Git repository."""
        return await self._run(["repo", repo_url])
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
        {"tool": "scan_image|scan_filesystem|scan_repo", "params": {...}}
    """
    agent = AgentTrivy()
    tool = task.get("tool", "")
    params = task.get("params", {})

    dispatcher = {
        "scan_image": lambda: agent.scan_image(
            image=params.get("image", ""),
        ),
        "scan_filesystem": lambda: agent.scan_filesystem(
            path=params.get("path", ""),
        ),
        "scan_repo": lambda: agent.scan_repo(
            repo_url=params.get("repo_url", ""),
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
