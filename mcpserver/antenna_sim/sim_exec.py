"""子进程执行细节（卷122 W122-02）。

集中放「起进程」这一件事，便于审计与替换。约定（调用方 `sim_runner` 已保证）：

- 传入的 `model` 是**已过路径校验**的绝对路径（落在允许目录内）
- argv 只包含**文件名**（`model.name`），目录靠 `cwd` 限定 → 命令行里不出现用户可控目录
- 不给 shell（argv 列表直执）、stdout/stderr 落日志、超时结束进程

与卷121 `code_workspace.sandbox.run_process` 的关系：同一个「argv 列表 + 无 shell + 超时」
的受控执行形态；仿真单次最长 1800s，超出沙箱默认 300s 上限，所以这里单独放一份并显式设定超时。

许可边界：OpenEMS/CSXCAD 为 GPL-3.0 独立工具链，这里只以「外部进程 + 文件」交互，不引其源码。
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def _has_parent_segment(value: str) -> bool:
    """路径里是否含 `..` 段（拒绝目录穿越用）。"""
    return ".." in str(value).replace("\\", "/").split("/")


def _guard_paths(argv: List[str], workdir: Path) -> str | None:
    """执行前的路径断言：argv 与工作目录都不得含 `..`。返回错误码或 None。"""
    if _has_parent_segment(str(workdir)):
        return "path_traversal_denied(workdir)"
    for token in argv:
        if _has_parent_segment(str(token)):
            return "path_traversal_denied(argv)"
    return None


def _spawn(argv: List[str], workdir: Path, log_path: Path, timeout: float,
           env: Dict[str, str] | None = None) -> Dict[str, Any]:
    """起子进程并等结束：日志落盘、超时 kill。返回 `{ok, exit_code, error, log}`。"""
    guard_error = _guard_paths(argv, workdir)
    if guard_error:
        return {"ok": False, "error": guard_error}
    started = time.perf_counter()
    try:
        proc = subprocess.Popen(  # noqa: S603 - argv 列表 + 无 shell + 路径已校验
            [str(token) for token in argv],
            cwd=str(workdir),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env,
        )
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"spawn_failed: {e}"}
    timed_out = False
    try:
        out, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        proc.kill()
        try:
            out, _ = proc.communicate(timeout=10)
        except Exception:  # noqa: BLE001
            out = b""
    try:
        log_path.write_bytes(out or b"")
    except OSError as e:  # noqa: BLE001 - 日志写不进不算失败
        logger.warning("[antenna_sim] 日志写盘失败: %s", e)
    duration = round(time.perf_counter() - started, 2)
    if timed_out:
        return {"ok": False, "error": "timeout", "log": str(log_path), "duration_s": duration}
    return {"ok": proc.returncode == 0, "exit_code": proc.returncode,
            "error": "" if proc.returncode == 0 else f"exit_{proc.returncode}",
            "log": str(log_path), "duration_s": duration}


def _openems_exe() -> Tuple[Path | None, str | None]:
    from .sim_runner import openems_dir

    directory = openems_dir()
    if directory is None:
        return None, "openems_not_found"
    exe = directory / ("openEMS.exe" if os.name == "nt" else "openEMS")
    if not exe.is_file():
        return None, "openems_not_found"
    return exe, None


def _dll_env() -> Dict[str, str]:
    """Windows 上扩展模块不从 PATH 找 DLL：把 OpenEMS 目录显式传给子进程。"""
    from .sim_runner import openems_dir

    env = dict(os.environ)
    directory = openems_dir()
    if directory is not None:
        env["ANTENNA_SIM_DLL_DIR"] = str(directory)
    return env


def run_openems_xml(model: Path, result_dir: Path, timeout: float) -> Dict[str, Any]:
    """CSX XML：`openEMS.exe <模型文件名>`（cwd = 结果目录，输出就地落盘）。"""
    exe, err = _openems_exe()
    if exe is None:
        return {"ok": False, "error": err,
                "hint": "设 ANTENNA_SIM_OPENEMS_DIR 指向含 openEMS.exe 的目录"}
    if model.suffix.lower() != ".xml":
        return {"ok": False, "error": "wrong_backend_for_model",
                "hint": "Python 模型请配 antenna_sim.openems_python（openems_py 后端）"}
    result_dir.mkdir(parents=True, exist_ok=True)
    return _spawn([str(exe), str(model.name)], result_dir, result_dir / "openems.log",
                  timeout, _dll_env())


def run_openems_python(model: Path, result_dir: Path, timeout: float) -> Dict[str, Any]:
    """Python 模型脚本：用装了官方 wheel 的解释器跑（脚本内做 S11 后处理并写 CSV）。

    工作目录 = 模型所在目录（脚本要能被找到），产物目录通过 `ANTENNA_SIM_OUT_DIR`
    传给脚本 → 输出仍落在结果目录，模型目录保持干净。
    """
    from .sim_runner import contained_workdir, openems_python

    interpreter = openems_python()
    if not interpreter:
        return {"ok": False, "error": "openems_python_not_configured",
                "hint": "配 antenna_sim.openems_python 指向装了 openEMS/CSXCAD wheel 的 python.exe"}
    if model.suffix.lower() != ".py":
        return {"ok": False, "error": "wrong_backend_for_model", "hint": "XML 模型请走 openems 后端"}
    result_dir.mkdir(parents=True, exist_ok=True)
    try:
        workdir = contained_workdir(model)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    env = _dll_env()
    env["ANTENNA_SIM_OUT_DIR"] = str(result_dir)
    return _spawn([interpreter, str(model.name)], workdir, result_dir / "openems.log", timeout, env)


def run_dry(result_dir: Path) -> Dict[str, Any]:
    """dry-run：准备目录、写占位结果，明确标注未真跑。"""
    (result_dir / "run").mkdir(parents=True, exist_ok=True)
    (result_dir / "job.json").write_bytes(json.dumps(
        {"dry_run": True, "note": "dry-run：只走状态机与目录准备，未执行求解"},
        ensure_ascii=False, indent=1).encode("utf-8"))
    return {"ok": True, "dry_run": True, "note": "未执行求解（dry-run）"}


__all__ = ["run_openems_xml", "run_openems_python", "run_dry"]
