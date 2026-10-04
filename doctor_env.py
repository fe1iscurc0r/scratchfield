#!/usr/bin/env python3
"""scratchpad 环境自检 —— 全新机器「缺什么报什么，不许默默失败」。

用法：
    python doctor_env.py            # 自检；有必装项缺失时退出码 1，全过退出码 0
    python doctor_env.py --fix      # 本卷只打印安装命令（不自动执行，见下方说明）
    python doctor_env.py --json     # 机器可读输出（CI 用）

设计约束（卷165）：
- **单文件 + 纯标准库**：它要在环境装好「之前」就能跑，所以不能依赖任何第三方包。
- **Python 3.10+ 可跑**：不在模块级使用 3.11+ 才有的语法/库（如 tomllib）。
- 检测逻辑平台无关（一律 `subprocess` 调 `--version`）；安装指引按平台给。
- 退出码：有任何 ❌ 必装缺失 → 1；只有 ⚠️ 可选项缺失 → 0。

事实基线：docs/环境依赖清单-Windows装机-2026-09-27.md
"""

from __future__ import annotations

import argparse
import json
import platform
import re
import shutil
import socket
import subprocess
import sys

# ---------------- 判据（与 docs/环境依赖清单 保持一致）----------------
PY_MIN = (3, 12)          # pyproject: requires-python = ">=3.12,<3.13"
PY_MAX_EXCL = (3, 13)     # 上界（不含）：装 3.13 会被 uv 拒
NODE_MIN = (20, 19)       # Vite 7 系要求 >=20.19
PORTS = ((8000, "apiserver"), (5173, "vite dev"))

OK, WARN, FAIL = "ok", "warn", "fail"
MARK = {OK: "[OK]  ", WARN: "[可选]", FAIL: "[缺失]"}

SYSTEM = platform.system()  # Windows / Darwin / Linux
IS_WIN = SYSTEM == "Windows"


def ensure_utf8_stdout() -> None:
    """中文 Windows 控制台默认 GBK，直接 print 表情/中文可能抛 UnicodeEncodeError。"""
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # py3.7+
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def run(cmd, timeout=20):
    """执行命令，返回 (returncode, stdout+stderr)。失败不抛异常，交由调用方判三态。

    注意：**显式 utf-8 + errors=replace**。中文 Windows 上 `node -v`/`ffmpeg -version`
    的输出可能是 GBK，用默认编码解码会抛 UnicodeDecodeError（本仓踩过同类坑）。
    """
    exe = shutil.which(cmd[0])
    if exe is None:
        return None, ""
    try:
        p = subprocess.run(
            [exe] + list(cmd[1:]),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, shell=False,
        )
        return p.returncode, ((p.stdout or "") + (p.stderr or "")).strip()
    except Exception as e:  # 超时/权限等
        return -1, "%s: %s" % (type(e).__name__, e)


def first_version(text):
    """从任意版本文本里抠出第一个 (major, minor, patch?) 元组。"""
    m = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", text or "")
    if not m:
        return None
    parts = [int(m.group(1)), int(m.group(2))]
    if m.group(3) is not None:
        parts.append(int(m.group(3)))
    return tuple(parts)


def fmt(v):
    return ".".join(str(x) for x in v) if v else "?"


# ---------------- 安装指引（按平台）----------------
def hint(tool: str) -> str:
    table = {
        "Windows": {
            "python": 'winget install -e --id Python.Python.3.12   （安装时务必勾选 "Add python.exe to PATH"）',
            "uv": 'powershell -c "irm https://astral.sh/uv/install.ps1 | iex"',
            "node": "winget install -e --id OpenJS.NodeJS.LTS",
            "git": "winget install -e --id Git.Git",
            "ffmpeg": "winget install -e --id Gyan.FFmpeg",
            "ollama": "winget install -e --id Ollama.Ollama   （装完 ollama pull <模型>）",
        },
        "Darwin": {
            "python": "brew install python@3.12",
            "uv": "brew install uv   （或 curl -LsSf https://astral.sh/uv/install.sh | sh）",
            "node": "brew install node",
            "git": "brew install git",
            "ffmpeg": "brew install ffmpeg",
            "ollama": "brew install --cask ollama",
        },
        "Linux": {
            "python": "sudo apt install python3.12 python3.12-venv   （或对应发行版包）",
            "uv": "curl -LsSf https://astral.sh/uv/install.sh | sh",
            "node": "sudo apt install nodejs npm   （建议用 nvm 装 >=20）",
            "git": "sudo apt install git",
            "ffmpeg": "sudo apt install ffmpeg",
            "ollama": "curl -fsSL https://ollama.com/install.sh | sh",
        },
    }
    return table.get(SYSTEM, table["Linux"]).get(tool, "(请参考官方文档)")


# ---------------- 各项检测 ----------------
def check_python() -> dict:
    cur = sys.version_info[:3]
    ok = (cur[:2] >= PY_MIN) and (cur[:2] < PY_MAX_EXCL)
    detail = "当前解释器 %s（%s）" % (fmt(cur), sys.executable)
    # 当前不达标时，看有没有可用的 3.12
    if not ok:
        if IS_WIN:
            rc, out = run(["py", "-3.12", "-c", "import sys;print(sys.version)"])
        else:
            rc, out = run(["python3.12", "-c", "import sys;print(sys.version)"])
        if rc == 0:
            detail += "；但检测到可用的 3.12：%s" % first_version(out)
    return {
        "name": "Python 3.12.x（严格：>=3.12,<3.13）",
        "status": OK if ok else FAIL,
        "found": fmt(cur),
        "detail": detail,
        "fix": hint("python"),
    }


def check_tool(key, display, cmd, min_ver=None, required=True, note="") -> dict:
    rc, out = run(cmd)
    if rc is None:
        return {"name": display, "status": FAIL if required else WARN, "found": "未安装",
                "detail": note or "未在 PATH 中找到", "fix": hint(key)}
    v = first_version(out)
    ok = True
    if min_ver and v:
        ok = v >= min_ver
    elif min_ver and not v:
        ok = False
    status = OK if ok else (FAIL if required else WARN)
    detail = out.splitlines()[0][:80] if out else ""
    if min_ver and v and not ok:
        detail = "版本过低（需 >= %s）｜%s" % (fmt(min_ver), detail)
    return {"name": display, "status": status, "found": fmt(v) if v else "未知",
            "detail": detail, "fix": hint(key) if status != OK else ""}


def check_port(port, who) -> dict:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", port))
        free = True
    except OSError:
        free = False
    finally:
        s.close()
    return {
        "name": "端口 %d（%s）" % (port, who),
        "status": OK if free else WARN,
        "found": "空闲" if free else "被占用",
        "detail": "空闲，可启动" if free else "已被占用：可能是你已经在跑一份，或用 netstat -ano | findstr :%d 查占用进程" % port,
        "fix": "",
    }


def collect():
    checks = [
        check_python(),
        check_tool("uv", "uv（Python 包/锁管理器）", ["uv", "--version"], required=True,
                   note="仓库用 uv.lock 锁版本；不要用裸 pip install（绕过锁会装出不可复现环境）"),
        check_tool("node", "Node.js（前端构建，需 >=20.19）", ["node", "-v"], min_ver=NODE_MIN, required=True),
        check_tool("node", "npm", ["npm", "-v"], required=True),
        check_tool("git", "Git", ["git", "--version"], required=True),
        check_tool("ffmpeg", "ffmpeg（语音功能需要，可后装）", ["ffmpeg", "-version"], required=False,
                   note="voice/ 模块直接调用 ffmpeg 可执行文件，pip 装不出来，必须系统级安装"),
        check_tool("ollama", "Ollama（本地 LLM 需要，可后装）", ["ollama", "--version"], required=False),
    ]
    checks += [check_port(p, who) for p, who in PORTS]
    return checks


# ---------------- 输出 ----------------
def render(checks) -> None:
    w = max(len(c["name"]) for c in checks)
    print("=" * 78)
    print("scratchpad 环境自检  ·  %s %s  ·  Python %s" % (SYSTEM, platform.release(), fmt(sys.version_info[:3])))
    print("=" * 78)
    for c in checks:
        print("%s %-*s  %-8s  %s" % (MARK[c["status"]], w, c["name"], c["found"], c["detail"]))
    bad = [c for c in checks if c["status"] == FAIL]
    opt = [c for c in checks if c["status"] == WARN]
    print("-" * 78)
    if bad:
        print("❌ 必装项缺失 %d 个 —— 装完重跑本脚本：" % len(bad))
        for c in bad:
            print("   · %s" % c["name"])
            if c["fix"]:
                print("     %s" % c["fix"])
    if opt:
        print("⚠️  可选项缺失 %d 个（不影响启动，按需后装）：" % len(opt))
        for c in opt:
            print("   · %s%s" % (c["name"], ("   → " + c["fix"]) if c["fix"] else ""))
    if not bad:
        print("✅ 必装项全部通过。下一步：  .\\setup.ps1        （Windows 一键安装依赖+构建）")
        print("                             python main.py     （或 uv run uvicorn apiserver.api_server:app --port 8000）")
    print("=" * 78)


def main() -> int:
    ensure_utf8_stdout()
    ap = argparse.ArgumentParser(description="scratchpad 环境自检（单文件/纯标准库）")
    ap.add_argument("--fix", action="store_true",
                    help="本卷只打印安装命令，不自动执行（自动装 winget 包需要 UAC，静默安装风险大）")
    ap.add_argument("--json", action="store_true", help="输出 JSON（CI 用）")
    args = ap.parse_args()

    checks = collect()

    if args.json:
        print(json.dumps({
            "platform": SYSTEM,
            "python": fmt(sys.version_info[:3]),
            "checks": checks,
            "failed": [c["name"] for c in checks if c["status"] == FAIL],
            "warnings": [c["name"] for c in checks if c["status"] == WARN],
        }, ensure_ascii=False, indent=2))
    else:
        render(checks)
        if args.fix:
            print("\n[--fix] 本卷不自动执行安装（需 UAC，静默装风险大）。上面每条「←」后就是可直接粘贴的一行命令。")

    return 1 if any(c["status"] == FAIL for c in checks) else 0


if __name__ == "__main__":
    sys.exit(main())
