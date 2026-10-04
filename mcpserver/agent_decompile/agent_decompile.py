"""
agent_decompile.py - MCP Agent wrapper for JADX APK/DEX decompiler.

Independently importable. Stdlib only.
"""

import asyncio
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

JADX_BIN = shutil.which("jadx")
DEFAULT_TIMEOUT = 600  # 10 minutes for decompilation


class AgentDecompile:
    """MCP Agent that wraps JADX CLI for APK/DEX decompilation."""

    def __init__(self):
        if not JADX_BIN:
            raise RuntimeError(
                "jadx not found on PATH. Install: https://github.com/skylot/jadx#install"
            )

    async def _run_jadx(
        self,
        args: list,
        output_dir: str,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> Dict[str, Any]:
        """Run jadx subprocess with timeout and return structured result."""
        cmd = [JADX_BIN] + args + ["-d", output_dir, "--no-res", "--show-bad-code"]
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
                    "message": f"jadx exited with code {proc.returncode}",
                    "data": {
                        "stderr": stderr_str,
                        "stdout": stdout_str,
                        "cmd": " ".join(shlex.quote(a) for a in cmd),
                    },
                }

            # Gather output stats
            out_path = Path(output_dir)
            java_files = list(out_path.rglob("*.java")) if out_path.is_dir() else []
            sources = out_path / "sources"
            source_files = list(sources.rglob("*.java")) if sources.is_dir() else []

            return {
                "status": "ok",
                "message": f"Decompilation complete: {len(java_files) or len(source_files)} Java files generated",
                "data": {
                    "output_dir": str(out_path.resolve()),
                    "file_count": max(len(java_files), len(source_files)),
                    "stdout": stdout_str,
                },
            }

        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            return {
                "status": "error",
                "message": f"jadx command timed out after {timeout}s",
                "data": None,
            }
        except FileNotFoundError:
            return {
                "status": "error",
                "message": f"jadx binary not found at {JADX_BIN}",
                "data": None,
            }
        except Exception as exc:
            return {
                "status": "error",
                "message": f"Unexpected error: {exc}",
                "data": None,
            }

    async def decompile_apk(
        self,
        apk_path: str,
        output_dir: str | None = None,
    ) -> Dict[str, Any]:
        """Decompile an APK file to Java source code.

        Args:
            apk_path: Path to the APK file
            output_dir: Optional output directory; auto-created in temp if omitted
        """
        apk = Path(apk_path)
        if not apk.is_file():
            return {
                "status": "error",
                "message": f"APK file not found: {apk_path}",
                "data": None,
            }

        out = output_dir or tempfile.mkdtemp(prefix="jadx_apk_")
        os.makedirs(out, exist_ok=True)

        result = await self._run_jadx([str(apk.resolve())], out)
        # Inject input path context
        if result["status"] == "ok" and result["data"]:
            result["data"]["apk_path"] = str(apk.resolve())
        return result

    async def decompile_dex(
        self,
        dex_path: str,
    ) -> Dict[str, Any]:
        """Decompile a DEX file to Java source code.

        Args:
            dex_path: Path to the .dex file
        """
        dex = Path(dex_path)
        if not dex.is_file():
            return {
                "status": "error",
                "message": f"DEX file not found: {dex_path}",
                "data": None,
            }

        out_dir = tempfile.mkdtemp(prefix="jadx_dex_")
        result = await self._run_jadx([str(dex.resolve())], out_dir)
        if result["status"] == "ok" and result["data"]:
            result["data"]["dex_path"] = str(dex.resolve())
        return result

    async def search_code(
        self,
        keyword: str,
        search_dir: str | None = None,
    ) -> Dict[str, Any]:
        """Search for a keyword in decompiled Java sources.

        Args:
            keyword: Keyword or regex pattern to search for
            search_dir: Directory containing decompiled Java source files
        """
        if not search_dir:
            return {
                "status": "error",
                "message": "search_dir is required. Provide the output directory from a previous decompilation.",
                "data": None,
            }

        base = Path(search_dir)
        if not base.is_dir():
            return {
                "status": "error",
                "message": f"Search directory not found: {search_dir}",
                "data": None,
            }

        # Build regex (case-insensitive by default)
        try:
            pattern = re.compile(keyword, re.IGNORECASE)
        except re.error as e:
            return {
                "status": "error",
                "message": f"Invalid regex pattern: {e}",
                "data": None,
            }

        matches: List[Dict[str, Any]] = []
        java_files = list(base.rglob("*.java"))
        sources_dir = base / "sources"
        if sources_dir.is_dir():
            java_files.extend(sources_dir.rglob("*.java"))

        # Deduplicate
        java_files = list(set(java_files))

        for jf in java_files[:1000]:  # cap at 1000 files
            try:
                content = jf.read_text(encoding="utf-8", errors="replace")
                for i, line in enumerate(content.splitlines(), start=1):
                    if pattern.search(line):
                        matches.append({
                            "file": str(jf.resolve()),
                            "line": i,
                            "content": line.strip()[:200],  # truncate long lines
                        })
                        if len(matches) >= 500:  # cap results
                            break
                if len(matches) >= 500:
                    break
            except (OSError, UnicodeDecodeError):
                continue

        return {
            "status": "ok",
            "message": f"Found {len(matches)} match(es) for '{keyword}'",
            "data": {
                "keyword": keyword,
                "match_count": len(matches),
                "matches": matches,
                "searched_files": len(java_files),
            },
        }
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
        {"tool": "decompile_apk|decompile_dex|search_code", "params": {...}}
    """
    agent = AgentDecompile()
    tool = task.get("tool", "")
    params = task.get("params", {})

    dispatcher = {
        "decompile_apk": lambda: agent.decompile_apk(
            apk_path=params.get("apk_path", ""),
            output_dir=params.get("output_dir"),
        ),
        "decompile_dex": lambda: agent.decompile_dex(
            dex_path=params.get("dex_path", ""),
        ),
        "search_code": lambda: agent.search_code(
            keyword=params.get("keyword", ""),
            search_dir=params.get("search_dir"),
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
