"""受限子进程执行 + 日志/指标收集 + sandbox 目录收敛（工单242 任务一/任务二）。

三件事：

1. **沙箱根**：默认 ``mcpserver/rf_workflow/sandbox/<workflow_id>/``（工单242 §2 指定），
   可用 ``RF_WORKFLOW_SANDBOX`` 覆盖（测试与云服都走这条）。
2. **受控执行**：argv 列表直执（无 shell）、cwd 固定在 workdir、
   ``stdin=DEVNULL``、超时 kill、stdout/stderr 合并落 ``log.txt``。
3. **指标提取**：脚本在 stdout 末尾打一行 ``__RF_METRICS__ {json}``；本模块解析它，
   并同时把 ``result.json`` 读回来（两者不一致 → 记为 ``metrics_mismatch``，不静默取其一）。

串行纪律沿用同族先例（``mcpserver/antenna_sim/sim_runner.py``）：一次只跑一个工作流步骤，
并发提交返回 ``busy``。
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

ENV_SANDBOX = "RF_WORKFLOW_SANDBOX"
ENV_PYTHON = "RF_WORKFLOW_PYTHON"
METRICS_MARKER = "__RF_METRICS__"
LOG_FILENAME = "log.txt"
RESULT_FILENAME = "result.json"
DEFAULT_TIMEOUT_S = 120.0
MAX_TIMEOUT_S = 1800.0

_WORKFLOW_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_running: str | None = None


# ---------------------------------------------------------------------------
# 目录收敛
# ---------------------------------------------------------------------------
def default_sandbox_root() -> Path:
    """仓内默认沙箱根（工单242 §2：``mcpserver/rf_workflow/sandbox/``）。"""
    return Path(__file__).resolve().parent / "sandbox"


def sandbox_root() -> Path:
    """沙箱根：``RF_WORKFLOW_SANDBOX`` 优先，否则仓内默认。"""
    override = os.environ.get(ENV_SANDBOX, "").strip()
    root = Path(override).expanduser() if override else default_sandbox_root()
    root.mkdir(parents=True, exist_ok=True)
    return root


def new_workflow_id() -> str:
    """``rfw-YYYYMMDD-<6hex>``（只含 ``[A-Za-z0-9_-]``，可安全拼进路径）。"""
    return f"rfw-{time.strftime('%Y%m%d')}-{uuid.uuid4().hex[:6]}"


def safe_workflow_id(workflow_id: str) -> tuple[str | None, str | None]:
    """校验 workflow_id（会拼进目录名）：只允许 ``[A-Za-z0-9_-]{1,64}``；空则自动生成。"""
    raw = str(workflow_id or "").strip()
    if not raw:
        return new_workflow_id(), None
    if not _WORKFLOW_ID_RE.match(raw):
        return None, "invalid_workflow_id"
    return raw, None


def workflow_dir(workflow_id: str) -> Path:
    """定位工作流目录；越界或非法 id 抛 ``ValueError``。"""
    clean, error = safe_workflow_id(workflow_id)
    if clean is None:
        raise ValueError(f"非法 workflow_id: {error}")
    base = sandbox_root().resolve()
    target = (base / clean).resolve()
    if target != base and base not in target.parents:
        raise ValueError("工作流目录越界")
    target.mkdir(parents=True, exist_ok=True)
    return target


def contained_script_path(workflow_id: str, filename: str) -> Path:
    """把 filename 收敛到工作流目录内（拒 ``..`` 与绝对路径）。"""
    name = str(filename or "").strip()
    if not name or ".." in Path(name).parts or Path(name).is_absolute():
        raise ValueError(f"非法脚本名: {filename!r}")
    directory = workflow_dir(workflow_id)
    candidate = (directory / name).resolve()
    if directory.resolve() not in candidate.parents and candidate != directory.resolve():
        raise ValueError("脚本路径越界")
    return candidate


# ---------------------------------------------------------------------------
# 执行
# ---------------------------------------------------------------------------
def python_bin() -> str:
    """跑脚本的解释器：``RF_WORKFLOW_PYTHON`` 优先，否则当前解释器。"""
    override = os.environ.get(ENV_PYTHON, "").strip()
    if override:
        return override
    return sys.executable or "python"


def run_script(script_path: Path | str, *, timeout_s: float = DEFAULT_TIMEOUT_S,
               workflow_id: str = "", log_name: str = LOG_FILENAME,
               result_name: str = RESULT_FILENAME) -> dict[str, Any]:
    """在脚本所在目录执行脚本，收集日志与指标。串行；超时 kill。"""
    global _running

    path = Path(script_path)
    if not path.is_file():
        return {"ok": False, "error": "script_not_found", "script": str(path)}
    if ".." in Path(log_name).parts or Path(log_name).is_absolute():
        return {"ok": False, "error": "invalid_log_name", "log_name": log_name}
    workdir = path.parent
    budget = float(timeout_s) if timeout_s else DEFAULT_TIMEOUT_S
    if not (0 < budget <= MAX_TIMEOUT_S):
        return {"ok": False, "error": "invalid_timeout",
                "hint": f"timeout_s 须在 (0, {MAX_TIMEOUT_S}] 内，收到 {timeout_s!r}"}
    if _running:
        return {"ok": False, "error": "busy", "running": _running,
                "hint": "工作流步骤串行执行：等当前步骤结束再提交"}

    _running = workflow_id or path.parent.name
    log_path = workdir / log_name
    started = time.perf_counter()
    try:
        proc = subprocess.Popen(  # noqa: S603 - argv 列表 + 无 shell + 路径已收敛
            [python_bin(), path.name],
            cwd=str(workdir),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        timed_out = False
        try:
            out, _ = proc.communicate(timeout=budget)
        except subprocess.TimeoutExpired:
            timed_out = True
            proc.kill()
            try:
                out, _ = proc.communicate(timeout=10)
            except Exception:  # noqa: BLE001
                out = b""
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"spawn_failed: {exc}"}
    finally:
        _running = None

    text = (out or b"").decode("utf-8", "replace")
    # 子进程在 Windows 上把 \n 翻成 \r\n；log.txt 会入库 ⇒ 一律归一成 LF（工单242 交付纪律）
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    try:
        log_path.write_text(text, encoding="utf-8", newline="\n")
    except OSError as exc:  # 日志写不进不算执行失败，但要留痕
        logger.warning("[rf_workflow] 日志写盘失败: %s", exc)

    duration = round(time.perf_counter() - started, 3)
    if timed_out:
        return {"ok": False, "error": "timeout", "log": str(log_path),
                "duration_s": duration, "stdout": text}
    exit_code = proc.returncode
    metrics = parse_metrics(text)
    result = read_result(workdir, result_name)
    outcome: dict[str, Any] = {
        "ok": exit_code == 0,
        "exit_code": exit_code,
        "error": "" if exit_code == 0 else f"exit_{exit_code}",
        "log": str(log_path),
        "duration_s": duration,
        "stdout": text,
        "metrics": metrics,
        "result": result,
    }
    if metrics and result and isinstance(result.get("metrics"), dict):
        outcome["metrics_mismatch"] = [
            key for key, value in metrics.items()
            if key in result["metrics"] and result["metrics"][key] != value
        ]
    return outcome


def parse_metrics(stdout: str) -> dict[str, Any] | None:
    """从 stdout 里取最后一行 ``__RF_METRICS__ {json}``；没有则 ``None``。"""
    found: dict[str, Any] | None = None
    for line in str(stdout or "").splitlines():
        stripped = line.strip()
        if not stripped.startswith(METRICS_MARKER):
            continue
        try:
            payload = json.loads(stripped[len(METRICS_MARKER):].strip())
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            found = payload
    return found


def read_result(workdir: Path | str, filename: str = RESULT_FILENAME) -> dict[str, Any] | None:
    """读 ``result.json``；缺失或坏 JSON 返回 ``None``（由调用方决定是否报错）。"""
    path = Path(workdir) / filename
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def write_workflow_state(workflow_id: str, state: dict[str, Any]) -> Path:
    """写 ``workflow.json``（LF、可读缩进）。"""
    path = workflow_dir(workflow_id) / "workflow.json"
    path.write_text(json.dumps(state, ensure_ascii=False, indent=1, sort_keys=True),
                    encoding="utf-8", newline="\n")
    return path


def read_workflow_state(workflow_id: str) -> dict[str, Any] | None:
    path = workflow_dir(workflow_id) / "workflow.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def reset_for_tests() -> None:
    """测试用：清掉「正在跑」标记。"""
    global _running
    _running = None


__all__ = [
    "DEFAULT_TIMEOUT_S", "ENV_PYTHON", "ENV_SANDBOX", "LOG_FILENAME", "MAX_TIMEOUT_S",
    "METRICS_MARKER", "RESULT_FILENAME", "contained_script_path", "default_sandbox_root",
    "new_workflow_id", "parse_metrics", "python_bin", "read_result", "read_workflow_state",
    "reset_for_tests", "run_script", "safe_workflow_id", "sandbox_root", "workflow_dir",
    "write_workflow_state",
]
