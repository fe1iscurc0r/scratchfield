#!/usr/bin/env python3
"""
陆墨 Windows 完整构建脚本

流程：
  1. 环境检查（Python, Node.js, npm）
  2. 同步 Python 依赖 + build 组（pyinstaller）
  3. 准备 OpenClaw 运行时（下载 Node.js 便携版 + 预装 OpenClaw/Agent Browser）
  4. PyInstaller 编译 Python 后端
  5. Electron 前端构建 + 打包
  6. 产物校验 + 输出汇总

默认在构建阶段预装 OpenClaw 与 Agent Browser，用户安装后可直接使用。

用法:
  python scripts/build-win.py                 # 完整构建
  python scripts/build-win.py --tag v5.1.5    # 带版本号构建（校验 tag 与 package.json 一致）
  python scripts/build-win.py --skip-openclaw # 跳过 OpenClaw 运行时准备
  python scripts/build-win.py --backend-only  # 仅编译后端
  python scripts/build-win.py --verify-only   # 不构建，只校验既有产物
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path
from typing import Optional

# ============ 常量 ============

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
BACKEND_DIST_DIR = FRONTEND_DIR / "backend-dist"
RUNTIME_DIR = BACKEND_DIST_DIR / "runtime"
NODE_RUNTIME_DIR = RUNTIME_DIR / "node"
OPENCLAW_RUNTIME_DIR = RUNTIME_DIR / "openclaw"
RELEASE_DIR = FRONTEND_DIR / "release"
PACKAGE_JSON = FRONTEND_DIR / "package.json"
SPEC_FILE = PROJECT_ROOT / "naga-backend.spec"

# 最低版本要求
MIN_NODE_MAJOR = 22
MIN_PYTHON = (3, 11)

# OpenClaw 运行时版本
NODE_VERSION = "22.13.1"
NODE_DIST_URL = f"https://nodejs.org/dist/v{NODE_VERSION}/node-v{NODE_VERSION}-win-x64.zip"
AGENT_BROWSER_NPM_SPEC = "agent-browser"
CACHE_DIR = PROJECT_ROOT / ".cache"

# uv standalone 二进制
UV_VERSION = "0.6.6"
UV_RUNTIME_DIR = RUNTIME_DIR / "uv"
UV_ARCHIVE = "uv-x86_64-pc-windows-msvc.zip"
UV_DIST_URL = f"https://github.com/astral-sh/uv/releases/download/{UV_VERSION}/{UV_ARCHIVE}"


def log(msg: str) -> None:
    print(f"[build-win] {msg}")


def log_step(step: int, total: int, title: str) -> None:
    print()
    print(f"{'=' * 50}")
    print(f"  Step {step}/{total}: {title}")
    print(f"{'=' * 50}")


def run(
    cmd: list[str],
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """执行命令并实时输出。自动通过 shutil.which 解析 .cmd/.bat（Windows）"""
    resolved = shutil.which(cmd[0])
    if resolved:
        cmd = [resolved, *cmd[1:]]
    log(f"$ {' '.join(cmd)}")
    return subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=env,
        text=True,
        check=check,
    )


def get_cmd_version(cmd: str, args: list[str] | None = None) -> str | None:
    """获取命令版本号，失败返回 None。通过 shutil.which 解析 .cmd/.bat"""
    resolved = shutil.which(cmd)
    if not resolved:
        return None
    try:
        result = subprocess.run(
            [resolved, *(args or ["--version"])],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


# ============ 产物清单与校验 ============

# 关键产物：(相对 PROJECT_ROOT 的路径, 人类可读名, 体积下限 MiB)
# 下限用于识别「存在但是空壳/截断」的假产物（0 字节文件、缺 dll 的残缺目录）
ARTIFACT_SPECS: list[tuple[str, str, float]] = [
    ("frontend/backend-dist/naga-backend/naga-backend.exe", "后端主程序", 5.0),
    ("frontend/backend-dist/runtime/node/node.exe", "Node 运行时", 20.0),
    ("frontend/backend-dist/runtime/node/npm.cmd", "npm 命令", 0.0005),
]


# NSIS 安装包体积异常阈值（MiB）：小于此值几乎必然缺 extraResources（后端/运行时没打进去）
NSIS_MIN_MIB = 200.0


def _dir_size_mib(path: Path) -> float:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / 1024 / 1024


def _nsis_installers() -> list[Path]:
    """返回 release/ 下的 NSIS 安装包（排除 blockmap / yml / unpacked 目录）"""
    if not RELEASE_DIR.is_dir():
        return []
    return sorted(
        p
        for p in RELEASE_DIR.iterdir()
        if p.is_file() and p.suffix.lower() == ".exe" and not p.name.endswith(".blockmap")
    )


def verify_artifacts(tag: str | None = None, *, verbose: bool = True) -> bool:
    """校验构建产物是否齐全且体积合理。返回 True 表示全部通过。

    任一关键文件缺失、体积低于下限，或 NSIS 安装包缺失/体积异常，即返回 False。
    """
    rows: list[tuple[str, str, str, str]] = []  # (检查项, 状态, 实际, 期望)
    ok = True

    for rel, label, min_mib in ARTIFACT_SPECS:
        path = PROJECT_ROOT / rel
        expect = f"≥ {min_mib:.2f} MiB" if min_mib >= 0.01 else "存在"
        if not path.exists():
            rows.append((f"{label}\n  {rel}", "缺失", "—", expect))
            ok = False
            continue
        size_mib = path.stat().st_size / 1024 / 1024
        if size_mib < min_mib:
            rows.append((f"{label}\n  {rel}", "过小", f"{size_mib:.2f} MiB", expect))
            ok = False
            continue
        rows.append((f"{label}\n  {rel}", "OK", f"{size_mib:.2f} MiB", expect))

    # NSIS 安装包
    installers = _nsis_installers()
    if not installers:
        rows.append(("NSIS 安装包\n  frontend/release/*.exe", "缺失", "—", "≥ 1 个"))
        ok = False
    else:
        for inst in installers:
            size_mib = inst.stat().st_size / 1024 / 1024
            if size_mib < NSIS_MIN_MIB:
                rows.append(
                    (
                        f"NSIS 安装包\n  {inst.name}",
                        "体积异常",
                        f"{size_mib:.0f} MiB",
                        f"≥ {NSIS_MIN_MIB:.0f} MiB",
                    )
                )
                ok = False
            else:
                rows.append(
                    (
                        f"NSIS 安装包\n  {inst.name}",
                        "OK",
                        f"{size_mib:.0f} MiB",
                        f"≥ {NSIS_MIN_MIB:.0f} MiB",
                    )
                )
            # 文件名是否带版本号（electron-builder 默认规则：<productName>-Setup-<version>.exe）
            if tag:
                want_ver = tag.lstrip("v")
                if want_ver not in inst.name:
                    rows.append(
                        (
                            f"  版本号落名 {inst.name}",
                            "警告",
                            "无版本号",
                            f"应含 {want_ver}",
                        )
                    )

    if verbose:
        print()
        print("=" * 72)
        print("  产物校验" + (f"（{tag}）" if tag else ""))
        print("=" * 72)
        width_label = max(len(r[0].split("\n")[0]) for r in rows) if rows else 10
        width_status = max(len(r[1]) for r in rows) if rows else 6
        for label, status, actual, expect in rows:
            head, *rest = label.split("\n")
            print(
                f"  [{status:<{width_status}}] {head:<{width_label}}  "
                f"{actual:>12} / 期望 {expect}"
            )
            for line in rest:
                print(f"{'':<{width_status + 6}}{line.strip()}")
        print("-" * 72)
        print(f"  结果：{'全部通过 ✓' if ok else '存在问题 ✗'}")
        print("=" * 72)

    return ok


# ============ 版本号单一来源 ============

TAG_RE = re.compile(r"^v\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.\-]+)?$")


def read_package_version() -> str:
    """读取 frontend/package.json 的 version"""
    if not PACKAGE_JSON.exists():
        raise FileNotFoundError(f"缺少 {PACKAGE_JSON}")
    data = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    version = data.get("version")
    if not version:
        raise ValueError(f"{PACKAGE_JSON} 中没有 version 字段")
    return str(version)


def _git(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        check=False,
    )


def verify_tag(tag: str) -> tuple[bool, str]:
    """校验 tag：格式合法 → tag 存在 → 与 package.json version 一致 → tag 指向 HEAD。

    任何一项不满足即返回 (False, 原因)，调用方必须停下。绝不自动改写任何文件。
    """
    if not TAG_RE.match(tag):
        return False, f"tag 格式非法：{tag!r}（应为 vX.Y.Z，如 v5.1.5）"

    # tag 是否存在
    exists = _git(["rev-parse", "--verify", "--quiet", f"refs/tags/{tag}"])
    if exists.returncode != 0:
        return False, f"tag 不存在：{tag}（先 `git tag -a {tag} -m ...` 再构建）"

    # 是否为 annotated tag（轻量 tag 没有独立对象，不适合作为发布锚点）
    obj_type = _git(["cat-file", "-t", tag])
    if obj_type.stdout.strip() != "tag":
        return False, f"{tag} 是轻量 tag（lightweight），发布锚点必须用 annotated tag（git tag -a）"

    # 与 package.json 一致
    pkg_version = read_package_version()
    tag_version = tag.lstrip("v")
    if tag_version != pkg_version:
        return (
            False,
            f"版本不一致：tag {tag} (= {tag_version}) "
            f"≠ frontend/package.json version ({pkg_version})。"
            f"\n    请先统一二者，再重新构建（脚本不会替你改写）。",
        )

    # tag 指向 HEAD（防止拿旧提交发新版本）
    tag_sha = _git(["rev-list", "-n", "1", tag]).stdout.strip()
    head_sha = _git(["rev-parse", "HEAD"]).stdout.strip()
    if tag_sha != head_sha:
        return (
            False,
            f"tag {tag} 指向 {tag_sha[:8]}，但当前 HEAD 是 {head_sha[:8]}。"
            f"\n    构建必须发生在 tag 所指向的提交上（防旧构建配新 tag）。",
        )

    return True, f"版本校验通过：{tag} == package.json {pkg_version}，且 tag 即 HEAD"


# ============ 前置自检（卷165 doctor_env.py） ============

DOCTOR_SCRIPT = PROJECT_ROOT / "doctor_env.py"


def run_doctor() -> bool:
    """调用卷165 的 doctor_env.py 做环境自检。脚本缺失时降级为提示（不阻塞）。"""
    if not DOCTOR_SCRIPT.exists():
        log(f"未找到 {DOCTOR_SCRIPT.name}（卷165 可能尚未合并），降级为内置精简检查")
        return True

    log(f"运行环境自检：{DOCTOR_SCRIPT.relative_to(PROJECT_ROOT)}")
    result = subprocess.run(
        [sys.executable, str(DOCTOR_SCRIPT)],
        cwd=str(PROJECT_ROOT),
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        log("环境自检未通过（doctor_env.py 返回非 0），构建中止")
        return False
    log("环境自检通过")
    return True


# ============ Step 1: 环境检查 ============


def check_environment() -> bool:
    """检查构建所需的工具是否就绪"""
    ok = True

    if os.name != "nt":
        log("  当前系统不是 Windows  ✗  (build-win.py 仅支持 Windows 打包)")
        return False

    # Python 版本
    py_ver = sys.version_info[:2]
    if py_ver >= MIN_PYTHON:
        log(f"  Python {sys.version.split()[0]}  ✓")
    else:
        log(f"  Python {sys.version.split()[0]}  ✗  (需要 >= {MIN_PYTHON[0]}.{MIN_PYTHON[1]})")
        ok = False

    # uv
    uv_ver = get_cmd_version("uv", ["-V"])
    if uv_ver:
        log(f"  {uv_ver}  ✓")
    else:
        log("  uv 未安装  ✗  (pip install uv)")
        ok = False

    # Node.js
    node_ver = get_cmd_version("node")
    if node_ver:
        major = int(node_ver.lstrip("v").split(".")[0])
        status = "✓" if major >= MIN_NODE_MAJOR else f"✗  (需要 >= {MIN_NODE_MAJOR})"
        log(f"  Node.js {node_ver}  {status}")
        if major < MIN_NODE_MAJOR:
            ok = False
    else:
        log(f"  Node.js 未安装  ✗  (需要 >= {MIN_NODE_MAJOR})")
        ok = False

    # npm
    npm_ver = get_cmd_version("npm")
    if npm_ver:
        log(f"  npm {npm_ver}  ✓")
    else:
        log("  npm 未安装  ✗")
        ok = False

    return ok


# ============ Step 2: 同步依赖 ============


def sync_dependencies() -> None:
    """uv sync + build 依赖组"""
    run(["uv", "sync", "--group", "build"], cwd=PROJECT_ROOT)
    log("Python 依赖同步完成")


# ============ Step 3: 准备 OpenClaw 运行时 ============


def download_node_runtime() -> Path:
    """下载 Node.js 便携版 zip，返回本地缓存路径"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    zip_name = f"node-v{NODE_VERSION}-win-x64.zip"
    zip_path = CACHE_DIR / zip_name

    if zip_path.exists():
        log(f"使用缓存 Node.js 包: {zip_path}")
        return zip_path

    log(f"下载 Node.js v{NODE_VERSION}: {NODE_DIST_URL}")
    urllib.request.urlretrieve(NODE_DIST_URL, str(zip_path))
    log(f"Node.js 下载完成: {zip_path} ({zip_path.stat().st_size / 1024 / 1024:.1f} MB)")
    return zip_path


def extract_node_runtime(zip_path: Path) -> None:
    """解压 Node.js 到 runtime/node"""
    if NODE_RUNTIME_DIR.exists():
        log(f"清理旧 Node.js 运行时: {NODE_RUNTIME_DIR}")
        shutil.rmtree(NODE_RUNTIME_DIR)

    NODE_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

    log(f"解压 Node.js 到: {NODE_RUNTIME_DIR}")
    with zipfile.ZipFile(zip_path, "r") as zf:
        prefix = f"node-v{NODE_VERSION}-win-x64/"
        for member in zf.infolist():
            if not member.filename.startswith(prefix):
                continue
            rel = member.filename[len(prefix) :]
            if not rel:
                continue
            target = NODE_RUNTIME_DIR / rel
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)

    node_exe = NODE_RUNTIME_DIR / "node.exe"
    npm_cmd = NODE_RUNTIME_DIR / "npm.cmd"
    if not node_exe.exists():
        raise FileNotFoundError(f"解压后缺少 node.exe: {node_exe}")
    if not npm_cmd.exists():
        raise FileNotFoundError(f"解压后缺少 npm.cmd: {npm_cmd}")
    log("Node.js 便携版解压完成")


def preinstall_openclaw(force: bool = False) -> None:
    """编译 vendor/openclaw 源码并复制到运行时目录"""
    vendor_root = PROJECT_ROOT / "vendor" / "openclaw"
    if not vendor_root.exists():
        raise FileNotFoundError(f"vendor/openclaw 不存在: {vendor_root}")

    node_exe = NODE_RUNTIME_DIR / "node.exe"
    npm_cmd = NODE_RUNTIME_DIR / "npm.cmd"
    if not node_exe.exists():
        raise FileNotFoundError(f"node.exe 不存在: {node_exe}")

    # 检测是否已有编译产物
    dist_marker = OPENCLAW_RUNTIME_DIR / "dist" / "gateway" / "server.js"
    if not force and dist_marker.exists():
        log("OpenClaw runtime 已存在，跳过编译")
        return

    # 清理旧运行时
    if OPENCLAW_RUNTIME_DIR.exists():
        log(f"清理旧 OpenClaw 运行时: {OPENCLAW_RUNTIME_DIR}")
        shutil.rmtree(OPENCLAW_RUNTIME_DIR)
    OPENCLAW_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    env["PATH"] = f"{NODE_RUNTIME_DIR}{os.pathsep}{env.get('PATH', '')}"

    # 1. 安装 vendor 依赖
    if not (vendor_root / "node_modules").exists():
        log("安装 vendor/openclaw 依赖...")
        run(
            [str(npm_cmd), "install", "--ignore-scripts"],
            cwd=vendor_root,
            env=env,
        )

    # 2. 编译 TypeScript
    log("编译 vendor/openclaw 源码...")
    compile_env = env.copy()
    compile_env["NODE_OPTIONS"] = "--max-old-space-size=4096"
    npx_cmd = NODE_RUNTIME_DIR / "npx.cmd"
    run(
        [str(npx_cmd), "tsc", "-p", "tsconfig.naga.json"],
        cwd=vendor_root,
        env=compile_env,
    )

    vendor_dist = vendor_root / "dist" / "gateway" / "server.js"
    if not vendor_dist.exists():
        raise FileNotFoundError(f"编译失败：dist/gateway/server.js 不存在: {vendor_dist}")

    # 3. 复制编译产物 + 依赖到 runtime
    log("复制编译产物到运行时目录...")
    shutil.copytree(vendor_root / "dist", OPENCLAW_RUNTIME_DIR / "dist")
    shutil.copytree(vendor_root / "node_modules", OPENCLAW_RUNTIME_DIR / "node_modules")
    shutil.copy2(vendor_root / "package.json", OPENCLAW_RUNTIME_DIR / "package.json")
    shutil.copy2(vendor_root / "openclaw.mjs", OPENCLAW_RUNTIME_DIR / "openclaw.mjs")

    # 4. 复制 gateway_start.mjs
    gateway_script_src = PROJECT_ROOT / "agentserver" / "openclaw" / "gateway_start.mjs"
    if gateway_script_src.exists():
        shutil.copy2(gateway_script_src, OPENCLAW_RUNTIME_DIR / "gateway_start.mjs")
        log(f"已复制 gateway_start.mjs -> {OPENCLAW_RUNTIME_DIR / 'gateway_start.mjs'}")

    log(f"OpenClaw 运行时准备完成（从源码编译）: {OPENCLAW_RUNTIME_DIR}")


def preinstall_agent_browser(force: bool = False) -> None:
    """在内嵌运行时目录中预装 agent-browser，并预下载浏览器内核"""
    npm_cmd = NODE_RUNTIME_DIR / "npm.cmd"
    node_exe = NODE_RUNTIME_DIR / "node.exe"
    if not npm_cmd.exists():
        raise FileNotFoundError(f"npm.cmd 不存在: {npm_cmd}")
    if not node_exe.exists():
        raise FileNotFoundError(f"node.exe 不存在: {node_exe}")

    agent_browser_cmd = OPENCLAW_RUNTIME_DIR / "node_modules" / ".bin" / "agent-browser.cmd"
    agent_browser_pkg = OPENCLAW_RUNTIME_DIR / "node_modules" / "agent-browser" / "package.json"
    playwright_core_cli = OPENCLAW_RUNTIME_DIR / "node_modules" / "playwright-core" / "cli.js"

    installed_version: str | None = None
    if agent_browser_pkg.exists():
        try:
            installed_version = json.loads(agent_browser_pkg.read_text(encoding="utf-8")).get("version")
        except Exception:
            installed_version = None

    def _browser_cache_dirs() -> list[Path]:
        return [
            OPENCLAW_RUNTIME_DIR / "node_modules" / "playwright-core" / ".local-browsers",
            OPENCLAW_RUNTIME_DIR / "node_modules" / "agent-browser" / "node_modules" / "playwright-core" / ".local-browsers",
        ]

    def _has_browser_cache() -> bool:
        for candidate in _browser_cache_dirs():
            if candidate.exists():
                try:
                    if any(candidate.iterdir()):
                        return True
                except Exception:
                    return True
        return False

    if not force and agent_browser_cmd.exists() and _has_browser_cache():
        log(f"agent-browser 已预装: {installed_version or 'unknown'}，跳过安装")
        return
    if agent_browser_cmd.exists() and not _has_browser_cache():
        log("检测到 agent-browser 命令已存在，但浏览器缓存缺失，继续补装 chromium")

    env = os.environ.copy()
    env["PATH"] = f"{NODE_RUNTIME_DIR}{os.pathsep}{env.get('PATH', '')}"
    env["NPM_CONFIG_AUDIT"] = "false"
    env["NPM_CONFIG_FUND"] = "false"
    env["NPM_CONFIG_GLOBAL"] = "false"
    # 将浏览器二进制放进 node_modules，避免首次运行再下载到用户目录。
    env["PLAYWRIGHT_BROWSERS_PATH"] = "0"
    env["CI"] = "1"

    log(f"预装 Agent Browser（npm install {AGENT_BROWSER_NPM_SPEC}）...")
    run(
        [
            str(npm_cmd),
            "install",
            AGENT_BROWSER_NPM_SPEC,
            "--global=false",
            "--location=project",
            "--prefix",
            str(OPENCLAW_RUNTIME_DIR),
        ],
        cwd=OPENCLAW_RUNTIME_DIR,
        env=env,
    )

    if not agent_browser_cmd.exists():
        raise FileNotFoundError(f"agent-browser 预装失败，未找到命令: {agent_browser_cmd}")
    if not playwright_core_cli.exists():
        raise FileNotFoundError(f"playwright-core cli 缺失，无法预装浏览器内核: {playwright_core_cli}")

    log("预下载 Agent Browser 浏览器依赖（playwright-core install chromium）...")
    run(
        [
            str(node_exe),
            str(playwright_core_cli),
            "install",
            "chromium",
        ],
        cwd=OPENCLAW_RUNTIME_DIR,
        env=env,
    )

    browsers_dirs = [str(path) for path in _browser_cache_dirs() if path.exists()]
    if browsers_dirs:
        log(f"Agent Browser 浏览器缓存已写入: {', '.join(browsers_dirs)}")
    elif not _has_browser_cache():
        raise FileNotFoundError("playwright-core install chromium 执行完成，但未找到浏览器缓存目录")
    log(f"Agent Browser 预装完成: {agent_browser_cmd}")


def download_uv_runtime() -> Path:
    """下载 uv standalone 二进制包，返回本地缓存路径"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    archive_path = CACHE_DIR / UV_ARCHIVE
    if archive_path.exists():
        log(f"使用缓存 uv 包: {archive_path}")
        return archive_path
    log(f"下载 uv v{UV_VERSION}: {UV_DIST_URL}")
    urllib.request.urlretrieve(UV_DIST_URL, str(archive_path))
    log(f"uv 下载完成: {archive_path} ({archive_path.stat().st_size / 1024 / 1024:.1f} MB)")
    return archive_path


def extract_uv_runtime(archive_path: Path) -> None:
    """解压 uv standalone 到 runtime/uv/"""
    if UV_RUNTIME_DIR.exists():
        if (UV_RUNTIME_DIR / "uv.exe").exists():
            log("uv 运行时已存在，跳过解压")
            return
        shutil.rmtree(UV_RUNTIME_DIR)

    UV_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    log(f"解压 uv 到 {UV_RUNTIME_DIR}")

    with zipfile.ZipFile(archive_path, "r") as zf:
        for member in zf.infolist():
            fname = Path(member.filename).name
            if not fname or member.is_dir():
                continue
            target = UV_RUNTIME_DIR / fname
            with zf.open(member) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)

    if not (UV_RUNTIME_DIR / "uv.exe").exists():
        raise FileNotFoundError("uv 解压后未找到 uv.exe")
    log(f"uv 运行时准备完成: {UV_RUNTIME_DIR}")


def prepare_openclaw_runtime(force: bool = False) -> None:
    """准备 OpenClaw 运行时：Node.js 便携版 + OpenClaw/Agent Browser 预装 + uv"""
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = download_node_runtime()
    extract_node_runtime(zip_path)
    preinstall_openclaw(force=force)
    preinstall_agent_browser(force=force)
    # 下载并解压 uv standalone（用于 MCP uvx 服务）
    uv_archive = download_uv_runtime()
    extract_uv_runtime(uv_archive)
    log("OpenClaw 运行时准备完成（Node.js + OpenClaw + Agent Browser + uv 已预装）")


# ============ Step 4: PyInstaller 编译后端 ============


def ensure_build_config_file() -> None:
    """确保构建阶段存在 config.json，缺失时从 config.json.example 生成。"""
    config_path = PROJECT_ROOT / "config.json"
    if config_path.exists():
        return

    example_path = PROJECT_ROOT / "config.json.example"
    if not example_path.exists():
        raise FileNotFoundError(
            f"缺少配置文件：{config_path} 与 {example_path} 均不存在，无法执行 PyInstaller 打包"
        )

    shutil.copy2(example_path, config_path)
    log(f"检测到缺失 config.json，已从模板生成: {config_path}")


def build_backend() -> None:
    """用 PyInstaller 编译 Python 后端"""
    if not SPEC_FILE.exists():
        raise FileNotFoundError(f"spec 文件不存在: {SPEC_FILE}")
    ensure_build_config_file()

    work_dir = PROJECT_ROOT / "build" / "pyinstaller"
    work_dir.mkdir(parents=True, exist_ok=True)

    run(
        [
            "uv",
            "run",
            "pyinstaller",
            str(SPEC_FILE),
            "--distpath",
            str(BACKEND_DIST_DIR),
            "--workpath",
            str(work_dir),
            "--clean",
            "-y",
        ],
        cwd=PROJECT_ROOT,
    )

    # 验证产物
    backend_exe = BACKEND_DIST_DIR / "naga-backend" / "naga-backend.exe"
    if not backend_exe.exists():
        raise FileNotFoundError(f"后端编译产物缺失: {backend_exe}")
    log(f"后端编译完成: {backend_exe}")


# ============ Step 5: Electron 前端构建 + 打包 ============


def build_frontend(debug: bool = False) -> None:
    """构建 Vue 前端 + Electron 打包。

    debug=True 时会注入 electron-builder metadata，
    让安装后的 Electron 主进程以“调试控制台模式”启动后端。
    """
    # 安装前端依赖
    node_modules = FRONTEND_DIR / "node_modules"
    if not node_modules.exists():
        log("安装前端依赖...")
        run(["npm", "install"], cwd=FRONTEND_DIR)

    # 构建 + 打包（npm run dist:win = vue-tsc + vite build + electron-builder --win）
    if debug:
        log("调试构建模式：已启用后端日志终端（安装后会弹 cmd 实时输出）")
        run(
            [
                "npm",
                "run",
                "dist:win",
                "--",
                "-c.extraMetadata.lumoDebugConsole=true",
            ],
            cwd=FRONTEND_DIR,
        )
    else:
        run(["npm", "run", "dist:win"], cwd=FRONTEND_DIR)

    log("Electron 打包完成")


# ============ Step 6: 汇总 ============


def print_summary() -> None:
    """打印构建产物信息"""
    print()
    print("=" * 50)
    print("  构建完成!")
    print("=" * 50)

    # 后端产物
    backend_dir = BACKEND_DIST_DIR / "naga-backend"
    if backend_dir.exists():
        log(f"后端产物: {backend_dir}  ({_dir_size_mib(backend_dir):.0f} MB)")

    # 运行时（Node.js + OpenClaw + uv）
    runtime_dir = BACKEND_DIST_DIR / "runtime"
    if runtime_dir.exists():
        log(f"OpenClaw 运行时: {runtime_dir}  ({_dir_size_mib(runtime_dir):.0f} MB)")

    # Electron 安装包
    for inst in _nsis_installers():
        log(f"安装包: {inst}  ({inst.stat().st_size / 1024 / 1024:.0f} MB)")


# ============ 主入口 ============


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="陆墨 Windows 构建脚本")
    parser.add_argument(
        "--tag",
        metavar="vX.Y.Z",
        help="发布版本号（annotated git tag）。校验 tag 与 frontend/package.json version 一致后才构建；"
        "不一致即报错退出，不会自动改写任何文件",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="不构建，只按产物清单校验既有构建（可配合 --tag 校验产物文件名里的版本号）",
    )
    parser.add_argument(
        "--skip-openclaw",
        action="store_true",
        help="跳过 OpenClaw 运行时准备（Node 便携版 + OpenClaw/Agent Browser 预装）",
    )
    parser.add_argument("--backend-only", action="store_true", help="仅编译后端，不打包 Electron")
    parser.add_argument(
        "--force-openclaw",
        action="store_true",
        help="强制重装 OpenClaw 与 Agent Browser 运行时",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="调试打包：安装后启动时弹出后端日志终端（仅 Windows 生效）",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    start_time = time.time()

    # --verify-only：只校验既有产物，不做任何构建动作
    if args.verify_only:
        # 带 --tag 时，tag 校验也必须跑——否则「产物齐全」可能是别的版本留下的，
        # 而 release-win.py 正是靠这一步做发布前把关。
        if args.tag:
            ok_tag, reason = verify_tag(args.tag)
            log(f"版本校验：{reason}")
            if not ok_tag:
                log("版本校验未通过，产物校验中止")
                sys.exit(1)
        ok = verify_artifacts(args.tag)
        sys.exit(0 if ok else 1)

    # Step 0: 版本号校验（--tag 时）
    if args.tag:
        ok, reason = verify_tag(args.tag)
        log(f"版本校验：{reason}")
        if not ok:
            log("版本校验未通过，构建中止")
            sys.exit(1)
        log(f"本次构建目标版本：{args.tag}")

    # 计算总步骤数
    total_steps = 3  # 环境自检 + 环境检查 + 同步依赖
    if not args.skip_openclaw:
        total_steps += 1
    total_steps += 1  # 编译后端
    if not args.backend_only:
        total_steps += 2  # 前端打包 + 产物校验

    step = 0

    # Step 0.5: 前置环境自检（卷165 doctor_env.py）
    step += 1
    log_step(step, total_steps, "前置环境自检")
    if not run_doctor():
        sys.exit(1)

    # Step 1: 环境检查
    step += 1
    log_step(step, total_steps, "环境检查")
    if not check_environment():
        log("环境检查未通过，请先安装缺失的工具")
        sys.exit(1)

    # Step 2: 同步依赖
    step += 1
    log_step(step, total_steps, "同步 Python 依赖")
    sync_dependencies()

    # Step 3: OpenClaw 运行时
    if not args.skip_openclaw:
        step += 1
        log_step(step, total_steps, "准备 OpenClaw 运行时（含预装）")
        prepare_openclaw_runtime(force=args.force_openclaw)

    # Step 4: 编译后端
    step += 1
    log_step(step, total_steps, "PyInstaller 编译后端")
    build_backend()

    # Step 5: 前端打包
    if not args.backend_only:
        step += 1
        title = "Electron 前端打包（DEBUG）" if args.debug else "Electron 前端打包"
        log_step(step, total_steps, title)
        build_frontend(debug=args.debug)

        # Step 6: 产物校验（任一失败退出码 1）
        step += 1
        log_step(step, total_steps, "产物校验")
        if not verify_artifacts(args.tag):
            print_summary()
            log("产物校验未通过，退出码 1")
            sys.exit(1)

    # 汇总
    print_summary()
    elapsed = time.time() - start_time
    log(f"总耗时: {elapsed / 60:.1f} 分钟")


if __name__ == "__main__":
    main()
