#!/usr/bin/env python3
"""子进程路径追踪器（诊断 B1：`<cwd>/git/scratchpad/.venv/...` 这类错误路径从哪来）。

用法（在仓库根执行）：

    ./.venv/Scripts/python.exe tools/trace_subprocess.py            # 跑 main.py --headless
    ./.venv/Scripts/python.exe tools/trace_subprocess.py -- <args>  # 透传参数

做法：把 `subprocess.Popen / subprocess.run / os.system / os.exec* / os.spawn*` 全部包一层，
**只记录不改变行为**，写 `build/subprocess_trace.log`；凡是 argv 里出现
"可能的相对路径"（不含盘符/不以 / 开头，且含 .venv / Scripts / python 等）就标 `SUSPECT`。

定位到 SUSPECT 行后，往上找该调用的调用栈（日志里带 stack），即可改到具体一行。
"""
from __future__ import annotations

import os
import pathlib
import runpy
import subprocess
import sys
import time
import traceback

ROOT = pathlib.Path(__file__).resolve().parent.parent
LOG = ROOT / "build" / "subprocess_trace.log"
LOG.parent.mkdir(parents=True, exist_ok=True)

_SUSPECT_TOKENS = (".venv", "Scripts", "python.exe", "site-packages")


def _looks_like_bare_relative(arg: str) -> bool:
    """不以盘符/根斜杠开头，但含可执行/venv 特征 ⇒ 很可能是"相对路径拼接"的坏值。"""
    if not isinstance(arg, str) or not arg:
        return False
    if os.path.isabs(arg) or (len(arg) > 1 and arg[1] == ":"):
        return False
    return any(tok in arg for tok in _SUSPECT_TOKENS)


def _record(kind: str, argv, cwd=None, extra: str = "") -> None:
    args = [str(a) for a in (argv if isinstance(argv, (list, tuple)) else [argv])]
    suspects = [a for a in args if _looks_like_bare_relative(a)]
    ts = time.strftime("%H:%M:%S")
    with LOG.open("a", encoding="utf-8") as f:
        f.write(f"\n[{ts}] {kind} cwd={cwd or os.getcwd()}\n  argv={args}\n")
        if extra:
            f.write(f"  note={extra}\n")
        if suspects:
            f.write(f"  ⚠️ SUSPECT 相对路径: {suspects}\n")
            for line in traceback.format_stack()[-8:-1]:
                f.write("    " + line.replace("\n", " ") + "\n")


def install() -> None:
    orig_popen = subprocess.Popen
    orig_run = subprocess.run
    orig_system = os.system

    class TracedPopen(orig_popen):  # type: ignore[misc,valid-type]
        def __init__(self, args, *a, **kw):
            _record("Popen", args if not isinstance(args, str) else [args], kw.get("cwd"))
            super().__init__(args, *a, **kw)

    def traced_run(args, *a, **kw):
        _record("run", args if not isinstance(args, str) else [args], kw.get("cwd"))
        return orig_run(args, *a, **kw)

    def traced_system(cmd):
        _record("os.system", [cmd])
        return orig_system(cmd)

    subprocess.Popen = TracedPopen          # type: ignore[assignment]
    subprocess.run = traced_run             # type: ignore[assignment]
    os.system = traced_system               # type: ignore[assignment]


def main() -> int:
    argv = sys.argv[1:]
    if argv and argv[0] == "--":
        argv = argv[1:]
    script = ROOT / "main.py"
    if not script.exists():
        print(f"找不到 {script}")
        return 2
    LOG.write_text(f"# trace start {time.ctime()}  cwd={os.getcwd()}\n", encoding="utf-8")
    print(f"[trace] 日志 = {LOG}")
    print(f"[trace] 运行: {script} {' '.join(argv)}")
    install()
    sys.argv = [str(script)] + argv
    try:
        runpy.run_path(str(script), run_name="__main__")
    except SystemExit as e:
        print(f"[trace] 退出码 {e.code}")
        return int(e.code or 0)
    except BaseException:
        print("[trace] 异常（已记录到日志尾部）：")
        traceback.print_exc()
        with LOG.open("a", encoding="utf-8") as f:
            f.write("\n[trace] EXCEPTION\n" + traceback.format_exc())
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
