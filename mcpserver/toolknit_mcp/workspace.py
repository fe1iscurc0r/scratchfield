"""工作区路径纪律（工单244 §2 任务一.1「workspace.py」+ §1 目标 4）。

为什么要有这一层
----------------
toolknit CLI 只接受**显式本地路径**，其 MCP ``instructions`` 原文即：

    "ToolKnit only processes explicit local paths. In an IDE, when the user says
     current project or workspace, resolve the IDE …"

工单 §1 目标 4 把这条纪律落成硬约束：**路径必须解析到工作区，禁止相对路径 / 跨目录**。
本模块就是那条约束的 Python 侧实现，四条规则：

1. 工作区根由 ``TOOLKNIT_WORKSPACE_ROOT`` 决定；未设时回退 ``<仓库根>/research``
   （工单原文给的是服务器上的绝对路径 ``/home/ubuntu/scratchpad/research/<workspace>/``，
   故设计成**环境变量可覆盖**，服务器侧显式设成该值即可，不必改代码）。
2. **工作区名只允许单段安全标识符**（``[A-Za-z0-9][A-Za-z0-9._-]{0,63}`` 且不含 ``..``）
   ⇒ ``../etc`` / ``a/b`` / 空串一律拒绝。
3. **输入必须是绝对路径且落在工作区根之内**（``resolve()`` 先解符号链接再判包含，
   再按平台大小写口径 ``normcase`` 归一）⇒ 相对路径与跨目录都拒绝。
4. **输出只能落在工作区内的约定子目录**，绝不写回源文件所在目录。

判据用 ``Path.resolve()`` 后的**规范路径**比较，而不是字符串前缀 —— 否则 ``/ws/a/../b``
与符号链接能绕过。
"""
from __future__ import annotations

import os
import re
from pathlib import Path

#: 工作区根的环境变量（服务器侧设为 /home/ubuntu/scratchpad/research）
WORKSPACE_ROOT_ENV = "TOOLKNIT_WORKSPACE_ROOT"

#: 工作区内约定用于承载产物的子目录（工单 §2 任务二：落 <workspace>/toolknit-output/）
OUTPUT_SUBDIR = "toolknit-output"

#: 工作区内承载调用日志的目录（JSONL append，见 tools.log_call）
LOG_SUBDIR = "toolknit-logs"

#: 工作区名：单段、不以符号开头、不含路径分隔符
_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class WorkspaceError(ValueError):
    """工作区纪律违例：空名 / 非法工作区名 / 相对路径 / 越界 / 目标不存在。

    继承 ``ValueError`` ⇒ 调用方既可按本类型精确捕获，也可按通用参数错误处理。
    """


def repo_root() -> Path:
    """本模块所在仓库的根目录（``mcpserver/toolknit_mcp/workspace.py`` → 上三级）。"""
    return Path(__file__).resolve().parents[2]


def workspace_root() -> Path:
    """工作区根目录（已 resolve）。环境变量为空/未设时回退 ``<仓库根>/research``。"""
    raw = os.environ.get(WORKSPACE_ROOT_ENV, "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return (repo_root() / "research").resolve()


def _normalized(path: Path) -> str:
    """平台归一化后的规范字符串（Windows 大小写不敏感 ⇒ 统一小写再比）。"""
    return os.path.normcase(str(path))


def _within(child: Path, root: Path) -> bool:
    """``child`` 是否落在 ``root`` 之内（含等于）。两侧都须已 resolve。"""
    c, r = _normalized(child), _normalized(root)
    return c == r or c.startswith(r.rstrip("\\/") + os.sep)


def resolve_workspace(name: str) -> Path:
    """工作区名 → 绝对工作区目录（**不创建**）。

    名字必须是单段安全标识符；含 ``..``、路径分隔符、盘符、或以 ``.``/``-`` 开头一律拒绝。
    """
    text = str(name or "").strip()
    if not text:
        raise WorkspaceError("工作区名不能为空")
    if not _SAFE_SEGMENT.match(text) or ".." in text:
        raise WorkspaceError(
            f"非法工作区名 {text!r}：只允许单段字母/数字/下划线/点/连字符（1-64 位），且不含 '..'")
    candidate = (workspace_root() / text).resolve()
    if not _within(candidate, workspace_root()):
        raise WorkspaceError(f"工作区 {text!r} 解析后越界：{candidate} 不在 {workspace_root()} 之内")
    return candidate


def _effective_root(workspace: str | None) -> Path:
    """给定工作区名时用该工作区，否则用工作区根。"""
    return resolve_workspace(workspace) if workspace else workspace_root()


def resolve_input(path: str | os.PathLike[str], *, workspace: str | None = None) -> Path:
    """输入路径 → 已解析的绝对路径。四条硬检查：非空 / 绝对 / 存在 / 不越界。

    ``workspace`` 为 ``None`` 时以工作区根为边界（即允许根下任意子目录）；
    显式给出时以该工作区为边界。
    """
    text = str(path or "").strip()
    if not text:
        raise WorkspaceError("输入路径不能为空")
    raw = Path(text)
    if not raw.is_absolute():
        raise WorkspaceError(f"禁止相对路径：{text!r}（工单 §1 目标 4）")
    resolved = raw.expanduser().resolve()
    root = _effective_root(workspace)
    if not _within(resolved, root):
        raise WorkspaceError(f"跨目录访问被拒：{resolved} 不在工作区 {root} 之内")
    if not resolved.exists():
        raise WorkspaceError(f"路径不存在：{resolved}")
    return resolved


def resolve_output_dir(*, workspace: str | None = None, create: bool = True) -> Path:
    """产物目录 ``<workspace>/toolknit-output``。``create=True`` 时按需建目录。"""
    root = _effective_root(workspace)
    target = root / OUTPUT_SUBDIR
    if create:
        target.mkdir(parents=True, exist_ok=True)
    return target


def resolve_log_path(*, workspace: str | None = None, create: bool = True) -> Path:
    """调用日志路径 ``<workspace>/toolknit-logs/toolknit-calls.jsonl``。

    环境变量 ``TOOLKNIT_LOG_PATH`` 可直接指定（测试与运维用），指定时按绝对路径使用。
    """
    override = os.environ.get("TOOLKNIT_LOG_PATH", "").strip()
    if override:
        target = Path(override).expanduser().resolve()
        if create:
            target.parent.mkdir(parents=True, exist_ok=True)
        return target
    root = _effective_root(workspace)
    directory = root / LOG_SUBDIR
    if create:
        directory.mkdir(parents=True, exist_ok=True)
    return directory / "toolknit-calls.jsonl"


def resolve_output_file(name: str, *, workspace: str | None = None) -> Path:
    """产物文件名 → 产物目录内的绝对路径。名字必须是单段（防 ``../`` 逃逸）。"""
    text = str(name or "").strip()
    if not text or not _SAFE_SEGMENT.match(text) or ".." in text:
        raise WorkspaceError(f"非法产物文件名 {text!r}")
    return resolve_output_dir(workspace=workspace) / text


def rel_to_workspace(path: str | os.PathLike[str], *, workspace: str | None = None) -> str:
    """把工作区内的绝对路径转成相对工作区的 POSIX 串（仅用于展示/日志）。

    **不抛异常**：不在工作区内时退回规范化的绝对 POSIX 串 —— 日志不该因为路径口径而失败。
    """
    resolved = Path(path).expanduser().resolve()
    root = _effective_root(workspace)
    try:
        rel = resolved.relative_to(root)
    except ValueError:
        return resolved.as_posix()
    return rel.as_posix()


__all__ = [
    "LOG_SUBDIR",
    "OUTPUT_SUBDIR",
    "WORKSPACE_ROOT_ENV",
    "WorkspaceError",
    "rel_to_workspace",
    "repo_root",
    "resolve_input",
    "resolve_log_path",
    "resolve_output_dir",
    "resolve_output_file",
    "resolve_workspace",
    "workspace_root",
]
