"""W121-04：代码工作区沙箱 —— 路径隔离 + 进程限制 + 命令白名单 + 审计。

安全模型（README 同步声明）：**沙箱 ≠ 完全隔离**（无容器/无 namespace）。
本模块给到的是：工作目录隔离、路径穿越防护、命令白名单、超时/内存上限、无交互、环境白名单、全量审计。
任何"任意 shell / 任意路径写"的能力都不提供。

- 工作区：`<workspace_root>/workspace/<session_id>/`，所有文件操作 resolve 后必须落在其内
- 路径穿越：拒绝 `..` 段、拒绝绝对路径、resolve 后校验（symlink 逃逸也拦住）
- 进程：`subprocess` + argv 列表（**不经 shell**）+ stdin=DEVNULL + 超时 kill + 内存上限
  * POSIX：`resource.setrlimit`（CPU/AS）
  * Windows：无 rlimit → `psutil` 看门狗超限即杀（psutil 已在依赖里）
  * cwd：必须落在 `workspace_root()` 内，不继承调用方 cwd（P0-2）
  * 环境：只透传 `ENV_ALLOWLIST` 里的变量 + 主动设定 `ENV_FORCED_DEFAULTS`；
    名字像凭据的一律丢弃（P0-2）—— 模型触发的代码执行不再继承调用方的 API key / token
- Python 片段（code_exec）带 `-I -E -B -X utf8`：隔离模式 + 不读 PYTHON* + 不写字节码
  （`-E` 使原来的 `PYTHONIOENCODING` / `PYTHONDONTWRITEBYTECODE` 环境变量失效，故改用命令行参数）
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
# 子进程环境白名单（P0-2）
# ---------------------------------------------------------------------------

#: **允许**透传给子进程的环境变量名（大写比对，Windows 大小写不敏感）。
#: 白名单之外一律丢弃 —— 模型触发的代码执行**不再继承**调用方的全部环境。
#: 这张表是单元测试的断言对象（见 tests/test_code_workspace.py），不要散落到各处。
ENV_ALLOWLIST: frozenset = frozenset(
    {
        # 可执行查找
        "PATH",
        "PATHEXT",
        # 临时目录（POSIX / Windows / *BSD 三种写法都照顾到）
        "TMPDIR",
        "TEMP",
        "TMP",
        # 区域、时区、终端
        "LANG",
        "LC_ALL",
        "TZ",
        "TERM",
        # 家目录与 shell（git/node/npm 缺了会告警或起不来）
        "HOME",
        "USERPROFILE",
        "SHELL",
        # Windows 系统位置：缺 SYSTEMROOT/WINDIR 时 python 的 socket、node 的 path 都会出问题
        "SYSTEMROOT",
        "WINDIR",
        "COMSPEC",
        "PROGRAMDATA",
        "PROGRAMFILES",
        "PROGRAMFILES(X86)",
        "LOCALAPPDATA",
        "APPDATA",
        "COMMONPROGRAMFILES",
        "SYSTEMDRIVE",
        "HOMEDRIVE",
        "HOMEPATH",
        "USERNAME",
        "USERDOMAIN",
        # 非凭据的运行时开关：留着它，父进程已有的取值不会被抹掉（见下面强制默认值）
        "PYTHONIOENCODING",
        "PYTHONDONTWRITEBYTECODE",
    }
)

#: 由沙箱**主动设定**的变量（不是从父进程继承来的）。白名单只管"继承"，管不了"父进程根本没有"。
#: 这两项改前是 run_process 里硬塞的；不塞就会出真实回归：
#: - 缺 ``PYTHONIOENCODING`` ⇒ shell_exec 里模型自拼的 ``python -c "print('中文')"`` 退回 GBK，
#:   父进程按 utf-8 解码成乱码（2026-10-22 实测）；
#: - 缺 ``PYTHONDONTWRITEBYTECODE`` ⇒ 自拼的 ``python -m pytest`` 往工作区撒 ``__pycache__``。
#: code_exec / test_run 另有 `-X utf8` / `-B` 命令行参数兜底（`-E` 会让环境变量失效）。
ENV_FORCED_DEFAULTS: dict = {"PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"}

#: 名字命中即**永不**透传：即使被误加进 ENV_ALLOWLIST、或从 env_extra 递进来，也拦掉。
#: 工单点名的四类形状（``*_API_KEY`` / ``*_TOKEN`` / ``*_SECRET`` / ``*PASSWORD*``）是下限，
#: 这里再补凭据类同义词，避免下一位改配置的人无意间把凭据放进白名单。
_SECRET_NAME_RE = re.compile(
    r"api[_.-]?key|access[_.-]?key|secret|token|passw|credential|authorization|"
    r"bearer|cookie|private[_.-]?key|psk|secret[_-]?key",
    re.IGNORECASE,
)


def is_secret_env_name(name: str) -> bool:
    """变量名是否属于凭据/密钥类 —— 只看名字，绝不触碰值。"""
    return bool(_SECRET_NAME_RE.search(str(name or "")))


#: 模型触发的 Python 代码片段（``code_exec``）的隔离参数。这张表也是单测断言对象。
#:
#: - ``-I`` 隔离模式：忽略用户 site 与 PYTHON*。Python 3.11+ 里 ``-I`` **隐含** ``-E -s -P``。
#:   代价：``sys.path`` 不再自动含工作目录（``-c`` 与脚本文件两种形态都不含，实测
#:   ``sys.flags.safe_path is True``）—— 工作区内模块要先 ``sys.path.insert(0, os.getcwd())``
#:   再 import；"写模块再用 pytest 测" 的路径走 ``test_run``（它不带 ``-I``，见下）。
#: - ``-E``  显式写出（虽然 ``-I`` 已含）：读代码的人不必记得隐含关系。
#: - ``-B``  不写字节码：``-E`` 让原来的 ``PYTHONDONTWRITEBYTECODE=1`` 失效，改用命令行参数。
#: - ``-X utf8`` 取代原来的 ``PYTHONIOENCODING=utf-8``：同样因 ``-E`` 失效而必须换成参数。
#:   实测本机不带它时子进程 stdout 编码退回 ``gbk``，父进程按 utf-8 解码会把中文输出打成乱码。
PYTHON_ISOLATION_FLAGS: tuple = ("-I", "-E", "-B", "-X", "utf8")

#: ``test_run`` 用的参数：只保留"不写字节码 + UTF-8 输出"，**不带** ``-I``。
#: 隔离模式会摘掉 cwd 与脚本目录，被测模块的 import 会整片失败；测试路径需要它能 import，
#: 而环境隔离由 ``build_child_env`` 白名单负责（PYTHON* 名字本就进不来）。
RUNTIME_ONLY_FLAGS: tuple = ("-E", "-B", "-X", "utf8")


def build_child_env(env_extra: Dict[str, str] | None = None) -> Tuple[Dict[str, str], List[str]]:
    """按 ENV_ALLOWLIST 构造子进程环境；返回 (env, 被丢弃的变量名列表)。

    三道闸，顺序不可换：
    1. 白名单 —— 不在 ``ENV_ALLOWLIST`` 里的名字直接丢弃（默认拒绝）；
    2. 秘密命名否决 —— 命中 ``_SECRET_NAME_RE`` 的名字即使被加进白名单也丢弃；
    3. 强制默认值 —— ``ENV_FORCED_DEFAULTS`` 补齐（白名单只管继承、管不了父进程本来就没有）。

    ``env_extra`` 走同样的两道闸（白名单 ∩ 非秘密），不再拥有"绕过白名单"的能力。
    返回值只含**名字**，供审计记录；任何情况下不把值写进审计。
    """
    by_upper: Dict[str, Tuple[str, str]] = {}
    for key, value in os.environ.items():
        by_upper.setdefault(str(key).upper(), (str(key), str(value)))

    env: Dict[str, str] = {}
    dropped: List[str] = []
    for upper, (original, value) in sorted(by_upper.items()):
        if upper in ENV_ALLOWLIST and not is_secret_env_name(upper):
            env[original] = value
        else:
            dropped.append(original)

    # 沙箱主动设定（父进程有就沿用，没有就补上）—— 保证子进程输出/工作区洁净度不退化
    for name, value in ENV_FORCED_DEFAULTS.items():
        if not any(k.upper() == name for k in env):
            env[name] = value

    for key, value in (env_extra or {}).items():
        name = str(key)
        upper = name.upper()
        if upper in ENV_ALLOWLIST and not is_secret_env_name(upper):
            # 丢掉原样大小写的那份（Windows 上是 Path）：环境块里同名变体只留一个
            for existing in [k for k in env if k.upper() == upper]:
                del env[existing]
            env[name] = str(value)
        else:
            dropped.append(name)
    return env, dropped


def require_cwd_in_sandbox(cwd: Path) -> Path:
    """进程工作目录必须落在沙箱根内 —— 不继承调用方 cwd。越界抛 SandboxError。"""
    target = Path(cwd).resolve()
    root = workspace_root().resolve()
    if target != root and root not in target.parents:
        raise SandboxError("cwd_outside_sandbox", f"拒绝在沙箱外执行进程: {cwd}")
    return target


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
    """在隔离工作目录执行 argv（不经 shell、无交互、有超时/内存上限）。

    环境按 ``ENV_ALLOWLIST`` 白名单构造（P0-2）：默认拒绝，凭据命名一票否决。
    工作目录必须在沙箱根内：不继承调用方 cwd。
    """
    default_timeout, default_mem, default_chars = _limits()
    timeout = float(timeout_s if timeout_s is not None else default_timeout)
    timeout = max(1.0, min(timeout, 300.0))
    mem = int(memory_mb if memory_mb is not None else default_mem)
    chars = int(max_output_chars if max_output_chars is not None else default_chars)

    try:
        workdir = require_cwd_in_sandbox(cwd)
    except SandboxError as e:
        return {**e.to_dict(), "exit_code": 126}
    env, env_dropped = build_child_env(env_extra)

    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    started = time.time()
    stop = threading.Event()
    try:
        proc = subprocess.Popen(  # noqa: S603 - argv 列表 + 白名单校验，无 shell
            argv,
            cwd=str(workdir),
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
        # 只记名字，绝不记值 —— 供审计回看"哪些变量被白名单挡住了"
        "env_dropped": sorted(set(env_dropped)),
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
    """语言 → 解释器 argv 前缀（只允许 python / javascript）。

    Python 侧带隔离参数（P0-2）；行为变化见 ``PYTHON_ISOLATION_FLAGS`` 注释。
    """
    lang = str(language or "python").strip().lower()
    if lang in ("python", "py", "python3"):
        return [sys.executable, *PYTHON_ISOLATION_FLAGS, "-c"]
    if lang in ("javascript", "js", "node"):
        return ["node", "-e"]
    raise SandboxError("unsupported_language", f"不支持的语言: {language}（可用 python/javascript）")
