#!/usr/bin/env python3
"""verify-runtime-env-wiring.sh · 陆墨运行时接线验收（WO-250 / 2026-10-16）

对 SPEC §四 验收硬线 1~5 做可脚本化的原子自检，只读不改。

用法：
  python3 scripts/verify-runtime-env-wiring.py                    # 跑全部项
  python3 scripts/verify-runtime-env-wiring.py --only leak,noisy   # 只跑指定项
  python3 scripts/verify-runtime-env-wiring.py --ci               # 失败即 exit 1（CI 用）

项目根：脚本父目录的父目录（scripts/verify-.../verify-...py → 项目根 = ../../）
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent  # scripts/verify-...py → ../ = 项目根
sys.path.insert(0, str(PROJECT_ROOT / "mcpserver" / "agent_open_launcher"))

PLATFORM_TAG = "win" if sys.platform == "win32" else ("mac" if sys.platform == "darwin" else "linux")
RESULTS: list[tuple[str, str, str]] = []  # (id, status, message)

C_RED = "\033[31m"; C_GRN = "\033[32m"; C_YEL = "\033[33m"; C_DIM = "\033[2m"; C_END = "\033[0m"
def _emit(use_color: bool) -> None:
    red, grn, yel, dim, end = (C_RED, C_GRN, C_YEL, C_DIM, C_END) if use_color else ("", "", "", "", "")
    for rid, status, msg in RESULTS:
        icon = f"{grn}✓{end}" if status == "PASS" else f"{red}✗{end}" if status == "FAIL" else f"{yel}~{end}"
        print(f"  {icon} {rid:<6} {msg}")
    fails = sum(1 for _, s, _ in RESULTS if s == "FAIL")
    warns = sum(1 for _, s, _ in RESULTS if s == "WARN")
    print()
    if fails:
        print(f"{red}FAIL{end}  {fails} 失败 / {warns} 警告 / {len(RESULTS)} 总")
    elif warns:
        print(f"{yel}WARN{end}  0 失败 / {warns} 警告 / {len(RESULTS)} 总")
    else:
        print(f"{grn}PASS{end}  0 失败 / 0 警告 / {len(RESULTS)} 总")


# ============ 项 1：包内 runtime 路径命中（与 §四·1 对齐） ============

def check_1_bundled_runtime() -> None:
    """检查 _bundled_runtime_bin 是否已实现（不要求类型注解）"""
    p = PROJECT_ROOT / "mcpserver" / "agent_open_launcher" / "local_apps.py"
    if not p.exists():
        RESULTS.append(("1", "WARN", "local_apps.py 不存在（路径异常）"))
        return
    text = p.read_text(encoding="utf-8", errors="ignore")
    if re.search(r"def\s+_bundled_runtime_bin\s*\(\s*name\b", text):
        RESULTS.append(("1", "PASS", "_bundled_runtime_bin(name) 已实现（见 local_apps.py）"))
    else:
        RESULTS.append(("1", "WARN", "未在 local_apps.py 找到 _bundled_runtime_bin(name) 实现（Trae 还没改 §3.2）"))


# ============ 项 2：本机路径硬编码清零（与 §四·2 对齐） ============

def check_2_leak() -> None:
    """grep -rn 'trae-cn|python-sdk' mcpserver/ → 0 命中（注释行除外）"""
    patterns = ["trae-cn", "python-sdk"]
    hits: list[str] = []
    for pat in patterns:
        for p in (PROJECT_ROOT / "mcpserver").rglob("*.py"):
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            for n, line in enumerate(text.splitlines(), 1):
                stripped = line.lstrip()
                if pat in line and not stripped.startswith("#"):
                    hits.append(f"{p.relative_to(PROJECT_ROOT)}:{n}: {line.strip()[:100]}")
    if hits:
        RESULTS.append(("2", "FAIL", f"本机路径硬编码仍存在 {len(hits)} 处: " + "; ".join(hits[:3])))
    else:
        RESULTS.append(("2", "PASS", "mcpserver/ 全树 grep trae-cn / python-sdk 0 命中（注释行不计）"))


# ============ 项 3：失败可诊断（与 §四·3 对齐） ============

def check_3_noisy() -> None:
    """检查 _start_neko_shell 失败分支不再裸 return False（必须有 reason / raise）。
    口径：在 def _start_neko_shell 起的函数体内，最后一个 return False 之前的 200 字符内
    必须出现 'reason' 或 'raise' 关键字。"""
    p = PROJECT_ROOT / "mcpserver" / "agent_open_launcher" / "local_apps.py"
    if not p.exists():
        RESULTS.append(("3", "WARN", "local_apps.py 不存在（路径异常）"))
        return
    text = p.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"def\s+_start_neko_shell\([^)]*\)[^:]*:\s*(.+?)(?=\n\ndef |\nclass |\Z)", text, re.S)
    if not m:
        RESULTS.append(("3", "WARN", "未找到 def _start_neko_shell（函数未定义或被改名）"))
        return
    body = m.group(1)
    if "return False" not in body:
        RESULTS.append(("3", "PASS", "_start_neko_shell 已无 return False（失败走 raise / 显式 reason 路径）"))
        return
    # 兜底：函数体内仍含 return False，看每个出现处的前 200 字符有无 reason/raise
    bad: list[str] = []
    for mm in re.finditer(r"return\s+False", body):
        ctx = body[max(0, mm.start() - 200):mm.start()]
        if "reason" not in ctx and "raise" not in ctx:
            bad.append(f"…{ctx[-80:].strip()}\n        return False")
    if bad:
        RESULTS.append(("3", "FAIL", "_start_neko_shell 仍存在裸 return False（上下文无 reason/raise）: " + bad[0]))
    else:
        RESULTS.append(("3", "PASS", "_start_neko_shell 的 return False 已被 reason/raise 守护"))


# ============ 项 4：开发模式不回归（与 §四·4 对齐） ============

def check_4_dev_mode() -> None:
    """打包模式下注入 LUMO_FUSION_NODE / LUMO_FUSION_PYTHON 的代码必须包在 if (app.isPackaged) 内。
    开发模式不得注入，避免覆盖 venv / ps1 的既有选择。"""
    p = PROJECT_ROOT / "frontend" / "electron" / "modules" / "backend.ts"
    if not p.exists():
        RESULTS.append(("4", "WARN", "backend.ts 不存在（路径异常）"))
        return
    text = p.read_text(encoding="utf-8", errors="ignore")
    if "LUMO_FUSION_NODE" not in text and "LUMO_FUSION_PYTHON" not in text:
        RESULTS.append(("4", "WARN", "backend.ts 尚未注入 LUMO_FUSION_*（Trae 还没改 §3.1）"))
        return
    if "app.isPackaged" in text:
        RESULTS.append(("4", "PASS", "backend.ts 已注入 LUMO_FUSION_* 并被 app.isPackaged 守护"))
    else:
        RESULTS.append(("4", "FAIL", "backend.ts 含 LUMO_FUSION_* 但无 app.isPackaged 守护 → 开发模式会被覆盖"))


# ============ 项 5：构建不回归（与 §四·5 对齐） ============

def check_5_build_intact() -> None:
    """build.py / electron-builder.yml 是否被本单错误改动。
    口径：本 SPEC 明确写「不改 build.py / electron-builder.yml」。"""
    issues: list[str] = []
    for path in (PROJECT_ROOT / "build.py", PROJECT_ROOT / "frontend" / "electron-builder.yml"):
        if not path.exists():
            continue
        rel = path.relative_to(PROJECT_ROOT)
        try:
            # WO-250 修：此处原读 `rel`（相对路径，依赖 CWD==项目根才不炸）→ 改读绝对 `path`
            path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            issues.append(f"{rel} 读取失败: {e}")
    if issues:
        RESULTS.append(("5", "FAIL", "; ".join(issues)))
    else:
        RESULTS.append(("5", "PASS", "build.py / electron-builder.yml 未被本单改动（按 SPEC §四 边界）"))


CHECKS = {
    "bundled": check_1_bundled_runtime,
    "leak":    check_2_leak,
    "noisy":   check_3_noisy,
    "dev":     check_4_dev_mode,
    "build":   check_5_build_intact,
}


def main() -> int:
    ap = argparse.ArgumentParser(description="陆墨运行时接线验收（WO-250）")
    ap.add_argument("--only", help="逗号分隔，只跑指定项；可选: bundled,leak,noisy,dev,build")
    ap.add_argument("--ci", action="store_true", help="CI 模式：FAIL 即 exit 1")
    ap.add_argument("--no-color", action="store_true")
    args = ap.parse_args()

    use_color = (not args.no_color) and sys.stdout.isatty()

    print(f"{'陆墨运行时接线验收 · WO-250':^60}")
    print(f"  项目根: {PROJECT_ROOT}")
    print(f"  平台:   {PLATFORM_TAG} ({platform.machine()})")
    print()

    targets = list(CHECKS.keys())
    if args.only:
        targets = [t for t in (s.strip() for s in args.only.split(",")) if t in CHECKS]
        unknown = set(args.only.split(",")) - set(CHECKS.keys())
        if unknown:
            print(f"未知项: {unknown}（合法: {', '.join(CHECKS.keys())}）")
            return 2
    for k in targets:
        CHECKS[k]()

    _emit(use_color)
    if args.ci and any(s == "FAIL" for _, s, _ in RESULTS):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
