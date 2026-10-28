"""工单 241 · agent_governance 核心测试（身份 / 授权 / 审计三件套 + 场景 A/B/C）。

验收口径（工单 §3 验收 1）：``pytest tests/test_agent_governance*.py -q`` 全绿，
覆盖场景 A/B/C + 边界。本文件覆盖三件套本体与三个场景；
接线层（mcp_manager hook / peak_switch re-sign / manifest）在
``tests/test_agent_governance_hook.py``。
"""

from __future__ import annotations

import asyncio
import base64
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from mcpserver.agent_governance import audit
from mcpserver.agent_governance.__main__ import resign, run_scenarios
from mcpserver.agent_governance.authorization import (
    DEFAULT_TTL_S,
    AuthorizationAuthority,
)
from mcpserver.agent_governance.errors import (
    E_AGENT_MISMATCH,
    E_BAD_SIGNATURE,
    E_CONTENT_MISMATCH,
    E_MALFORMED,
    E_MISSING_KEY,
    E_PROVIDER_MISMATCH,
    E_TOKEN_EXPIRED,
    E_TOKEN_MISSING,
    GovernanceError,
)
from mcpserver.agent_governance.governance import handle_handoff
from mcpserver.agent_governance.identity import (
    ENV_ID_KEY,
    IdentitySigner,
    content_digest,
)
from mcpserver.agent_governance.integration import guard_dispatch, wrap_handler

pytestmark = [pytest.mark.core]

REPO_ROOT = Path(__file__).resolve().parent.parent
KEY = b"unit-test-key-0123456789abcdef"
OTHER_KEY = b"attacker-key-fedcba9876543210"
PROVIDER = "MiniMax-M3"


def _code(exc: pytest.ExceptionInfo[GovernanceError]) -> str:
    return exc.value.code


# --------------------------------------------------------------------- 身份层
def test_identity_sign_then_verify_roundtrip() -> None:
    signer = IdentitySigner(KEY)
    env = signer.sign("agent-A", PROVIDER, model=PROVIDER, content="结论：带宽利用率 87%")
    again = signer.verify(env.to_dict(), "结论：带宽利用率 87%")
    assert again.agent_id == "agent-A"
    assert again.provider == PROVIDER
    assert again.content_sha256 == content_digest("结论：带宽利用率 87%")
    assert again.key_id == signer.key_id
    assert len(again.sig) == 64  # HMAC-SHA256 hex


def test_identity_verify_rejects_tampered_content() -> None:
    signer = IdentitySigner(KEY)
    env = signer.sign("agent-A", PROVIDER, content="原始结论")
    with pytest.raises(GovernanceError) as exc:
        signer.verify(env.to_dict(), "被第三方模型注入污染后的结论")
    assert _code(exc) == E_CONTENT_MISMATCH


def test_identity_verify_rejects_foreign_key() -> None:
    """场景 C 的身份层等价物：别的密钥签出来的信封必须被拒。"""
    forged = IdentitySigner(OTHER_KEY).sign("agent-A", PROVIDER, content="冒充 M3 的输出")
    with pytest.raises(GovernanceError) as exc:
        IdentitySigner(KEY).verify(forged.to_dict(), "冒充 M3 的输出")
    assert _code(exc) == E_BAD_SIGNATURE


def test_identity_sig_covers_provider_and_model() -> None:
    """防「降级模型冒充」：把 provider/model 改掉，签名立刻失效。"""
    signer = IdentitySigner(KEY)
    ok = signer.sign("agent-A", PROVIDER, model=PROVIDER, content="x").to_dict()
    for field, value in (("provider", "deepseek-flash"), ("model", "deepseek-flash")):
        tampered = dict(ok)
        tampered[field] = value
        with pytest.raises(GovernanceError) as exc:
            signer.verify(tampered, "x")
        assert _code(exc) == E_BAD_SIGNATURE, field


@pytest.mark.parametrize(
    ("payload", "why"),
    [
        ({"agent_id": "a"}, "缺字段"),
        ("not-a-dict", "非 dict"),
        ({"version": "x"}, "version 非数字"),
    ],
    ids=["missing-fields", "not-a-dict", "bad-version"],
)
def test_identity_verify_rejects_malformed_envelope(payload: object, why: str) -> None:
    with pytest.raises(GovernanceError) as exc:
        IdentitySigner(KEY).verify(payload, "")
    assert _code(exc) == E_MALFORMED, why


def test_identity_from_env_reads_key_and_fails_fast_when_absent() -> None:
    signer = IdentitySigner.from_env(environ={ENV_ID_KEY: "env-key"})
    assert signer.key_id == IdentitySigner("env-key").key_id
    with pytest.raises(GovernanceError) as exc:
        IdentitySigner.from_env(environ={})
    assert _code(exc) == E_MISSING_KEY


# --------------------------------------------------------------------- 授权层
def test_authorization_issue_then_verify_roundtrip() -> None:
    auth = AuthorizationAuthority(KEY)
    token = auth.issue("agent-A", PROVIDER)
    claims = auth.verify(token, agent_id="agent-A", provider=PROVIDER)
    assert claims.agent_id == "agent-A"
    assert claims.provider == PROVIDER
    assert claims.ttl_s == DEFAULT_TTL_S == 3600
    assert claims.nonce and len(claims.nonce) == 16


def test_authorization_default_ttl_is_one_hour_end_to_end() -> None:
    now = datetime(2026, 10, 14, 9, 30, tzinfo=UTC)
    auth = AuthorizationAuthority(KEY)
    token = auth.issue("agent-A", PROVIDER, now=now)
    claims = auth.verify(token, now=now + timedelta(minutes=59) + timedelta(seconds=59))
    assert claims.exp - claims.iat == 3600
    with pytest.raises(GovernanceError) as exc:
        auth.verify(token, now=now + timedelta(hours=1) + timedelta(seconds=1))
    assert _code(exc) == E_TOKEN_EXPIRED


def test_scenario_b_expired_token_is_rejected_with_stable_code() -> None:
    """场景 B：ttl=0 的令牌必须被拒，且错误码稳定可断言。"""
    auth = AuthorizationAuthority(KEY)
    token = auth.issue("agent-A", PROVIDER, ttl_s=0)
    with pytest.raises(GovernanceError) as exc:
        auth.verify(token)
    assert _code(exc) == E_TOKEN_EXPIRED


def test_scenario_c_forged_agent_id_rejected_and_audited(tmp_path: Path) -> None:
    """场景 C：随机密钥伪造的 agent 必须被拒，且审计留下 unauthorized_attempt。"""
    log = tmp_path / "agent_calls.jsonl"
    forged_token = AuthorizationAuthority(OTHER_KEY).issue("agent-forged", PROVIDER)
    with pytest.raises(GovernanceError) as exc:
        AuthorizationAuthority(KEY).verify(forged_token)
    assert _code(exc) == E_BAD_SIGNATURE
    audit.record_unauthorized(exc.value.code, agent_id="agent-forged", path=log)
    assert audit.count_events(log, event=audit.EVENT_UNAUTHORIZED) == 1
    assert audit.read_events(log)[0]["ok"] is False


def test_authorization_agent_and_provider_mismatch_are_distinct_codes() -> None:
    auth = AuthorizationAuthority(KEY)
    token = auth.issue("agent-A", PROVIDER)
    with pytest.raises(GovernanceError) as exc:
        auth.verify(token, agent_id="agent-B")
    assert _code(exc) == E_AGENT_MISMATCH
    with pytest.raises(GovernanceError) as exc:
        auth.verify(token, provider="deepseek-flash")
    assert _code(exc) == E_PROVIDER_MISMATCH


@pytest.mark.parametrize(
    "token",
    ["", "v1", "v2.abc.def", "v1.!!!.???"],
    ids=["empty", "one-part", "bad-version", "bad-base64"],
)
def test_authorization_malformed_token_code(token: str) -> None:
    with pytest.raises(GovernanceError) as exc:
        AuthorizationAuthority(KEY).verify(token)
    assert _code(exc) == E_MALFORMED


def test_authorization_tampered_payload_breaks_signature() -> None:
    """改载荷（把 exp 往后推）→ HMAC 失配，不能靠改字段续命。"""
    auth = AuthorizationAuthority(KEY)
    token = auth.issue("agent-A", PROVIDER)
    version, body, sig = token.split(".")
    raw = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
    payload = json.loads(raw)
    payload["exp"] = payload["exp"] + 86400
    forged_body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    with pytest.raises(GovernanceError) as exc:
        auth.verify(f"{version}.{forged_body}.{sig}")
    assert _code(exc) == E_BAD_SIGNATURE


# --------------------------------------------------------------------- 场景 A
def test_scenario_a_closed_loop_every_hop_verifies(tmp_path: Path) -> None:
    """场景 A：授权链 A→B→C→A 闭环，每一段都能独立验签。"""
    result = run_scenarios(tmp_path, verbose=False)
    scenario = result["A"]
    assert scenario["closed_loop"] is True
    assert len(scenario["hops"]) == 4
    assert all(hop["ok"] for hop in scenario["hops"])
    assert [hop["verified_from"] for hop in scenario["hops"]] == ["agent-A", "agent-A", "agent-B", "agent-C"]


def test_run_scenarios_all_three_pass_and_leave_audit_trail(tmp_path: Path) -> None:
    result = run_scenarios(tmp_path, verbose=False)
    assert result["A"]["closed_loop"] is True
    assert result["B"]["rejected"] is True and result["B"]["code"] == E_TOKEN_EXPIRED
    assert result["C"]["rejected"] is True and result["C"]["code"] == E_BAD_SIGNATURE
    assert result["unauthorized_attempt_count"] == 2


# --------------------------------------------------------------------- 审计层
def test_audit_appends_one_line_per_event(tmp_path: Path) -> None:
    log = tmp_path / "agent_calls.jsonl"
    for i in range(3):
        audit.record(audit.EVENT_AGENT_CALL, agent_id=f"agent-{i}", provider=PROVIDER, path=log)
    lines = log.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    assert [json.loads(line)["agent_id"] for line in lines] == ["agent-0", "agent-1", "agent-2"]
    # 追加语义：第 4 条不得重写前三条
    audit.record(audit.EVENT_AGENT_CALL, agent_id="agent-3", path=log)
    lines = log.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 4 and json.loads(lines[0])["agent_id"] == "agent-0"


def test_audit_source_uses_append_never_json_dump() -> None:
    """工单 §3 验收 4 的静态契约：禁止 `json.dump` 一次性写，必须 append + 每次一行。"""
    source = (REPO_ROOT / "mcpserver" / "agent_governance" / "audit.py").read_text(encoding="utf-8")
    assert "json.dump(" not in source, "审计模块不得出现 json.dump —— 被杀会丢整段历史"
    assert 'open(target, "a"' in source, '审计必须用 append 模式 open(..., "a")'
    assert 'handle.write(line + "\\n")' in source, "必须每次写一行"


def test_audit_writes_lf_only(tmp_path: Path) -> None:
    log = tmp_path / "agent_calls.jsonl"
    audit.record(audit.EVENT_AGENT_CALL, agent_id="agent-A", path=log)
    audit.record_unauthorized(E_TOKEN_MISSING, agent_id="agent-B", path=log)
    raw = log.read_bytes()
    assert raw.count(b"\r\n") == 0
    assert raw.count(b"\n") == 2


def test_audit_tolerates_corrupt_tail_line(tmp_path: Path) -> None:
    """被杀进程最坏只坏末行 —— 读取方必须能吃到前面的完整记录。"""
    log = tmp_path / "agent_calls.jsonl"
    audit.record(audit.EVENT_AGENT_CALL, agent_id="agent-A", path=log)
    audit.record(audit.EVENT_AGENT_CALL, agent_id="agent-B", path=log)
    with open(log, "a", encoding="utf-8", newline="\n") as handle:
        handle.write('{"event": "agent_call", "agent_i')  # 模拟半行
    events = audit.read_events(log)
    assert [e["agent_id"] for e in events] == ["agent-A", "agent-B"]
    assert audit.tail(log, n=1)[0]["agent_id"] == "agent-B"


def test_audit_dir_env_override(tmp_path: Path) -> None:
    assert audit.resolve_audit_dir({}) == Path(audit.DEFAULT_AUDIT_DIR).expanduser()
    override = audit.resolve_audit_dir({audit.ENV_AUDIT_DIR: str(tmp_path)})
    assert override == tmp_path
    assert audit.resolve_audit_path({audit.ENV_AUDIT_DIR: str(tmp_path)}).name == audit.AUDIT_FILENAME


def test_audit_unauthorized_event_shape(tmp_path: Path) -> None:
    log = tmp_path / "agent_calls.jsonl"
    rec = audit.record_unauthorized(E_BAD_SIGNATURE, agent_id="agent-forged", provider=PROVIDER, path=log)
    assert rec["event"] == audit.EVENT_UNAUTHORIZED
    assert rec["ok"] is False
    assert rec["code"] == E_BAD_SIGNATURE
    assert rec["timestamp"].endswith("+00:00")  # 可被 trace_audit 的时间戳解析器吃下


# --------------------------------------------------------------------- 接线层
def test_guard_dispatch_disabled_is_bypass(tmp_path: Path) -> None:
    blocked = guard_dispatch("svc", {}, environ={}, audit_path=tmp_path / "a.jsonl")
    assert blocked is None
    assert not (tmp_path / "a.jsonl").exists(), "旁路时不得碰审计"


def test_guard_dispatch_enabled_without_token_is_blocked(tmp_path: Path) -> None:
    environ = {"AGENT_GOVERNANCE": "1", "HERMES_AGENT_ID_KEY": KEY.decode()}
    blocked = guard_dispatch("svc", {}, environ=environ, audit_path=tmp_path / "a.jsonl")
    payload = json.loads(blocked)
    assert payload["status"] == "error"
    assert payload["error_type"] == "governance_required"
    assert payload["code"] == E_TOKEN_MISSING
    assert audit.count_events(tmp_path / "a.jsonl", event=audit.EVENT_UNAUTHORIZED) == 1


def test_guard_dispatch_enabled_with_valid_token_records_agent_call(tmp_path: Path) -> None:
    log = tmp_path / "a.jsonl"
    environ = {"AGENT_GOVERNANCE": "on", "HERMES_AGENT_ID_KEY": KEY.decode()}
    token = AuthorizationAuthority(KEY).issue("agent-A", PROVIDER)
    call = {"tool": "x", "_gov_token": token, "_gov_agent_id": "agent-A", "_gov_provider": PROVIDER}
    assert guard_dispatch("svc", call, environ=environ, audit_path=log) is None
    events = audit.read_events(log)
    assert [e["event"] for e in events] == [audit.EVENT_AGENT_CALL]
    assert events[0]["agent_id"] == "agent-A"


def test_guard_dispatch_expired_token_is_denied_with_code(tmp_path: Path) -> None:
    log = tmp_path / "a.jsonl"
    environ = {"AGENT_GOVERNANCE": "true", "HERMES_AGENT_ID_KEY": KEY.decode()}
    token = AuthorizationAuthority(KEY).issue("agent-A", PROVIDER, ttl_s=0)
    call = {"params": {"_gov_token": token, "_gov_agent_id": "agent-A"}}
    payload = json.loads(guard_dispatch("svc", call, environ=environ, audit_path=log))
    assert payload["error_type"] == "governance_denied"
    assert payload["code"] == E_TOKEN_EXPIRED
    assert audit.count_events(log, event=audit.EVENT_UNAUTHORIZED) == 1


def test_guard_dispatch_enabled_without_key_is_fail_closed(tmp_path: Path) -> None:
    """启用治理但密钥缺失 → 拒绝（fail-closed），不是静默放行。"""
    blocked = guard_dispatch(
        "svc",
        {"_gov_token": "v1.x.y"},
        environ={"AGENT_GOVERNANCE": "1"},
        audit_path=tmp_path / "a.jsonl",
    )
    assert json.loads(blocked)["code"] == E_MISSING_KEY


def test_wrap_handler_blocks_before_calling_handler(tmp_path: Path) -> None:
    calls: list[dict] = []

    def handler(tool_call: dict) -> str:
        calls.append(tool_call)
        return "executed"

    wrapped = wrap_handler(
        "svc",
        handler,
        environ={"AGENT_GOVERNANCE": "1", "HERMES_AGENT_ID_KEY": KEY.decode()},
        audit_path=tmp_path / "a.jsonl",
    )
    blocked = wrapped({"tool": "x"})
    assert calls == [], "被拒时不得调用真实 handler"
    assert json.loads(blocked)["code"] == E_TOKEN_MISSING
    token = AuthorizationAuthority(KEY).issue("agent-A", PROVIDER)
    assert wrapped({"tool": "x", "_gov_token": token, "_gov_agent_id": "agent-A"}) == "executed"
    assert len(calls) == 1


# --------------------------------------------------------------------- MCP agent 适配
def test_governance_agent_sign_and_verify_tools() -> None:
    key = KEY.decode()
    signed = json.loads(
        asyncio.run(
            handle_handoff(
                {"tool": "sign_output", "params": {"agent_id": "a", "provider": PROVIDER, "content": "c", "key": key}}
            )
        )
    )
    assert signed["status"] == "ok"
    envelope = signed["data"]
    checked = json.loads(
        asyncio.run(handle_handoff({"tool": "verify_output", "params": {"envelope": envelope, "content": "c", "key": key}}))
    )
    assert checked["status"] == "ok"
    bad = json.loads(
        asyncio.run(
            handle_handoff(
                {"tool": "verify_output", "params": {"envelope": envelope, "content": "tampered", "key": key}}
            )
        )
    )
    assert bad["status"] == "error" and bad["code"] == E_CONTENT_MISMATCH


def test_governance_agent_unknown_tool_returns_json_not_raise() -> None:
    payload = json.loads(asyncio.run(handle_handoff({"tool": "no_such_tool", "params": {}})))
    assert payload["status"] == "error"
    assert payload["error_type"] == "unknown_tool"
    assert "sign_output" in payload["available"]


def test_governance_agent_missing_key_is_structured_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_ID_KEY, raising=False)
    payload = json.loads(
        asyncio.run(handle_handoff({"tool": "issue_token", "params": {"agent_id": "a", "provider": PROVIDER}}))
    )
    assert payload["status"] == "error" and payload["code"] == E_MISSING_KEY


# --------------------------------------------------------------------- re-sign
def test_resign_updates_provider_and_counts(tmp_path: Path) -> None:
    """峰谷切换后重签：envelope 换成新 provider 签的，计数可用于日志指标。"""
    audit_dir = tmp_path
    pending = tmp_path / "pending_tasks.jsonl"
    old = IdentitySigner(KEY).sign("agent-A", "deepseek-flash", model="deepseek-flash", content="任务载荷")
    rows = [
        {"task_id": "t-1", "agent_id": "agent-A", "content": "任务载荷", "provider": "deepseek-flash", "envelope": old.to_dict()},
        {"task_id": "t-2", "agent_id": "agent-B", "content": "另一条", "provider": "deepseek-flash"},
    ]
    pending.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows), encoding="utf-8", newline="\n")

    count = resign("MiniMax-M3", pending=pending, audit_dir=audit_dir, key=KEY)
    assert count == 2
    updated = [json.loads(line) for line in pending.read_text(encoding="utf-8").splitlines()]
    assert [row["provider"] for row in updated] == ["MiniMax-M3", "MiniMax-M3"]
    for row in updated:
        verified = IdentitySigner(KEY).verify(row["envelope"], row["content"])
        assert verified.provider == "MiniMax-M3"
        assert row["re_signed_at"].endswith("+00:00")
    events = audit.read_events(audit_dir / audit.AUDIT_FILENAME, limit=2)
    assert [e["event"] for e in events] == [audit.EVENT_RE_SIGN] * 2
    assert events[0]["detail"]["from_provider"] == "deepseek-flash"
    assert events[0]["detail"]["to_provider"] == "MiniMax-M3"
    assert pending.read_bytes().count(b"\r\n") == 0


def test_resign_without_pending_file_is_zero_not_error(tmp_path: Path) -> None:
    count = resign("MiniMax-M3", pending=tmp_path / "missing.jsonl", audit_dir=tmp_path, key=KEY)
    assert count == 0
    assert not (tmp_path / "missing.jsonl").exists()


def test_resign_dry_run_does_not_rewrite_pending(tmp_path: Path) -> None:
    pending = tmp_path / "pending_tasks.jsonl"
    original = json.dumps({"task_id": "t-1", "agent_id": "agent-A", "content": "x", "provider": "deepseek-flash"}) + "\n"
    pending.write_text(original, encoding="utf-8", newline="\n")
    count = resign("MiniMax-M3", pending=pending, audit_dir=tmp_path, key=KEY, dry_run=True)
    assert count == 1
    assert pending.read_text(encoding="utf-8") == original
