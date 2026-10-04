#!/usr/bin/env python3
"""陆墨 Windows 安装包发布脚本（GitHub Release）

线B（分发渠道）唯一入口：把本地构建好的 NSIS 安装包发成 GitHub Release **草稿**。

设计原则：
  * draft 起步，**绝不自动 publish**——人工过目后才点发布
  * 前置校验失败即停：产物不齐、HEAD 与 tag 不一致，一律不发
  * release notes 生成后先过敏感词扫描，命中即中止（隐私铁律）
  * token 只从 `gh` 的登录态走，脚本本身不碰任何凭证文件

用法:
  python scripts/release-win.py --tag v5.1.5              # 生成 notes 并创建 draft release + 上传安装包
  python scripts/release-win.py --tag v5.1.5 --dry-run    # 只做校验与 notes，不发任何请求
  python scripts/release-win.py --tag v5.1.5 --notes-only # 只生成 notes 文件，不发布

前置要求：
  * 已安装 `gh` CLI 且 `gh auth login` 完成（本机登录态，token 不进仓库）
  * 已执行 `python scripts/build-win.py --tag v5.1.5` 且产物校验全过
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "frontend"
RELEASE_DIR = FRONTEND_DIR / "release"
PACKAGE_JSON = FRONTEND_DIR / "package.json"
CHANGELOG = PROJECT_ROOT / "CHANGELOG.md"
BLOCKLIST = PROJECT_ROOT / "scripts" / "release-notes-blocklist.txt"
NOTES_OUT = PROJECT_ROOT / "build" / "release-notes"

TAG_RE = re.compile(r"^v(\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.\-]+)?)$")
GITHUB_REPO_RE = re.compile(r"github\.com[:/](?P<owner>[^/]+)/(?P<repo>[^/.]+)")


def log(msg: str) -> None:
    print(f"[release] {msg}", flush=True)


def run(
    cmd: list[str], *, check: bool = True, capture: bool = False
) -> subprocess.CompletedProcess[str]:
    resolved = shutil.which(cmd[0]) if not Path(cmd[0]).is_absolute() else cmd[0]
    if not resolved:
        raise FileNotFoundError(f"未找到命令：{cmd[0]}")
    return subprocess.run(
        [resolved, *cmd[1:]],
        cwd=str(PROJECT_ROOT),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=capture,
        check=check,
    )


# ============ 前置校验 ============


def _find_gh() -> str | None:
    """定位 gh 可执行文件。

    先查 PATH；winget 装完的 gh 常位于 `C:\\Program Files\\GitHub CLI\\gh.exe`，
    但当前 shell 的 PATH 可能尚未刷新，故做一次常见路径回退。
    """
    found = shutil.which("gh")
    if found:
        return found
    for candidate in (
        Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "GitHub CLI" / "gh.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "GitHub CLI" / "gh.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "GitHub CLI" / "gh.exe",
    ):
        if candidate.is_file():
            return str(candidate)
    return None


def require_gh() -> None:
    """确认 gh 可用且已登录"""
    gh = _find_gh()
    if not gh:
        log("未找到 gh CLI。安装：winget install --id GitHub.cli")
        log("（winget 装完后请重开一个终端，或直接重跑本脚本——脚本会自动探测常见安装路径）")
        log("安装后执行 gh auth login，再重跑本脚本。")
        sys.exit(1)
    if gh != "gh":
        log(f"通过回退路径找到 gh：{gh}")

    result = subprocess.run(
        [gh, "auth", "status"],
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    if result.returncode != 0:
        log("gh 未登录。请先执行：gh auth login")
        log("（脚本不会读取或写入任何 token 文件，完全依赖 gh 自身登录态）")
        sys.exit(1)
    log("gh 可用且已登录 ✓")


def resolve_repo() -> str:
    """从 origin remote 解析 owner/repo"""
    out = run(["git", "config", "--get", "remote.origin.url"], capture=True).stdout.strip()
    m = GITHUB_REPO_RE.search(out)
    if not m:
        log(f"无法从 origin URL 解析 GitHub owner/repo：{out!r}")
        sys.exit(1)
    return f"{m.group('owner')}/{m.group('repo')}"


def verify_release_preconditions(tag: str) -> tuple[str, str]:
    """校验：tag 格式 → tag 存在且为 annotated → tag == HEAD → package.json 一致。

    返回 (version, repo)。任一失败即 sys.exit(1)。
    产物校验不在本函数内（见 verify_artifacts_ready），只在真正创建 release 前执行。
    """
    m = TAG_RE.match(tag)
    if not m:
        log(f"tag 格式非法：{tag!r}（应为 vX.Y.Z）")
        sys.exit(1)
    version = m.group(1)

    # tag 存在 + annotated
    exists = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"refs/tags/{tag}"],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
    )
    if exists.returncode != 0:
        log(f"tag 不存在：{tag}")
        sys.exit(1)
    obj_type = subprocess.run(
        ["git", "cat-file", "-t", tag],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
    ).stdout.strip()
    if obj_type != "tag":
        log(f"{tag} 是轻量 tag（lightweight）。发布锚点必须用 annotated tag：git tag -a {tag}")
        sys.exit(1)

    # tag == HEAD
    tag_sha = subprocess.run(
        ["git", "rev-list", "-n", "1", tag], cwd=str(PROJECT_ROOT), capture_output=True, text=True
    ).stdout.strip()
    head_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=str(PROJECT_ROOT), capture_output=True, text=True
    ).stdout.strip()
    if tag_sha != head_sha:
        log(f"HEAD ({head_sha[:8]}) 与 tag {tag} ({tag_sha[:8]}) 不一致")
        log("发布必须发生在 tag 所指向的提交上（防拿旧构建发新 tag）")
        sys.exit(1)
    log(f"tag 校验：{tag} 存在、annotated、即 HEAD ({head_sha[:8]}) ✓")

    # package.json 版本一致
    pkg_version = json.loads(PACKAGE_JSON.read_text(encoding="utf-8")).get("version")
    if str(pkg_version) != version:
        log(f"版本不一致：tag {tag} (= {version}) ≠ package.json ({pkg_version})")
        sys.exit(1)
    log(f"版本一致：{version} ✓")

    repo = resolve_repo()
    log(f"目标仓库：{repo} ✓")
    return version, repo


def verify_artifacts_ready(tag: str) -> None:
    """产物校验（复用 build-win.py 的清单，保证只有一个真源）。

    只在确实要创建 release 时调用——--dry-run / --notes-only 不要求本机已有完整产物。
    """
    log("跑产物校验（复用 build-win.py --verify-only）…")
    verify = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "build-win.py"),
            "--verify-only",
            "--tag",
            tag,
        ],
        cwd=str(PROJECT_ROOT),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    # 捕获后重新输出，保证日志顺序确定（子进程直写 stdout 会绕过父进程缓冲）
    sys.stdout.write(verify.stdout)
    if verify.stderr:
        sys.stderr.write(verify.stderr)
    sys.stdout.flush()
    if verify.returncode != 0:
        log("产物校验未通过，拒绝发布。先跑 build-win.py 完成构建。")
        sys.exit(1)


# ============ release notes 生成 ============


def _extract_changelog_section(version: str) -> str | None:
    """从 CHANGELOG.md 抽取 [version] 段落。找不到返回 None。"""
    if not CHANGELOG.exists():
        return None
    text = CHANGELOG.read_text(encoding="utf-8")
    # 匹配 ## [5.1.5] 或 ## [v5.1.5] 或 ## 5.1.5，取到下一个同级 ## 或文件尾
    pattern = re.compile(
        rf"^##\s*\[?v?{re.escape(version)}\]?.*?$(?P<body>.*?)(?=^##\s|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    m = pattern.search(text)
    if not m:
        return None
    body = m.group("body").strip()
    return body or None


def build_notes(version: str, repo: str) -> str:
    """生成 release notes。优先抽 CHANGELOG 对应版本段落，否则用骨架。"""
    tag = f"v{version}"
    today = date.today().isoformat()
    section = _extract_changelog_section(version)

    header = f"# 陆墨 Lumo {tag}\n\n发布日期：{today}\n"

    if section:
        body = f"\n## 本次更新\n\n{section}\n"
        source = "CHANGELOG.md 对应版本段落"
    else:
        body = (
            "\n## 本次更新\n\n"
            "- （待补充：CHANGELOG.md 中尚无本版本段落，发布前请手工补全要点）\n"
            "- 架构与功能说明见仓库根目录 `README.md`\n"
        )
        source = "骨架（CHANGELOG 无对应版本段落）"

    install = (
        "\n## 安装方法\n\n"
        f"1. 在下方 Assets 中下载 `Lumo-Setup-{version}.exe`\n"
        "2. 双击运行，按向导完成安装（可选择安装目录）\n"
        "3. 首次启动后在设置中填入 LLM API key 即可使用\n\n"
        "> 安装包未做代码签名，Windows SmartScreen 可能提示「已保护你的电脑」——\n"
        "> 点「更多信息」→「仍要运行」即可。\n"
    )

    known_items = [
        "- 仅提供 Windows x64 安装包（macOS / Linux 暂需从源码构建）",
        "- 未做代码签名，首次运行会有 SmartScreen 提示（正常现象）",
    ]
    known_items.append("- 其余已知问题待补充")
    known = "\n## 已知问题\n\n" + "\n".join(known_items) + "\n"

    footer = (
        "\n---\n\n"
        f"- 校验与反馈：请到 [Issues](https://github.com/{repo}/issues) 提交\n"
        f"- 源码：https://github.com/{repo}\n"
    )

    notes = header + body + install + known + footer
    log(f"release notes 生成完毕（来源：{source}，{len(notes.splitlines())} 行）")
    return notes


# ============ 敏感词扫描 ============


def load_blocklist() -> list[tuple[int, str, re.Pattern[str]]]:
    """加载黑名单，返回 [(行号, 原文, 编译后的正则)]。占位符与注释跳过。"""
    if not BLOCKLIST.exists():
        log(f"警告：未找到黑名单 {BLOCKLIST.relative_to(PROJECT_ROOT)}，跳过扫描（不建议）")
        return []

    rules: list[tuple[int, str, re.Pattern[str]]] = []
    for lineno, raw in enumerate(BLOCKLIST.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # 未替换的占位符不生效
        if line.startswith("<") and line.endswith(">"):
            continue
        try:
            rules.append((lineno, line, re.compile(line, re.IGNORECASE)))
        except re.error as exc:
            log(f"黑名单第 {lineno} 行正则非法，已跳过：{line!r}（{exc}）")
    return rules


def scan_notes(notes: str) -> list[tuple[int, str, str]]:
    """扫描 notes，返回命中列表 [(行号, 违规行内容, 命中的规则)]"""
    hits: list[tuple[int, str, str]] = []
    rules = load_blocklist()
    if not rules:
        return hits

    for lineno, line in enumerate(notes.splitlines(), start=1):
        for rule_lineno, rule_text, pattern in rules:
            if pattern.search(line):
                hits.append((lineno, line.strip(), f"规则#{rule_lineno} {rule_text}"))
    return hits


def guard_privacy(notes: str) -> None:
    """隐私铁律：命中即中止发布。"""
    hits = scan_notes(notes)
    if not hits:
        log("敏感词扫描：未命中 ✓")
        return

    print()
    print("=" * 72)
    print("  敏感词扫描命中 —— 发布已中止")
    print("=" * 72)
    for lineno, content, rule in hits:
        print(f"  notes 第 {lineno} 行：{content}")
        print(f"    命中规则：{rule}")
    print("-" * 72)
    print(f"  共 {len(hits)} 处命中。请清理 notes 后重跑；规则可在")
    print(f"  {BLOCKLIST.relative_to(PROJECT_ROOT)} 中调整。")
    print("=" * 72)
    sys.exit(1)


# ============ 发布 ============


def collect_installers() -> list[Path]:
    """收集 release/ 下的 NSIS 安装包（.exe 直传，不压缩）"""
    if not RELEASE_DIR.is_dir():
        log(f"产物目录不存在：{RELEASE_DIR}")
        sys.exit(1)
    installers = sorted(
        p
        for p in RELEASE_DIR.iterdir()
        if p.is_file() and p.suffix.lower() == ".exe" and not p.name.endswith(".blockmap")
    )
    if not installers:
        log(f"未在 {RELEASE_DIR} 找到任何 .exe 安装包")
        sys.exit(1)
    return installers


def create_draft_release(tag: str, version: str, repo: str, notes_file: Path, installers: list[Path]) -> None:
    """创建 draft release 并上传安装包（.exe 直链，不做 zip）"""
    gh = _find_gh() or "gh"
    title = f"陆墨 v{version}"
    log(f"创建 draft release：{tag} （{title}）")
    run(
        [
            gh,
            "release",
            "create",
            tag,
            "--repo",
            repo,
            "--draft",
            "--title",
            title,
            "--notes-file",
            str(notes_file),
        ]
    )

    for inst in installers:
        size_mib = inst.stat().st_size / 1024 / 1024
        # 显式指定资产名：gh 会把非 ASCII 段剥离（实测「陆墨 Setup 5.1.5.exe」
        # → 「Setup.5.1.5.exe」），导致 notes 里写的名字与实际资产名对不上。
        asset_name = f"Lumo-Setup-{version}.exe"
        log(f"上传资产：{inst.name} → {asset_name}（{size_mib:.0f} MiB）")
        run(
            [
                gh,
                "release",
                "upload",
                tag,
                f"{inst}#{asset_name}",
                "--repo",
                repo,
                "--clobber",
            ]
        )

    print()
    print("=" * 72)
    print(f"  Draft Release 已创建：{tag}")
    print("=" * 72)
    log(f"资产：{asset_name}（本地文件 {installers[0].name}）")
    log(f"审阅地址：https://github.com/{repo}/releases")
    log("状态为 draft —— 请人工过目后到该页面点「Publish release」正式发布。")
    log("（本脚本不会自动 publish。）")
    print("=" * 72)


# ============ 主入口 ============


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="陆墨 Windows 安装包发布脚本（GitHub Release，draft 起步）")
    parser.add_argument("--tag", required=True, metavar="vX.Y.Z", help="发布版本号（annotated git tag）")
    parser.add_argument("--dry-run", action="store_true", help="只做校验与生成 notes，不发任何网络请求")
    parser.add_argument("--notes-only", action="store_true", help="只生成 notes 文件，不创建 release")
    parser.add_argument("--repo", help="覆盖 GitHub 仓库（owner/repo），默认从 origin 解析")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    version, repo = verify_release_preconditions(args.tag)
    if args.repo:
        repo = args.repo
        log(f"仓库被手动覆盖为：{repo}")

    # 生成 notes + 隐私扫描（无论是否 dry-run 都做）
    notes = build_notes(version, repo)
    guard_privacy(notes)

    NOTES_OUT.mkdir(parents=True, exist_ok=True)
    notes_file = NOTES_OUT / f"release-notes-{args.tag}.md"
    notes_file.write_text(notes, encoding="utf-8")
    log(f"notes 已写入：{notes_file.relative_to(PROJECT_ROOT)}")

    if args.dry_run:
        print()
        print("=" * 72)
        print("  DRY RUN —— 校验与 notes 生成完毕，未发送任何请求")
        print("=" * 72)
        print(notes)
        print("=" * 72)
        return

    if args.notes_only:
        log("--notes-only：不创建 release，结束。")
        return

    # 真要发布：先验产物（本地、快），再查 gh，最后才动网络
    verify_artifacts_ready(args.tag)
    require_gh()
    installers = collect_installers()
    create_draft_release(args.tag, version, repo, notes_file, installers)


if __name__ == "__main__":
    main()
