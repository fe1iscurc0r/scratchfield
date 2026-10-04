"""外来文件接入审查门 —— 静态检查 + PASS/WARN/FAIL 结论。

供应链铁律「外来文件默认不信任」的半自动落地：
  输入外来文件/仓库路径 → 递归静态扫描 → 检查项：
    - 来源（可选 source 参数，黑名单/未验证标记）
    - 许可（LICENSE 存在性 + SPDX 识别 + NOASSERTION，复用 liccheck.py）
    - 代码危险模式（AST / 正则静态检查，不执行代码）
    - 大文件 / 二进制 blob
  → 输出 PASS / WARN / FAIL + 风险清单。

判定：
  - FAIL：危险代码模式命中，或目标不存在（硬阻断）
  - WARN：无 LICENSE / 许可无法断言 / 大文件 / 二进制 blob / 来源未验证或黑名单
  - PASS：以上均无

不删改外来文件，只出报告。纯 stdlib。
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

from mcpserver.trace_audit import liccheck
from mcpserver.trust_layer import BLACKLIST_SOURCES, TRUSTED_SOURCES

# 递归扫描时跳过的目录
SKIP_DIRS: frozenset[str] = frozenset({
    ".git", ".hg", ".svn", "__pycache__", "node_modules",
    ".venv", "venv", ".tox", "dist", "build",
})

# 危险 import 模块（导入即具备危险能力，os/urllib 走方法级判定）
DANGEROUS_IMPORTS: frozenset[str] = frozenset({
    "subprocess", "socket", "requests", "aiohttp", "websocket", "httpx",
})

# 危险内建函数名（直接调用即危险）
DANGEROUS_NAMES: frozenset[str] = frozenset({"exec", "eval", "__import__", "compile"})

# 危险模块方法（module.attr 调用）
DANGEROUS_METHODS: dict[str, frozenset[str]] = {
    "os": frozenset({"system", "popen", "spawnl", "spawnlp", "spawnv", "execv", "execl"}),
    "subprocess": frozenset({
        "Popen", "run", "call", "check_call", "check_output", "getoutput", "getstatusoutput",
    }),
    "socket": frozenset({"socket", "connect", "connect_ex", "create_connection"}),
    "requests": frozenset({"get", "post", "put", "delete", "patch", "request", "head", "options"}),
    "urllib": frozenset({"urlopen", "urlretrieve"}),
    "urllib.request": frozenset({"urlopen", "urlretrieve"}),
    "httpx": frozenset({"get", "post", "put", "delete", "request"}),
    "aiohttp": frozenset({"ClientSession", "request"}),
    "websocket": frozenset({"create_connection", "WebSocket"}),
}

# 文本脚本正则兜底（非 .py 的可执行脚本）
_REGEX_DANGEROUS = re.compile(
    r"\b(exec|eval|__import__)\s*\(|\bsubprocess\b|\bos\.(system|popen)\b"
    r"|\burlopen\b|\bsocket\.(socket|connect|create_connection)\b",
    re.IGNORECASE,
)

# 做危险模式扫描的扩展名（代码/可执行脚本）
CODE_EXTENSIONS: frozenset[str] = frozenset({
    ".py", ".sh", ".ps1", ".bat", ".cmd", ".js", ".ts", ".mjs", ".cjs",
})

# 默认大文件阈值（字节）
DEFAULT_MAX_FILE_SIZE: int = 1024 * 1024  # 1MB


@dataclass
class GateRisk:
    kind: str       # source / license / danger / large / binary / target
    message: str
    path: str | None = None


@dataclass
class GateReport:
    """审查门报告：verdict + 风险清单 + 扫描统计。"""

    verdict: str = "PASS"
    risks: list[GateRisk] = field(default_factory=list)
    files_scanned: int = 0
    target: str = ""
    _seen: set[tuple] = field(default_factory=set, repr=False, compare=False)

    def add_risk(self, kind: str, message: str, path: str | None = None) -> None:
        key = (kind, message, path)
        if key in self._seen:
            return
        self._seen.add(key)
        self.risks.append(GateRisk(kind, message, path))

    def to_text(self) -> str:
        lines = [
            f"GATE VERDICT: {self.verdict}",
            f"target: {self.target}",
            f"files_scanned: {self.files_scanned}",
        ]
        if not self.risks:
            lines.append("RISK[none]: 未发现风险")
        for r in self.risks:
            suffix = f" ({r.path})" if r.path else ""
            lines.append(f"RISK[{r.kind}]: {r.message}{suffix}")
        return "\n".join(lines)

    def __str__(self) -> str:
        return self.to_text()


def _finalize(report: GateReport) -> str:
    kinds = {r.kind for r in report.risks}
    if kinds & {"danger", "target"}:
        return "FAIL"
    if kinds & {"license", "large", "binary", "source"}:
        return "WARN"
    return "PASS"


def _check_source(source: str, report: GateReport) -> None:
    if not source or source == "local":
        return  # 本地/未提供 → 溯源在链外，不额外降级
    s = source.lower()
    for bad in BLACKLIST_SOURCES:
        if s.startswith(bad.lower()):
            report.add_risk("source", f"黑名单来源: {source}")
            return
    for good in TRUSTED_SOURCES:
        if s.startswith(good.lower()):
            return  # 可信源，无风险
    report.add_risk("source", f"未验证来源: {source}")


def _walk_files(root: Path):
    """递归产出文件路径（跳过 SKIP_DIRS），root 为文件时直接产出自身。"""
    if root.is_file():
        yield root
        return
    stack = [root]
    while stack:
        d = stack.pop()
        try:
            entries = sorted(d.iterdir())
        except OSError:
            continue
        for e in entries:
            if e.is_dir():
                if e.name not in SKIP_DIRS:
                    stack.append(e)
            elif e.is_file():
                yield e


def _is_binary(path: Path, n: int = 1024) -> bool:
    try:
        with open(path, "rb") as f:
            return b"\x00" in f.read(n)
    except OSError:
        return False


def _attr_module(f: ast.Attribute) -> str:
    """返回调用对象链的模块部分（去掉最后的方法名）。

    os.system → "os"；urllib.request.urlopen → "urllib.request"。
    """
    parts: list[str] = []
    node: ast.AST = f
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        parts.reverse()
        return ".".join(parts[:-1]) if len(parts) > 1 else parts[0]
    return ""


def _check_import(module: str, path: Path, report: GateReport) -> None:
    top = module.split(".")[0]
    if top in DANGEROUS_IMPORTS:
        report.add_risk("danger", f"危险 import: {module}", str(path))


def _check_call(node: ast.Call, path: Path, report: GateReport) -> None:
    f = node.func
    if isinstance(f, ast.Name):
        if f.id in DANGEROUS_NAMES:
            report.add_risk("danger", f"危险调用: {f.id}", str(path))
    elif isinstance(f, ast.Attribute):
        mod = _attr_module(f)
        for m, attrs in DANGEROUS_METHODS.items():
            if mod == m and f.attr in attrs:
                report.add_risk("danger", f"危险调用: {m}.{f.attr}", str(path))


def _scan_python(path: Path, report: GateReport) -> None:
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    try:
        tree = ast.parse(src, filename=str(path))
    except SyntaxError:
        _scan_text(path, report)  # 解析失败回退正则
        return
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                _check_import(a.name, path, report)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                _check_import(node.module, path, report)
        elif isinstance(node, ast.Call):
            _check_call(node, path, report)


def _scan_text(path: Path, report: GateReport) -> None:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    found = {m.group(0).strip() for m in _REGEX_DANGEROUS.finditer(text)}
    for pat in sorted(found):
        report.add_risk("danger", f"危险模式: {pat}", str(path))


def _scan_file(path: Path, report: GateReport, max_file_size: int) -> None:
    report.files_scanned += 1
    try:
        size = path.stat().st_size
    except OSError:
        return
    if size > max_file_size:
        report.add_risk("large", f"大文件 {size} 字节（阈值 {max_file_size}）", str(path))
    if _is_binary(path):
        report.add_risk("binary", "二进制 blob", str(path))
        return  # 二进制不解析代码
    if path.suffix.lower() in CODE_EXTENSIONS:
        if path.suffix.lower() == ".py":
            _scan_python(path, report)
        else:
            _scan_text(path, report)


def run_gate(path: str | Path, source: str = "local",
             max_file_size: int = DEFAULT_MAX_FILE_SIZE) -> GateReport:
    """对外来文件/仓库路径跑接入审查门，返回 GateReport。"""
    target = Path(path)
    report = GateReport(target=str(target))

    if not target.exists():
        report.add_risk("target", f"目标不存在: {target}")
        report.verdict = "FAIL"
        return report

    _check_source(source, report)

    # 许可核实
    lic = liccheck.check_license(target)
    if not lic.found:
        report.add_risk("license", "无 LICENSE 文件")
    elif lic.noassertion:
        report.add_risk("license", f"许可无法断言（NOASSERTION）: {lic.path}")

    # 文件扫描
    for f in _walk_files(target):
        _scan_file(f, report, max_file_size)

    report.verdict = _finalize(report)
    return report
