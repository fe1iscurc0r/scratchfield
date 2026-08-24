#!/usr/bin/env python3
"""
NagaAgent 跨平台构建脚本（Windows / macOS / Linux）

流程：
  1. 环境检查（Python, uv, Node.js, npm）
  2. 同步 Python 依赖 + build 组（pyinstaller）
  3. 准备 OpenClaw 运行时（复用构建机 Node.js + 预装 OpenClaw/Agent Browser）
  4. PyInstaller 编译 Python 后端
  5. Electron 前端构建 + 打包
  6. 输出汇总

默认在构建阶段预装 OpenClaw 与 Agent Browser，用户安装后首次启动可直接使用。

用法:
  python scripts/build.py                  # 完整构建（自动检测平台）
  python scripts/build.py --skip-openclaw  # 跳过 OpenClaw 运行时准备
  python scripts/build.py --backend-only   # 仅编译后端
  python scripts/build.py --force-openclaw # 强制重装 OpenClaw
  python scripts/build.py --debug          # 调试模式（仅 Windows 生效）
"""

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import time
import zipfile
from urllib.parse import unquote, urlparse

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # Python < 3.11 fallback
import urllib.request
from pathlib import Path
from typing import Optional

# ============ 平台检测 ============

IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"
IS_LINUX = sys.platform.startswith("linux")
PLATFORM_TAG = "win" if IS_WINDOWS else "mac" if IS_MACOS else "linux"

# macOS: 区分 arm64 (Apple Silicon) 和 x86_64 (Intel)
MAC_ARCH = "arm64" if platform.machine() == "arm64" else "x64"

# ============ 常量 ============

PROJECT_ROOT = Path(__file__).resolve().parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
BACKEND_DIST_DIR = FRONTEND_DIR / "backend-dist"
RUNTIME_DIR = BACKEND_DIST_DIR / "runtime"
NODE_RUNTIME_DIR = RUNTIME_DIR / "node"
OPENCLAW_RUNTIME_DIR = RUNTIME_DIR / "openclaw"
PYTHON_RUNTIME_DIR = RUNTIME_DIR / "python"
SPEC_FILE = PROJECT_ROOT / "naga-backend.spec"
AGENT_BROWSER_NPM_SPEC = "agent-browser@0.34.0"
OPENCLAW_SOURCE_REGISTER = PROJECT_ROOT / "agentserver" / "openclaw" / "source_register.mjs"

# 最低版本要求
MIN_NODE_MAJOR = 22
MIN_PYTHON = (3, 11)

# OpenClaw 运行时版本
NODE_VERSION = "22.13.1"
PYTHON_RUNTIME_VERSION = "3.11.15"
PYTHON_RUNTIME_RELEASE = "20260303"
CACHE_DIR = PROJECT_ROOT / ".cache"

# Node.js 下载地址（按平台）
if IS_WINDOWS:
    NODE_ARCHIVE = f"node-v{NODE_VERSION}-win-x64.zip"
elif IS_MACOS:
    NODE_ARCHIVE = f"node-v{NODE_VERSION}-darwin-{MAC_ARCH}.tar.gz"
else:
    NODE_ARCHIVE = f"node-v{NODE_VERSION}-linux-x64.tar.xz"

NODE_DIST_URL = f"https://nodejs.org/dist/v{NODE_VERSION}/{NODE_ARCHIVE}"

# Python standalone 运行时（用于外部 Python MCP）
if IS_WINDOWS:
    PYTHON_ARCHIVE = (
        f"cpython-{PYTHON_RUNTIME_VERSION}+{PYTHON_RUNTIME_RELEASE}"
        "-x86_64-pc-windows-msvc-install_only_stripped.tar.gz"
    )
elif IS_MACOS:
    _py_arch = "aarch64" if MAC_ARCH == "arm64" else "x86_64"
    PYTHON_ARCHIVE = (
        f"cpython-{PYTHON_RUNTIME_VERSION}+{PYTHON_RUNTIME_RELEASE}"
        f"-{_py_arch}-apple-darwin-install_only_stripped.tar.gz"
    )
else:
    PYTHON_ARCHIVE = (
        f"cpython-{PYTHON_RUNTIME_VERSION}+{PYTHON_RUNTIME_RELEASE}"
        "-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz"
    )

PYTHON_DIST_URL = (
    "https://github.com/astral-sh/python-build-standalone/releases/download/"
    f"{PYTHON_RUNTIME_RELEASE}/{PYTHON_ARCHIVE}"
)

# uv standalone 二进制版本与下载地址
UV_VERSION = "0.6.6"
UV_RUNTIME_DIR = RUNTIME_DIR / "uv"
if IS_WINDOWS:
    UV_ARCHIVE = "uv-x86_64-pc-windows-msvc.zip"
elif IS_MACOS:
    _uv_arch = "aarch64" if MAC_ARCH == "arm64" else "x86_64"
    UV_ARCHIVE = f"uv-{_uv_arch}-apple-darwin.tar.gz"
else:
    UV_ARCHIVE = "uv-x86_64-unknown-linux-gnu.tar.gz"
UV_DIST_URL = f"https://github.com/astral-sh/uv/releases/download/{UV_VERSION}/{UV_ARCHIVE}"

# 平台相关路径
NODE_BIN = "node.exe" if IS_WINDOWS else "bin/node"
NPM_BIN = "npm.cmd" if IS_WINDOWS else "bin/npm"
BACKEND_EXT = ".exe" if IS_WINDOWS else ""
INSTALLER_GLOB = "*.exe" if IS_WINDOWS else "*.dmg" if IS_MACOS else "*.AppImage"


# ── 供应链完整性校验（#14 高危修复）──
# 下载的运行时压缩包必须以权威 SHA-256 校验，防止中间人/被篡改下载投毒。
# 哈希来源：nodejs.org SHASUMS256.txt、uv 官方 release .sha256、
#          python-build-standalone release SHA256SUMS。
_ARCHIVE_SHA256: dict[str, str] = {
    # Node.js v22.13.1
    "node-v22.13.1-win-x64.zip": "398a61e250a5584a62a5959e2f69f5d597fc83f1a5ebe3ed8fff29ba39d55f14",
    "node-v22.13.1-darwin-arm64.tar.gz": "97483ff4361d239a56d038c6335767a56a291e78c10f07446f463f05d9d19b89",
    "node-v22.13.1-darwin-x64.tar.gz": "6fdcc8412d434664238b0651ebd5ad55d15a08598ff42dcb6d9cf1d434a6c4be",
    "node-v22.13.1-linux-x64.tar.xz": "0d2a5af33c7deab5555c8309cd3f373446fe1526c1b95833935ab3f019733b3b",
    # uv v0.6.6
    "uv-x86_64-pc-windows-msvc.zip": "72d7866fac1a9f5e895ec632a0b8a98ea59627cb2c3b8e68af4fec899ee4b43b",
    "uv-aarch64-apple-darwin.tar.gz": "d0fb047593122746c7529960f8efd5d7d10d2cb230302f71158e9765ad37727b",
    "uv-x86_64-apple-darwin.tar.gz": "c584b85e81df8d8ae8142876b80ae977e41c6bba14c57cc1061b6a87f361ad2e",
    "uv-x86_64-unknown-linux-gnu.tar.gz": "4c3426c4919d9f44633ab9884827fa1ad64ad8d993516d636eb955a3835c4a8c",
    # Python standalone 3.11.15+20260303
    "cpython-3.11.15+20260303-x86_64-pc-windows-msvc-install_only_stripped.tar.gz": "05272c1b0dce6ac310ec821872391da642a91278a33d0472df8bf57390e48239",
    "cpython-3.11.15+20260303-aarch64-apple-darwin-install_only_stripped.tar.gz": "3ac3262428d899422dcf07ec0c69f8c99abc78ba36b497ffcb0f981d28ae0136",
    "cpython-3.11.15+20260303-x86_64-apple-darwin-install_only_stripped.tar.gz": "9038d161defcbedc0b723fa48f60890057d18a89167609d594299432f2e059f1",
    "cpython-3.11.15+20260303-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz": "bf1f2b630fed4b65b8fbee7971e7e50b36df3de506c7c5ae32aa3373651c4403",
}


def _verify_archive_sha256(archive_path: Path) -> None:
    """校验下载压缩包的 SHA-256，不匹配则删除并抛错（防供应链投毒）。

    仅信任 _ARCHIVE_SHA256 中显式登记的版本；未登记的归档直接拒绝使用。
    """
    import hashlib

    expected = _ARCHIVE_SHA256.get(archive_path.name)
    if not expected:
        raise RuntimeError(
            f"未登记 {archive_path.name} 的 SHA-256，拒绝使用（请在 _ARCHIVE_SHA256 登记）"
        )
    hasher = hashlib.sha256()
    with open(archive_path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            hasher.update(chunk)
    actual = hasher.hexdigest()
    if actual.lower() != expected.lower():
        archive_path.unlink(missing_ok=True)
        raise RuntimeError(
            f"{archive_path.name} SHA-256 校验失败（期望 {expected}，实际 {actual}），"
            "已删除可疑文件，请重新下载"
        )


def safe_print(*values: object, sep: str = " ", end: str = "\n", file=None) -> None:
    stream = file or sys.stdout
    text = sep.join(str(value) for value in values)
    try:
        print(text, end=end, file=stream, flush=True)
        return
    except UnicodeEncodeError:
        encoding = getattr(stream, "encoding", None) or "utf-8"
        fallback = text.encode(encoding, errors="backslashreplace").decode(encoding, errors="strict")
        stream.write(fallback)
        stream.write(end)
        stream.flush()


def read_version() -> str:
    """从 pyproject.toml 读取版本号（唯一版本源）"""
    with open(PROJECT_ROOT / "pyproject.toml", "rb") as f:
        return tomllib.load(f)["project"]["version"]


def sync_frontend_version() -> None:
    """将 pyproject.toml 版本同步到 package.json（electron-builder 用它生成安装包文件名）"""
    ver = read_version()
    pkg_path = FRONTEND_DIR / "package.json"
    pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
    if pkg.get("version") == ver:
        return
    pkg["version"] = ver
    pkg_path.write_text(json.dumps(pkg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    log(f"已同步版本 {ver} → package.json")


def log(msg: str) -> None:
    safe_print(f"[build] {msg}")


def log_step(step: int, total: int, title: str) -> None:
    safe_print()
    safe_print(f"{'=' * 50}")
    safe_print(f"  Step {step}/{total}: {title}")
    safe_print(f"{'=' * 50}")


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

    platform_name = "Windows" if IS_WINDOWS else "macOS" if IS_MACOS else "Linux"
    log(f"  平台: {platform_name} ({platform.machine()})  ✓")
    log(f"  构建版本: {read_version()}")

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
    """下载 Node.js 便携版，返回本地缓存路径"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    archive_path = CACHE_DIR / NODE_ARCHIVE

    if archive_path.exists():
        log(f"使用缓存 Node.js 包: {archive_path}")
        return archive_path

    log(f"下载 Node.js v{NODE_VERSION}: {NODE_DIST_URL}")
    urllib.request.urlretrieve(NODE_DIST_URL, str(archive_path))
    _verify_archive_sha256(archive_path)
    log(f"Node.js 下载完成: {archive_path} ({archive_path.stat().st_size / 1024 / 1024:.1f} MB)")
    return archive_path


def _find_node_runtime_npm_cli(runtime_root: Path) -> Path | None:
    candidates = [
        runtime_root / "node_modules" / "npm" / "bin" / "npm-cli.js",
        runtime_root / "node_modules" / "npm" / "bin" / "npm-cli.mjs",
        runtime_root / "lib" / "node_modules" / "npm" / "bin" / "npm-cli.js",
        runtime_root / "lib" / "node_modules" / "npm" / "bin" / "npm-cli.mjs",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _resolve_build_node_runtime_root() -> Path | None:
    node_cmd = shutil.which("node")
    if not node_cmd:
        return None

    node_path = Path(node_cmd).resolve()
    root_candidates: list[Path] = []
    if node_path.parent.name == "bin":
        root_candidates.append(node_path.parent.parent)
    root_candidates.append(node_path.parent)

    seen: set[Path] = set()
    for runtime_root in root_candidates:
        if runtime_root in seen:
            continue
        seen.add(runtime_root)
        if not (runtime_root / NODE_BIN).exists():
            continue
        npm_cmd = runtime_root / NPM_BIN
        npm_cli = _find_node_runtime_npm_cli(runtime_root)
        if npm_cmd.exists() or npm_cli is not None:
            return runtime_root
    return None


def _extract_zip(archive_path: Path) -> None:
    """解压 .zip 格式的 Node.js（Windows）"""
    prefix = f"node-v{NODE_VERSION}-win-x64/"
    with zipfile.ZipFile(archive_path, "r") as zf:
        for member in zf.infolist():
            if not member.filename.startswith(prefix):
                continue
            rel = member.filename[len(prefix):]
            if not rel:
                continue
            target = NODE_RUNTIME_DIR / rel
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)


def _extract_prefixed_tarball(archive_path: Path, prefix: str, target_root: Path) -> None:
    mode = "r:gz" if archive_path.name.endswith(".tar.gz") else "r:xz"
    with tarfile.open(archive_path, mode) as tf:
        for member in tf.getmembers():
            if not member.name.startswith(prefix):
                continue
            rel = member.name[len(prefix):]
            if not rel:
                continue
            target = target_root / rel
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            elif member.issym():
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists() or target.is_symlink():
                    target.unlink()
                os.symlink(member.linkname, target)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                extracted = tf.extractfile(member)
                if extracted:
                    with open(target, "wb") as dst:
                        shutil.copyfileobj(extracted, dst)
                    if member.mode & 0o111:
                        target.chmod(target.stat().st_mode | 0o755)


def _extract_tarball(archive_path: Path) -> None:
    """解压 .tar.gz / .tar.xz 格式的 Node.js（macOS / Linux）"""
    # 推断 archive 内的顶层目录名
    stem = NODE_ARCHIVE
    for suffix in (".tar.gz", ".tar.xz"):
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    prefix = f"{stem}/"

    _extract_prefixed_tarball(archive_path, prefix, NODE_RUNTIME_DIR)


def extract_node_runtime(archive_path: Path) -> None:
    """解压 Node.js 到 runtime/node"""
    if NODE_RUNTIME_DIR.exists():
        log(f"清理旧 Node.js 运行时: {NODE_RUNTIME_DIR}")
        shutil.rmtree(NODE_RUNTIME_DIR)

    NODE_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

    log(f"解压 Node.js 到: {NODE_RUNTIME_DIR}")
    if archive_path.suffix == ".zip":
        _extract_zip(archive_path)
    else:
        _extract_tarball(archive_path)

    # 验证关键文件
    node_bin = NODE_RUNTIME_DIR / NODE_BIN
    npm_bin = NODE_RUNTIME_DIR / NPM_BIN
    if not node_bin.exists():
        raise FileNotFoundError(f"解压后缺少 node: {node_bin}")
    if not npm_bin.exists():
        raise FileNotFoundError(f"解压后缺少 npm: {npm_bin}")
    log("Node.js 便携版解压完成")


def _remove_runtime_path(path: Path) -> None:
    if not path.exists() and not path.is_symlink():
        return
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path, ignore_errors=True)
    else:
        path.unlink(missing_ok=True)


def _sanitize_copied_node_runtime() -> None:
    """清理构建机 Node 安装中的全局包污染，只保留运行时必需文件。"""
    if IS_WINDOWS:
        bin_dir = NODE_RUNTIME_DIR
        allowed_bins = {"node.exe", "npm", "npm.cmd", "npx", "npx.cmd", "corepack", "corepack.cmd"}
    else:
        bin_dir = NODE_RUNTIME_DIR / "bin"
        allowed_bins = {"node", "npm", "npx", "corepack"}

    if bin_dir.exists():
        for child in bin_dir.iterdir():
            if IS_WINDOWS and child.is_dir() and not child.is_symlink():
                # Windows 的 Node 安装根目录本身还承载 node_modules 等必需目录，
                # 这里只清理意外带进来的全局命令壳子，不动目录主体。
                continue
            if child.name not in allowed_bins:
                _remove_runtime_path(child)

    for modules_root in (NODE_RUNTIME_DIR / "lib" / "node_modules", NODE_RUNTIME_DIR / "node_modules"):
        if not modules_root.exists():
            continue
        for child in modules_root.iterdir():
            if child.name not in {"npm", "corepack"}:
                _remove_runtime_path(child)


def prepare_node_runtime() -> None:
    """优先复用构建机 Node.js 安装目录到 runtime/node，找不到时再回退下载。"""
    shared_runtime_root = _resolve_build_node_runtime_root()
    if shared_runtime_root is None:
        log("未定位到可复用的构建机 Node.js 安装，回退到下载便携版")
        archive_path = download_node_runtime()
        extract_node_runtime(archive_path)
        return

    if NODE_RUNTIME_DIR.exists():
        log(f"清理旧 Node.js 运行时: {NODE_RUNTIME_DIR}")
        shutil.rmtree(NODE_RUNTIME_DIR)

    log(f"复用构建机 Node.js 到: {NODE_RUNTIME_DIR} <- {shared_runtime_root}")
    shutil.copytree(shared_runtime_root, NODE_RUNTIME_DIR, symlinks=not IS_WINDOWS)
    _sanitize_copied_node_runtime()

    node_bin = NODE_RUNTIME_DIR / NODE_BIN
    npm_bin = NODE_RUNTIME_DIR / NPM_BIN
    npm_cli = _find_node_runtime_npm_cli(NODE_RUNTIME_DIR)
    if not node_bin.exists():
        raise FileNotFoundError(f"复制后缺少 node: {node_bin}")
    if not npm_bin.exists() and npm_cli is None:
        raise FileNotFoundError(f"复制后缺少 npm: {NODE_RUNTIME_DIR}")

    shared_node_ver = get_cmd_version("node") or "unknown"
    log(f"Node.js 运行时已与构建机对齐: {shared_node_ver}")


def _find_runtime_npm_cli() -> Path:
    candidate = _find_node_runtime_npm_cli(NODE_RUNTIME_DIR)
    if candidate is not None:
        return candidate
    raise FileNotFoundError(f"Node runtime 中未找到 npm-cli.js: {NODE_RUNTIME_DIR}")


def _find_vendor_typescript_cli(vendor_root: Path) -> Path:
    candidates = [
        vendor_root / "node_modules" / "typescript" / "bin" / "tsc",
        vendor_root / "node_modules" / "typescript" / "bin" / "tsc.js",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"vendor/openclaw 中未找到 TypeScript CLI: {vendor_root / 'node_modules' / 'typescript'}")


def _runtime_npm_command(*args: str) -> list[str]:
    node_bin = NODE_RUNTIME_DIR / NODE_BIN
    if not node_bin.exists():
        raise FileNotFoundError(f"node 不存在: {node_bin}")
    npm_cli = _find_runtime_npm_cli()
    return [str(node_bin), str(npm_cli), *args]


def _apply_runtime_npm_env(env: dict[str, str]) -> dict[str, str]:
    npm_cache_dir = CACHE_DIR / "npm"
    npm_cache_dir.mkdir(parents=True, exist_ok=True)
    env["NPM_CONFIG_CACHE"] = str(npm_cache_dir)
    return env


def _install_openclaw_vendor_dependencies(vendor_root: Path, env: dict[str, str], force: bool) -> None:
    node_modules_dir = vendor_root / "node_modules"
    package_lock = vendor_root / "package-lock.json"

    if force and node_modules_dir.exists():
        log(f"强制重建 vendor/openclaw 依赖: {node_modules_dir}")
        shutil.rmtree(node_modules_dir)

    if node_modules_dir.exists():
        return

    install_attempts = [["ci"], ["install"]] if package_lock.exists() else [["install"]]
    last_error: subprocess.CalledProcessError | None = None
    for index, install_args in enumerate(install_attempts):
        install_desc = " ".join(install_args)
        if index == 0:
            log(f"安装 vendor/openclaw 依赖（{install_desc}，启用平台脚本）...")
        else:
            log(f"vendor/openclaw 依赖安装回退到 `{install_desc}`（锁文件与平台原生包可能不完全同步）...")
        try:
            run(
                _runtime_npm_command(*install_args),
                cwd=vendor_root,
                env=env,
            )
            return
        except subprocess.CalledProcessError as exc:
            last_error = exc
            if index == len(install_attempts) - 1:
                raise
    if last_error is not None:
        raise last_error


def _write_openclaw_import_diagnostics(output: str) -> Path | None:
    if not output.strip():
        return None
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    diag_path = CACHE_DIR / "openclaw-gateway-import.log"
    diag_path.write_text(output, encoding="utf-8")
    return diag_path


_OPENCLAW_TS_SOURCE_SUFFIXES = {".ts", ".tsx", ".mts", ".cts"}
_OPENCLAW_COPY_SOURCE_SUFFIXES = {".js", ".mjs", ".cjs", ".json", ".html", ".css", ".hash"}


def _is_openclaw_emit_source(relative_posix_path: str) -> bool:
    return not (
        relative_posix_path.endswith(".d.ts")
        or relative_posix_path.endswith(".d.mts")
        or relative_posix_path.endswith(".d.cts")
        or relative_posix_path.endswith(".test.ts")
        or relative_posix_path.endswith(".live.test.ts")
        or relative_posix_path.endswith(".e2e.test.ts")
    )


def _openclaw_dist_output_path(source_root: Path, dist_root: Path, source_path: Path) -> Path | None:
    relative_path = source_path.relative_to(source_root)
    relative_posix = relative_path.as_posix()
    suffix = source_path.suffix

    if suffix in _OPENCLAW_TS_SOURCE_SUFFIXES:
        if not _is_openclaw_emit_source(relative_posix):
            return None
        output_suffix = {
            ".ts": ".js",
            ".tsx": ".js",
            ".mts": ".mjs",
            ".cts": ".cjs",
        }[suffix]
        return dist_root / relative_path.with_suffix(output_suffix)

    if suffix in _OPENCLAW_COPY_SOURCE_SUFFIXES:
        return dist_root / relative_path

    return None


def _transpile_openclaw_source_module(
    node_bin: Path,
    vendor_root: Path,
    source_path: Path,
    output_path: Path,
    env: dict[str, str],
) -> None:
    typescript_lib = vendor_root / "node_modules" / "typescript" / "lib" / "typescript.js"
    tsconfig_path = vendor_root / "tsconfig.naga.json"
    if not typescript_lib.exists():
        raise FileNotFoundError(f"缺少 TypeScript 运行库: {typescript_lib}")
    if not tsconfig_path.exists():
        raise FileNotFoundError(f"缺少 tsconfig.naga.json: {tsconfig_path}")

    module_kind = "CommonJS" if source_path.suffix == ".cts" else "ESNext"
    script = (
        "const fs = require('node:fs');"
        "const path = require('node:path');"
        "const [tsLibPath, tsconfigPath, srcPath, outPath, moduleKindName] = process.argv.slice(1);"
        "const ts = require(tsLibPath);"
        "const configFile = ts.readConfigFile(tsconfigPath, ts.sys.readFile);"
        "if (configFile.error) {"
        "  throw new Error(ts.flattenDiagnosticMessageText(configFile.error.messageText, '\\n'));"
        "}"
        "const parsed = ts.parseJsonConfigFileContent(configFile.config, ts.sys, path.dirname(tsconfigPath));"
        "const source = fs.readFileSync(srcPath, 'utf8');"
        "const output = ts.transpileModule(source, {"
        "  compilerOptions: {"
        "    ...parsed.options,"
        "    module: ts.ModuleKind[moduleKindName],"
        "    noEmit: false,"
        "    declaration: false,"
        "    sourceMap: false,"
        "    inlineSourceMap: false,"
        "    inlineSources: false,"
        "    verbatimModuleSyntax: true"
        "  },"
        "  fileName: srcPath,"
        "  reportDiagnostics: true"
        "});"
        "fs.mkdirSync(path.dirname(outPath), { recursive: true });"
        "fs.writeFileSync(outPath, output.outputText, 'utf8');"
        "const errors = (output.diagnostics || []).filter((d) => d.category === ts.DiagnosticCategory.Error);"
        "if (errors.length > 0) {"
        "  const summary = errors.slice(0, 5)"
        "    .map((d) => ts.flattenDiagnosticMessageText(d.messageText, '\\n'))"
        "    .join('\\n');"
        "  console.error(summary);"
        "}"
    )
    result = subprocess.run(
        [
            str(node_bin),
            "-e",
            script,
            str(typescript_lib),
            str(tsconfig_path),
            str(source_path),
            str(output_path),
            module_kind,
        ],
        cwd=vendor_root,
        env=env,
        capture_output=True,
        text=True,
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        output = "\n".join(part for part in (result.stdout, result.stderr) if part).strip()
        raise RuntimeError(
            f"补齐 OpenClaw dist 产物失败: {source_path} -> {output_path}"
            + (f"\n{output}" if output else "")
        )


def _reconcile_openclaw_dist_from_source(
    node_bin: Path,
    vendor_root: Path,
    dist_root: Path,
    env: dict[str, str],
) -> tuple[int, int]:
    source_root = vendor_root / "src"
    transpiled_count = 0
    copied_count = 0

    for source_path in sorted(source_root.rglob("*")):
        if not source_path.is_file():
            continue
        output_path = _openclaw_dist_output_path(source_root, dist_root, source_path)
        if output_path is None or output_path.exists():
            continue
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if source_path.suffix in _OPENCLAW_TS_SOURCE_SUFFIXES:
            _transpile_openclaw_source_module(node_bin, vendor_root, source_path, output_path, env)
            transpiled_count += 1
        else:
            shutil.copy2(source_path, output_path)
            copied_count += 1

    return transpiled_count, copied_count


_MISSING_MODULE_RE = re.compile(r"Cannot find module ['\"](?P<path>[^'\"]+)['\"]")


def _resolve_missing_module_target(raw_path: str) -> Path | None:
    raw = raw_path.strip()
    if not raw:
        return None
    if raw.startswith("file://"):
        parsed = urlparse(raw)
        raw = unquote(parsed.path)
        if IS_WINDOWS and re.match(r"^/[A-Za-z]:", raw):
            raw = raw[1:]
    try:
        path = Path(raw)
        if path.is_absolute():
            return path
        return path.resolve()
    except Exception:
        return None


def _relative_path_under_root(root: Path, candidate: Path) -> Path | None:
    try:
        return candidate.relative_to(root)
    except ValueError:
        root_norm = str(root).replace("\\", "/").rstrip("/")
        candidate_norm = str(candidate).replace("\\", "/")
        prefix = f"{root_norm}/"
        if candidate_norm.casefold().startswith(prefix.casefold()):
            return Path(candidate_norm[len(prefix):])
        return None


def _find_openclaw_source_candidate(source_root: Path, dist_root: Path, missing_target: Path) -> Path | None:
    relative_path = _relative_path_under_root(dist_root, missing_target)
    if relative_path is None:
        return None

    direct_candidate = source_root / relative_path
    if direct_candidate.exists():
        return direct_candidate

    source_suffixes = (".ts", ".tsx", ".mts", ".cts", ".js", ".mjs", ".cjs", ".json", ".html", ".css", ".hash")
    relative_parent = relative_path.parent
    base_name = relative_path.name
    matched_dist_suffix = next((suffix for suffix in source_suffixes if base_name.endswith(suffix)), None)

    candidate_roots: list[str] = []
    if matched_dist_suffix is not None:
        root_name = base_name[: -len(matched_dist_suffix)]
        if root_name:
            candidate_roots.append(root_name)
            stripped_name = root_name
            while "." in stripped_name:
                stripped_name = stripped_name.rsplit(".", 1)[0]
                if stripped_name:
                    candidate_roots.append(stripped_name)
    else:
        candidate_roots.append(base_name)

    seen: set[Path] = set()
    for root_name in candidate_roots:
        for suffix in source_suffixes:
            candidate = source_root / relative_parent / f"{root_name}{suffix}"
            if candidate in seen:
                continue
            seen.add(candidate)
            if candidate.exists():
                return candidate
    return None


def _hydrate_missing_openclaw_runtime_module(
    node_bin: Path,
    vendor_root: Path,
    dist_root: Path,
    missing_target: Path,
    env: dict[str, str],
) -> bool:
    source_root = vendor_root / "src"
    source_candidate = _find_openclaw_source_candidate(source_root, dist_root, missing_target)
    if source_candidate is None:
        return False

    missing_target.parent.mkdir(parents=True, exist_ok=True)
    if source_candidate.suffix in _OPENCLAW_TS_SOURCE_SUFFIXES:
        _transpile_openclaw_source_module(node_bin, vendor_root, source_candidate, missing_target, env)
    else:
        shutil.copy2(source_candidate, missing_target)
    log(
        "已从源码补齐 OpenClaw runtime 缺失模块: "
        f"{missing_target.relative_to(dist_root).as_posix()} <- {source_candidate.relative_to(vendor_root).as_posix()}"
    )
    return True


def _verify_openclaw_runtime_import(
    node_bin: Path,
    env: dict[str, str],
    runtime_root: Path,
    vendor_root: Path,
) -> None:
    dist_entry = runtime_root / "dist" / "gateway" / "server.js"
    if not dist_entry.exists():
        raise FileNotFoundError(f"OpenClaw Gateway 编译入口不存在: {dist_entry}")

    verify_env = env.copy()
    verify_env["OPENCLAW_GATEWAY_ENTRY_MODE"] = "compiled"
    verify_env["OPENCLAW_GATEWAY_VENDOR_ROOT"] = str(runtime_root)
    verify_script = (
        "import { resolve } from 'node:path';"
        "import { pathToFileURL } from 'node:url';"
        "const target = pathToFileURL(resolve('dist/gateway/server.js')).href;"
        "const mod = await import(target);"
        "if (typeof mod.startGatewayServer !== 'function') {"
        "  throw new Error('startGatewayServer export missing');"
        "}"
        "console.log('openclaw-gateway-dist-import-ok');"
    )
    dist_root = runtime_root / "dist"
    max_hydrate_attempts = 32
    hydrated_count = 0

    for _attempt in range(max_hydrate_attempts + 1):
        result = subprocess.run(
            [
                str(node_bin),
                "--input-type=module",
                "-e",
                verify_script,
            ],
            cwd=runtime_root,
            env=verify_env,
            capture_output=True,
            text=True,
            errors="replace",
            check=False,
        )
        if result.returncode == 0:
            log("OpenClaw Gateway 编译产物导入校验通过")
            return

        output = "\n".join(part for part in (result.stdout, result.stderr) if part).strip()
        missing_match = _MISSING_MODULE_RE.search(output)
        if missing_match:
            missing_target = _resolve_missing_module_target(missing_match.group("path"))
            if (
                missing_target is not None
                and _hydrate_missing_openclaw_runtime_module(
                    node_bin,
                    vendor_root,
                    dist_root,
                    missing_target,
                    env,
                )
            ):
                hydrated_count += 1
                continue
            if missing_target is not None:
                log(f"无法将缺失的 OpenClaw dist 模块映射回源码: {missing_target}")

        diag_path = _write_openclaw_import_diagnostics(output) if output else None
        if diag_path:
            log(f"OpenClaw Gateway 编译产物导入校验失败，日志已写入 {diag_path}")
            _log_openclaw_tsc_excerpt(output)
        raise RuntimeError("OpenClaw Gateway 编译产物导入校验失败")

    raise RuntimeError(f"OpenClaw Gateway 编译产物导入校验失败（已补齐 {hydrated_count} 个缺失模块后仍未通过）")


def download_python_runtime() -> Path:
    """下载最小 Python standalone 运行时，返回本地缓存路径"""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    archive_path = CACHE_DIR / PYTHON_ARCHIVE
    if archive_path.exists():
        log(f"使用缓存 Python standalone 包: {archive_path}")
        return archive_path
    log(f"下载 Python standalone {PYTHON_RUNTIME_VERSION}: {PYTHON_DIST_URL}")
    urllib.request.urlretrieve(PYTHON_DIST_URL, str(archive_path))
    _verify_archive_sha256(archive_path)
    log(f"Python standalone 下载完成: {archive_path} ({archive_path.stat().st_size / 1024 / 1024:.1f} MB)")
    return archive_path


def _write_unix_python_shim(path: Path, target_name: str) -> None:
    path.write_text(
        "#!/bin/sh\n"
        'SCRIPT_DIR="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"\n'
        f'exec "$SCRIPT_DIR/{target_name}" "$@"\n',
        encoding="utf-8",
    )
    path.chmod(0o755)


def _write_unix_pip_shim(path: Path) -> None:
    path.write_text(
        "#!/bin/sh\n"
        'SCRIPT_DIR="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"\n'
        'exec "$SCRIPT_DIR/python" -m pip "$@"\n',
        encoding="utf-8",
    )
    path.chmod(0o755)


def _write_windows_pip_shim(path: Path) -> None:
    path.write_text("@echo off\r\n\"%~dp0python.exe\" -m pip %*\r\n", encoding="utf-8")


def _find_extracted_python_binary() -> Path:
    candidates = []
    if IS_WINDOWS:
        candidates.extend(
            [
                PYTHON_RUNTIME_DIR / "python.exe",
                PYTHON_RUNTIME_DIR / "bin" / "python.exe",
            ]
        )
    else:
        candidates.extend(
            [
                PYTHON_RUNTIME_DIR / "bin" / "python",
                PYTHON_RUNTIME_DIR / "bin" / f"python{PYTHON_RUNTIME_VERSION[:4]}",
                PYTHON_RUNTIME_DIR / "bin" / "python3",
            ]
        )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(f"Python standalone 解压后未找到解释器: {PYTHON_RUNTIME_DIR}")


def _path_size_bytes(path: Path) -> int:
    if not path.exists() and not path.is_symlink():
        return 0
    if path.is_file() or path.is_symlink():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    total = 0
    for candidate in path.rglob("*"):
        try:
            if candidate.is_file() and not candidate.is_symlink():
                total += candidate.stat().st_size
        except OSError:
            continue
    return total


def _remove_path(path: Path) -> bool:
    if not path.exists() and not path.is_symlink():
        return False
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
        return True
    path.unlink()
    return True


def _python_stdlib_roots() -> list[Path]:
    roots: list[Path] = []
    for candidate in sorted(PYTHON_RUNTIME_DIR.glob("lib/python3.*")):
        if candidate.is_dir():
            roots.append(candidate)
    lib_dir = PYTHON_RUNTIME_DIR / "Lib"
    if lib_dir.is_dir():
        roots.append(lib_dir)
    return roots


def _materialize_python_shims() -> None:
    python_bin = _find_extracted_python_binary()
    if IS_WINDOWS:
        root = python_bin.parent
        pip_cmd = root / "pip.cmd"
        pip3_cmd = root / "pip3.cmd"
        if not pip_cmd.exists():
            _write_windows_pip_shim(pip_cmd)
        if not pip3_cmd.exists():
            _write_windows_pip_shim(pip3_cmd)
        python3_exe = root / "python3.exe"
        if not python3_exe.exists():
            shutil.copy2(python_bin, python3_exe)
        return

    bin_dir = python_bin.parent
    python_name = python_bin.name
    for shim_name in ("python", "python3"):
        shim_path = bin_dir / shim_name
        if shim_path.exists():
            continue
        _write_unix_python_shim(shim_path, python_name)
    for shim_name in ("pip", "pip3"):
        shim_path = bin_dir / shim_name
        if shim_path.exists():
            continue
        _write_unix_pip_shim(shim_path)


def _prune_python_runtime() -> None:
    """裁剪 Python standalone 中与 MCP 运行无关的开发/GUI组件。"""
    before_bytes = _path_size_bytes(PYTHON_RUNTIME_DIR)
    removed_paths: list[str] = []

    def drop(path: Path) -> None:
        if _remove_path(path):
            removed_paths.append(path.relative_to(PYTHON_RUNTIME_DIR).as_posix())

    for rel in ("include", "share", "lib/pkgconfig"):
        drop(PYTHON_RUNTIME_DIR / rel)

    bin_dir = _find_extracted_python_binary().parent
    for pattern in ("2to3*", "idle3*", "pydoc3*", "python*-config"):
        for candidate in sorted(bin_dir.glob(pattern)):
            drop(candidate)

    for pattern in (
        "lib/libtcl*",
        "lib/libtk*",
        "lib/tcl*",
        "lib/tk*",
        "lib/itcl*",
        "lib/thread*",
        "DLLs/tcl*.dll",
        "DLLs/tk*.dll",
    ):
        for candidate in sorted(PYTHON_RUNTIME_DIR.glob(pattern)):
            drop(candidate)

    for stdlib_root in _python_stdlib_roots():
        for rel in (
            "idlelib",
            "tkinter",
            "turtledemo",
            "__phello__",
            "ensurepip",
            "lib2to3",
            "pydoc_data",
            "test",
            "tests",
            "turtle.py",
            "pydoc.py",
        ):
            candidate = stdlib_root / rel
            if _remove_path(candidate):
                removed_paths.append(candidate.relative_to(PYTHON_RUNTIME_DIR).as_posix())
        for candidate in sorted(stdlib_root.glob("config-*")):
            if _remove_path(candidate):
                removed_paths.append(candidate.relative_to(PYTHON_RUNTIME_DIR).as_posix())
        lib_dynload = stdlib_root / "lib-dynload"
        if lib_dynload.is_dir():
            for pattern in ("_tkinter*", "_test*", "_ctypes_test*", "xxlimited*"):
                for candidate in sorted(lib_dynload.glob(pattern)):
                    if _remove_path(candidate):
                        removed_paths.append(candidate.relative_to(PYTHON_RUNTIME_DIR).as_posix())
        site_packages = stdlib_root / "site-packages"
        if site_packages.is_dir():
            for rel in ("pkg_resources/tests", "pkg_resources/api_tests.txt", "setuptools/tests"):
                candidate = site_packages / rel
                if _remove_path(candidate):
                    removed_paths.append(candidate.relative_to(PYTHON_RUNTIME_DIR).as_posix())

    after_bytes = _path_size_bytes(PYTHON_RUNTIME_DIR)
    removed_mb = max(before_bytes - after_bytes, 0) / 1024 / 1024
    log(
        "Python MCP 运行时裁剪完成: "
        f"-{removed_mb:.1f} MB"
        + (f" ({len(removed_paths)} 项)" if removed_paths else " (无可裁剪项)")
    )


def extract_python_runtime(archive_path: Path) -> None:
    """解压 Python standalone 到 runtime/python/"""
    if PYTHON_RUNTIME_DIR.exists():
        log(f"清理旧 Python 运行时: {PYTHON_RUNTIME_DIR}")
        shutil.rmtree(PYTHON_RUNTIME_DIR)

    PYTHON_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    log(f"解压 Python standalone 到: {PYTHON_RUNTIME_DIR}")
    _extract_prefixed_tarball(archive_path, "python/", PYTHON_RUNTIME_DIR)
    _materialize_python_shims()
    _prune_python_runtime()

    python_bin = _find_extracted_python_binary()
    if not python_bin.exists():
        raise FileNotFoundError(f"解压后缺少 python: {python_bin}")
    log(f"Python standalone 运行时准备完成: {PYTHON_RUNTIME_DIR}")


_RELATIVE_TS_IMPORT_RE = re.compile(r'(?P<quote>["\'])(?P<path>\.{1,2}/[^"\']+?)\.tsx?(?P=quote)')
_RELATIVE_DIST_IMPORT_RE = re.compile(r'(?P<quote>["\'])(?P<path>\.{1,2}/[^"\']+\.(?:js|mjs|cjs|json|html|css|hash))(?P=quote)')


def _rewrite_openclaw_dist_import_suffixes(dist_root: Path) -> None:
    """将编译产物里残留的相对 .ts/.tsx import 后缀改写为 .js。"""
    changed_files = 0
    changed_refs = 0

    for pattern in ("*.js", "*.mjs", "*.cjs"):
        for candidate in dist_root.rglob(pattern):
            try:
                content = candidate.read_text(encoding="utf-8")
            except Exception:
                continue

            original = content
            rewritten_lines: list[str] = []
            for line in content.splitlines(keepends=True):
                if "import" not in line and "export" not in line:
                    rewritten_lines.append(line)
                    continue
                line, count = _RELATIVE_TS_IMPORT_RE.subn(
                    lambda match: f"{match.group('quote')}{match.group('path')}.js{match.group('quote')}",
                    line,
                )
                changed_refs += count
                rewritten_lines.append(line)

            updated = "".join(rewritten_lines)
            if updated == original:
                continue

            candidate.write_text(updated, encoding="utf-8")
            changed_files += 1

    log(f"OpenClaw dist import 后处理完成: {changed_files} 个文件, {changed_refs} 处引用")


def _sync_openclaw_runtime_sidefiles(vendor_root: Path) -> None:
    """同步 OpenClaw 编译运行所需的 side files。"""
    dist_root = OPENCLAW_RUNTIME_DIR / "dist"
    if dist_root.exists():
        _rewrite_openclaw_dist_import_suffixes(dist_root)

    shared_assets_src = vendor_root / "apps" / "shared" / "OpenClawKit"
    if shared_assets_src.exists():
        target_dir = OPENCLAW_RUNTIME_DIR / "apps" / "shared" / "OpenClawKit"
        shutil.copytree(shared_assets_src, target_dir, dirs_exist_ok=True)
        log(f"已复制 OpenClawKit 共享资源 -> {target_dir}")

    for rel_path in ("package.json", "openclaw.mjs", "LICENSE"):
        source_path = vendor_root / rel_path
        if source_path.exists():
            shutil.copy2(source_path, OPENCLAW_RUNTIME_DIR / rel_path)

    gateway_script_src = PROJECT_ROOT / "agentserver" / "openclaw" / "gateway_start.mjs"
    if gateway_script_src.exists():
        shutil.copy2(gateway_script_src, OPENCLAW_RUNTIME_DIR / "gateway_start.mjs")
        log(f"已复制 gateway_start.mjs -> {OPENCLAW_RUNTIME_DIR / 'gateway_start.mjs'}")


def _prune_openclaw_runtime_dependencies(env: dict[str, str]) -> None:
    package_json = OPENCLAW_RUNTIME_DIR / "package.json"
    node_modules_dir = OPENCLAW_RUNTIME_DIR / "node_modules"
    if not package_json.exists() or not node_modules_dir.exists():
        return

    before_bytes = _path_size_bytes(node_modules_dir)
    log("裁剪 OpenClaw 运行时 devDependencies（npm prune --omit=dev）...")
    run(
        _runtime_npm_command(
            "prune",
            "--omit=dev",
            "--prefix",
            str(OPENCLAW_RUNTIME_DIR),
        ),
        cwd=OPENCLAW_RUNTIME_DIR,
        env=env,
    )
    after_bytes = _path_size_bytes(node_modules_dir)
    removed_mb = max(before_bytes - after_bytes, 0) / 1024 / 1024
    log(f"OpenClaw 运行时依赖裁剪完成: -{removed_mb:.1f} MB")


def _hydrate_openclaw_dist_missing_imports(
    node_bin: Path,
    vendor_root: Path,
    dist_root: Path,
    env: dict[str, str],
) -> int:
    hydrated_count = 0
    max_passes = 8

    for _pass in range(max_passes):
        changed = 0
        for pattern in ("*.js", "*.mjs", "*.cjs"):
            for candidate in dist_root.rglob(pattern):
                try:
                    content = candidate.read_text(encoding="utf-8")
                except Exception:
                    continue

                for match in _RELATIVE_DIST_IMPORT_RE.finditer(content):
                    target = (candidate.parent / match.group("path")).resolve(strict=False)
                    if target.exists():
                        continue
                    if _hydrate_missing_openclaw_runtime_module(
                        node_bin,
                        vendor_root,
                        dist_root,
                        target,
                        env,
                    ):
                        hydrated_count += 1
                        changed += 1
        if changed == 0:
            break

    return hydrated_count


def _write_openclaw_tsc_diagnostics(output: str) -> Path | None:
    if not output.strip():
        return None
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    diag_path = CACHE_DIR / "openclaw-tsc.log"
    diag_path.write_text(output, encoding="utf-8")
    return diag_path


def _log_openclaw_tsc_excerpt(output: str, limit: int = 20) -> None:
    lines = [line.rstrip() for line in output.splitlines() if line.strip()]
    if not lines:
        return
    for line in lines[:limit]:
        log(f"[openclaw-tsc] {line}")
    remaining = len(lines) - limit
    if remaining > 0:
        log(f"[openclaw-tsc] ... 其余 {remaining} 行已省略")


def preinstall_openclaw(force: bool = False) -> None:
    """从 vendor/openclaw 源码编译完整 dist，并准备打包运行时。"""
    vendor_root = PROJECT_ROOT / "vendor" / "openclaw"
    if not vendor_root.exists():
        raise FileNotFoundError(f"vendor/openclaw 不存在: {vendor_root}")

    node_bin = NODE_RUNTIME_DIR / NODE_BIN
    if not node_bin.exists():
        raise FileNotFoundError(f"node 不存在: {node_bin}")

    dist_marker = OPENCLAW_RUNTIME_DIR / "dist" / "gateway" / "server.js"
    node_modules_marker = OPENCLAW_RUNTIME_DIR / "node_modules"
    gateway_marker = PROJECT_ROOT / "agentserver" / "openclaw" / "gateway_start.mjs"
    if not force and dist_marker.exists() and node_modules_marker.exists() and gateway_marker.exists():
        _verify_openclaw_runtime_import(
            node_bin,
            _apply_runtime_npm_env(os.environ.copy()),
            OPENCLAW_RUNTIME_DIR,
            vendor_root,
        )
        log("vendor/openclaw 已就绪，跳过重建")
        return

    if OPENCLAW_RUNTIME_DIR.exists():
        log(f"清理旧 OpenClaw 运行时: {OPENCLAW_RUNTIME_DIR}")
        shutil.rmtree(OPENCLAW_RUNTIME_DIR)
    OPENCLAW_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    if IS_WINDOWS:
        env["PATH"] = f"{NODE_RUNTIME_DIR}{os.pathsep}{env.get('PATH', '')}"
    else:
        node_bin_dir = NODE_RUNTIME_DIR / "bin"
        env["PATH"] = f"{node_bin_dir}{os.pathsep}{env.get('PATH', '')}"
    env = _apply_runtime_npm_env(env)

    _install_openclaw_vendor_dependencies(vendor_root, env, force=force)

    runtime_dist_dir = OPENCLAW_RUNTIME_DIR / "dist"
    tsc_cli = _find_vendor_typescript_cli(vendor_root)
    compile_env = env.copy()
    compile_env["NODE_OPTIONS"] = "--max-old-space-size=4096"

    log("编译 vendor/openclaw 源码...")
    result = subprocess.run(
        [
            str(node_bin),
            str(tsc_cli),
            "-p",
            "tsconfig.naga.json",
            "--outDir",
            str(runtime_dist_dir),
        ],
        cwd=vendor_root,
        env=compile_env,
        capture_output=True,
        text=True,
        errors="replace",
        check=False,
    )
    output = "\n".join(part for part in (result.stdout, result.stderr) if part).strip()
    transpiled_count, copied_count = _reconcile_openclaw_dist_from_source(node_bin, vendor_root, runtime_dist_dir, env)
    log(
        "OpenClaw runtime dist 源码对齐完成: "
        f"{transpiled_count} 个源码转译, {copied_count} 个资源复制"
    )

    diag_path = _write_openclaw_tsc_diagnostics(output) if output else None
    if result.returncode != 0:
        if dist_marker.exists():
            warning = "警告：vendor/openclaw 编译返回非零退出码 "
            warning += f"{result.returncode}，但 runtime dist 已生成，继续打包"
            if diag_path:
                warning += f"；诊断日志已写入 {diag_path}"
            log(warning)
        else:
            if diag_path:
                log(f"OpenClaw TypeScript 编译失败，诊断日志已写入 {diag_path}")
                _log_openclaw_tsc_excerpt(output)
            raise RuntimeError("OpenClaw runtime dist 编译失败")

    log("复制 OpenClaw 依赖到运行时目录...")
    shutil.copytree(
        vendor_root / "node_modules",
        OPENCLAW_RUNTIME_DIR / "node_modules",
        dirs_exist_ok=True,
        symlinks=not IS_WINDOWS,
    )
    _sync_openclaw_runtime_sidefiles(vendor_root)
    _prune_openclaw_runtime_dependencies(env)
    prehydrated_count = _hydrate_openclaw_dist_missing_imports(node_bin, vendor_root, runtime_dist_dir, env)
    if prehydrated_count > 0:
        log(f"OpenClaw dist 缺失依赖预补齐完成: {prehydrated_count} 个模块")

    log("校验 OpenClaw 编译产物入口...")
    _verify_openclaw_runtime_import(node_bin, env, OPENCLAW_RUNTIME_DIR, vendor_root)

    log(f"OpenClaw 运行时准备完成（从源码编译 dist）: {OPENCLAW_RUNTIME_DIR}")


def _agent_browser_bin_name() -> str:
    return "agent-browser.cmd" if IS_WINDOWS else "agent-browser"


def _runtime_node_path_prefix() -> str:
    return str(NODE_RUNTIME_DIR if IS_WINDOWS else NODE_RUNTIME_DIR / "bin")


def _find_playwright_core_cli(install_root: Path) -> Path | None:
    candidates = [
        install_root / "node_modules" / "playwright-core" / "cli.js",
        install_root / "node_modules" / "agent-browser" / "node_modules" / "playwright-core" / "cli.js",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _agent_browser_browser_cache_dirs(install_root: Path) -> list[Path]:
    return [
        install_root / "node_modules" / "playwright-core" / ".local-browsers",
        install_root / "node_modules" / "agent-browser" / "node_modules" / "playwright-core" / ".local-browsers",
    ]


def _has_agent_browser_native_bundle(install_root: Path) -> bool:
    bin_dir = install_root / "node_modules" / "agent-browser" / "bin"
    if not bin_dir.exists():
        return False
    for candidate in bin_dir.iterdir():
        if candidate.is_file() and candidate.name.startswith("agent-browser-") and candidate.name != "agent-browser.js":
            return True
    return False


def _has_agent_browser_browser_cache(install_root: Path) -> bool:
    for candidate in _agent_browser_browser_cache_dirs(install_root):
        if candidate.exists():
            try:
                if any(candidate.iterdir()):
                    return True
            except Exception:
                return True
    return False


def _remove_agent_browser_browser_cache(install_root: Path) -> int:
    removed = 0
    for candidate in _agent_browser_browser_cache_dirs(install_root):
        if candidate.exists():
            shutil.rmtree(candidate, ignore_errors=True)
            removed += 1
    return removed


def preinstall_agent_browser(force: bool = False) -> None:
    """在外部 runtime/openclaw 中预装 agent-browser，避免 PyInstaller 冻结浏览器二进制。"""
    node_bin = NODE_RUNTIME_DIR / NODE_BIN
    if not node_bin.exists():
        raise FileNotFoundError(f"node 不存在: {node_bin}")

    OPENCLAW_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    agent_browser_cmd = OPENCLAW_RUNTIME_DIR / "node_modules" / ".bin" / _agent_browser_bin_name()
    agent_browser_pkg = OPENCLAW_RUNTIME_DIR / "node_modules" / "agent-browser" / "package.json"

    installed_version: str | None = None
    if agent_browser_pkg.exists():
        try:
            installed_version = json.loads(agent_browser_pkg.read_text(encoding="utf-8")).get("version")
        except Exception:
            installed_version = None

    if not force and agent_browser_cmd.exists() and (
        _has_agent_browser_browser_cache(OPENCLAW_RUNTIME_DIR) or _has_agent_browser_native_bundle(OPENCLAW_RUNTIME_DIR)
    ):
        if _has_agent_browser_native_bundle(OPENCLAW_RUNTIME_DIR):
            removed = _remove_agent_browser_browser_cache(OPENCLAW_RUNTIME_DIR)
            if removed > 0:
                log(f"已清理 agent-browser 浏览器缓存目录: {removed} 个")
        log(f"agent-browser 已预装: {installed_version or 'unknown'}，跳过安装")
        return
    if agent_browser_cmd.exists() and not (
        _has_agent_browser_browser_cache(OPENCLAW_RUNTIME_DIR) or _has_agent_browser_native_bundle(OPENCLAW_RUNTIME_DIR)
    ):
        log("检测到 agent-browser 命令已存在，但浏览器缓存缺失，继续补装 chromium")

    env = os.environ.copy()
    env["PATH"] = f"{_runtime_node_path_prefix()}{os.pathsep}{env.get('PATH', '')}"
    env["NPM_CONFIG_AUDIT"] = "false"
    env["NPM_CONFIG_FUND"] = "false"
    env["NPM_CONFIG_GLOBAL"] = "false"
    env = _apply_runtime_npm_env(env)
    # 将浏览器二进制放进 node_modules，避免首次运行再下载到用户目录。
    env["PLAYWRIGHT_BROWSERS_PATH"] = "0"
    env["CI"] = "1"

    log(f"预装 Agent Browser（npm install {AGENT_BROWSER_NPM_SPEC}）...")
    run(
        _runtime_npm_command(
            "install",
            AGENT_BROWSER_NPM_SPEC,
            "--global=false",
            "--location=project",
            "--prefix",
            str(OPENCLAW_RUNTIME_DIR),
        ),
        cwd=OPENCLAW_RUNTIME_DIR,
        env=env,
    )

    if not agent_browser_cmd.exists():
        raise FileNotFoundError(f"agent-browser 预装失败，未找到命令: {agent_browser_cmd}")
    if _has_agent_browser_native_bundle(OPENCLAW_RUNTIME_DIR):
        removed = _remove_agent_browser_browser_cache(OPENCLAW_RUNTIME_DIR)
        if removed > 0:
            log(f"已清理 agent-browser 浏览器缓存目录: {removed} 个")
        log("agent-browser 当前版本自带原生浏览器二进制，跳过 playwright-core 预下载")
        log(f"Agent Browser 预装完成: {agent_browser_cmd}")
        return

    playwright_core_cli = _find_playwright_core_cli(OPENCLAW_RUNTIME_DIR)
    if playwright_core_cli is None:
        raise FileNotFoundError(f"playwright-core cli 缺失，无法预装浏览器内核: {OPENCLAW_RUNTIME_DIR / 'node_modules'}")

    log("预下载 Agent Browser 浏览器依赖（playwright-core install chromium）...")
    run(
        [
            str(node_bin),
            str(playwright_core_cli),
            "install",
            "chromium",
        ],
        cwd=OPENCLAW_RUNTIME_DIR,
        env=env,
    )

    browsers_dirs = [str(path) for path in _agent_browser_browser_cache_dirs(OPENCLAW_RUNTIME_DIR) if path.exists()]
    if browsers_dirs:
        log(f"Agent Browser 浏览器缓存已写入: {', '.join(browsers_dirs)}")
    elif not (
        _has_agent_browser_browser_cache(OPENCLAW_RUNTIME_DIR) or _has_agent_browser_native_bundle(OPENCLAW_RUNTIME_DIR)
    ):
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
    _verify_archive_sha256(archive_path)
    log(f"uv 下载完成: {archive_path} ({archive_path.stat().st_size / 1024 / 1024:.1f} MB)")
    return archive_path


def extract_uv_runtime(archive_path: Path) -> None:
    """解压 uv standalone 到 runtime/uv/"""
    if UV_RUNTIME_DIR.exists():
        # 检查是否已解压
        ext = ".exe" if IS_WINDOWS else ""
        if (UV_RUNTIME_DIR / f"uv{ext}").exists():
            log("uv 运行时已存在，跳过解压")
            return
        shutil.rmtree(UV_RUNTIME_DIR)

    UV_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    log(f"解压 uv 到 {UV_RUNTIME_DIR}")

    if str(archive_path).endswith(".zip"):
        with zipfile.ZipFile(archive_path, "r") as zf:
            for member in zf.infolist():
                fname = Path(member.filename).name
                if not fname or member.is_dir():
                    continue
                target = UV_RUNTIME_DIR / fname
                with zf.open(member) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
    else:
        import tarfile
        with tarfile.open(archive_path) as tf:
            for member in tf.getmembers():
                if not member.isfile():
                    continue
                fname = Path(member.name).name
                if not fname:
                    continue
                member.name = fname
                tf.extract(member, UV_RUNTIME_DIR)
                extracted = UV_RUNTIME_DIR / fname
                if not IS_WINDOWS:
                    extracted.chmod(0o755)

    ext = ".exe" if IS_WINDOWS else ""
    if not (UV_RUNTIME_DIR / f"uv{ext}").exists():
        raise FileNotFoundError(f"uv 解压后未找到 uv{ext}")
    log(f"uv 运行时准备完成: {UV_RUNTIME_DIR}")


def prepare_openclaw_runtime(force: bool = False) -> None:
    """准备嵌入式运行时：共享 Node.js + Python standalone + OpenClaw/Agent Browser + uv"""
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    prepare_node_runtime()
    python_archive = download_python_runtime()
    extract_python_runtime(python_archive)
    preinstall_openclaw(force=force)
    preinstall_agent_browser(force=force)
    # 下载并解压 uv standalone（用于 MCP uvx 服务）
    uv_archive = download_uv_runtime()
    extract_uv_runtime(uv_archive)
    log("嵌入式运行时准备完成（已预装 Node.js + Python + OpenClaw + Agent Browser + uv）")


# ============ Step 4: PyInstaller 编译后端 ============


def build_backend() -> None:
    """用 PyInstaller 编译 Python 后端"""
    if not SPEC_FILE.exists():
        raise FileNotFoundError(f"spec 文件不存在: {SPEC_FILE}")

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
    backend_bin = BACKEND_DIST_DIR / "naga-backend" / f"naga-backend{BACKEND_EXT}"
    if not backend_bin.exists():
        raise FileNotFoundError(f"后端编译产物缺失: {backend_bin}")
    log(f"后端编译完成: {backend_bin}")


# ============ Step 5: Electron 前端构建 + 打包 ============


def build_frontend(debug: bool = False) -> None:
    """构建 Vue 前端 + Electron 打包。

    debug=True 时（仅 Windows）会注入 electron-builder metadata，
    让安装后的 Electron 主进程以"调试控制台模式"启动后端。
    """
    # 同步版本号 pyproject.toml → package.json
    sync_frontend_version()

    # 安装前端依赖
    node_modules = FRONTEND_DIR / "node_modules"
    if not node_modules.exists():
        log("安装前端依赖...")
        run(["npm", "install"], cwd=FRONTEND_DIR)

    dist_script = f"dist:{PLATFORM_TAG}"

    if debug and IS_WINDOWS:
        log("调试构建模式：已启用后端日志终端（安装后会弹 cmd 实时输出）")
        run(
            [
                "npm",
                "run",
                dist_script,
                "--",
                "-c.extraMetadata.nagaDebugConsole=true",
            ],
            cwd=FRONTEND_DIR,
        )
    else:
        if debug and not IS_WINDOWS:
            log("注意：--debug 调试控制台仅在 Windows 上生效，已忽略")
        run(["npm", "run", dist_script], cwd=FRONTEND_DIR)

    log("Electron 打包完成")


# ============ Step 6: 汇总 ============


def print_summary() -> None:
    """打印构建产物信息"""
    safe_print()
    safe_print("=" * 50)
    safe_print("  构建完成!")
    safe_print("=" * 50)

    # 后端产物
    backend_dir = BACKEND_DIST_DIR / "naga-backend"
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
        for f in release_dir.glob(INSTALLER_GLOB):
            log(f"安装包: {f}  ({f.stat().st_size / 1024 / 1024:.0f} MB)")


# ============ 主入口 ============


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="NagaAgent 跨平台构建脚本")
    parser.add_argument(
        "--skip-openclaw",
        action="store_true",
        help="跳过 OpenClaw 运行时准备（Node 便携版 + OpenClaw 预装）",
    )
    parser.add_argument("--backend-only", action="store_true", help="仅编译后端，不打包 Electron")
    parser.add_argument(
        "--force-openclaw",
        action="store_true",
        help="强制重新安装 OpenClaw（先删除旧安装）",
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
