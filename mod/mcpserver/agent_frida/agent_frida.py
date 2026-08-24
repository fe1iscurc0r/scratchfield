"""agent_frida - Frida dynamic instrumentation MCP agent.

Provides runtime hooking, memory reading, process listing, and script injection
via frida-python native bindings (NOT subprocess).

Gracefully degrades if frida is not installed.
"""

import json
import logging
import sys
import traceback

logger = logging.getLogger(__name__)

# ── lazy import with graceful fallback ──────────────────────────────────
_FRIDA_AVAILABLE = False
_frida_import_error = None
_frida_module = None

def _try_import_frida():
    """Attempt to import frida; store result in module globals."""
    global _FRIDA_AVAILABLE, _frida_import_error, _frida_module
    try:
        import frida
        _frida_module = frida
        _FRIDA_AVAILABLE = True
    except ImportError as e:
        _frida_import_error = str(e)
        _FRIDA_AVAILABLE = False


def _require_frida():
    """Raise a helpful error if frida is not available."""
    if not _FRIDA_AVAILABLE:
        return {
            "status": "error",
            "message": (
                "frida-python is not installed. Install with:\n"
                "  pip install frida-tools\n\n"
                f"Import error: {_frida_import_error}"
            ),
            "data": None,
        }
    return None

# ── Session tracking ────────────────────────────────────────────────────


class FridaSessionTracker:
    """Track active Frida sessions to prevent leaks."""

    def __init__(self):
        self._sessions = {}  # pid_or_name → frida.Session

    def add(self, key: str, session):
        self._sessions[key] = session

    def get(self, key: str):
        return self._sessions.get(key)

    def remove(self, key: str):
        return self._sessions.pop(key, None)

    def list_keys(self):
        return list(self._sessions.keys())

    def detach_all(self):
        """Detach all active sessions and clear tracker."""
        errors = []
        for key, session in list(self._sessions.items()):
            try:
                session.detach()
            except Exception as e:
                errors.append(f"{key}: {e}")
            finally:
                self._sessions.pop(key, None)
        return errors

    @property
    def active_count(self):
        return len(self._sessions)


# ── Agent ────────────────────────────────────────────────────────────────


class FridaAgent:
    """Frida dynamic instrumentation agent.

    Manages the full Frida session lifecycle:
      1. Attach to process (by pid or name)
      2. Operate (list, hook, inject, read memory)
      3. Detach cleanly
    """

    def __init__(self):
        _try_import_frida()
        self._tracker = FridaSessionTracker()

    async def handle_handoff(self, task: dict) -> dict:
        """Main entry point for handoff tasks.

        Expected task format:
            {"tool": "...", "args": {...}}

        Returns:
            {"status": "ok"|"error", "message": "...", "data": ...}
        """
        tool = task.get("tool", "")
        args = task.get("args", {})

        TOOLS = {
            "list_processes": self._list_processes,
            "attach_process": self._attach_process,
            "inject_script": self._inject_script,
            "hook_function": self._hook_function,
            "read_memory": self._read_memory,
            "detach": self._detach,
            "list_sessions": self._list_sessions,
            "detach_all": self._detach_all,
        }
        handler = TOOLS.get(tool)

        if handler is None:
            return json.dumps({
                "status": "error",
                "message": f"Unknown tool: {tool}. Available: {list(TOOLS.keys())}",
                "data": None,
            }, ensure_ascii=False)

        try:
            result = await handler(args)
        except Exception as e:
            logger.error("Error in tool %s: %s", tool, traceback.format_exc())
            result = {
                "status": "error",
                "message": str(e),
                "data": {"traceback": traceback.format_exc()},
            }
        return json.dumps(result, ensure_ascii=False)

    # ── Tools ──────────────────────────────────────────────────────────

    async def _list_processes(self, args: dict) -> dict:
        """List processes on a Frida device.

        Args:
            device: Device type ("usb", "local", "remote:host:port"). Default "usb".
        """
        fail = _require_frida()
        if fail:
            return fail

        device_str = args.get("device", "usb")

        try:
            if device_str == "local":
                dev = _frida_module.get_local_device()
            elif device_str == "usb":
                dev = _frida_module.get_usb_device()
            elif device_str.startswith("remote:"):
                # remote:host:port
                parts = device_str[len("remote:"):].rsplit(":", 1)
                host = parts[0]
                port = int(parts[1]) if len(parts) > 1 else 27042
                dev = _frida_module.get_device_manager().add_remote_device(f"{host}:{port}")
            else:
                return {
                    "status": "error",
                    "message": f"Unknown device type: {device_str}. Use 'usb', 'local', or 'remote:host:port'",
                    "data": None,
                }

            processes = dev.enumerate_processes()
            result = [
                {"pid": p.pid, "name": p.name}
                for p in sorted(processes, key=lambda x: x.pid)
            ]
            return {
                "status": "ok",
                "message": f"Found {len(result)} processes on device {device_str}",
                "data": {"processes": result, "count": len(result)},
            }
        except _frida_module.ServerNotStartedError as e:
            return {"status": "error", "message": f"Frida server not running on {device_str}: {e}", "data": None}
        except Exception as e:
            return {"status": "error", "message": str(e), "data": None}

    async def _attach_process(self, args: dict) -> dict:
        """Attach to a process by pid or name.

        Args:
            pid: Process ID (int) OR name: Process name (str). Required.
            device: Device type. Default "usb".
        """
        fail = _require_frida()
        if fail:
            return fail

        device_str = args.get("device", "usb")
        pid = args.get("pid")
        name = args.get("name")

        if pid is None and name is None:
            return {"status": "error", "message": "Must provide 'pid' or 'name'", "data": None}

        key = str(pid or name)
        if self._tracker.get(key):
            return {
                "status": "error",
                "message": f"Already attached to '{key}'. Detach first or use a different target.",
                "data": None,
            }

        try:
            dev = self._resolve_device(device_str)

            if pid is not None:
                session = dev.attach(int(pid))
            else:
                session = dev.attach(name)

            self._tracker.add(key, session)
            return {
                "status": "ok",
                "message": f"Attached to {key} on device {device_str}",
                "data": {
                    "session_key": key,
                    "active_sessions": self._tracker.active_count,
                    "all_sessions": self._tracker.list_keys(),
                },
            }
        except _frida_module.ProcessNotFoundError as e:
            return {"status": "error", "message": f"Process not found: {e}", "data": None}
        except Exception as e:
            return {"status": "error", "message": str(e), "data": None}

    async def _inject_script(self, args: dict) -> dict:
        """Inject and execute a JavaScript snippet into a target process.

        Args:
            pid: Process ID (int). Required.
            script: JavaScript source code (str). Required.
        """
        fail = _require_frida()
        if fail:
            return fail

        pid = args.get("pid")
        script_src = args.get("script")

        if pid is None or script_src is None:
            return {"status": "error", "message": "Must provide 'pid' and 'script'", "data": None}

        session = self._tracker.get(str(pid))
        if session is None:
            return {"status": "error", "message": f"No active session for pid {pid}. Call attach_process first.", "data": None}

        try:
            script = session.create_script(script_src)
            output = []

            def on_message(message, data):
                output.append({"message": message, "payload": str(data) if data else None})

            script.on("message", on_message)
            script.load()

            return {
                "status": "ok",
                "message": f"Script injected into pid {pid}",
                "data": {"output": output},
            }
        except _frida_module.InvalidOperationError as e:
            return {"status": "error", "message": f"Injection failed: {e}", "data": None}
        except Exception as e:
            return {"status": "error", "message": str(e), "data": None}

    async def _hook_function(self, args: dict) -> dict:
        """Hook a function in a target process.

        Args:
            pid: Process ID (int). Required.
            module: Module name (e.g. "libc.so", "kernel32.dll"). Required.
            function_name: Function to hook (e.g. "open", "MessageBoxW"). Required.
        """
        fail = _require_frida()
        if fail:
            return fail

        pid = args.get("pid")
        module = args.get("module")
        function_name = args.get("function_name")

        if not all([pid, module, function_name]):
            return {
                "status": "error",
                "message": "Must provide 'pid', 'module', and 'function_name'",
                "data": None,
            }

        session = self._tracker.get(str(pid))
        if session is None:
            return {"status": "error", "message": f"No active session for pid {pid}. Call attach_process first.", "data": None}

        hook_script = f"""
        (function() {{
            var target = Module.findExportByName({json.dumps(module)}, {json.dumps(function_name)});
            if (!target) {{
                send({{status: "error", message: "Function '{function_name}' not found in module '{module}'"}});
                return;
            }}
            Interceptor.attach(target, {{
                onEnter: function(args) {{
                    send({{
                        status: "hook_enter",
                        function: {json.dumps(function_name)},
                        module: {json.dumps(module)},
                        args: [args[0].toInt32(), args[1].toInt32(), args[2].toInt32()]
                    }});
                }},
                onLeave: function(retval) {{
                    send({{
                        status: "hook_leave",
                        function: {json.dumps(function_name)},
                        retval: retval.toInt32()
                    }});
                }}
            }});
            send({{status: "hooked", function: {json.dumps(function_name)}, module: {json.dumps(module)}}});
        }})();
        """

        return await self._inject_script({"pid": pid, "script": hook_script})

    async def _read_memory(self, args: dict) -> dict:
        """Read raw memory from a target process.

        Args:
            pid: Process ID (int). Required.
            address: Memory address as hex string or int. Required.
            size: Number of bytes to read (int). Default 64.
        """
        fail = _require_frida()
        if fail:
            return fail

        pid = args.get("pid")
        address = args.get("address")
        size = args.get("size", 64)

        if pid is None or address is None:
            return {"status": "error", "message": "Must provide 'pid' and 'address'", "data": None}

        session = self._tracker.get(str(pid))
        if session is None:
            return {"status": "error", "message": f"No active session for pid {pid}. Call attach_process first.", "data": None}

        # Normalize address
        if isinstance(address, str):
            addr = int(address, 16) if address.startswith("0x") else int(address)
        else:
            addr = int(address)

        read_script = f"""
        (function() {{
            var addr = ptr("{hex(addr)}");
            var data = Memory.readByteArray(addr, {size});
            send({{status: "ok", address: "{hex(addr)}", size: {size}, hex: hexdump(data, {{offset: {addr}, length: {size}, header: false}})}});
        }})();
        """

        return await self._inject_script({"pid": pid, "script": read_script})

    async def _detach(self, args: dict) -> dict:
        """Detach from a specific process session.

        Args:
            pid: Process ID (int) or process name (str). Required.
        """
        fail = _require_frida()
        if fail:
            return fail

        pid = args.get("pid")
        name = args.get("name")
        key = str(pid or name)

        if not key:
            return {"status": "error", "message": "Must provide 'pid' or 'name' to detach", "data": None}

        session = self._tracker.remove(key)
        if session is None:
            return {
                "status": "error",
                "message": f"No active session for '{key}'. Active sessions: {self._tracker.list_keys()}",
                "data": None,
            }

        try:
            session.detach()
        except Exception as e:
            logger.warning("Detach warning for %s: %s", key, e)

        return {
            "status": "ok",
            "message": f"Detached from {key}",
            "data": {
                "detached_key": key,
                "remaining_sessions": self._tracker.active_count,
                "all_sessions": self._tracker.list_keys(),
            },
        }

    async def _list_sessions(self, _args: dict) -> dict:
        """List all active Frida sessions."""
        return {
            "status": "ok",
            "message": f"{self._tracker.active_count} active session(s)",
            "data": {
                "count": self._tracker.active_count,
                "sessions": self._tracker.list_keys(),
            },
        }

    async def _detach_all(self, _args: dict) -> dict:
        """Detach all active sessions."""
        errors = self._tracker.detach_all()
        data = {"detached_count": 0, "errors": errors}
        if errors:
            data["detached_count"] = len(errors)
            return {"status": "warning", "message": "Some sessions had errors during detach", "data": data}
        return {"status": "ok", "message": "All sessions detached", "data": data}

    # ── Helpers ────────────────────────────────────────────────────────

    def _resolve_device(self, device_str: str):
        """Resolve a Frida device string to a device object."""
        if device_str == "local":
            return _frida_module.get_local_device()
        elif device_str == "usb":
            return _frida_module.get_usb_device()
        elif device_str.startswith("remote:"):
            parts = device_str[len("remote:"):].rsplit(":", 1)
            host = parts[0]
            port = int(parts[1]) if len(parts) > 1 else 27042
            return _frida_module.get_device_manager().add_remote_device(f"{host}:{port}")
        raise ValueError(f"Unknown device: {device_str}")
