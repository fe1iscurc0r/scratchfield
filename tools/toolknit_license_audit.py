"""toolknit 依赖许可审计（**可重跑**，工单244 §3.7 的固化）。

用法::

    python tools/toolknit_license_audit.py                      # 审计钉死版本（默认 2.3.1）
    python tools/toolknit_license_audit.py --version 2.3.1 --json-out audit.json
    python tools/toolknit_license_audit.py --strict              # 有 copyleft / 无声明则非零退出

为什么要有这个脚本
------------------
工单244 §3.7 要求核验上游许可。**一次性的结论会腐烂**：上游发一版，
依赖树就可能变。结论必须能被**重跑复算**（见 `memory/REFERENCE.md` §R12）。

实现要点（第一版踩坑后定的四条）
--------------------------------
1. **不要用 ``node_modules/<name>/package.json`` 直查**。npm 的目录**非扁平**
   （嵌套依赖、scope 包、未被提升的包各自在自己的 ``node_modules`` 下）
   ⇒ 直查会把绝大多数包判成 ``UNKNOWN``（第一版 118/119 全中此坑）。
   必须**文件系统递归枚举** ``package.json``。
2. **交叉校验要比「集合」而不是「节点数」**。``npm ls`` 里同一个包会因嵌套位置重复出现
   （实测原始节点 **205** 个 vs 磁盘唯一包 **112** 个）⇒ 数节点做校验恒假警报。
   本脚本比 ``name@version`` 集合差（``only_on_disk`` / ``only_in_tree``），
   两侧都干净才算结论可信；``--strict`` 下不一致直接失败。
3. **``OR`` 表达式必须单独分类**。``(MIT OR GPL-3.0-or-later)``（jszip）是
   **双许可、可选宽松分支** ⇒ **不构成传染**。朴素子串命中会把 ``GPL-3.0`` 判成强 copyleft
   （第一版就这么错），故本脚本用 ``ELECTABLE-PERMISSIVE`` 单独归类。
4. **没有 ``license`` 字段的包要嗅探 LICENSE 文件**（老包常见），再退回 ``UNKNOWN``。
   ``UNKNOWN`` 不等于「有问题」，但**必须人工确认**后才能在交付里写「无风险」。
5. **人工确认过的例外要落成\"已受理清单\"**（``ACCEPTED_EXCEPTIONS``），而不是留在报告里当一句话。
   否则 ``--strict`` 永远红着 ⇒ 没人会用它 ⇒ 这个检查等于没有（「狼来了」）。
   受理条目**必须写理由 + 指认守着它的回归测试**；``--strict`` 只对**新增**的未知项失败。
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

#: **已受理的例外**：`name@version -> 理由`。
#:
#: 只放「已人工确认、且有能力边界守护」的条目。加进来时必须写清：
#: ① 为什么可接受；② **哪个测试守着这条边界**（否则就是口头豁免）。
#: ⚠️ 上游换版本后 key 会变 ⇒ 条目自然失效、``--strict`` 会重新报警（这是**有意**的）。
ACCEPTED_EXCEPTIONS: dict[str, str] = {
    "buffers@0.1.1": (
        "无任何许可声明（package.json 无 license 字段、包内无 LICENSE、"
        "声明仓库 substack/node-buffers 已 404）。可接受的理由：引入链 "
        "exceljs → unzipper → binary → buffers **只在表格路径上**，"
        "而 mcpserver/toolknit_mcp 的白名单不含任何表格工具、CLI 驱动层也不出现表格关键词；"
        "且本仓不 vendor、不 redistribute（只 npx 运行时拉取）。"
        "守着这条边界的是 tests/test_toolknit_mcp.py::test_whitelist_never_touches_the_table_path"
        "——它每次 CI 都重新证明「不经过该链」。"
    ),
}
from typing import Any

#: 默认审计对象（与 mcpserver/toolknit_mcp 的 CLI 钉死版本保持一致）
DEFAULT_PACKAGE = "@toolknit/cli"
DEFAULT_VERSION = "2.3.1"

#: 强 copyleft —— 传染性义务，进仓/分发前必须评估
STRONG_COPYLEFT = ("GPL-2.0", "GPL-3.0", "AGPL", "SSPL", "EUPL", "OSL-", "CPAL", "CC-BY-SA-4.0")
#: 弱 copyleft —— 库级传染或条件义务
WEAK_COPYLEFT = ("LGPL", "MPL", "EPL", "CDDL", "MS-RL")
#: 宽松
PERMISSIVE = ("MIT", "ISC", "BSD", "APACHE", "0BSD", "UNLICENSE", "ZLIB", "CC0", "X11", "BSL-1.0")

#: 严重度顺序（``AND`` 组合与降级判定用）
_SEVERITY = ("STRONG-COPYLEFT", "WEAK-COPYLEFT", "UNKNOWN", "PERMISSIVE")

#: LICENSE 文件里能认出来的 SPDX 记号
_SPDX_HINT = re.compile(
    r"\b(MIT|ISC|Apache-2\.0|BSD-[23]-Clause|GPL-\d[\w.-]*|LGPL[\w.-]*|MPL-2\.0|Unlicense|0BSD)\b",
    re.IGNORECASE,
)

_LICENSE_FILE_HINTS = ("LICENSE", "LICENCE", "COPYING", "NOTICE")

#: 默认 npm 调用超时（安装全树 + 列树）
DEFAULT_TIMEOUT_S = 600


# --------------------------------------------------------------------------- 分类


def _rank(token: str) -> str:
    """单个许可记号 → 类别（前缀匹配，兼容 ``Apache-2.0`` / ``BSD-3-Clause`` 这类带后缀写法）。"""
    upper = token.strip().strip("()").strip().upper()
    if not upper:
        return "UNKNOWN"
    if upper.startswith(STRONG_COPYLEFT):
        return "STRONG-COPYLEFT"
    if upper.startswith(WEAK_COPYLEFT):
        return "WEAK-COPYLEFT"
    if upper.startswith(PERMISSIVE):
        return "PERMISSIVE"
    return "UNKNOWN"


def _strictest(ranks: list[str]) -> str:
    """按严重度取最严的一档。"""
    for level in _SEVERITY:
        if level in ranks:
            return level
    return "UNKNOWN"


def classify(expr: str) -> str:
    """SPDX 表达式 → 判定类别。

    ``OR`` 里只要存在宽松分支 ⇒ ``ELECTABLE-PERMISSIVE``（可择宽松，**不传染**）；
    ``AND`` 取最严；单表达式按前缀匹配。
    """
    raw = (expr or "").strip()
    if not raw:
        return "UNKNOWN"
    upper = raw.upper()
    if " OR " in upper:
        ranks = [_rank(part) for part in re.split(r"\s+OR\s+", upper)]
        if "PERMISSIVE" in ranks:
            return "ELECTABLE-PERMISSIVE"
        return _strictest(ranks)
    if " AND " in upper:
        return _strictest([_rank(part) for part in re.split(r"\s+AND\s+", upper)])
    return _rank(raw)


# --------------------------------------------------------------------------- 枚举


def _sniff_license_file(pkg_dir: Path) -> str:
    """包里没有 ``license`` 字段时，从 LICENSE/COPYING 正文嗅探 SPDX 记号。"""
    for stem in _LICENSE_FILE_HINTS:
        for candidate in sorted(pkg_dir.glob(f"{stem}*")):
            if not candidate.is_file():
                continue
            try:
                text = candidate.read_text(encoding="utf-8", errors="replace")[:4000]
            except OSError:
                continue
            match = _SPDX_HINT.search(text)
            if match:
                return match.group(1)
    return ""


def _license_expression(data: dict[str, Any]) -> str:
    """从 ``package.json`` 取许可表达式（兼容 ``license`` 字符串/对象与旧 ``licenses`` 数组）。"""
    raw = data.get("license")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    if isinstance(raw, dict) and raw.get("type"):
        return str(raw["type"]).strip()
    legacy = data.get("licenses")
    if isinstance(legacy, list):
        parts = [str(item.get("type") or "").strip() for item in legacy if isinstance(item, dict)]
        return " OR ".join(part for part in parts if part)
    return ""


def _is_package_manifest(pkg_json: Path) -> bool:
    """按 npm 布局规则判断这是不是**一个包**的清单。

    反例（实测，逼出来的规则）：``chart.js`` 会在包内附 ``auto/package.json``、
    ``helpers/package.json`` 这类**子路径 shim**（只写 ``{"type":"module"}``，没有 name/version）。
    它们是包的一部分，不是独立包 ⇒ 不过滤就会凭空多出 ``chart.js-auto@`` 这种空版本条目。
    """
    parts = pkg_json.parts[:-1]  # 去掉 "package.json"
    try:
        idx = max(index for index, part in enumerate(parts) if part == "node_modules")
    except ValueError:
        return False
    tail = parts[idx + 1:]
    if len(tail) == 1:
        return True
    return len(tail) == 2 and tail[0].startswith("@")


def collect_packages(root: Path) -> dict[str, dict[str, Any]]:
    """递归枚举 ``root`` 下所有已安装包（**不按名字直查**，见模块 docstring 第 1 条）。"""
    found: dict[str, dict[str, Any]] = {}
    for pkg_json in sorted(root.rglob("package.json")):
        if "node_modules" not in pkg_json.parts or not _is_package_manifest(pkg_json):
            continue
        try:
            data = json.loads(pkg_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        name = str(data.get("name") or "").strip()
        if not name:
            continue
        version = str(data.get("version") or "").strip()
        expr = _license_expression(data)
        declared = "package.json"
        if not expr:
            expr = _sniff_license_file(pkg_json.parent)
            declared = "LICENSE-file" if expr else "none"
        found[f"{name}@{version}"] = {
            "name": name,
            "version": version,
            "license": expr or None,
            "declared_by": declared,
            "path": str(pkg_json.parent),
            "verdict": classify(expr),
        }
    return found


# --------------------------------------------------------------------------- npm


def resolve_npm() -> str:
    """``npm`` 绝对路径（Windows 上是 ``npm.cmd``）。"""
    found = shutil.which("npm.cmd") or shutil.which("npm")
    if not found:
        raise RuntimeError("未找到 npm（需要 Node >= 20.12）")
    return found


def install_tree(package: str, version: str, workdir: Path, *, timeout: int) -> None:
    """在临时目录里 ``npm install`` 目标包（拉到整棵依赖树）。"""
    manifest = workdir / "package.json"
    manifest.write_text(
        json.dumps({"name": "toolknit-license-audit", "version": "0.0.0", "private": True},
                   ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8", newline="\n",
    )
    argv = [resolve_npm(), "install", f"{package}@{version}",
            "--no-audit", "--no-fund", "--loglevel=error"]
    proc = subprocess.run(argv, cwd=str(workdir), capture_output=True, text=True,
                          timeout=timeout, shell=False)
    if proc.returncode != 0:
        raise RuntimeError(f"npm install 失败 rc={proc.returncode}: {(proc.stderr or '')[-500:]}")


def tree_package_keys(workdir: Path, *, timeout: int) -> set[str]:
    """``npm ls --all --json`` 里的 ``name@version`` 集合（与磁盘枚举做**集合差**）。

    ⚠️ **不要数「节点个数」**：同一个包在树里会因嵌套位置重复出现
    （实测原始节点 **205** 个，而磁盘唯一包只有 **112** 个）⇒ 用节点数做交叉校验
    **必然假警报**（第一版就栽在这，``counts_match`` 恒为 False）。
    要比的是**集合**，而且只比双方都有版本的条目。
    """
    proc = subprocess.run([resolve_npm(), "ls", "--all", "--json"], cwd=str(workdir),
                          capture_output=True, text=True, timeout=timeout, shell=False)
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return set()
    keys: set[str] = set()
    stack: list[tuple[str, Any]] = list((data.get("dependencies") or {}).items())
    while stack:
        key, node = stack.pop()
        if not isinstance(node, dict):
            continue
        name = str(node.get("name") or key or "").strip()
        version = str(node.get("version") or "").strip()
        if name and version:
            keys.add(f"{name}@{version}")
        stack.extend((node.get("dependencies") or {}).items())
    return keys


# --------------------------------------------------------------------------- 主流程


def audit(package: str = DEFAULT_PACKAGE, version: str = DEFAULT_VERSION,
          *, timeout: int = DEFAULT_TIMEOUT_S) -> dict[str, Any]:
    """跑一次完整审计，返回可判定的结构化结果。"""
    workdir = Path(tempfile.mkdtemp(prefix="toolknit-license-audit-"))
    try:
        install_tree(package, version, workdir, timeout=timeout)
        packages = collect_packages(workdir)
        on_disk = {key for key in packages if not key.endswith("@")}
        in_tree = tree_package_keys(workdir, timeout=timeout)
        only_on_disk = sorted(on_disk - in_tree)
        only_in_tree = sorted(in_tree - on_disk)
        verdicts: dict[str, list[str]] = {}
        for key, info in sorted(packages.items()):
            verdicts.setdefault(info["verdict"], []).append(key)
        return {
            "package": package,
            "version": version,
            "packages_enumerated": len(packages),
            "tree_packages": len(in_tree),
            "only_on_disk": only_on_disk,
            "only_in_tree": only_in_tree,
            "sets_match": not only_on_disk and not only_in_tree,
            "verdict_counts": {key: len(value) for key, value in sorted(verdicts.items())},
            "verdicts": verdicts,
            "packages": packages,
        }
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _unaccepted(level: str, report: dict[str, Any]) -> list[str]:
    """该等级里**未**被受理清单覆盖的包。"""
    return [key for key in report["verdicts"].get(level, []) if key not in ACCEPTED_EXCEPTIONS]


def risky(report: dict[str, Any]) -> list[str]:
    """**需要处理**的条目（``ACCEPTED_EXCEPTIONS`` 里的不算，由 :func:`accepted_note` 单列）。

    这样 ``--strict`` 只在**新增**未知项时失败 ⇒ 检查才有人用（否则恒红 = 狼来了）。
    """
    problems = [f"{level}: {', '.join(left)}"
                for level in ("STRONG-COPYLEFT", "WEAK-COPYLEFT", "UNKNOWN")
                if (left := _unaccepted(level, report))]
    if not report["sets_match"]:
        problems.append(
            f"磁盘枚举与 npm 依赖树不一致 ⇒ 结论不可信：只在磁盘 {report['only_on_disk'][:5]}"
            f"；只在树 {report['only_in_tree'][:5]}"
        )
    return problems


def accepted_note(report: dict[str, Any]) -> list[str]:
    """本次命中的**已受理**条目（带理由），供人工复核与报告引用。"""
    return [f"{key}（{level}）⇒ {ACCEPTED_EXCEPTIONS[key]}"
            for level in ("STRONG-COPYLEFT", "WEAK-COPYLEFT", "UNKNOWN")
            for key in report["verdicts"].get(level, []) if key in ACCEPTED_EXCEPTIONS]


def build_parser() -> argparse.ArgumentParser:
    """命令行入口。"""
    parser = argparse.ArgumentParser(description="toolknit 依赖许可审计（可重跑）")
    parser.add_argument("--package", default=DEFAULT_PACKAGE, help="npm 包名")
    parser.add_argument("--version", default=DEFAULT_VERSION, help="版本（默认钉死版）")
    parser.add_argument("--json-out", default="", help="把完整报告写到该 JSON 路径")
    parser.add_argument("--strict", action="store_true",
                        help="出现**未受理**的强/弱 copyleft 或无声明包时非零退出"
                             "（已受理清单见 ACCEPTED_EXCEPTIONS）")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_S, help="npm 调用超时（秒）")
    return parser


def main(argv: list[str] | None = None) -> int:
    """跑审计并打印摘要；``--strict`` 时按**未受理**风险非零退出。"""
    args = build_parser().parse_args(argv)
    report = audit(args.package, args.version, timeout=args.timeout)
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8", newline="\n",
        )
    print(f"{report['package']}@{report['version']}")
    print(f"  磁盘枚举 = {report['packages_enumerated']} 个；npm 依赖树 = {report['tree_packages']} 个"
          f"（集合一致 = {report['sets_match']}）")
    for level, count in report["verdict_counts"].items():
        print(f"  {level:<22} {count}")
    for note in accepted_note(report):
        print(f"  ℹ️ 已受理：{note}")
    problems = risky(report)
    if problems:
        print("  ⚠️ **需处理**：")
        for item in problems:
            print(f"    - {item}")
    else:
        print("  ✅ 无**未受理**的强/弱 copyleft、无**未受理**的未声明包")
    return 1 if (problems and args.strict) else 0


if __name__ == "__main__":
    sys.exit(main())
