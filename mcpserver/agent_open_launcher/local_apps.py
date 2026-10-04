# local_apps.py # 陆墨生态应用启动器（NEKO / HamLog）
#
# 设计要点：
# - 本模块由 agent_app_launcher.py 在后端进程内调用，LUMO_PROXY_TOKEN 直接从
#   os.environ 读取（与 lumo_proxy 同一份），符合铁律7（不落盘明文 token）。
# - fail-fast：依赖缺失（Python/Node/脚本不存在、token 缺失）一律明确报错，
#   不静默降级。
# - 幂等：启动前先探测端口/进程，已在运行直接返回 running，避免重复拉起。
import os
import socket
import subprocess
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_WRAPPER = _PROJECT_ROOT / "scripts" / "neko_launcher_wrapper.py"
_NEKO_ROOT = _PROJECT_ROOT / "NEKO" / "N.E.K.O"
_NEKO_SHELL_DIR = _PROJECT_ROOT / "neko-electron-shell"
_HAMLOG_DIR = _PROJECT_ROOT / "HamLog" / "programs" / "R1.0.0"
_HAMLOG_ENTRY = "HAMLOG GUI.py"
_HAMLOG_MATCH = "HAMLOG GUI"  # 进程探测关键字：比入口名略短，避免误匹配含 hamlog 字样的无关命令行
_NEKO_SHELL_MATCH = "neko-electron-shell"  # 桌宠窗口进程探测关键字（electron 命令行含 shell 目录路径）
_NEKO_MAIN_PORT = 48911

_DETACHED_FLAGS = 0
if sys.platform == "win32":
    # 独立进程组 + 脱离控制台：后端重启不牵连桌宠，桌宠也不抢后端终端
    # CREATE_NO_WINDOW：DETACHED_PROCESS 会给控制台子进程（python.exe/node.exe）
    # 新建一个可见控制台黑框，叠加此标志才能完全隐藏（日志已重定向到文件）
    _DETACHED_FLAGS = (subprocess.CREATE_NEW_PROCESS_GROUP
                       | subprocess.DETACHED_PROCESS
                       | subprocess.CREATE_NO_WINDOW)


def _port_listening(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _process_running(keyword: str, proc_names: tuple[str, ...] | None = None) -> bool:
    """按命令行关键字查进程（Windows 专用，其他平台直接返回 False）。

    proc_names 限定进程名白名单：子 powershell 自身命令行含关键字，
    不限定会自我匹配导致永远“已在运行”。
    """
    if sys.platform != "win32":
        return False
    name_filter = ""
    if proc_names:
        name_conds = " -or ".join(f"$_.Name -eq '{n}'" for n in proc_names)
        name_filter = f"({name_conds}) -and "
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"Get-CimInstance Win32_Process | Where-Object {{ {name_filter}$_.CommandLine -match '{keyword}' }} | Measure-Object | Select-Object -ExpandProperty Count"],
            capture_output=True, text=True, timeout=10,
        )
        return int(out.stdout.strip() or 0) > 0
    except Exception:
        return False


def _find_python() -> str | None:
    """Python 解释器探测：环境变量 > 当前进程解释器 > 已知路径。

    当前进程解释器（sys.executable）优先——后端能跑起来说明环境可用。
    """
    for var in ("LUMO_LOCAL_PYTHON", "LUMO_FUSION_PYTHON"):
        p = os.environ.get(var, "").strip()
        if p and Path(p).exists():
            return p
    if sys.executable and Path(sys.executable).exists():
        return sys.executable
    fallback = Path(os.environ.get("USERPROFILE", "")) / "python-sdk" / "python3.13.2" / "python.exe"
    return str(fallback) if fallback.exists() else None


def _find_node() -> str | None:
    for var in ("LUMO_FUSION_NODE",):
        p = os.environ.get(var, "").strip()
        if p and Path(p).exists():
            return p
    candidates = [
        Path(os.environ.get("USERPROFILE", "")) / ".trae-cn" / "binaries" / "node" / "versions" / "24.18.0" / "node.exe",
    ]
    path_dirs = os.environ.get("PATH", "").split(os.pathsep)
    candidates.extend(Path(d) / ("node.exe" if sys.platform == "win32" else "node") for d in path_dirs if d)
    for c in candidates:
        if c.exists():
            return str(c)
    return None


def get_launch_status() -> dict:
    """查询 NEKO / HamLog 运行状态（秒级探测，不发请求）。"""
    neko_main = _port_listening(_NEKO_MAIN_PORT)
    neko_shell = _process_running(_NEKO_SHELL_MATCH, ("electron.exe",))
    hamlog_up = _process_running(_HAMLOG_MATCH, ("python.exe", "pythonw.exe"))
    return {
        "neko": {
            "running": neko_main,
            "shell_running": neko_shell,
            "detail": f"Main Server 端口 {_NEKO_MAIN_PORT} " + ("已就绪" if neko_main else "未监听")
                      + "；桌宠窗口" + ("在运行" if neko_shell else "未运行"),
        },
        "hamlog": {
            "running": hamlog_up,
            "detail": "HamLog GUI 进程" + ("在运行" if hamlog_up else "未运行"),
        },
    }


def _start_neko_shell(env: dict, log_dir: Path) -> bool:
    """启动桌宠窗口（node electron/cli.js）。node/electron 缺失时返回 False。"""
    node_exe = _find_node()
    shell_cli = _NEKO_SHELL_DIR / "node_modules" / "electron" / "cli.js"
    if not (node_exe and shell_cli.exists()):
        return False
    shell_log = open(log_dir / "neko_shell.log", "ab")
    subprocess.Popen(
        [node_exe, str(shell_cli), "."],
        cwd=str(_NEKO_SHELL_DIR), env=env,
        stdout=shell_log, stderr=subprocess.STDOUT,
        creationflags=_DETACHED_FLAGS, close_fds=True,
    )
    return True


def launch_neko() -> dict:
    """启动 NEKO（wrapper + 桌宠 shell），复用当前后端的 persona 代理与共享 token。

    前置条件：scratchpad 后端（本进程所在服务）已带 LUMO_PROXY_TOKEN 运行。
    幂等分两层：Main Server 端口存活时不再重拉 wrapper；但桌宠窗口进程
    不在时仍会补拉窗口（端口在≠窗口在，避免“端口就绪但无桌面”）。
    """
    port_up = _port_listening(_NEKO_MAIN_PORT)
    shell_up = _process_running(_NEKO_SHELL_MATCH, ("electron.exe",))

    if port_up and shell_up:
        return {"status": "success", "message": f"NEKO 已在运行（端口 {_NEKO_MAIN_PORT} 就绪，桌宠窗口在运行），无需重复启动",
                "data": {"neko": "already_running"}}

    token = os.environ.get("LUMO_PROXY_TOKEN", "").strip()
    if not token:
        return {"status": "error",
                "message": "后端未设置 LUMO_PROXY_TOKEN（需通过 lumo_fusion.ps1 启动后端才能与 NEKO 共享鉴权）。"
                           "请先退出当前后端，改用 .\\lumo_fusion.ps1 -NoNeo4j -NoFrontend 启动后再试",
                "data": {}}

    env = dict(os.environ)
    env.setdefault("LUMO_PROXY_BASE_URL", "http://127.0.0.1:8000/persona/v1")
    log_dir = _PROJECT_ROOT / "build" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    if port_up:
        # 端口已在（wrapper 存活），只补拉桌宠窗口
        shell_started = _start_neko_shell(env, log_dir)
        if shell_started:
            return {"status": "success",
                    "message": f"NEKO Main Server 已在运行（端口 {_NEKO_MAIN_PORT}），已补拉桌宠窗口，稍候几秒即会出现在桌面",
                    "data": {"neko": "shell_started", "main_port": _NEKO_MAIN_PORT}}
        return {"status": "error",
                "message": "NEKO Main Server 已在运行，但桌宠窗口启动失败（未找到 node 或 neko-electron-shell 依赖未装，"
                           "可在 neko-electron-shell 目录运行 npm install --legacy-peer-deps 补齐）",
                "data": {"neko": "shell_start_failed"}}

    if not _WRAPPER.exists():
        return {"status": "error", "message": f"NEKO wrapper 不存在: {_WRAPPER}", "data": {}}
    python_exe = _find_python()
    if not python_exe:
        return {"status": "error", "message": "未找到可用的 Python 解释器（设置 LUMO_LOCAL_PYTHON 可指定）", "data": {}}

    wrapper_log = open(log_dir / "neko_wrapper.log", "ab")
    subprocess.Popen(
        [python_exe, str(_WRAPPER)],
        cwd=str(_NEKO_ROOT), env=env,
        stdout=wrapper_log, stderr=subprocess.STDOUT,
        creationflags=_DETACHED_FLAGS, close_fds=True,
    )

    # 桌宠 shell：node 缺失时不阻断，仅提示（wrapper/Main Server 是核心链路）
    shell_started = _start_neko_shell(env, log_dir)

    msg = ("NEKO 已启动（wrapper + 桌宠窗口）。Main Server 就绪约需 10-30 秒，"
           "在 NEKO 设置中选择「陆墨（本地人格代理）」即可对话" if shell_started else
           "NEKO wrapper 已启动，但桌宠窗口未启动（未找到 node 或 electron 依赖未装，"
           "可手动运行 lumo_fusion.ps1 补齐）。Main Server 就绪约需 10-30 秒")
    return {"status": "success", "message": msg,
            "data": {"wrapper_pid": "detached", "shell_started": shell_started,
                     "main_port": _NEKO_MAIN_PORT, "log": str(log_dir / "neko_wrapper.log")}}


def _kill_processes(keyword: str, proc_names: tuple[str, ...]) -> int:
    """按命令行关键字 + 进程名白名单终止进程树，返回终止数量（Windows 专用）。

    白名单限制与 _process_running 同理：避免误杀命令行恰好含关键字的无关进程。
    taskkill /T 连带终止子进程（wrapper 下的 NEKO Main Server 一并带走）。
    """
    if sys.platform != "win32":
        return 0
    name_conds = " -or ".join(f"$_.Name -eq '{n}'" for n in proc_names)
    killed = 0
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             f"Get-CimInstance Win32_Process | Where-Object {{ ({name_conds}) -and $_.CommandLine -match '{keyword}' }} | Select-Object -ExpandProperty ProcessId"],
            capture_output=True, text=True, timeout=10,
        )
        for line in out.stdout.splitlines():
            pid = line.strip()
            if pid.isdigit():
                subprocess.run(["taskkill", "/PID", pid, "/T", "/F"],
                               capture_output=True, timeout=10)
                killed += 1
    except Exception:
        pass
    return killed


def stop_hamlog() -> dict:
    """关闭 HamLog GUI。未运行时幂等返回。"""
    killed = _kill_processes(_HAMLOG_MATCH, ("python.exe", "pythonw.exe"))
    if killed == 0:
        return {"status": "success", "message": "HamLog 未在运行，无需关闭", "data": {"hamlog": "not_running"}}
    return {"status": "success", "message": f"HamLog 已关闭（终止 {killed} 个进程）",
            "data": {"hamlog": "stopped", "killed": killed}}


def stop_neko() -> dict:
    """关闭 NEKO（桌宠窗口 + wrapper 及其下的 Main Server）。未运行时幂等返回。"""
    port_up = _port_listening(_NEKO_MAIN_PORT)
    shell_killed = _kill_processes(_NEKO_SHELL_MATCH, ("electron.exe",))
    # wrapper 用 /T 连带终止其子进程树（NEKO Main Server）
    wrapper_killed = _kill_processes("neko_launcher_wrapper", ("python.exe",))
    if shell_killed == 0 and wrapper_killed == 0 and not port_up:
        return {"status": "success", "message": "NEKO 未在运行，无需关闭", "data": {"neko": "not_running"}}
    still_up = _port_listening(_NEKO_MAIN_PORT)
    msg = f"NEKO 已关闭（桌宠窗口 {shell_killed} 个、wrapper {wrapper_killed} 个进程被终止）"
    if still_up:
        msg += f"，但端口 {_NEKO_MAIN_PORT} 仍在监听（可能是 fusion 脚本拉起的实例，需在其终端 Ctrl+C 关闭）"
    return {"status": "success", "message": msg,
            "data": {"neko": "stopped", "shell_killed": shell_killed,
                     "wrapper_killed": wrapper_killed, "port_still_up": still_up}}


def launch_hamlog() -> dict:
    """启动 HamLog GUI（PyQt6，无控制台模式）。"""
    if _process_running(_HAMLOG_MATCH, ("python.exe", "pythonw.exe")):
        return {"status": "success", "message": "HamLog 已在运行，无需重复启动",
                "data": {"hamlog": "already_running"}}
    if not (_HAMLOG_DIR / _HAMLOG_ENTRY).exists():
        return {"status": "error",
                "message": f"未找到 HamLog 入口: {_HAMLOG_DIR / _HAMLOG_ENTRY}（先 clone HamLog 仓库到 scratchpad/HamLog）",
                "data": {}}
    venv_dir = _PROJECT_ROOT / ".venv" / "Scripts"
    pythonw = venv_dir / ("pythonw.exe" if sys.platform == "win32" else "pythonw")
    python_exe = str(pythonw) if pythonw.exists() else _find_python()
    if not python_exe:
        return {"status": "error", "message": "未找到可用的 Python 解释器", "data": {}}
    try:
        subprocess.Popen(
            [python_exe, _HAMLOG_ENTRY],
            cwd=str(_HAMLOG_DIR),
            creationflags=_DETACHED_FLAGS, close_fds=True,
        )
    except Exception as exc:
        return {"status": "error", "message": f"启动 HamLog 失败: {exc}（确认 venv 已装 PyQt6: pip install PyQt6）",
                "data": {}}
    return {"status": "success",
            "message": "HamLog 已启动。首次使用请在「设置」里填写本台呼号（my_callsign），之后陆墨即可读取通联台账",
            "data": {"entry": str(_HAMLOG_DIR / _HAMLOG_ENTRY)}}
