#!/usr/bin/env python3
"""doctor.py — 陆墨一键健康自检（卷186-B2）。

安装后第一步：`python scripts/doctor.py`
快速模式（跳过前端 build）：`python scripts/doctor.py --quick`

只查不修：每项给出 ✅/⚠️/❌ + 修复建议。只用标准库。

检查项（对齐 README「快速开始」）：
  1. Python 版本（要求 >=3.12,<3.13，见 pyproject.toml requires-python）
  2. uv 可用（后端一律 uv sync，不要裸 pip install）
  3. Node / npm（前端构建需要）
  4. 关键依赖可导入（fastapi / uvicorn / pydantic / httpx / yaml / requests）
  5. .env.local 存在且不含占位符（change-me）
  6. 数据目录可写
  7. 前端依赖与产物（--quick 只查存在性；完整模式加跑 npm run build）
"""
from __future__ import annotations

import argparse
import importlib
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OK, WARN, FAIL = "✅", "⚠️", "❌"

# pyproject.toml requires-python = ">=3.12,<3.13"
PY_OK = (3, 12) <= sys.version_info[:2] < (3, 13)

# 后端核心依赖（pyproject dependencies 的关键子集；导入名 != 包名的写映射）
KEY_DEPS = [
    ("fastapi", "fastapi"),
    ("uvicorn", "uvicorn"),
    ("pydantic", "pydantic"),
    ("httpx", "httpx"),
    ("yaml", "PyYAML"),
    ("requests", "requests"),
]

PLACEHOLDER_HINTS = ("change-me", "changeme", "your-api-key", "<", "TODO")


def _node_ver() -> tuple[int, int] | None:
    exe = shutil.which("node")
    if not exe:
        return None
    try:
        out = subprocess.run([exe, "-v"], capture_output=True, text=True,
                             timeout=10).stdout.strip()  # e.g. v22.12.0
        parts = out.lstrip("v").split(".")
        return (int(parts[0]), int(parts[1]))
    except (ValueError, IndexError, subprocess.TimeoutExpired):
        return None


def check_python() -> tuple[str, str, str]:
    v = sys.version_info
    if PY_OK:
        return OK, f"Python {v.major}.{v.minor}.{v.micro}", ""
    if (3, 13) <= v[:2]:
        return (FAIL, f"Python {v.major}.{v.minor}（要求 >=3.12,<3.13）",
                "pyproject.toml 的 requires-python 锁在 3.12——请用 uv 装对应解释器："
                "`uv python install 3.12`")
    return (FAIL, f"Python {v.major}.{v.minor}（要求 >=3.12,<3.13）",
            "版本过旧——`uv python install 3.12` 后 `uv sync`")


def check_uv() -> tuple[str, str, str]:
    p = shutil.which("uv")
    if p:
        return OK, f"uv 可用（{p}）", ""
    return (FAIL, "未找到 uv",
            "README 快速开始：后端一律 `uv sync`，不要用裸 pip install。"
            "安装：https://docs.astral.sh/uv/")


def check_node() -> tuple[str, str, str]:
    v = _node_ver()
    if v is None:
        return (WARN, "未找到 node", "前端构建需要 Node ≥18；纯后端使用可忽略此项")
    if v >= (18, 0):
        return OK, f"node {'.'.join(map(str, v))}", ""
    return (WARN, f"node {'.'.join(map(str, v))}（建议 ≥18）",
            "升级 Node：https://nodejs.org/")


def check_deps() -> tuple[str, str, str]:
    missing = []
    for mod, pkg in KEY_DEPS:
        try:
            importlib.import_module(mod)
        except Exception:
            missing.append(pkg)
    if not missing:
        n = len(KEY_DEPS)
        return OK, f"核心依赖 {n}/{n} 可导入", ""
    return (FAIL, f"缺依赖：{', '.join(missing)}",
            "在仓库根跑 `uv sync`（判例/论文 PDF→MD 再加 `--extra pdf2md`）；"
            "若你是用系统 Python 跑的本脚本，请改用 `.venv/Scripts/python.exe scripts/doctor.py`")


def check_env_local() -> tuple[str, str, str]:
    p = ROOT / ".env.local"
    if not p.exists():
        return (FAIL, ".env.local 不存在",
                "MCP 安全配置缺失。复制模板：`cp .env .env.local` 后填入实际值"
                "（尤其 MCP_API_KEY，占位符是 change-me-…）")
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except OSError as e:
        return FAIL, f".env.local 不可读：{e}", "检查文件权限"
    hits = [ln.split("=")[0].strip() for ln in text.splitlines()
            if "=" in ln and not ln.strip().startswith("#")
            and any(h in ln.split("=", 1)[1] for h in PLACEHOLDER_HINTS)]
    if hits:
        return (WARN, f".env.local 仍含占位符：{', '.join(hits[:4])}"
                      + ("…" if len(hits) > 4 else ""),
                "编辑 .env.local 把这些值换成真实值（MCP_API_KEY 建议随机 32 字符）")
    return OK, ".env.local 存在且无占位符", ""


def check_data_writable() -> tuple[str, str, str]:
    data = ROOT / "data"
    try:
        data.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=data, prefix="doctor_", delete=True):
            pass
        return OK, f"数据目录可写（{data}）", ""
    except OSError as e:
        return (FAIL, f"数据目录不可写：{e}",
                "检查磁盘空间与目录权限（杀毒软件/受控文件夹访问也可能拦截）")


def check_frontend(quick: bool) -> tuple[str, str, str]:
    fe = ROOT / "frontend"
    if not fe.exists():
        return WARN, "无 frontend/ 目录", "纯后端部署可忽略"
    nm = fe / "node_modules"
    dist = fe / "dist"
    if not nm.exists():
        return (FAIL, "frontend/node_modules 缺失",
                "前端还没装依赖：`cd frontend && npm install`")
    if not (dist / "index.html").exists():
        if quick:
            return (WARN, "frontend/dist 缺失（--quick 未构建）",
                    "跑 `cd frontend && npm install && npm run build`")
        # 完整模式：现场构建
        npm = shutil.which("npm") or shutil.which("npm.cmd")
        if not npm:
            return FAIL, "找不到 npm", "装 Node 后重试（https://nodejs.org/）"
        print(f"   （npm run build 中，目录 {fe}…）")
        try:
            r = subprocess.run([npm, "run", "build"], cwd=fe, timeout=600,
                               capture_output=True, text=True, shell=False)
        except subprocess.TimeoutExpired:
            return WARN, "前端 build 超时（>10min）", "手动跑 `npm run build` 看卡在哪一步"
        if r.returncode == 0:
            return OK, "前端 build 成功", ""
        tail = (r.stdout or r.stderr or "").strip().splitlines()[-3:]
        return (FAIL, "前端 build 失败", "；".join(tail) or "查看上方输出")
    return OK, "前端依赖与构建产物齐全", ""


def main() -> int:
    ap = argparse.ArgumentParser(description="陆墨一键健康自检")
    ap.add_argument("--quick", action="store_true", help="跳过前端 build（只查存在性）")
    args = ap.parse_args()

    print("陆墨 · 健康自检（doctor）")
    print("=" * 56)
    checks = [
        check_python, check_uv, check_node, check_deps,
        check_env_local, check_data_writable,
        lambda: check_frontend(args.quick),
    ]
    n_fail = n_warn = 0
    for fn in checks:
        status, detail, hint = fn()
        if status is FAIL:
            n_fail += 1
        elif status is WARN:
            n_warn += 1
        print(f"{status} {detail}")
        if hint:
            print(f"   ↳ {hint}")
    print("=" * 56)
    if n_fail == 0 and n_warn == 0:
        print("全部通过，可以按 README「快速开始」继续。")
        return 0
    print(f"结果：{n_fail} 个 ❌ / {n_warn} 个 ⚠️"
          + ("——先修 ❌ 项再继续安装。" if n_fail else "——⚠️ 项按需处理。"))
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
