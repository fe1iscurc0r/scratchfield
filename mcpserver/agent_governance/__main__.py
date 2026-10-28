"""agent_governance CLI —— 可观测验证入口（工单 241 任务二 场景 A/B/C）。

用法::

    python -m mcpserver.agent_governance demo                 # 跑场景 A/B/C，打印证据
    python -m mcpserver.agent_governance selftest             # 同上，失败退出码非 0
    python -m mcpserver.agent_governance audit-tail -n 5
    python -m mcpserver.agent_governance resign --provider MiniMax-M3

``resign`` 供 ``tools/agent_rekey.sh`` 在峰谷切换后调用：把挂起任务的签名换成
新 provider 签的，并输出 ``re-sign count: N``（工单 §2 任务三）。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from mcpserver.agent_governance import audit
from mcpserver.agent_governance.authorization import AuthorizationAuthority
from mcpserver.agent_governance.errors import E_MISSING_KEY, E_TOKEN_EXPIRED, GovernanceError
from mcpserver.agent_governance.identity import ENV_ID_KEY, IdentitySigner, utc_now_iso

DEMO_KEY = b"workorder-241-demo-key-not-for-production"
PENDING_FILENAME = "pending_tasks.jsonl"


# --------------------------------------------------------------------------- 场景
def scenario_a(signer: IdentitySigner, audit_dir: Path) -> dict[str, Any]:
    """场景 A：授权链 A→B→C→A 闭环签名往返，每段都能独立验签。"""
    hops: list[dict[str, Any]] = []
    carrier = "A->B 初始载荷"
    chain = [("agent-A", "MiniMax-M3"), ("agent-B", "MiniMax-M3"), ("agent-C", "deepseek-flash")]
    envelope = signer.sign("agent-A", "MiniMax-M3", model="MiniMax-M3", content=carrier)
    for agent_id, provider in chain:
        verified = signer.verify(envelope, carrier)
        hops.append(
            {
                "at": agent_id,
                "provider": provider,
                "verified_from": verified.agent_id,
                "verified_provider": verified.provider,
                "ok": True,
            }
        )
        carrier = f"{agent_id} 转交的载荷"
        envelope = signer.sign(agent_id, provider, model=provider, content=carrier)
    # 闭环：C 产出回到 A
    final = signer.verify(envelope, carrier)
    hops.append({"at": "agent-A", "provider": "MiniMax-M3", "verified_from": final.agent_id, "ok": True})
    audit.record(
        audit.EVENT_AGENT_CALL,
        agent_id="agent-A",
        provider="MiniMax-M3",
        ok=True,
        detail={"scenario": "A", "hops": len(hops)},
        path=audit_dir / audit.AUDIT_FILENAME,
    )
    return {"scenario": "A", "closed_loop": final.agent_id == "agent-C", "hops": hops}


def scenario_b(authority: AuthorizationAuthority, audit_dir: Path) -> dict[str, Any]:
    """场景 B：过期令牌（ttl=0）必须被拒，并给出明确错误码。"""
    token = authority.issue("agent-A", "MiniMax-M3", ttl_s=0)
    try:
        authority.verify(token)
    except GovernanceError as err:
        audit.record_unauthorized(
            err.code,
            agent_id="agent-A",
            provider="MiniMax-M3",
            detail={"scenario": "B"},
            path=audit_dir / audit.AUDIT_FILENAME,
        )
        return {"scenario": "B", "rejected": True, "code": err.code, "expected": E_TOKEN_EXPIRED}
    return {"scenario": "B", "rejected": False, "code": None, "expected": E_TOKEN_EXPIRED}


def scenario_c(audit_dir: Path) -> dict[str, Any]:
    """场景 C：伪造 agent ID（随机密钥）必须被拒，且审计留下 unauthorized_attempt。"""
    honest = IdentitySigner(DEMO_KEY)
    forged = AuthorizationAuthority(b"attacker-random-key")
    forged_token = forged.issue("agent-forged", "MiniMax-M3")
    try:
        AuthorizationAuthority(DEMO_KEY).verify(forged_token)
    except GovernanceError as err:
        audit.record_unauthorized(
            err.code,
            agent_id="agent-forged",
            detail={"scenario": "C"},
            path=audit_dir / audit.AUDIT_FILENAME,
        )
        return {
            "scenario": "C",
            "rejected": True,
            "code": err.code,
            "honest_key_id": honest.key_id,
            "forged_key_id": forged.key_id,
        }
    return {
        "scenario": "C",
        "rejected": False,
        "code": None,
        "honest_key_id": honest.key_id,
        "forged_key_id": forged.key_id,
    }


def run_scenarios(audit_dir: Path, *, verbose: bool = True) -> dict[str, Any]:
    """跑完三个场景，返回结构化结果（供 CLI 与测试共用）。"""
    signer = IdentitySigner(DEMO_KEY)
    authority = AuthorizationAuthority(DEMO_KEY)
    result = {
        "key_id": signer.key_id,
        "audit_path": str(audit_dir / audit.AUDIT_FILENAME),
        "A": scenario_a(signer, audit_dir),
        "B": scenario_b(authority, audit_dir),
        "C": scenario_c(audit_dir),
    }
    result["unauthorized_attempt_count"] = audit.count_events(
        audit_dir / audit.AUDIT_FILENAME, event=audit.EVENT_UNAUTHORIZED
    )
    if verbose:
        print(f"[A] 闭环={result['A']['closed_loop']} 段数={len(result['A']['hops'])}（每段独立验签通过）")
        print(f"[B] 过期令牌被拒={result['B']['rejected']} code={result['B']['code']}")
        print(f"[C] 伪造 agent 被拒={result['C']['rejected']} code={result['C']['code']}")
        print(f"[审计] unauthorized_attempt 条数={result['unauthorized_attempt_count']}")
        print(f"[审计] 落点={result['audit_path']}")
    return result


# --------------------------------------------------------------------------- resign
def _load_pending(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return list(audit.iter_jsonl(path))


def resign(
    provider: str,
    *,
    pending: Path,
    audit_dir: Path,
    key: bytes,
    dry_run: bool = False,
) -> int:
    """把挂起任务的签名换成新 provider 签的；返回 re-sign 数量。

    每个被重签的任务写一条 ``re_sign`` 审计事件（含 from/to provider）。
    """
    signer = IdentitySigner(key)
    entries = _load_pending(pending)
    count = 0
    for entry in entries:
        agent_id = str(entry.get("agent_id") or "unknown-agent")
        content = str(entry.get("content") or "")
        old = entry.get("envelope") if isinstance(entry.get("envelope"), dict) else None
        from_provider = str(entry.get("provider") or (old or {}).get("provider") or "")
        envelope = signer.sign(agent_id, provider, model=str(entry.get("model", provider)), content=content)
        entry["provider"] = provider
        entry["envelope"] = envelope.to_dict()
        entry["envelope_provider"] = provider
        entry["re_signed_at"] = utc_now_iso()
        count += 1
        audit.record(
            audit.EVENT_RE_SIGN,
            agent_id=agent_id,
            provider=provider,
            model=envelope.model,
            ok=True,
            detail={"task_id": entry.get("task_id"), "from_provider": from_provider, "to_provider": provider},
            path=audit_dir / audit.AUDIT_FILENAME,
        )
    if entries and not dry_run:
        pending.parent.mkdir(parents=True, exist_ok=True)
        tmp = pending.with_suffix(".jsonl.tmp")
        with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
            for entry in entries:
                handle.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
        os.replace(tmp, pending)
    return count


# --------------------------------------------------------------------------- CLI
def _key_from_env(allow_demo: bool) -> bytes:
    raw = os.environ.get(ENV_ID_KEY, "").strip()
    if raw:
        return raw.encode("utf-8")
    if allow_demo:
        return DEMO_KEY
    raise GovernanceError(E_MISSING_KEY, f"环境变量 {ENV_ID_KEY} 未设置", env_var=ENV_ID_KEY)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m mcpserver.agent_governance", description="agent 身份-授权-审计三件套")
    parser.add_argument("--audit-dir", default=None, help=f"审计目录（默认 ${audit.ENV_AUDIT_DIR} 或 {audit.DEFAULT_AUDIT_DIR}）")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("demo", help="跑场景 A/B/C 并打印证据（用演示密钥 + 临时审计目录）")
    sub.add_parser("selftest", help="同 demo，但任一场景失败则退出码非 0")
    tail = sub.add_parser("audit-tail", help="打印最近审计事件")
    tail.add_argument("-n", "--limit", type=int, default=5)
    rs = sub.add_parser("resign", help="把挂起任务的签名换成新 provider（峰谷切换用）")
    rs.add_argument("--provider", required=True)
    rs.add_argument("--pending", default=None, help=f"挂起任务 JSONL（默认 <audit-dir>/{PENDING_FILENAME}）")
    rs.add_argument("--dry-run", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    command = args.command or "demo"
    audit_dir = Path(args.audit_dir).expanduser() if args.audit_dir else audit.resolve_audit_dir()

    if command in ("demo", "selftest"):
        with tempfile.TemporaryDirectory(prefix="agent_gov_demo_") as tmp:
            target = Path(tmp) if args.audit_dir is None else audit_dir
            result = run_scenarios(target)
            ok = bool(result["A"]["closed_loop"] and result["B"]["rejected"] and result["C"]["rejected"])
            if command == "selftest":
                print(f"selftest: {'PASS' if ok else 'FAIL'}")
                return 0 if ok else 1
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if command == "audit-tail":
        rows = audit.tail(audit_dir / audit.AUDIT_FILENAME, n=args.limit)
        for row in rows:
            print(json.dumps(row, ensure_ascii=False, sort_keys=True))
        print(f"共 {len(rows)} 条（{audit_dir / audit.AUDIT_FILENAME}）")
        return 0

    if command == "resign":
        try:
            key = _key_from_env(allow_demo=False)
        except GovernanceError as err:
            print(f"错误: {err.message}", file=sys.stderr)
            return 2
        pending = Path(args.pending).expanduser() if args.pending else audit_dir / PENDING_FILENAME
        count = resign(args.provider, pending=pending, audit_dir=audit_dir, key=key, dry_run=args.dry_run)
        print(f"re-sign count: {count}")
        print(f"provider: {args.provider}  pending: {pending}")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
