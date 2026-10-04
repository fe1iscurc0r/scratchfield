"""W121-04：代码工作区沙箱 —— 路径隔离 + 进程限制 + 命令白名单 + 审计。

安全模型（README 同步声明）：**沙箱 ≠ 完全隔离**（无容器/无 namespace）。
本模块给到的是：工作目录隔离、路径穿越防护、命令白名单、超时/内存上限、无交互、全量审计。
任何"任意 shell / 任意路径写"的能力都不提供。

- 工作区：`<workspace_root>/workspace/<session_id>/`，所有文件操作 resolve 后必须落在其内
- 路径穿越：拒绝 `..` 段、拒绝绝对路径、resolve 后校验（symlink 逃逸也拦住）
- 进程：`subprocess` + argv 列表（**不经 shell**）+ stdin=DEVNULL + 超时 kill + 内存上限
  * POSIX：`resource.setrlimit`（CPU/AS）
  * Windows：无 rlimit → `psutil` 看门狗超限即杀（psutil 已在依赖里）
- 白名单：`config.code_space.shell_allowlist` 首 token 精确匹配；含 shell 元字符直接拒；
  `sudo/rm/dd/mkfs/curl/wget/ssh/scp` 等永不在白名单内且额外硬拒
- 审计：每次执行/文件写操作追加 `<user_data>/audit/code_workspace.ndjson`（脱敏 + 截断）
"""
from __future__ import annotations

import json
import logging
import os
import re
import shlex
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

#: 永不执行的命令（即使被误加进配置白名单）
_HARD_DENY = frozenset({
    "sudo", "su", "doas", "rm", "rmdir", "dd", "mkfs", "fdisk", "format",
    "shutdown", "reboot", "taskkill", "kill", "killall", "curl", "wget",
    "ssh", "scp", "sftp", "nc", "netcat", "ncat", "telnet", "chmod", "chown",
    "attrib", "icacls", "takeown", "reg", "sc", "net", "powershell", "pwsh", "cmd",
})

#: shell 元字符（与 agentic_tool_loop 的执行白名单同源的保守集）
_SHELL_METACHARS_RE = re.compile(r"[;&|`$><\n\r\x00]")

_MAX_PATH_SEGMENTS = 32


class SandboxError(RuntimeError):
    """沙箱拒绝（路径越界 / 白名单 / 资源）—— 错误码形式回给 LLM。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def to_dict(self) -> Dict[str, str]:
        return {"error": self.code, "message": self.message}


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------


def _cfg() -> Any:
    try:
        from system.config import get_config

        return get_config().code_space
    except Exception as e:  # noqa: BLE001 - 配置不可用时用保守默认
        logger.debug("[code_workspace] 读取配置失败，用默认值: %s", e)
        return None


def workspace_root() -> Path:
    cfg = _cfg()
    configured = str(getattr(cfg, "workspace_root", "") or "").strip()
    if configured:
        root = Path(configured).expanduser()
    else:
        from system.config import get_data_dir

        root = Path(get_data_dir()) / "code_workspace"
    root.mkdir(parents=True, exist_ok=True)
    return root


def session_workspace(session_id: str) -> Path:
    """会话工作目录（不存在则创建）。session_id 被消毒成安全目录名。"""
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", str(session_id or "default"))[:64] or "default"
    path = workspace_root() / "workspace" / safe
    path.mkdir(parents=True, exist_ok=True)
    return path


def shell_allowlist() -> set[str]:
    cfg = _cfg()
    listed = getattr(cfg, "shell_allowlist", None) or []
    return {str(x).strip().lower() for x in listed if str(x).strip()}


def _limits() -> Tuple[float, int, int]:
    cfg = _cfg()
    timeout = float(getattr(cfg, "exec_timeout_s", 10.0) or 10.0)
    memory_mb = int(getattr(cfg, "memory_limit_mb", 256) or 256)
    max_chars = int(getattr(cfg, "max_output_chars", 20000) or 20000)
    return timeout, memory_mb, max_chars


# ---------------------------------------------------------------------------
# 路径隔离
# ---------------------------------------------------------------------------


def resolve_in_workspace(relative_path: str, session_id: str) -> Path:
    """把相对路径解析到会话工作区内；越界一律 SandboxError。

    拒绝：空路径、`..` 段、绝对路径、resolve 后不在根内（含 symlink 逃逸）、段数过多。
    """
    raw = str(relative_path or "").strip()
    if not raw:
        raise SandboxError("empty_path", "路径不能为空")
    if len(raw) > 512:
        raise SandboxError("path_too_long", "路径过长（>512 字符）")

    candidate = Path(raw)
    if candidate.is_absolute() or raw.startswith(("~", "/", "\\")):
        raise SandboxError("absolute_path_denied", f"拒绝绝对路径: {raw}")
    if len(candidate.parts) > _MAX_PATH_SEGMENTS:
        raise SandboxError("path_too_deep", f"路径层级过深（>{_MAX_PATH_SEGMENTS}）")
    if any(part in ("..", "") for part in candidate.parts):
        raise SandboxError("path_traversal_denied", f"拒绝路径穿越: {raw}")

    root = session_workspace(session_id).resolve()
    resolved = (root / candidate).resolve()
    if resolved != root and root not in resolved.parents:
        # resolve 之后仍越界 = symlink 逃逸或奇怪路径
        raise SandboxError("path_escape_denied", f"路径越出工作区: {raw}")
    return resolved


# ---------------------------------------------------------------------------
# 命令校验
# ---------------------------------------------------------------------------


def validate_command(command: str) -> List[str]:
    """校验并切分出 argv（不经 shell）。返回 argv 列表，违规抛 SandboxError。"""
    text = str(command or "").strip()
    if not text:
        raise SandboxError("empty_command", "命令不能为空")
    if len(text) > 2000:
        raise SandboxError("command_too_long", "命令过长（>2000 字符）")
    if _SHELL_METACHARS_RE.search(text):
        raise SandboxError("shell_metachar_denied", "命令包含 shell 元字符（;&|`$>< 换行等），已拒绝")

    try:
        argv = shlex.split(text)
    except ValueError as e:
        raise SandboxError("command_parse_error", f"命令解析失败: {e}") from e
    if not argv:
        raise SandboxError("empty_command", "命令不能为空")

    # 允许 `python -c ...` 这类带路径的可执行名：取 basename 比对
    head = Path(argv[0]).name.lower()
    if head.endswith(".exe"):
        head = head[:-4]
    if head in _HARD_DENY:
        raise SandboxError("hard_denied", f"命令 {head} 属硬拒绝清单（永不允许）")
    allowed = shell_allowlist()
    if head not in allowed:
        raise SandboxError(
            "not_allowlisted",
            f"命令 {head} 不在白名单内；可用: {', '.join(sorted(allowed)) or '(空)'}",
        )
    return argv


# ---------------------------------------------------------------------------
# 执行
# ---------------------------------------------------------------------------


def _truncate(text: str, limit: int) -> str:
    text = str(text or "")
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n…<截断，原文 {len(text)} 字符>"


def _posix_preexec(memory_mb: int):
    """POSIX：子进程资源上限（CPU 秒 + 地址空间）。"""
    if os.name == "nt":  # pragma: no cover - Windows 无 resource
        return None

    def _apply() -> None:  # pragma: no cover - 仅 POSIX 生效
        try:
            import resource

            cpu_s = max(1, int(memory_mb / 32))
            resource.setrlimit(resource.RLIMIT_CPU, (cpu_s, cpu_s))
            limit_bytes = memory_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (limit_bytes, limit_bytes))
        except Exception:
            pass

    return _apply


def _watch_memory(proc: subprocess.Popen, memory_mb: int, stop: threading.Event) -> None:
    """Windows 兜底：psutil 看门狗，超限即杀（POSIX 由 rlimit 负责）。"""
    try:
        import psutil
    except Exception:  # noqa: BLE001 - 没有 psutil 就只靠超时
        return
    limit = memory_mb * 1024 * 1024
    try:
        handle = psutil.Process(proc.pid)
    except Exception:  # noqa: BLE001
        return
    while not stop.is_set():
        try:
            rss = handle.memory_info().rss
            if rss > limit:
                logger.warning("[code_workspace] 子进程内存超限（%dMB），终止", rss // 1024 // 1024)
                proc.kill()
                return
            for child in handle.children(recursive=True):
                if child.memory_info().rss > limit:
                    proc.kill()
                    return
        except Exception:  # noqa: BLE001 - 进程已退出
            return
        stop.wait(0.2)


def run_process(
    argv: List[str],
    *,
    cwd: Path,
    timeout_s: float | None = None,
    memory_mb: int | None = None,
    max_output_chars: int | None = None,
    env_extra: Dict[str, str] | None = None,
) -> Dict[str, Any]:
    """在隔离工作目录执行 argv（不经 shell、无交互、有超时/内存上限）。"""
    default_timeout, default_mem, default_chars = _limits()
    timeout = float(timeout_s if timeout_s is not None else default_timeout)
    timeout = max(1.0, min(timeout, 300.0))
    mem = int(memory_mb if memory_mb is not None else default_mem)
    chars = int(max_output_chars if max_output_chars is not None else default_chars)

    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"}
    if env_extra:
        env.update({str(k): str(v) for k, v in env_extra.items()})

    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    started = time.time()
    stop = threading.Event()
    try:
        proc = subprocess.Popen(  # noqa: S603 - argv 列表 + 白名单校验，无 shell
            argv,
            cwd=str(cwd),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=creationflags,
            preexec_fn=_posix_preexec(mem) if os.name != "nt" else None,
        )
    except FileNotFoundError as e:
        return {"error": "executable_not_found", "message": str(e), "exit_code": 127}
    except Exception as e:  # noqa: BLE001
        return {"error": "spawn_failed", "message": f"{type(e).__name__}: {e}", "exit_code": 1}

    watchdog = None
    if os.name == "nt":
        watchdog = threading.Thread(target=_watch_memory, args=(proc, mem, stop), daemon=True)
        watchdog.start()

    timed_out = False
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        proc.kill()
        try:
            out, err = proc.communicate(timeout=5)
        except Exception:  # noqa: BLE001
            out, err = "", ""
    finally:
        stop.set()

    duration = round(time.time() - started, 3)
    result: Dict[str, Any] = {
        "stdout": _truncate(out, chars),
        "stderr": _truncate(err, chars),
        "exit_code": proc.returncode,
        "duration_s": duration,
    }
    if timed_out:
        result.update({"error": "timeout", "message": f"执行超时（>{timeout}s），已终止"})
    return result


# ---------------------------------------------------------------------------
# 审计
# ---------------------------------------------------------------------------


def _audit_path() -> Path:
    from system.config import get_data_dir

    return Path(get_data_dir()) / "audit" / "code_workspace.ndjson"


def audit(record: Dict[str, Any]) -> None:
    """每次执行/写操作落一条审计（脱敏 + 截断；失败只告警）。"""
    try:
        from apiserver.metric_sanitize import sanitize_value

        safe = sanitize_value({**record, "ts": time.time()})
        path = _audit_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(safe, ensure_ascii=False, default=str)[:4000] + "\n")
    except OSError as e:
        logger.warning("[code_workspace] 审计落盘失败: %s", e)


def interpreter_for(language: str) -> List[str]:
    """语言 → 解释器 argv 前缀（只允许 python / javascript）。"""
    lang = str(language or "python").strip().lower()
    if lang in ("python", "py", "python3"):
        return [sys.executable, "-c"]
    if lang in ("javascript", "js", "node"):
        return ["node", "-e"]
    raise SandboxError("unsupported_language", f"不支持的语言: {language}（可用 python/javascript）")
