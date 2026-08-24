#!/usr/bin/env python3
"""
陆墨 Windows 完整构建脚本

流程：
  1. 环境检查（Python, Node.js, npm）
  2. 同步 Python 依赖 + build 组（pyinstaller）
  3. 准备 OpenClaw 运行时（下载 Node.js 便携版 + 预装 OpenClaw/Agent Browser）
  4. PyInstaller 编译 Python 后端
  5. Electron 前端构建 + 打包
  6. 输出汇总

默认在构建阶段预装 OpenClaw 与 Agent Browser，用户安装后可直接使用。

用法:
  python scripts/build-win.py            # 完整构建
  python scripts/build-win.py --skip-openclaw   # 跳过 OpenClaw 运行时准备
  python scripts/build-win.py --backend-only    # 仅编译后端
"""

import argparse
import json
import os
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
SPEC_FILE = PROJECT_ROOT / "lumo-backend.spec"

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
        [str(npx_cmd), "tsc", "-p", "tsconfig.lumo.json"],
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
    backend_exe = BACKEND_DIST_DIR / "lumo-backend" / "lumo-backend.exe"
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
    backend_dir = BACKEND_DIST_DIR / "lumo-backend"
    if backend_dir.exists():
        size = sum(f.stat().st_size for f in backend_dir.rglob("*") if f.is_file())
        log(f"后端产物: {backend_dir}  ({size / 1024 / 1024:.0f} MB)")

    # 运行时（Node.js + OpenClaw + uv）
    runtime_dir = BACKEND_DIST_DIR / "runtime"
    if runtime_dir.exists():
        size = sum(f.stat().st_size for f in runtime_dir.rglob("*") if f.is_file())
        log(f"OpenClaw 运行时: {runtime_dir}  ({size / 1024 / 1024:.0f} MB)")

    # Electron 安装包
    release_dir = FRONTEND_DIR / "release"
    if release_dir.exists():
        for f in release_dir.glob("*.exe"):
            log(f"安装包: {f}  ({f.stat().st_size / 1024 / 1024:.0f} MB)")


# ============ 主入口 ============


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="陆墨 Windows 构建脚本")
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

    # 计算总步骤数
    total_steps = 2  # 环境检查 + 同步依赖
    if not args.skip_openclaw:
        total_steps += 1
    total_steps += 1  # 编译后端
    if not args.backend_only:
        total_steps += 1  # 前端打包

    step = 0

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

    # 汇总
    print_summary()
    elapsed = time.time() - start_time
    log(f"总耗时: {elapsed / 60:.1f} 分钟")


if __name__ == "__main__":
    main()
