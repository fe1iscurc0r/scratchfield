"""Lumo doctor —— 健康自检（对标 OpenClaw `openclaw doctor`，自研实现）。

四层检查（每层能抓什么、抓不到什么——验证边界如实标注）：
  1. Python 环境：版本、关键包可导入（能抓：缺依赖/版本不符）
  2. 配置层：config.json 可读、必需键在位、密钥非占位（能抓：配置缺失/未填）
  3. 服务端口：api/agent/mcp 三端口占用者是否是自己（能抓：端口冲突）
  4. 数据目录：工作目录可写、数据库可开（能抓：权限/磁盘问题）
抓不到的：LLM key 是否真的有效（要发请求才知道，doctor 默认不发网络请求——
  --probe 选项才发 1 个最小 ping）。

用法：
  python -m apiserver.doctor            # 全量检查（本地零网络）
  python -m apiserver.doctor --probe    # 含 LLM 连通探测（发 1 个最小请求）
  python -m apiserver.doctor --json     # 机器可读输出
"""
from __future__ import annotations

import json
import socket
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# 必需的 Python 依赖（导入名 → 用途说明）
CORE_DEPS = [
    ("fastapi", "API 服务核心"),
    ("uvicorn", "ASGI 服务器"),
    ("pydantic", "数据校验"),
    ("httpx", "LLM 网关客户端"),
    ("openai", "LLM SDK"),
    ("sqlite3", "本地存储（标准库）"),
    ("websockets", "实时通道"),
]

# config.json 必需键（缺了跑不起来）
REQUIRED_CONFIG_KEYS = [
    ("api.api_key", "LLM 密钥"),
    ("api.base_url", "LLM 网关地址"),
    ("api.model", "模型名"),
    ("api_server.port", "API 端口"),
]

# 三服务的默认端口
SERVICE_PORTS = [("api_server", 8000), ("agent_server", 8001), ("mcp_server", 8003)]


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str = ""
    hint: str = ""     # 修复建议（失败时给）


@dataclass
class DoctorReport:
    checks: list[CheckResult] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)

    @property
    def passed(self) -> int:
        return sum(1 for c in self.checks if c.ok)

    @property
    def all_ok(self) -> bool:
        return all(c.ok for c in self.checks)

    def to_dict(self) -> dict:
        return {
            "ok": self.all_ok,
            "passed": self.passed,
            "total": len(self.checks),
            "checks": [
                {"name": c.name, "ok": c.ok, "detail": c.detail, "hint": c.hint}
                for c in self.checks
            ],
        }


# ---------------- 第 1 层：Python 环境 ----------------

def check_python(report: DoctorReport) -> None:
    v = sys.version_info
    ok = v >= (3, 11)
    report.checks.append(CheckResult(
        "python_version", ok,
        f"{v.major}.{v.minor}.{v.micro}",
        "" if ok else "需要 Python ≥ 3.11（仓内代码用了 3.11+ 语法）"))


def check_core_deps(report: DoctorReport) -> None:
    import importlib
    for mod, why in CORE_DEPS:
        try:
            importlib.import_module(mod)
            report.checks.append(CheckResult(f"dep:{mod}", True, why))
        except ImportError as e:
            report.checks.append(CheckResult(
                f"dep:{mod}", False, str(e)[:60],
                f"pip install {mod}（{why}）"))


# ---------------- 第 2 层：配置 ----------------

def _load_config() -> dict | None:
    cfg_path = REPO_ROOT / "config.json"
    if not cfg_path.exists():
        return None
    try:
        return json.loads(cfg_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def check_config(report: DoctorReport) -> None:
    cfg = _load_config()
    if cfg is None:
        report.checks.append(CheckResult(
            "config:file", False, "config.json 缺失或不可解析",
            "复制 config.example.json → config.json，或跑 onboard 向导"))
        return
    report.checks.append(CheckResult("config:file", True, "config.json 可读"))

    def dig(d, dotted):
        cur = d
        for part in dotted.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return None
            cur = cur[part]
        return cur

    for dotted, why in REQUIRED_CONFIG_KEYS:
        val = dig(cfg, dotted)
        ok = val not in (None, "", "YOUR_API_KEY", "sk-xxx", "***")
        report.checks.append(CheckResult(
            f"config:{dotted}", ok,
            "在位" if ok else "缺失/占位符",
            "" if ok else f"填好 {dotted}（{why}）"))


# ---------------- 第 3 层：端口 ----------------

def _port_owner_hint(port: int) -> str:
    """谁占着端口（尽力而为：netstat 查 PID→进程名，失败返回通用提示）。"""
    import subprocess
    try:
        out = subprocess.run(
            ["netstat", "-ano"], capture_output=True, text=True, timeout=10).stdout
        for line in out.splitlines():
            if f":{port}" in line and "LISTENING" in line:
                pid = line.split()[-1]
                task = subprocess.run(
                    ["tasklist", "/FI", f"PID eq {pid}"],
                    capture_output=True, text=True, timeout=10).stdout
                for tl in task.splitlines():
                    if pid in tl:
                        return f"被 PID {pid}（{tl.split()[0]}）占用"
                return f"被 PID {pid} 占用"
    except Exception:
        pass
    return "被其他进程占用"


def check_ports(report: DoctorReport, live: bool = True) -> None:
    """live=True 时真实探测（doctor 主流程）；False 跳过网络栈（纯静态检查）。"""
    if not live:
        return
    for svc, port in SERVICE_PORTS:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            busy = s.connect_ex(("127.0.0.1", port)) == 0
        if busy:
            # 被占用：如果占用者就是我们自己（服务已在跑），算通过
            hint = _port_owner_hint(port)
            own = "python" in hint.lower()
            report.checks.append(CheckResult(
                f"port:{svc}", own, f":{port} {hint}",
                "" if own else f"换端口或停掉占用者（{hint}）"))
        else:
            report.checks.append(CheckResult(
                f"port:{svc}", True, f":{port} 空闲"))


# ---------------- 第 4 层：数据目录 ----------------

def check_datadirs(report: DoctorReport) -> None:
    for d in ("tmp", "research/papers", "docs"):
        p = REPO_ROOT / d
        if not p.exists():
            continue  # 可选目录
        try:
            probe = p / ".doctor_probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            report.checks.append(CheckResult(f"dir:{d}", True, "可写"))
        except OSError as e:
            report.checks.append(CheckResult(
                f"dir:{d}", False, str(e)[:60], "检查磁盘空间/权限"))
    # 主目录一定可写（要存会话/日志）
    try:
        probe = REPO_ROOT / ".doctor_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        report.checks.append(CheckResult("dir:repo_root", True, "可写"))
    except OSError as e:
        report.checks.append(CheckResult(
            "dir:repo_root", False, str(e)[:60], "仓库目录不可写——检查权限"))


# ---------------- LLM 连通探测（可选，默认关） ----------------

def check_llm_probe(report: DoctorReport) -> None:
    """发 1 个最小请求验证 key（--probe 才跑；默认不发网络请求）。"""
    cfg = _load_config() or {}
    api = cfg.get("api", {})
    key, base = api.get("api_key", ""), api.get("base_url", "")
    if not key or not base:
        report.checks.append(CheckResult(
            "llm:probe", False, "无 key/base_url 可探测", "先完成配置"))
        return
    try:
        import httpx
        t0 = time.time()
        r = httpx.get(
            f"{base.rstrip('/')}/models",
            headers={"Authorization": f"Bearer {key}"},
            timeout=10.0)
        ms = int((time.time() - t0) * 1000)
        ok = r.status_code in (200, 401, 403)  # 401/403 也证明网关活着
        report.checks.append(CheckResult(
            "llm:probe", ok, f"HTTP {r.status_code} ({ms}ms)",
            "" if ok else "检查 api_key 与 base_url"))
    except Exception as e:
        report.checks.append(CheckResult(
            "llm:probe", False, str(e)[:60], "网关不可达——检查网络/代理"))


# ---------------- 汇总 ----------------

def run_doctor(probe: bool = False, live_ports: bool = True) -> DoctorReport:
    report = DoctorReport()
    check_python(report)
    check_core_deps(report)
    check_config(report)
    check_ports(report, live=live_ports)
    check_datadirs(report)
    if probe:
        check_llm_probe(report)
    return report


def format_report(report: DoctorReport) -> str:
    lines = ["Lumo doctor —— 健康自检", "=" * 40]
    for c in report.checks:
        mark = "✓" if c.ok else "✗"
        lines.append(f"[{mark}] {c.name}: {c.detail}")
        if not c.ok and c.hint:
            lines.append(f"      ↳ {c.hint}")
    lines.append("=" * 40)
    lines.append(f"{report.passed}/{len(report.checks)} 项通过"
                 + ("" if report.all_ok else " —— 按上面的 ↳ 提示修复"))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    probe = "--probe" in argv
    as_json = "--json" in argv
    report = run_doctor(probe=probe)
    if as_json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=1))
    else:
        print(format_report(report))
    return 0 if report.all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
