"""W121-01：Code Workspace 工具集 —— 让 Lumo 能「动手」写/跑/测代码。

六个工具（全部受 sandbox 约束，无任意 shell、无任意路径写）：
- `code_exec`   跑 Python/JS 代码片段（隔离工作目录、无交互、超时/内存上限）
- `file_read`   读工作区内文件
- `file_write`  写工作区内文件（默认返回 diff 预览；`dry_run=True` 只预览不落盘）
- `file_edit`   old→new 片段替换（patch 语义，同样支持 dry_run）
- `shell_exec`  白名单命令执行（首 token 白名单 + 硬拒清单 + 无 shell 元字符）
- `test_run`    跑 pytest 并解析摘要（passed/failed/error + 失败用例名）

错误语义：沙箱拒绝/超时/资源超限一律回结构化错误码（`{error: "timeout"}` 等），不吞异常。
"""
from __future__ import annotations

import difflib
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from . import sandbox
from .sandbox import SandboxError

logger = logging.getLogger(__name__)

MAX_FILE_BYTES = 1 * 1024 * 1024  # 单文件读写上限 1MB

_PYTEST_SUMMARY_RE = re.compile(r"(\d+)\s+(passed|failed|error|errors|skipped|xfailed|xpassed)")
_PYTEST_FAILED_LINE_RE = re.compile(r"^(FAILED|ERROR)\s+(\S+)", re.MULTILINE)


def _diff_preview(old_text: str, new_text: str, *, path: str, max_lines: int = 200) -> str:
    diff = list(
        difflib.unified_diff(
            (old_text or "").splitlines(),
            (new_text or "").splitlines(),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            lineterm="",
        )
    )
    if len(diff) > max_lines:
        diff = diff[:max_lines] + [f"...<diff 截断，共 {len(diff)} 行>"]
    return "\n".join(diff)


def _read_text(path: Path) -> str:
    data = path.read_bytes()
    if len(data) > MAX_FILE_BYTES:
        raise SandboxError("file_too_large", f"文件超过 {MAX_FILE_BYTES // 1024}KB，拒绝读取")
    return data.decode("utf-8", errors="replace")


def _parse_pytest_output(output: str) -> Dict[str, Any]:
    counts: Dict[str, int] = {}
    for value, kind in _PYTEST_SUMMARY_RE.findall(output or ""):
        key = "error" if kind.startswith("error") else kind
        counts[key] = counts.get(key, 0) + int(value)
    failed = [m.group(2) for m in _PYTEST_FAILED_LINE_RE.finditer(output or "")]
    return {
        "passed": counts.get("passed", 0),
        "failed": counts.get("failed", 0),
        "errors": counts.get("error", 0),
        "skipped": counts.get("skipped", 0),
        "failed_tests": failed[:20],
    }


class CodeWorkspaceBridge:
    """mcpserver 扫描入口（entryPoint {module, class}）。"""

    name = "code_workspace"

    # ---- 工具 ----

    def code_exec(
        self,
        code: str,
        language: str = "python",
        timeout_s: float | None = None,
        session_id: str = "default",
    ) -> Dict[str, Any]:
        """执行代码片段（隔离工作目录，无交互）。"""
        if not str(code or "").strip():
            return {"error": "empty_code", "message": "code 不能为空"}
        try:
            argv_prefix = sandbox.interpreter_for(language)
        except SandboxError as e:
            return e.to_dict()
        cwd = sandbox.session_workspace(session_id)
        result = sandbox.run_process([*argv_prefix, code], cwd=cwd, timeout_s=timeout_s)
        sandbox.audit(
            {
                "tool": "code_exec",
                "session_id": session_id,
                "language": language,
                "code": str(code)[:500],
                "exit_code": result.get("exit_code"),
                "error": result.get("error", ""),
            }
        )
        if "error" in result:
            return result
        return {
            "ok": result.get("exit_code") == 0,
            "stdout": result.get("stdout", ""),
            "stderr": result.get("stderr", ""),
            "exit_code": result.get("exit_code", 1),
            "duration_s": result.get("duration_s"),
        }

    def file_read(self, path: str, session_id: str = "default") -> Dict[str, Any]:
        """读工作区内文件。"""
        try:
            target = sandbox.resolve_in_workspace(path, session_id)
        except SandboxError as e:
            return e.to_dict()
        if not target.exists() or not target.is_file():
            return {"error": "not_found", "message": f"文件不存在: {path}"}
        try:
            content = _read_text(target)
        except SandboxError as e:
            return e.to_dict()
        return {"ok": True, "path": path, "content": content, "bytes": len(content.encode("utf-8"))}

    def file_write(
        self,
        path: str,
        content: str,
        session_id: str = "default",
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """写文件（默认返回 diff 预览；dry_run=True 不落盘）。"""
        try:
            target = sandbox.resolve_in_workspace(path, session_id)
        except SandboxError as e:
            return e.to_dict()
        old_text = _read_text(target) if target.exists() and target.is_file() else ""
        new_text = str(content or "")
        diff = _diff_preview(old_text, new_text, path=path)
        payload: Dict[str, Any] = {
            "ok": True,
            "path": path,
            "created": not target.exists(),
            "diff": diff,
            "dry_run": bool(dry_run),
        }
        if dry_run:
            return payload
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            # 走字节写入：Windows 文本模式会把 \n 改写成 \r\n，破坏 diff/补丁一致性
            target.write_bytes(new_text.encode("utf-8"))
        except OSError as e:
            return {"error": "write_failed", "message": str(e)}
        sandbox.audit(
            {
                "tool": "file_write",
                "session_id": session_id,
                "path": path,
                "bytes": len(new_text.encode("utf-8")),
                "diff": diff[:1000],
            }
        )
        return payload

    def file_edit(
        self,
        path: str,
        old: str,
        new: str,
        session_id: str = "default",
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """old→new 片段替换（patch 语义）。old 必须唯一命中。"""
        try:
            target = sandbox.resolve_in_workspace(path, session_id)
        except SandboxError as e:
            return e.to_dict()
        if not target.exists() or not target.is_file():
            return {"error": "not_found", "message": f"文件不存在: {path}"}
        old_text = _read_text(target)
        if not str(old or ""):
            return {"error": "empty_old", "message": "old 不能为空"}
        hits = old_text.count(old)
        if hits == 0:
            return {"error": "old_not_found", "message": "未找到 old 片段，文件未修改"}
        if hits > 1:
            return {"error": "old_ambiguous", "message": f"old 片段命中 {hits} 次，请给出更长的唯一片段"}
        new_text = old_text.replace(old, new, 1)
        diff = _diff_preview(old_text, new_text, path=path)
        payload: Dict[str, Any] = {"ok": True, "path": path, "diff": diff, "dry_run": bool(dry_run)}
        if dry_run:
            return payload
        try:
            target.write_text(new_text, encoding="utf-8")
        except OSError as e:
            return {"error": "write_failed", "message": str(e)}
        sandbox.audit(
            {"tool": "file_edit", "session_id": session_id, "path": path, "diff": diff[:1000]}
        )
        return payload

    def shell_exec(
        self, command: str, session_id: str = "default", timeout_s: float | None = None
    ) -> Dict[str, Any]:
        """白名单命令执行（首 token 白名单 + 硬拒清单 + 无 shell 元字符）。"""
        try:
            argv = sandbox.validate_command(command)
        except SandboxError as e:
            sandbox.audit(
                {"tool": "shell_exec", "session_id": session_id, "command": str(command)[:300], "denied": e.code}
            )
            return e.to_dict()
        cwd = sandbox.session_workspace(session_id)
        result = sandbox.run_process(argv, cwd=cwd, timeout_s=timeout_s)
        sandbox.audit(
            {
                "tool": "shell_exec",
                "session_id": session_id,
                "command": str(command)[:300],
                "exit_code": result.get("exit_code"),
                "error": result.get("error", ""),
            }
        )
        if "error" in result:
            return result
        return {
            "ok": result.get("exit_code") == 0,
            "stdout": result.get("stdout", ""),
            "stderr": result.get("stderr", ""),
            "exit_code": result.get("exit_code", 1),
            "duration_s": result.get("duration_s"),
        }

    def test_run(
        self,
        path: str = ".",
        session_id: str = "default",
        timeout_s: float | None = None,
        extra_args: str = "",
    ) -> Dict[str, Any]:
        """跑 pytest 并解析摘要（passed/failed/error + 失败用例名）。"""
        try:
            target = sandbox.resolve_in_workspace(path, session_id)
        except SandboxError as e:
            return e.to_dict()
        argv = [sys.executable, "-m", "pytest", str(target), "-q", "--no-header", "-p", "no:cacheprovider"]
        if str(extra_args or "").strip():
            import shlex

            try:
                argv.extend(shlex.split(extra_args))
            except ValueError as e:
                return {"error": "bad_extra_args", "message": str(e)}
        cwd = sandbox.session_workspace(session_id)
        result = sandbox.run_process(argv, cwd=cwd, timeout_s=timeout_s)
        output = f"{result.get('stdout', '')}\n{result.get('stderr', '')}"
        summary = _parse_pytest_output(output)
        sandbox.audit(
            {
                "tool": "test_run",
                "session_id": session_id,
                "path": path,
                "exit_code": result.get("exit_code"),
                "summary": summary,
                "error": result.get("error", ""),
            }
        )
        payload: Dict[str, Any] = {
            "ok": result.get("exit_code") == 0 and not summary["failed"] and not summary["errors"],
            "exit_code": result.get("exit_code"),
            "summary": summary,
            "output_tail": (result.get("stdout", "") or "")[-2000:],
        }
        if "error" in result:
            payload["error"] = result["error"]
            payload["message"] = result.get("message", "")
        return payload

    # ---- manifest 桥接约定 ----

    _TOOLS: Dict[str, Callable[..., Dict[str, Any]]] = {}

    def __init__(self) -> None:
        self._TOOLS = {
            "code_exec": self.code_exec,
            "file_read": self.file_read,
            "file_write": self.file_write,
            "file_edit": self.file_edit,
            "shell_exec": self.shell_exec,
            "test_run": self.test_run,
        }

    async def handle_handoff(self, task: dict) -> str:
        tool_name = str(task.get("tool_name") or "").strip()
        if not tool_name:
            return json.dumps({"status": "error", "message": "缺少 tool_name", "data": {}}, ensure_ascii=False)
        fn = self._TOOLS.get(tool_name)
        if fn is None:
            return json.dumps(
                {
                    "status": "error",
                    "message": f"未知工具 {tool_name}，可用: {', '.join(sorted(self._TOOLS))}",
                    "data": {},
                },
                ensure_ascii=False,
            )
        if isinstance(task.get("params"), dict):
            arguments = task["params"]
        elif isinstance(task.get("arguments"), dict):
            arguments = task["arguments"]
        else:
            # MCP dispatch 会把 _tool_call_id/_original_name/_original_args 等内部字段
            # 平铺在同一个 dict 里，必须整体剔除（下划线前缀一律不是工具入参）
            arguments = {
                k: v
                for k, v in task.items()
                if not k.startswith("_") and k not in ("tool_name", "agentType", "service_name")
            }
        try:
            import asyncio

            data = await asyncio.to_thread(lambda: fn(**arguments))
        except TypeError as e:
            return json.dumps({"status": "error", "message": f"参数错误: {e}", "data": {}}, ensure_ascii=False)
        except SandboxError as e:
            return json.dumps({"status": "error", "message": e.message, "data": e.to_dict()}, ensure_ascii=False)
        except Exception as e:  # noqa: BLE001
            return json.dumps(
                {"status": "error", "message": f"{type(e).__name__}: {e}", "data": {}}, ensure_ascii=False
            )
        if isinstance(data, dict) and data.get("error"):
            return json.dumps(
                {"status": "error", "message": str(data.get("message") or data["error"]), "data": data},
                ensure_ascii=False,
            )
        return json.dumps({"status": "success", "message": "ok", "data": data}, ensure_ascii=False, default=str)
