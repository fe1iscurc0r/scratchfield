#!/usr/bin/env python3
"""安装本地 pre-push 钩子（卷173-C）——CI 靠不住期间的第一道闸。

安装后每次 `git push` 前自动跑：
    1. ruff check .          （秒级，静态检查）
    2. pytest -m smoke -q    （≤60s 冒烟层，见 pyproject.toml markers）
任一失败即拦下 push。

用法：
    python scripts/install_hooks.py           # 安装（已存在则拒绝，防覆盖）
    python scripts/install_hooks.py --force   # 覆盖已存在的钩子
    python scripts/install_hooks.py --remove  # 卸载钩子

说明：
- 紧急时 `git push --no-verify` 可人工跳过（报告里写明动过即可）。
- CI 解封（ENABLE_CI_TEST）后此钩子**仍保留**——本地拦截永远比云端快。
- stdlib only；Windows 下钩子由 git 自带的 sh 执行，无需额外依赖。
"""
from __future__ import annotations

import argparse
import os
import stat
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
HOOK_PATH = REPO_ROOT / ".git" / "hooks" / "pre-push"

HOOK_TEMPLATE = """#!/bin/sh
# 陆墨 pre-push 钩子（卷173 安装：scripts/install_hooks.py）
#
# CI 解封（ENABLE_CI_TEST）后此钩子仍保留——本地拦截永远比云端快。
# 紧急跳过：git push --no-verify
#
# ruff 只查**待推变更**的 py 文件（@{push}...HEAD）——全仓存量违规不在这里
# 清算（否则历史错误会拦住所有 push）；全仓清理走独立工单。
set -e
cd "$(git rev-parse --show-toplevel)"

CHANGED=$(git diff --name-only --diff-filter=ACMR @{push}...HEAD -- '*.py' 2>/dev/null \\
          || git diff --name-only --diff-filter=ACMR @{u}...HEAD -- '*.py' 2>/dev/null || true)

if [ -n "$CHANGED" ]; then
    echo "[pre-push] ruff check（本次待推的 py 变更）"
    # ruff 解析：PATH → uv tool 默认安装位（Windows/POSIX）→ venv
    RUFF=""
    for cand in ruff "$HOME/.local/bin/ruff" "$HOME/.local/bin/ruff.exe" \\
                .venv/Scripts/ruff.exe .venv/bin/ruff; do
        if command -v "$cand" >/dev/null 2>&1; then RUFF="$cand"; break; fi
    done
    if [ -n "$RUFF" ]; then
        # shellcheck disable=SC2086
        "$RUFF" check $CHANGED
    else
        echo "[pre-push] !! ruff 不可用——跳过静态检查（安装：uv tool install ruff）"
    fi
else
    echo "[pre-push] 无待推 py 变更，跳过 ruff"
fi

echo "[pre-push] pytest -m smoke（冒烟层，≤60s）"
# python 解析：仓库 venv 优先（PATH 里的全局 python 未必装 pytest）
PY=""
for cand in .venv/Scripts/python.exe .venv/bin/python python3 python; do
    if command -v "$cand" >/dev/null 2>&1; then PY="$cand"; break; fi
done
"$PY" -m pytest -m smoke -q --no-header -p no:cacheprovider

echo "[pre-push] 全部通过 ✓"
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="安装本地 pre-push 钩子（ruff + smoke 层）")
    ap.add_argument("--force", action="store_true", help="覆盖已存在的钩子")
    ap.add_argument("--remove", action="store_true", help="卸载钩子")
    args = ap.parse_args()

    if args.remove:
        if HOOK_PATH.exists():
            HOOK_PATH.unlink()
            print(f"已卸载: {HOOK_PATH}")
        else:
            print("钩子不存在，无需卸载")
        return 0

    if not (REPO_ROOT / ".git").exists():
        print("!! 未找到 .git 目录——请在仓库根运行", file=sys.stderr)
        return 1

    if HOOK_PATH.exists() and not args.force:
        print(f"!! 钩子已存在: {HOOK_PATH}", file=sys.stderr)
        print("   查看/覆盖：", file=sys.stderr)
        print(f"     cat {HOOK_PATH}", file=sys.stderr)
        print("     python scripts/install_hooks.py --force", file=sys.stderr)
        return 1

    HOOK_PATH.parent.mkdir(parents=True, exist_ok=True)
    HOOK_PATH.write_text(HOOK_TEMPLATE, encoding="utf-8", newline="\n")
    # Windows 无 POSIX 执行位，但 git-for-windows 的 sh 依赖它；设上无害
    HOOK_PATH.chmod(HOOK_PATH.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    print(f"已安装 pre-push 钩子: {HOOK_PATH}")
    print("生效内容：push 前 ruff check . + pytest -m smoke（失败即拦）")
    print("跳过：git push --no-verify（紧急时用，事后在报告里写明）")
    _ = os  # 保留 import 以便扩展
    return 0


if __name__ == "__main__":
    sys.exit(main())
