"""
agent_llm_decompile.py - LLM4Decompile Agent

Assumes the LLM4Decompile model is running as a service.
Communicates via HTTP API (REST) or gRPC to decompile binaries.
If the service is not running, returns an error with startup instructions.

LLM4Decompile: https://github.com/albertan017/LLM4Decompile
"""

import asyncio
import json
import os
import re
import struct
import subprocess
from typing import Optional

# Default service endpoint
DEFAULT_API_ENDPOINT = "http://127.0.0.1:8000"
DEFAULT_GRPC_ENDPOINT = "127.0.0.1:50051"


class LLMDecompileAgent:
    """LLM4Decompile agent that communicates with the decompilation service."""

    def __init__(self):
        self._api_endpoint = os.environ.get(
            "LLM4DECOMPILE_ENDPOINT", DEFAULT_API_ENDPOINT
        )
        self._grpc_endpoint = os.environ.get(
            "LLM4DECOMPILE_GRPC_ENDPOINT", DEFAULT_GRPC_ENDPOINT
        )
        self._service_alive = None  # cached

    # ------------------------------------------------------------------
    # Handoff entry point
    # ------------------------------------------------------------------
    async def handle_handoff(self, task: dict) -> dict:
        """MCP handoff entry."""
        tool = task.get("tool", "")
        params = task.get("params", {})

        try:
            if tool == "decompile_binary":
                result = await self.decompile_binary(
                    binary_path=params.get("binary_path", ""),
                    arch=params.get("arch", "x86"),
                    format=params.get("format", "elf"),
                )
            elif tool == "decompile_function":
                result = await self.decompile_function(
                    binary_path=params.get("binary_path", ""),
                    function_addr=params.get("function_addr", ""),
                )
            else:
                result = {
                    "status": "error",
                    "message": f"Unknown tool: {tool}",
                    "data": None,
                }
        except Exception as e:
            result = {"status": "error", "message": str(e), "data": None}
        return json.dumps(result, ensure_ascii=False)

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------
    async def decompile_binary(
        self, binary_path: str, arch: str = "x86", format: str = "elf"
    ) -> dict:
        """Decompile an entire binary file.

        Args:
            binary_path: Path to the binary file.
            arch: Target architecture ('x86', 'arm', 'mips').
            format: Binary format ('elf', 'pe').
        """
        if not binary_path:
            return {"status": "error", "message": "No binary_path provided", "data": None}
        if not os.path.exists(binary_path):
            return {"status": "error", "message": f"Binary not found: {binary_path}", "data": None}

        alive = await self._check_service_alive()
        if not alive:
            return self._service_not_running_error()

        # Validate arch and format
        valid_archs = {"x86", "arm", "mips", "ppc", "riscv"}
        valid_formats = {"elf", "pe", "macho"}

        if arch.lower() not in valid_archs:
            return {
                "status": "error",
                "message": f"Unsupported architecture: {arch}. Supported: {', '.join(sorted(valid_archs))}",
                "data": None,
            }
        if format.lower() not in valid_formats:
            return {
                "status": "error",
                "message": f"Unsupported format: {format}. Supported: {', '.join(sorted(valid_formats))}",
                "data": None,
            }

        # Basic binary validation
        bin_info = self._inspect_binary(binary_path)
        if bin_info.get("error"):
            return {
                "status": "error",
                "message": f"Invalid binary: {bin_info['error']}",
                "data": bin_info,
            }

        # Get file size (warn if too large)
        file_size = os.path.getsize(binary_path)
        if file_size > 10 * 1024 * 1024:  # 10 MB
            return {
                "status": "error",
                "message": f"Binary too large ({file_size / 1024 / 1024:.1f} MB). Max: 10 MB.",
                "data": {"size_bytes": file_size},
            }

        # Make API request
        try:
            result = await self._call_api("decompile", {
                "binary_path": binary_path,
                "arch": arch.lower(),
                "format": format.lower(),
                "mode": "full",
            })

            return {
                "status": "ok",
                "message": f"Decompilation complete for {binary_path}",
                "data": {
                    "binary": binary_path,
                    "arch": arch.lower(),
                    "format": format.lower(),
                    "binary_info": bin_info,
                    "result": result,
                },
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Decompilation failed: {e}",
                "data": None,
            }

    async def decompile_function(
        self, binary_path: str, function_addr: str
    ) -> dict:
        """Decompile a single function by address or name.

        Args:
            binary_path: Path to the binary file.
            function_addr: Function address (hex, e.g. '0x401000') or name.
        """
        if not binary_path:
            return {"status": "error", "message": "No binary_path provided", "data": None}
        if not function_addr:
            return {"status": "error", "message": "No function_addr provided", "data": None}
        if not os.path.exists(binary_path):
            return {"status": "error", "message": f"Binary not found: {binary_path}", "data": None}

        alive = await self._check_service_alive()
        if not alive:
            return self._service_not_running_error()

        # Normalize address
        addr = function_addr.strip()
        if addr.startswith("0x") or addr.startswith("0X"):
            try:
                _ = int(addr, 16)
            except ValueError:
                return {
                    "status": "error",
                    "message": f"Invalid hex address: {function_addr}",
                    "data": None,
                }
        else:
            try:
                _ = int(addr)
            except ValueError:
                # Assume it's a function name
                pass

        bin_info = self._inspect_binary(binary_path)

        try:
            result = await self._call_api("decompile_function", {
                "binary_path": binary_path,
                "function_addr": addr,
            })

            return {
                "status": "ok",
                "message": f"Function decompilation complete for {addr}",
                "data": {
                    "binary": binary_path,
                    "function_addr": addr,
                    "binary_info": bin_info,
                    "result": result,
                },
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Function decompilation failed: {e}",
                "data": None,
            }

    # ------------------------------------------------------------------
    # Service health check
    # ------------------------------------------------------------------
    async def _check_service_alive(self) -> bool:
        """Check if the LLM4Decompile service is reachable."""
        if self._service_alive is not None:
            return self._service_alive

        # Try to import urllib for health check
        try:
            import urllib.request
            req = urllib.request.Request(
                f"{self._api_endpoint}/health",
                method="GET",
            )
            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(
                None,
                lambda: urllib.request.urlopen(req, timeout=5)
            )
            self._service_alive = resp.status == 200
        except Exception:
            # Try process check
            try:
                proc = await asyncio.create_subprocess_exec(
                    "pgrep", "-f", "llm4decompile",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                try:
                    stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=3)
                except TimeoutError:
                    proc.kill()
                    await proc.wait()
                    stdout = b""
                self._service_alive = proc.returncode == 0 and len(stdout.strip()) > 0
            except Exception:
                self._service_alive = False

        return self._service_alive

    def _service_not_running_error(self) -> dict:
        """Return error with instructions to start the service."""
        return {
            "status": "error",
            "message": "LLM4Decompile service is not running",
            "data": {
                "how_to_start": {
                    "description": "Start the LLM4Decompile model service before using this agent.",
                    "docker": (
                        "docker run -d --name llm4decompile \\\n"
                        "  -p 8000:8000 \\\n"
                        "  -v /path/to/models:/models \\\n"
                        "  llm4decompile/server:latest"
                    ),
                    "python": (
                        "git clone https://github.com/albertan017/LLM4Decompile.git\n"
                        "cd LLM4Decompile\n"
                        "pip install -r requirements.txt\n"
                        "python server.py --host 0.0.0.0 --port 8000"
                    ),
                    "endpoint": f"Default API endpoint: {self._api_endpoint}",
                    "env_var": "Set LLM4DECOMPILE_ENDPOINT environment variable to customize.",
                },
            },
        }

    # ------------------------------------------------------------------
    # API communication
    # ------------------------------------------------------------------
    async def _call_api(self, endpoint: str, payload: dict) -> dict:
        """Call the LLM4Decompile REST API."""
        import urllib.error
        import urllib.request

        url = f"{self._api_endpoint}/{endpoint}"
        data = json.dumps(payload).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(
                None,
                lambda: urllib.request.urlopen(req, timeout=120)
            )
            body = resp.read().decode("utf-8")
            return json.loads(body)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"API error {e.code}: {body}")
        except Exception as e:
            raise RuntimeError(f"API call failed: {e}")

    # ------------------------------------------------------------------
    # Binary inspection
    # ------------------------------------------------------------------
    @staticmethod
    def _inspect_binary(filepath: str) -> dict:
        """Basic binary file inspection."""
        info = {
            "path": filepath,
            "size": os.path.getsize(filepath),
        }

        try:
            with open(filepath, "rb") as f:
                header = f.read(64)

            if len(header) < 4:
                info["error"] = "File too small to be a valid binary"
                return info

            # ELF detection
            if header[:4] == b"\x7fELF":
                info["detected_format"] = "elf"
                info["elf_class"] = "64-bit" if header[4] == 2 else "32-bit"
                endian = "little-endian" if header[5] == 1 else "big-endian"
                info["endianness"] = endian
                # Machine type
                if len(header) >= 20:
                    machine_map = {
                        3: "x86", 62: "x86-64", 40: "ARM", 183: "AArch64",
                        8: "MIPS", 20: "PowerPC", 243: "RISC-V",
                    }
                    machine = struct.unpack("<H", header[18:20])[0]
                    info["machine"] = machine_map.get(machine, f"unknown ({machine})")

            # PE detection
            elif header[:2] == b"MZ":
                info["detected_format"] = "pe"
                # Read PE offset at 0x3C
                if len(header) >= 64:
                    try:
                        pe_offset = struct.unpack("<I", header[0x3C:0x40])[0]
                        info["pe_offset"] = pe_offset
                    except struct.error:
                        pass

            # Mach-O detection
            elif header[:4] in (
                b"\xcf\xfa\xed\xfe",
                b"\xce\xfa\xed\xfe",
                b"\xfe\xed\xfa\xcf",
                b"\xfe\xed\xfa\xce",
            ):
                info["detected_format"] = "macho"
                magic = struct.unpack("<I", header[:4])[0]
                info["macho_magic"] = hex(magic)

            else:
                info["detected_format"] = "unknown"
                info["warning"] = "Could not identify binary format from magic bytes"

        except Exception as e:
            info["error"] = str(e)

        return info
