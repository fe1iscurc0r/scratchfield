"""本地执行后端（授粉-C1）。

shell 任务走 ``subprocess.run`` 子进程，python 任务在工作线程里
直接调用 callable（保持统一的 Future 返回语义）。
Windows 下子进程叠加 CREATE_NO_WINDOW，避免弹出控制台黑框。
"""

from __future__ import annotations

import contextlib
import logging
import os
import subprocess
import sys
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any

from research.execution.base import ExecutionBackend, TaskSpec

logger = logging.getLogger(__name__)

_DEFAULT_MAX_WORKERS = 4

# Windows 下隐藏子进程控制台窗口（无窗口可继承时 subprocess 会新建一个）
_WIN_NO_WINDOW = (
    getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
)


def _run_shell_task(task: TaskSpec) -> dict[str, Any]:
    """在子进程里跑一条 shell 命令。

    stdout/stderr 给了落盘路径就重定向到文件，否则捕获进内存。
    返回 ``{"returncode", "stdout", "stderr"}``（捕获模式下为文本）。
    """
    env = None
    if task.env:
        env = {**os.environ, **task.env}

    stdout_fh = open(task.stdout, "w", encoding="utf-8") if task.stdout else None
    stderr_fh = open(task.stderr, "w", encoding="utf-8") if task.stderr else None
    try:
        result = subprocess.run(
            task.command,
            shell=True,
            cwd=task.working_dir,
            env=env,
            stdout=stdout_fh if stdout_fh else subprocess.PIPE,
            stderr=stderr_fh if stderr_fh else subprocess.PIPE,
            creationflags=_WIN_NO_WINDOW,
            check=False,
        )
    finally:
        for fh in (stdout_fh, stderr_fh):
            if fh is not None:
                with contextlib.suppress(OSError):
                    fh.close()

    return {
        "returncode": result.returncode,
        "stdout": (result.stdout or b"").decode("utf-8", "replace") if stdout_fh is None else None,
        "stderr": (result.stderr or b"").decode("utf-8", "replace") if stderr_fh is None else None,
    }


def _run_python_task(task: TaskSpec) -> Any:
    """在工作线程里直接调用 callable。"""
    if task.callable is None:
        raise ValueError(f"任务 '{task.task_id}': task_type='python' 必须提供 callable。")
    return task.callable(*task.args, **task.kwargs)


class LocalBackend(ExecutionBackend):
    """本地执行后端：线程池派发，shell 走 subprocess.run。

    配置
    ----
    ``max_workers`` : int
        最大并发工作线程数（默认 4）。
    """

    def __init__(self) -> None:
        super().__init__()
        self._pool: ThreadPoolExecutor | None = None

    def initialize(self, system: str = "local", **kwargs: Any) -> None:
        if self._initialized:
            logger.warning("LocalBackend 已初始化，忽略重复 initialize。")
            return
        max_workers = kwargs.get("max_workers", _DEFAULT_MAX_WORKERS)
        self._pool = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="lumo-exec"
        )
        self._initialized = True
        logger.info("LocalBackend 已初始化（max_workers=%d）", max_workers)

    def submit(self, task: TaskSpec) -> Future:
        if not self._initialized or self._pool is None:
            raise RuntimeError("LocalBackend 未初始化，先调用 initialize()。")

        if task.task_type == "python":
            return self._pool.submit(_run_python_task, task)
        if task.task_type == "shell":
            if task.command is None:
                raise ValueError(f"任务 '{task.task_id}': task_type='shell' 必须提供 command。")
            return self._pool.submit(_run_shell_task, task)
        raise ValueError(f"任务 '{task.task_id}': 不支持的 task_type '{task.task_type}'。")

    def shutdown(self) -> None:
        if self._pool is not None:
            logger.info("关闭 LocalBackend 线程池。")
            self._pool.shutdown(wait=True)
            self._pool = None
        self._initialized = False
