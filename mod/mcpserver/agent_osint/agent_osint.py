"""
agent_osint.py - MCP Agent wrapper for Sherlock username search across social networks.

Independently importable. Stdlib only.
"""

import asyncio
import json
import os
import shlex
import shutil
import subprocess
import tempfile
from typing import Any, Dict, List, Optional

SHERLOCK_BIN = shutil.which("sherlock")
DEFAULT_TIMEOUT = 600  # 10 minutes for broad username searches


class AgentOsint:
    """MCP Agent that wraps Sherlock CLI for cross-platform username search."""

    def __init__(self):
        if not SHERLOCK_BIN:
            raise RuntimeError(
                "sherlock not found on PATH. Install: pip install sherlock-project"
            )

    async def _run(
        self,
        args: list,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> dict[str, Any]:
        """Run sherlock subprocess with timeout and return structured result."""
        # Sherlock writes results to a JSON file; we use a temp file
        with tempfile.NamedTemporaryFile(
            suffix=".json", mode="w+", delete=False, encoding="utf-8"
        ) as tmp:
            output_file = tmp.name

        try:
            cmd = [SHERLOCK_BIN] + args + [
                "--output", output_file,
                "--folderoutput", os.path.dirname(output_file),
                "--print-found",
                "--timeout", "30",
                "--no-color",
            ]
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

            # Read the JSON output file
            results_data = None
            parse_error = None
            try:
                with open(output_file, encoding="utf-8") as f:
                    results_data = json.load(f)
            except (OSError, json.JSONDecodeError, FileNotFoundError) as e:
                parse_error = str(e)
                # Fall back to parsing stdout lines
                results_data = {}
                for line in stdout_str.splitlines():
                    line = line.strip()
                    if line.startswith("[+]"):
                        parts = line.replace("[+]", "").strip().split(":", 1)
                        if len(parts) == 2:
                            results_data[parts[0].strip()] = parts[1].strip()

            # Count found vs total
            found_count = 0
            total_count = 0
            if isinstance(results_data, dict):
                total_count = len(results_data)
                found_count = sum(
                    1 for v in results_data.values()
                    if v and v not in ("Not Found!", "Error!", "")
                )

            return {
                "status": "ok",
                "message": f"Search complete: {found_count} found out of {total_count} sites checked",
                "data": {
                    "results": results_data,
                    "found_count": found_count,
                    "total_sites": total_count,
                    "stdout": stdout_str,
                    "stderr": stderr_str,
                    "parse_error": parse_error,
                },
            }

        except TimeoutError:
            proc.kill()
            await proc.wait()
            return {
                "status": "error",
                "message": f"sherlock command timed out after {timeout}s",
                "data": None,
            }
        except FileNotFoundError:
            return {
                "status": "error",
                "message": f"sherlock binary not found at {SHERLOCK_BIN}",
                "data": None,
            }
        except Exception as exc:
            return {
                "status": "error",
                "message": f"Unexpected error: {exc}",
                "data": None,
            }
        finally:
            # Cleanup temp output file
            try:
                if os.path.exists(output_file):
                    os.unlink(output_file)
            except OSError:
                pass

    async def search_username(
        self,
        username: str,
        sites: str | None = None,
    ) -> dict[str, Any]:
        """Search for a username across social networks.

        Args:
            username: The username to search for
            sites: Optional comma-separated list of specific site names
        """
        args = [username]
        if sites:
            args.extend(["--site", sites])
        return await self._run(args)

    async def search_batch(self, usernames: str) -> dict[str, Any]:
        """Search multiple usernames (comma-separated) across social networks.

        Args:
            usernames: Comma-separated list of usernames
        """
        user_list = [u.strip() for u in usernames.split(",") if u.strip()]
        if not user_list:
            return {
                "status": "error",
                "message": "No valid usernames provided",
                "data": None,
            }

        all_results = {}
        errors = []
        for user in user_list:
            result = await self._run([user])
            if result["status"] == "ok":
                all_results[user] = result["data"]
            else:
                errors.append({"username": user, "error": result["message"]})

        return {
            "status": "ok" if not errors else "partial",
            "message": f"Batch search: {len(all_results)} succeeded, {len(errors)} failed",
            "data": {"results": all_results, "errors": errors},
        }


async def handle_handoff(task: dict[str, Any]) -> str:
    """Entry point: receive a task dict, dispatch to tool, return JSON string.

    Task format:
        {"tool": "search_username|search_batch", "params": {...}}
    """
    agent = AgentOsint()
    tool = task.get("tool", "")
    params = task.get("params", {})

    dispatcher = {
        "search_username": lambda: agent.search_username(
            username=params.get("username", ""),
            sites=params.get("sites"),
        ),
        "search_batch": lambda: agent.search_batch(
            usernames=params.get("usernames", ""),
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
