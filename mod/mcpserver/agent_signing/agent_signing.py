"""
agent_signing.py - MCP Agent wrapper for Cosign container image signing verification.

Independently importable. Stdlib only.
"""

import asyncio
import json
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

COSIGN_BIN = shutil.which("cosign")
DEFAULT_TIMEOUT = 180  # 3 minutes for signing operations


class AgentSigning:
    """MCP Agent that wraps Cosign CLI for container image signing verification."""

    def __init__(self):
        if not COSIGN_BIN:
            raise RuntimeError(
                "cosign not found on PATH. Install: https://docs.sigstore.dev/cosign/installation/"
            )

    async def _run(
        self,
        args: list,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> dict[str, Any]:
        """Run cosign subprocess with timeout and return structured result."""
        cmd = [COSIGN_BIN] + args + ["--output-file=-"]
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
                    "message": f"cosign exited with code {proc.returncode}",
                    "data": {
                        "stderr": stderr_str,
                        "stdout": stdout_str,
                        "cmd": " ".join(shlex.quote(a) for a in cmd),
                    },
                }

            output_data = None
            parse_error = None
            if stdout_str:
                try:
                    # cosign outputs JSON lines or single JSON object
                    output_data = json.loads(stdout_str)
                except json.JSONDecodeError:
                    # Try parsing as JSON-lines
                    lines = [l.strip() for l in stdout_str.splitlines() if l.strip()]
                    parsed = []
                    for line in lines:
                        try:
                            parsed.append(json.loads(line))
                        except json.JSONDecodeError:
                            parsed.append({"raw": line})
                    if len(parsed) == 1:
                        output_data = parsed[0]
                        parse_error = None
                    else:
                        output_data = parsed
                        parse_error = None

            return {
                "status": "ok",
                "message": "Verification completed successfully",
                "data": {
                    "result": output_data,
                    "parse_error": parse_error,
                },
            }

        except TimeoutError:
            proc.kill()
            await proc.wait()
            return {
                "status": "error",
                "message": f"cosign command timed out after {timeout}s",
                "data": None,
            }
        except FileNotFoundError:
            return {
                "status": "error",
                "message": f"cosign binary not found at {COSIGN_BIN}",
                "data": None,
            }
        except Exception as exc:
            return {
                "status": "error",
                "message": f"Unexpected error: {exc}",
                "data": None,
            }

    async def verify_image(
        self,
        image: str,
        key: str | None = None,
    ) -> dict[str, Any]:
        """Verify a signed container image.

        Args:
            image: Container image reference to verify
            key: Optional path to public key file
        """
        args = ["verify"]
        if key:
            key_path = Path(key)
            if not key_path.is_file():
                return {
                    "status": "error",
                    "message": f"Key file not found: {key}",
                    "data": None,
                }
            args.extend(["--key", str(key_path.resolve())])
        args.append(image)
        return await self._run(args)

    async def verify_attestation(
        self,
        image: str,
        type: str | None = None,
    ) -> dict[str, Any]:
        """Verify attestations attached to a container image.

        Args:
            image: Container image reference
            type: Optional attestation type filter (e.g. slsaprovenance, vuln, spdx)
        """
        args = ["verify-attestation"]
        if type:
            args.extend(["--type", type])
        args.append(image)
        return await self._run(args)


async def handle_handoff(task: dict[str, Any]) -> str:
    """Entry point: receive a task dict, dispatch to tool, return JSON string.

    Task format:
        {"tool": "verify_image|verify_attestation", "params": {...}}
    """
    agent = AgentSigning()
    tool = task.get("tool", "")
    params = task.get("params", {})

    dispatcher = {
        "verify_image": lambda: agent.verify_image(
            image=params.get("image", ""),
            key=params.get("key"),
        ),
        "verify_attestation": lambda: agent.verify_attestation(
            image=params.get("image", ""),
            type=params.get("type"),
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
