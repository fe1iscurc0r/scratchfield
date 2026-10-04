"""每轮验证门（卷123 W123-03）。

ZCode 的「每轮自动验证 + fail-closed」：**实现类步骤**（type=code，或该步落过文件写入）
完成后自动跑一次验证——优先跑受影响测试，其次语法门（`python -m py_compile`）；
失败就把这一步标 blocked、任务整体 blocked，等模型改完重试（限 `task_flow.verify_max_retries`）。

与卷119 W119-03 工具安全门的关系：那条链路管**工具执行前**（审计/敏感/熔断/确认），
本门管**步骤完成后**，是同一套安全体系里的「事后验证」一环；审计走同一个
tool_gate 审计通道（`phase=verify_gate`），因此 `audit/code_tool_calls*.ndjson` 一处可查。

验证结果用**正交字段**（对齐 DSH 失败纪律）：`exit_code / passed / failed / errors /
timeout / error` 分开，不用一个 "ok" 糊住所有失败形态。
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

#: 验证门判定用的步骤类型（含文件写入的实现类步骤）
_VERIFY_STEP_TYPES = {"code", "test"}


def _cfg() -> Any:
    try:
        from system.config import get_config

        return getattr(get_config(), "task_flow", None)
    except Exception:  # noqa: BLE001
        return None


def audit_only() -> bool:
    cfg = _cfg()
    return bool(getattr(cfg, "verify_audit_only", False)) if cfg is not None else False


def max_retries() -> int:
    cfg = _cfg()
    return int(getattr(cfg, "verify_max_retries", 2)) if cfg is not None else 2


def _audit(record: Dict[str, Any]) -> None:
    """验证门审计（复用 tool_gate 的审计通道；失败不影响主流程）。"""
    try:
        from apiserver.event_bus.tool_gate import get_tool_gate_runtime

        get_tool_gate_runtime().audit({"ts": time.time(), "phase": "verify_gate", **record})
    except Exception:  # noqa: BLE001
        logger.debug("[task_verify] 审计落盘失败", exc_info=True)


# ---------------------------------------------------------------------------
# 目标选择
# ---------------------------------------------------------------------------


def pick_test_targets(task: Dict[str, Any], step: Dict[str, Any]) -> List[str]:
    """挑验证目标：优先该步/任务涉及的测试文件，其次测试目录，再退回空（走语法门）。"""
    refs = [str(p) for p in (task.get("file_refs") or [])]
    for extra in (step.get("result_ref") or "", step.get("desc") or ""):
        for token in str(extra).replace("\n", " ").split():
            clean = token.strip("`'\"，,。.()（）[]")
            if clean.endswith(".py"):
                refs.append(clean)
    tests = [r for r in refs if "test" in Path(r).name.lower()]
    if tests:
        return list(dict.fromkeys(tests))
    dirs = [r for r in refs if r.startswith("tests/") or r.startswith("tests\\")]
    if dirs:
        return list(dict.fromkeys(dirs))
    return []


def pick_compile_targets(task: Dict[str, Any], step: Dict[str, Any]) -> List[str]:
    """语法门目标：该步涉及/任务记录的 .py 文件。"""
    refs = [str(p) for p in (task.get("file_refs") or [])]
    for token in f"{step.get('result_ref') or ''} {step.get('desc') or ''}".replace("\n", " ").split():
        clean = token.strip("`'\"，,。.()（）[]")
        if clean.endswith(".py"):
            refs.append(clean)
    return list(dict.fromkeys(r for r in refs if r.endswith(".py")))


# ---------------------------------------------------------------------------
# 执行验证
# ---------------------------------------------------------------------------


def _empty_outcome(mode: str) -> Dict[str, Any]:
    return {"mode": mode, "ran": False, "ok": False, "exit_code": None, "passed": 0, "failed": 0,
            "errors": 0, "skipped": 0, "timeout": False, "error": None, "detail": ""}


def _run_test_targets(targets: List[str], session_id: str, timeout_s: float) -> Dict[str, Any]:
    from mcpserver.code_workspace.tools import CodeWorkspaceBridge

    bridge = CodeWorkspaceBridge()
    if len(targets) == 1:
        payload = bridge.test_run(targets[0], session_id=session_id, timeout_s=timeout_s)
    else:
        payload = bridge.test_run("tests", session_id=session_id, timeout_s=timeout_s)
    outcome = _empty_outcome("pytest")
    outcome["ran"] = True
    if payload.get("error") == "timeout":
        outcome.update({"timeout": True, "error": "timeout"})
        return outcome
    summary = payload.get("summary") or {}
    outcome.update(
        {
            "ok": bool(payload.get("ok")) and not payload.get("error"),
            "exit_code": payload.get("exit_code"),
            "passed": int(summary.get("passed") or 0),
            "failed": int(summary.get("failed") or 0),
            "errors": int(summary.get("errors") or 0),
            "skipped": int(summary.get("skipped") or 0),
            "error": payload.get("message") or payload.get("error"),
            "detail": str(summary.get("failed_tests") or payload.get("output_tail") or "")[:600],
        }
    )
    return outcome


def _run_compile_gate(targets: List[str], session_id: str, timeout_s: float) -> Dict[str, Any]:
    """语法门：`python -m py_compile <files>`（没有测试可跑时的最低门槛）。"""
    from mcpserver.code_workspace.tools import CodeWorkspaceBridge

    bridge = CodeWorkspaceBridge()
    outcome = _empty_outcome("py_compile")
    if not targets:
        # 既没测试也没 .py 目标：无处可验，记「跳过」而不是判失败——
        # fail-closed 针对的是「验证跑了且没过」，不是「没东西可验」
        outcome["error"] = None
        outcome["ok"] = True
        outcome["skipped_reason"] = "no_target"
        outcome["detail"] = "既没有测试也没有可编译的 .py 文件，语法门跳过"
        return outcome
    cmd = "python -m py_compile " + " ".join(f'"{t}"' for t in targets[:20])
    payload = bridge.shell_exec(cmd, session_id=session_id, timeout_s=timeout_s)
    outcome["ran"] = True
    if payload.get("error") == "timeout":
        outcome.update({"timeout": True, "error": "timeout"})
        return outcome
    outcome.update(
        {
            "ok": bool(payload.get("ok")) and int(payload.get("exit_code") or 0) == 0,
            "exit_code": payload.get("exit_code"),
            "errors": 0 if int(payload.get("exit_code") or 0) == 0 else 1,
            "error": payload.get("message") or payload.get("error"),
            "detail": str(payload.get("stderr") or payload.get("stdout") or "")[:600],
        }
    )
    return outcome


def _existing_targets(paths: List[str], session_id: str) -> List[str]:
    """只保留工作区里真实存在的文件。

    任务 file_refs 里可能有「计划提到、但这一步还没写」的路径——不能拿它当验证目标，
    否则会把「还没轮到写」误判成验证失败。顺带走一遍隔离校验（越界路径直接丢）。
    """
    from mcpserver.code_workspace.sandbox import SandboxError, resolve_in_workspace

    existing: List[str] = []
    for path in paths:
        try:
            resolved = resolve_in_workspace(path, session_id or "default")
        except SandboxError:
            continue
        if resolved.is_file():
            existing.append(path)
    return list(dict.fromkeys(existing))


def run_verify_gate(
    task: Dict[str, Any], step: Dict[str, Any], *, session_id: str = "", timeout_s: float = 120.0
) -> Dict[str, Any]:
    """对一个步骤跑验证门，返回正交结果（同时写审计）。"""
    sid = session_id or str(task.get("session_id") or "default")
    targets = _existing_targets(pick_test_targets(task, step), sid)
    if targets:
        outcome = _run_test_targets(targets, sid, timeout_s)
    else:
        outcome = _run_compile_gate(_existing_targets(pick_compile_targets(task, step), sid), sid, timeout_s)
    outcome["targets"] = targets
    outcome["audit_only"] = audit_only()
    _audit(
        {
            "task_id": task.get("task_id"),
            "step_id": step.get("id"),
            "session_id": sid,
            "mode": outcome.get("mode"),
            "ok": outcome.get("ok"),
            "exit_code": outcome.get("exit_code"),
            "passed": outcome.get("passed"),
            "failed": outcome.get("failed"),
            "errors": outcome.get("errors"),
            "timeout": outcome.get("timeout"),
            "audit_only": outcome["audit_only"],
        }
    )
    logger.info(
        "[task_verify] %s/%s mode=%s ok=%s (passed=%s failed=%s errors=%s timeout=%s)",
        task.get("task_id"), step.get("id"), outcome.get("mode"), outcome.get("ok"),
        outcome.get("passed"), outcome.get("failed"), outcome.get("errors"), outcome.get("timeout"),
    )
    return outcome


def needs_verification(step: Dict[str, Any]) -> bool:
    """实现类步骤才过验证门（explore/verify 步不跑，避免自证循环）。"""
    return str(step.get("type") or "code") in _VERIFY_STEP_TYPES


def format_outcome(outcome: Dict[str, Any]) -> str:
    """一行给人/模型看的结果摘要（正交字段保留）。"""
    mode = outcome.get("mode") or "verify"
    if outcome.get("timeout"):
        return f"[验证门 {mode}] 超时"
    if not outcome.get("ran"):
        reason = outcome.get("skipped_reason") or outcome.get("error") or "无目标"
        head = "跳过" if outcome.get("ok") else "未执行"
        return f"[验证门 {mode}] {head}（{reason}）"
    bits = [f"exit={outcome.get('exit_code')}"]
    if mode == "pytest":
        bits.append(f"passed={outcome.get('passed')} failed={outcome.get('failed')} "
                    f"errors={outcome.get('errors')} skipped={outcome.get('skipped')}")
    if outcome.get("ok"):
        return f"[验证门 {mode}] 通过（{'，'.join(bits)}）"
    return (f"[验证门 {mode}] 未通过（{'，'.join(bits)}）：{outcome.get('detail') or ''}"[:400])


def retries_left(step: Dict[str, Any]) -> int:
    """该步还剩几次「改完再验」的机会。

    `verify_attempts` 是**已跑过的**验证次数；`max_retries` 是失败后允许的重试次数，
    所以第 1 次失败后剩余 = max_retries - (attempts - 1)。
    """
    used = int(step.get("verify_attempts") or 0)
    return max(0, max_retries() - max(0, used - 1))


def bump_attempts(task_id: str, step_id: str) -> None:
    """累加该步的验证尝试计数（写回 steps_json）。"""
    from apiserver import task_store

    task = task_store.get_task(task_id)
    if not task:
        return
    for step in task.get("steps") or []:
        if str(step.get("id")) != str(step_id):
            continue
        step["verify_attempts"] = int(step.get("verify_attempts") or 0) + 1
        task_store._update_fields(
            task_id, {"steps_json": json.dumps(task["steps"], ensure_ascii=False)}
        )
        return
