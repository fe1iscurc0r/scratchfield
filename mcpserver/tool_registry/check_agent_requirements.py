#!/usr/bin/env python3
"""装前预检：按 manifest 的 `requires` 块判定每个能力的环境可用性。

与 check_classification.py 的分工：
- 那个管「声明是否合规」（词汇表 / 闸门）—— 规范层
- 这个管「环境是否具备」（包 / CLI / 服务）—— 能力层

requires 块结构（全部可选，空 = 无外部依赖）：
    "requires": {
      "python_packages": ["frida", {"name": "docling", "optional": true}],
      "external_cli": ["nuclei"],
      "services": ["ollama@127.0.0.1:11434"]
    }
条目缺省为必须；对象形态带 `"optional": true` 的为软依赖——缺失不判 missing，
只进 optional_missing（语义：功能降级但 agent 可用）。
判定方式：python_packages 走 importlib.util.find_spec；external_cli 走
shutil.which；services 走 TCP 探测（name@host:port）。

报告模式：
    --report       输出「可用 / 缺依赖 / 未声明」三列矩阵（默认）
    --only-missing 只看缺依赖的
    --strict       存在未声明 requires 的 agent 即失败（用于推动逐步补全）

stdlib only，纯静态 + 轻探测（which/find_spec/socket），不 import 任何 agent。
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
import socket
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def iter_manifests() -> list[tuple[Path, dict]]:
    out = []
    for p in sorted(REPO_ROOT.glob("mcpserver/**/agent-manifest.json")):
        try:
            out.append((p, json.loads(p.read_text(encoding="utf-8"))))
        except (json.JSONDecodeError, OSError):
            continue
    return out


# ── 检查逻辑单一真源在 apiserver/mcp_assembly.py（脚本与 GET /mcp/services 共用）──
# 本脚本按文件路径加载它，绕开 apiserver 包的 __init__ 重依赖链。
_spec = importlib.util.spec_from_file_location(
    "mcp_assembly", REPO_ROOT / "apiserver" / "mcp_assembly.py"
)
assert _spec and _spec.loader, "加载 apiserver/mcp_assembly.py 失败"
_assembly = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_assembly)
check_python_package = _assembly.check_python_package
check_service = _assembly.check_service
check_requires = _assembly.check_requirements


def main() -> int:
    ap = argparse.ArgumentParser(description="agent 依赖装前预检")
    ap.add_argument("--only-missing", action="store_true", help="只显示缺依赖的")
    ap.add_argument("--strict", action="store_true", help="存在未声明 requires 的 agent 即失败")
    args = ap.parse_args()

    manifests = iter_manifests()
    no_req: list[str] = []
    rows: list[tuple[str, str, list[str], list[str]]] = []  # (name, verdict, missing, optional_missing)

    for path, data in manifests:
        name = data.get("name") or path.parent.name
        req = data.get("requires")
        if not isinstance(req, dict):
            no_req.append(name)
            continue
        missing, optional_missing, _available = check_requires(req)
        if missing:
            verdict = "missing"
        elif optional_missing:
            verdict = "degraded"  # 软依赖缺失：功能降级但可用
        else:
            verdict = "ready"
        rows.append((name, verdict, missing, optional_missing))

    ready = sum(1 for _, v, _, _ in rows if v == "ready")
    with_missing = [(n, m, om) for n, v, m, om in rows if v == "missing"]
    degraded = [(n, om) for n, v, _, om in rows if v == "degraded"]

    print(f"已声明 requires：{len(rows)}/{len(manifests)}　"
          f"其中 ready {ready}、缺依赖 {len(with_missing)}、软依赖降级 {len(degraded)}")
    print(f"未声明 requires：{len(no_req)} 个")
    print()

    if not args.only_missing:
        for n, v, m, om in rows:
            suffix = f"（另缺可选: {', '.join(om)}）" if om else ""
            print(f"  [{v:7s}] {n:24s} 缺: {', '.join(m) if m else '—'}{suffix}")
    if with_missing:
        print(f"\n=== 缺依赖明细（{len(with_missing)}）===")
        for n, m, om in with_missing:
            suffix = f"　（另缺可选: {', '.join(om)}）" if om else ""
            print(f"  {n:24s} {', '.join(m)}{suffix}")
    if degraded:
        print(f"\n=== 软依赖降级（{len(degraded)}，缺了照样能用 ===")
        for n, om in degraded:
            print(f"  {n:24s} {', '.join(om)}")

    if no_req:
        print(f"\n未声明清单（--strict 模式下视为失败）：{', '.join(no_req)}")

    if args.strict and (no_req or with_missing):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
