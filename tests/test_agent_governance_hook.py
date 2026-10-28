"""工单 241 · 接线层测试（mcp_manager hook / peak_switch re-sign / manifest 一致性）。

分两类：

* **静态契约**：hook 三行一字不差地出现在 ``mcpserver/mcp_manager.py`` 里 ——
  接线被删会被抓（自指式维护，同仓 ``.github/workflows/ci.yml`` 注释的做法）。
* **行为契约**：真的 import ``mcpserver.mcp_manager`` 并调 ``unified_call``，
  证明「关闭时行为与改造前一字不差」「开启时真的拦得住」。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from mcpserver.agent_governance import audit
from mcpserver.agent_governance.authorization import AuthorizationAuthority
from mcpserver.agent_governance.governance import DISPATCH
from mcpserver.agent_governance.integration import (
    ENV_ENABLE,
    HOOK_CALL_SITE,
    HOOK_COMMENT,
    HOOK_LINES,
)

pytestmark = [pytest.mark.core]

REPO_ROOT = Path(__file__).resolve().parent.parent
MCP_MANAGER = REPO_ROOT / HOOK_CALL_SITE
PEAK_SWITCH = REPO_ROOT / "tools" / "peak_switch.sh"
MANIFEST = REPO_ROOT / "mcpserver" / "agent_governance" / "agent-manifest.json"

KEY = b"unit-test-key-0123456789abcdef"
PROVIDER = "MiniMax-M3"
LEGACY_NOT_FOUND = "未找到服务"
RESULT_MARKER = "@RESULT@"


# ------------------------------------------------------------------ 静态契约
def test_mcp_manager_contains_gated_hook_lines() -> None:
    source = MCP_MANAGER.read_text(encoding="utf-8")
    assert HOOK_COMMENT in source, "接线注释丢失 —— hook 可能被误删"
    for line in HOOK_LINES:
        assert line in source, f"接线的这一行不见了: {line!r}"


def test_mcp_manager_checks_gate_before_importing_governance() -> None:
    """门控必须在 import 之前 —— 否则关闭治理时也会引入依赖/开销。"""
    source = MCP_MANAGER.read_text(encoding="utf-8")
    gate_at = source.index('os.environ.get("AGENT_GOVERNANCE"')
    import_at = source.index("from mcpserver.agent_governance.integration import guard_dispatch")
    assert gate_at < import_at, "必须先判开关再 import 治理模块"
    assert "fail-closed" in source


# ------------------------------------------------------------------ 行为契约
def _run_unified_call(env_extra: dict[str, str], tool_call_json: str = "{}") -> tuple[str, str]:
    """在子进程里真调一次 ``unified_call``，返回 (标记行解析出的结果, 完整 stdout)。"""
    script = (
        "import asyncio, json\n"
        "from mcpserver.mcp_manager import get_mcp_manager\n"
        f"call = json.loads({tool_call_json!r})\n"
        "out = asyncio.run(get_mcp_manager().unified_call('no-such-service-241', call))\n"
        f"print({RESULT_MARKER!r} + json.dumps({{'out': out}}, ensure_ascii=False))\n"
    )
    env = dict(os.environ)
    for key in (ENV_ENABLE, "AGENT_GOVERNANCE_TOKEN", "AGENT_GOVERNANCE_AGENT_ID", "AGENT_GOVERNANCE_PROVIDER", audit.ENV_AUDIT_DIR):
        env.pop(key, None)
    env.update(env_extra)
    proc = subprocess.run(
        [sys.executable, "-c", script],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr[-3000:]
    for line in proc.stdout.splitlines():
        if line.startswith(RESULT_MARKER):
            return json.loads(line[len(RESULT_MARKER) :])["out"], proc.stdout
    raise AssertionError(f"子进程未产出结果标记；stdout 尾部={proc.stdout[-2000:]!r}")


def test_hook_disabled_keeps_legacy_behaviour_and_touches_no_audit(tmp_path: Path) -> None:
    """关闭（默认）时：行为与改造前完全一致，且不产生任何审计副作用。"""
    audit_dir = tmp_path / "audit"
    out, _ = _run_unified_call({audit.ENV_AUDIT_DIR: str(audit_dir)})
    assert LEGACY_NOT_FOUND in out, out
    assert not audit_dir.exists(), "旁路时不得创建审计目录"


def test_hook_enabled_without_token_is_blocked() -> None:
    out, _ = _run_unified_call({ENV_ENABLE: "1", "HERMES_AGENT_ID_KEY": KEY.decode()})
    payload = json.loads(out)
    assert payload["status"] == "error"
    assert payload["error_type"] == "governance_required"
    assert payload["code"] == "GOV_TOKEN_MISSING"


def test_hook_enabled_with_valid_token_passes_through_and_audits(tmp_path: Path) -> None:
    """带合法令牌：放行到原有路由（此处服务不存在 → 原报错），并留下 agent_call 审计。"""
    audit_dir = tmp_path / "audit"
    token = AuthorizationAuthority(KEY).issue("agent-A", PROVIDER)
    out, _ = _run_unified_call(
        {
            ENV_ENABLE: "on",
            "HERMES_AGENT_ID_KEY": KEY.decode(),
            "AGENT_GOVERNANCE_TOKEN": token,
            audit.ENV_AUDIT_DIR: str(audit_dir),
        }
    )
    assert LEGACY_NOT_FOUND in out, out
    events = audit.read_events(audit_dir / audit.AUDIT_FILENAME)
    assert [e["event"] for e in events] == [audit.EVENT_AGENT_CALL]
    assert events[0]["agent_id"] == "agent-A"


def test_hook_enabled_with_tampered_token_is_denied(tmp_path: Path) -> None:
    audit_dir = tmp_path / "audit"
    forged = AuthorizationAuthority(b"attacker-key").issue("agent-forged", PROVIDER)
    out, _ = _run_unified_call(
        {
            ENV_ENABLE: "1",
            "HERMES_AGENT_ID_KEY": KEY.decode(),
            "AGENT_GOVERNANCE_TOKEN": forged,
            audit.ENV_AUDIT_DIR: str(audit_dir),
        }
    )
    payload = json.loads(out)
    assert payload["error_type"] == "governance_denied"
    assert payload["code"] == "GOV_BAD_SIGNATURE"
    assert audit.count_events(audit_dir / audit.AUDIT_FILENAME, event=audit.EVENT_UNAUTHORIZED) == 1


# ------------------------------------------------------------------ peak_switch re-sign
def _sh_exe() -> str:
    exe = shutil.which("sh")
    if not exe:
        pytest.skip("本机无 POSIX sh，无法执行 tools/peak_switch.sh")
    return exe


def _write_exe(path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8", newline="")
    path.chmod(0o755)


def _switch_harness(tmp_path: Path, snapshot: str = "1 09 30") -> tuple[dict[str, str], Path, Path]:
    """假 date / 假 hermes / 假 rekey 脚本，返回 (env, hermes 调用日志, rekey 调用日志)。"""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_exe(bin_dir / "date", '#!/bin/sh\nprintf "%s\\n" "' + snapshot + '"\n')
    hermes_log = tmp_path / "hermes.log"
    _write_exe(bin_dir / "hermes", '#!/bin/sh\nprintf "%s\\n" "$*" >> "$HERMES_CALL_LOG"\n')
    rekey_log = tmp_path / "rekey.log"
    rekey = bin_dir / "fake_rekey.sh"
    _write_exe(
        rekey,
        '#!/bin/sh\nprintf "%s\\n" "$*" >> "$REKEY_CALL_LOG"\nprintf "re-sign count: 2\\n"\n',
    )
    env = dict(os.environ)
    env["PATH"] = str(bin_dir) + os.pathsep + env["PATH"]
    env["HERMES_CALL_LOG"] = str(hermes_log)
    env["REKEY_CALL_LOG"] = str(rekey_log)
    env["AGENT_REKEY_BIN"] = str(rekey)
    for key in ("PEAK_MODEL", "VALLEY_MODEL", "CONFIG_KEYS", "HERMES_BIN", "DATE_BIN", "AGENT_REKEY"):
        env.pop(key, None)
    return env, hermes_log, rekey_log


def _run_switch(args: list[str], env: dict[str, str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [_sh_exe(), PEAK_SWITCH.as_posix(), *args],
        env=env,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def _lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def test_peak_switch_default_off_never_rekeys(tmp_path: Path) -> None:
    env, hermes_log, rekey_log = _switch_harness(tmp_path)
    result = _run_switch([], env, tmp_path)
    assert result.returncode == 0, result.stderr
    assert _lines(hermes_log) == [f"config set model.default {PROVIDER}"]
    assert _lines(rekey_log) == [], "默认关时不得调用重签"
    assert "re-sign" not in result.stdout


@pytest.mark.parametrize("trigger", [["--rekey"], ["AGENT_REKEY=1"]], ids=["flag", "env"])
def test_peak_switch_rekey_invokes_and_reports_count(tmp_path: Path, trigger: list[str]) -> None:
    env, hermes_log, rekey_log = _switch_harness(tmp_path)
    args: list[str] = []
    if "=" in trigger[0]:
        name, value = trigger[0].split("=", 1)
        env[name] = value
    else:
        args = trigger
    result = _run_switch(args, env, tmp_path)
    assert result.returncode == 0, result.stderr
    assert _lines(rekey_log) == [PROVIDER], "重签脚本必须收到新 provider"
    assert "re-sign count: 2" in result.stdout, "切换日志必须带 re-sign count 指标"
    assert _lines(hermes_log) == [f"config set model.default {PROVIDER}"]


def test_peak_switch_rekey_in_dry_run_prints_without_running(tmp_path: Path) -> None:
    env, hermes_log, rekey_log = _switch_harness(tmp_path)
    result = _run_switch(["--dry-run", "--rekey"], env, tmp_path)
    assert result.returncode == 0, result.stderr
    assert "[dry-run]" in result.stdout
    assert _lines(hermes_log) == [] and _lines(rekey_log) == []


def test_peak_switch_rekey_missing_binary_warns_but_succeeds(tmp_path: Path) -> None:
    env, _, _ = _switch_harness(tmp_path)
    env["AGENT_REKEY_BIN"] = str(tmp_path / "nope.sh")
    result = _run_switch(["--rekey"], env, tmp_path)
    assert result.returncode == 0, result.stderr
    assert "跳过 re-sign" in result.stderr


def test_peak_switch_unknown_flag_still_exits_2(tmp_path: Path) -> None:
    env, hermes_log, rekey_log = _switch_harness(tmp_path)
    result = _run_switch(["--bogus"], env, tmp_path)
    assert result.returncode == 2
    assert _lines(hermes_log) == [] and _lines(rekey_log) == []


# ------------------------------------------------------------------ manifest 一致性
def test_manifest_entrypoint_class_importable_and_dispatchable() -> None:
    import importlib

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    entry = manifest["entryPoint"]
    module = importlib.import_module(entry["module"])
    klass = getattr(module, entry["class"])
    assert hasattr(klass(), "handle_handoff"), "MCP 路由要求 entryPoint 类带 handle_handoff"
    assert manifest["agentType"] == "mcp"
    assert manifest["name"] == "agent_governance"


def test_manifest_tools_match_dispatch_table() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    declared = sorted(tool["name"] for tool in manifest["tools"])
    assert declared == sorted(DISPATCH), "manifest 与 DISPATCH 表必须一一对应"
    assert len(declared) >= 6


def test_agent_rekey_script_is_lf_and_posix_executable() -> None:
    script = REPO_ROOT / "tools" / "agent_rekey.sh"
    raw = script.read_bytes()
    assert raw.count(b"\r\n") == 0, "*.sh 必须 LF（.gitattributes: *.sh eol=lf）"
    assert raw.startswith(b"#!/bin/sh\n")


def test_audit_default_dir_matches_workorder() -> None:
    """默认落点必须与工单一致；本机没有 ~/.hermes 时才靠 AGENT_AUDIT_DIR 覆盖。"""
    assert audit.DEFAULT_AUDIT_DIR == "~/.hermes/audit"
    assert audit.AUDIT_FILENAME == "agent_calls.jsonl"
