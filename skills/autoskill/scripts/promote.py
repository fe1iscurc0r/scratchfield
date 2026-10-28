"""Promote a proposal out of ``_proposed/<ts>/`` and into ``skills/``.

上游是「屏幕采集 → LLM 生成」的产物。改动前这里只看"源在不在、目标在不在"，
一次 ``shutil.move`` 就把没人读过的代码永久挂进猫娘的技能面——技能是会被人照着执行
的东西，转正这一步必须是**显式的人工动作**。

工单 269 T3（P0-8）加了三道闸：

1. **静态审查**：命中可疑模式（起进程、``eval``/``exec``、网络外发、读 ``~/.ssh``
   与 ``.env``、写注册表、``--force`` 类危险参数）即拒。表在 ``_PY_*`` /
   ``_TEXT_PATTERNS`` 里，单测直接断言表本身。
2. **人工放行**：被拒之后只有一个出口——人把那一版内容读完，再带上脚本打印的
   内容摘要 ``--approve-reviewed <sha>`` 重新跑。摘要按 ``{相对路径, 文件 sha256}``
   逐行算，审的内容和转的内容不是同一份就对不上，"批一次"不能覆盖后续修改。
3. **默认 dry-run**：不带 ``--apply`` 只打印将要移动的路径与审查结论，一个文件都不动。

"目标已存在"的报错原样保留（那是正确行为）；退出码新增 2 = 审查未通过，和 1
（找不到提案 / 目标已存在）区分开，方便上层脚本判断是"要人看"还是"用法错"。
"""
import argparse
import ast
import hashlib
import re
import shutil
import sys
from pathlib import Path


class PromoteError(Exception):
    pass


class ReviewRefused(PromoteError):
    """静态审查命中，且没有匹配的人工放行摘要。"""

    def __init__(self, name, report, approved_sha):
        self.name = name
        self.report = report
        self.approved_sha = approved_sha
        super().__init__(
            f"skill {name!r} 未通过静态审查"
            + (f"（放行摘要 {approved_sha} 与当前内容不一致）" if approved_sha else "")
        )


_KINDS = ("new-skills", "composition-recipes")

#: 参与内容摘要的文件上限（单个）。超过只摘要不扫描，避免为一个大二进制把正则跑飞。
_MAX_SCAN_BYTES = 1 << 20

#: 只对这些后缀做模式扫描；其余文件仍然进摘要。
_PY_SUFFIXES = (".py",)
_TEXT_SUFFIXES = (
    ".py", ".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".sh", ".bash", ".zsh", ".ps1", ".psm1", ".bat", ".cmd",
    ".js", ".mjs", ".cjs", ".ts", ".jsx", ".tsx", ".rb", ".pl", ".lua",
)

# ---------------------------------------------------------------- 审查表（单测断言对象）

#: Python 里 import 这些模块即视为"要动本机/要出网"，需要人看一眼。
_PY_DANGEROUS_MODULES = frozenset({
    "subprocess",
    "socket",
    "ssl",
    "ctypes",
    "winreg",
    "smtplib",
    "ftplib",
    "telnetlib",
    "paramiko",
    "urllib",
    "urllib2",
    "urllib3",
    "http",
    "requests",
    "httpx",
    "aiohttp",
})

#: Python 里这些名字被调用即命中（``eval``/``exec`` 之类既能拼代码也能执行）。
_PY_DANGEROUS_CALLS = frozenset({
    "eval",
    "exec",
    "compile",
    "__import__",
    "urlopen",
    "system",
    "popen",
    "startfile",
    "registerserver",
})

#: 文本层（shell / powershell / js / 说明文档里的命令）模式：名字 → 说明。
_TEXT_PATTERNS = {
    "rm -rf": re.compile(r"\brm\s+(?:-[a-zA-Z]\s+)*-?[rR]f?\b", re.I),
    "curl 下载并执行": re.compile(r"\bcurl\b[^\n|;&]*\|\s*(?:ba)?sh\b", re.I),
    "curl/wget 出网": re.compile(r"\b(?:curl|wget)\b", re.I),
    "Invoke-WebRequest": re.compile(
        r"\b(?:Invoke-WebRequest|iwr|Invoke-RestMethod|Start-BitsTransfer)\b", re.I
    ),
    "远端 shell": re.compile(r"\b(?:ssh|scp|sftp|rsh|telnet|nc|netcat)\b", re.I),
    "PowerShell 绕过执行策略": re.compile(r"-ExecutionPolicy\s+Bypass", re.I),
    "--force 类危险参数": re.compile(r"(?:^|[\s\"'])--?force(?:$|[\s\"'=])", re.I),
    "注册表写入": re.compile(r"\b(?:reg\s+(?:add|import|delete)|HKCU|HKLM|New-ItemProperty)\b", re.I),
    "SSH 私钥路径": re.compile(r"(?:~|\$HOME|%USERPROFILE%)[/\\]\.ssh\b|\bid_rsa\b|\bid_ed25519\b", re.I),
    ".env 凭据文件": re.compile(r"(?:^|[\s'\"/\\])\.env(?:\.\w+)?(?:$|[\s'\"/\\])", re.I | re.M),
    "管道给解释器": re.compile(r"\|\s*(?:python(?:\d\.\d+)?|node|bash|sh|zsh|pwsh|powershell)\b", re.I),
}


def _is_escape_link(path: Path) -> bool:
    """路径是否把内容指到目录外。

    只查 ``is_symlink()`` 在这台机器上会漏：Windows 的目录联接点（junction）
    ``is_symlink()`` 返回 False（实测），但 ``rglob`` 会照常递归进去 —— 技能包里
    塞一个 junction 就能把目录外的一大片文件带进转正，而且造它**不需要任何特权**。
    """
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)  # 3.12+ 才有；老解释器按 False 处理
    return bool(is_junction is not None and is_junction())


def _iter_files(source: Path):
    """列出参与摘要的文件；链接/联接点单独报出来（技能包不该带链，链能把内容指到目录外）。"""
    links = []
    files = []
    for path in sorted(source.rglob("*")):
        if _is_escape_link(path):
            links.append(path)
            continue
        if path.is_dir():
            continue
        if path.name == "__pycache__" or path.suffix == ".pyc":
            continue
        files.append(path)
    return files, links


def _scan_python(rel: str, text: str):
    findings = []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        # 语法都过不去的 .py 更该给人看
        return [f"{rel}: 无法解析的 Python 文件"]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                head = alias.name.split(".")[0]
                if head in _PY_DANGEROUS_MODULES:
                    findings.append(f"{rel}:{node.lineno}: import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            head = (node.module or "").split(".")[0]
            if head in _PY_DANGEROUS_MODULES:
                findings.append(f"{rel}:{node.lineno}: from {node.module} import …")
        elif isinstance(node, ast.Call):
            func = node.func
            name = getattr(func, "attr", None) or getattr(func, "id", None)
            if name in _PY_DANGEROUS_CALLS:
                findings.append(f"{rel}:{node.lineno}: 调用 {name}()")
    return findings


def _scan_text(rel: str, text: str):
    findings = []
    for label, pattern in _TEXT_PATTERNS.items():
        match = pattern.search(text)
        if match:
            line = text[: match.start()].count(chr(10)) + 1
            findings.append(f"{rel}:{line}: {label}")
    return findings


def review(source: Path):
    """静态审查 + 内容摘要。返回 ``(digest, findings)``。"""
    files, links = _iter_files(source)
    findings = [
        f"不该出现在技能包里的链接（符号链接/联接点）: {p.relative_to(source).as_posix()}"
        for p in links
    ]
    index = []
    for path in files:
        rel = path.relative_to(source).as_posix()
        data = path.read_bytes()
        index.append(f"{rel}\t{hashlib.sha256(data).hexdigest()}")
        if not any(path.suffix.lower().endswith(suf) for suf in _TEXT_SUFFIXES):
            continue
        if len(data) > _MAX_SCAN_BYTES:
            findings.append(f"{rel}: 超过 1MiB，只进摘要未扫描（请人工确认）")
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            findings.append(f"{rel}: 文本后缀但非 UTF-8，未扫描（请人工确认）")
            continue
        if path.suffix.lower() in _PY_SUFFIXES:
            findings.extend(_scan_python(rel, text))
        else:
            findings.extend(_scan_text(rel, text))
    digest = hashlib.sha256(chr(10).join(sorted(index)).encode("utf-8")).hexdigest()
    return digest, findings


def _approval_matches(approved: str, digest: str) -> bool:
    """放行摘要允许写成 12 位以上的前缀，但必须唯一命中当前摘要。"""
    needle = str(approved or "").strip().lower()
    if len(needle) < 12:
        return False
    return digest.lower().startswith(needle)


def _refused(findings, approved: str, digest: str) -> bool:
    """唯一的拒/放行判定。

    CLI 与 ``promote()`` 共用这一处：两处各写一份的话，改一处漏一处，
    "打印说 REJECTED、函数却把文件搬走"这种分裂就是这么来的。
    """
    return bool(findings) and not _approval_matches(approved, digest)


def find_source(proposed_path, name):
    proposed_path = Path(proposed_path)
    for kind in _KINDS:
        candidate = proposed_path / kind / name
        if candidate.is_dir():
            return candidate
    return None


def review_proposal(proposed_path, skills_dir, name):
    """定位提案、检查目标、跑静态审查。既有两种报错语义原样保留。"""
    source = find_source(proposed_path, name)
    if source is None:
        raise PromoteError(f"proposed skill {name!r} not found under {proposed_path}")
    target = Path(skills_dir) / name
    if target.exists():
        raise PromoteError(f"target {target} already exists")
    digest, findings = review(source)
    return source, target, digest, findings


def promote(proposed_path, skills_dir, name, *, apply=False, approve_reviewed=""):
    """审查 → （可选）移动。``apply=False`` 时一个文件都不动，只回报结论。

    ``PromoteError`` 的两种既有语义保持不变：找不到提案、目标已存在。
    """
    source, target, digest, findings = review_proposal(proposed_path, skills_dir, name)
    if _refused(findings, approve_reviewed, digest):
        raise ReviewRefused(name, (digest, findings), approve_reviewed)
    if not apply:
        return None
    shutil.move(str(source), str(target))
    return target


def _print_plan(name, source, target, digest, findings, *, apply, approved, refused):
    print(f"skill        : {name}")
    print(f"source       : {source}")
    print(f"planned move : {source} -> {target}")
    print(f"content-sha256: {digest}")
    if findings:
        print(f"review       : 命中 {len(findings)} 处可疑模式")
        for line in findings:
            print(f"  - {line}")
        if refused:
            print(
                "verdict      : REJECTED —— 需要人工读过上面每一条，再带 --approve-reviewed <sha> 重跑"
                + (
                    f"（带上的人工放行摘要 {approved[:16]}… 与当前内容不一致：审完又改过，得重审）"
                    if approved
                    else ""
                )
            )
        elif apply:
            print(f"verdict      : 人工放行（{approved[:16]}…）后转正")
    else:
        print("review       : 无可疑模式")
    if not apply and not refused:
        print("verdict      : DRY-RUN —— 没有移动任何文件；确认无误再加 --apply")


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="autoskill-promote",
        description=(
            "Move a proposed skill from _proposed/<ts>/ into skills/. "
            "默认只审查并打印将要移动的路径（dry-run），要真动文件得加 --apply。"
        ),
    )
    parser.add_argument("--proposed", required=True,
                        help="path to the _proposed/<ts>/ directory")
    parser.add_argument("--skills-dir", required=True,
                        help="path to skills/")
    parser.add_argument("--name", required=True, help="skill name to promote")
    parser.add_argument("--apply", action="store_true",
                        help="actually move the proposal (default is dry-run)")
    parser.add_argument("--approve-reviewed", metavar="SHA", default="",
                        help="内容摘要（dry-run 打印的 content-sha256）；静态审查命中时唯一的放行出口")
    args = parser.parse_args(argv)

    try:
        source, target, digest, findings = review_proposal(args.proposed, args.skills_dir, args.name)
        refused = _refused(findings, args.approve_reviewed, digest)
        _print_plan(args.name, source, target, digest, findings,
                    apply=args.apply, approved=args.approve_reviewed, refused=refused)
        if refused:
            return 2
        if not args.apply:
            return 0
        moved = promote(args.proposed, args.skills_dir, args.name,
                        apply=True, approve_reviewed=args.approve_reviewed)
    except ReviewRefused as e:
        print(f"promote refused: {e}", file=sys.stderr)
        return 2
    except PromoteError as e:
        print(f"promote failed: {e}", file=sys.stderr)
        return 1

    print(f"promoted: {args.name} -> {moved}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
