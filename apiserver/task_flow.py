"""任务流的对话侧协议（卷123 W123-01 / W123-02 地基）。

两个入口：

1. **用户元指令**（`task:create <目标>` / `task:list` / `task:continue <id>` / `task:pause <id>` /
   `task:resume <id>` / `task:review <id>`）——聊天路由在进 LLM 前直接处理，命中即短路回复。
2. **模型 `[TASK]` 段**（`[TASK]{json}[/TASK]`）——模型在回复里声明任务操作，
   loop 每轮结束后 `apply_task_ops` 落到 task_store（create / step / complete / pause）。

状态一律以 task_store（SQLite）为权威，本模块不缓存。
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from apiserver import task_store

logger = logging.getLogger(__name__)

#: Goal Mode 默认分解模板（W123-02：探查 → 实现 → 测试 → 验证）
DEFAULT_STEP_TEMPLATE: List[Dict[str, str]] = [
    {"desc": "探查：读相关文件与目录结构，输出理解摘要与最小改动路径", "type": "explore"},
    {"desc": "实现：按最小改动路径落地代码", "type": "code"},
    {"desc": "测试：跑受影响测试（无测试则语法门）", "type": "test"},
    {"desc": "验证：复核改动是否符合目标、有无副作用", "type": "verify"},
]

_TASK_META_RE = re.compile(r"^\s*task\s*[:：]\s*([a-zA-Z_-]+)\s*(.*)$", re.IGNORECASE | re.DOTALL)
_TASK_BLOCK_RE = re.compile(r"\[TASK\]([\s\S]*?)(?:\[/TASK\]|$)", re.IGNORECASE)
_PLAN_BLOCK_RE = re.compile(r"\[PLAN\]([\s\S]*?)(?:\[/PLAN\]|$)", re.IGNORECASE)
_PLAN_LINE_RE = re.compile(r"^\s*(?:[-*•]|\d+\s*[.、)）]|\[\s*[ xX]?\s*\])\s*(.+?)\s*$")

#: 步骤类型推断关键词（模型没写 type 时按描述猜）
_TYPE_HINTS: List[Tuple[str, Tuple[str, ...]]] = [
    ("explore", ("探查", "调查", "阅读", "读文件", "仓库", "结构", "inspect", "explore", "read", "搜索")),
    ("test", ("测试", "pytest", "跑测试", "test", "用例")),
    ("verify", ("验证", "复核", "审查", "检查结果", "verify", "review")),
    ("code", ("实现", "修改", "改代码", "写", "新增", "修复", "重构", "implement", "fix", "edit")),
]

#: 行首显式类型词（`实现：…` / `探查：…` 这类写法优先于关键词扫描）
_LEADING_TYPE_HINTS: List[Tuple[str, Tuple[str, ...]]] = [
    ("explore", ("探查", "调查", "勘察", "阅读", "inspect", "explore")),
    ("test", ("测试", "跑测试", "test")),
    ("verify", ("验证", "复核", "审查", "review", "verify")),
    ("code", ("实现", "修改", "新增", "修复", "重构", "写", "implement", "fix", "edit")),
]

_TOOL_HINT_RE = re.compile(r"[（(]\s*(?:工具|tool)\s*[:：]?\s*([^）)]+)[）)]", re.IGNORECASE)

_META_HELP = (
    "可用任务指令：\n"
    "- `task:create <目标>` 建任务（默认四步：探查→实现→测试→验证）\n"
    "- `goal:<目标>` 目标模式（模型先出计划，再等确认）\n"
    "- `task:confirm` 确认计划并开始逐步执行\n"
    "- `task:list` 列本会话任务\n"
    "- `task:continue <task_id>` 继续某任务\n"
    "- `task:skip <step_id>` 跳过某步\n"
    "- `task:replan <新目标>` 重新计划\n"
    "- `task:pause <task_id>` / `task:resume <task_id>` 暂停 / 恢复\n"
    "- `task:review <task_id>` 出审查报告"
)


def _cfg() -> Any:
    try:
        from system.config import get_config

        return getattr(get_config(), "task_flow", None)
    except Exception:  # noqa: BLE001
        return None


def default_steps() -> List[Dict[str, str]]:
    """默认步骤模板（配置可覆盖 `task_flow.step_template`，格式：`type:描述` 每行一条）。"""
    cfg = _cfg()
    raw = getattr(cfg, "step_template", None) if cfg is not None else None
    if isinstance(raw, list) and raw:
        steps: List[Dict[str, str]] = []
        for item in raw:
            text = str(item)
            if ":" in text:
                kind, desc = text.split(":", 1)
                if kind.strip() in task_store.EXEC_MODES:
                    steps.append({"desc": desc.strip(), "type": kind.strip()})
                    continue
            steps.append({"desc": text.strip(), "type": "code"})
        if steps:
            return steps
    return [dict(s) for s in DEFAULT_STEP_TEMPLATE]


# ---------------------------------------------------------------------------
# 用户元指令
# ---------------------------------------------------------------------------


def parse_meta_command(text: str) -> Tuple[str, str] | None:
    """解析 `task:xxx ...` 元指令，返回 (op, arg)；不是元指令返回 None。"""
    if not text:
        return None
    match = _TASK_META_RE.match(str(text))
    if not match:
        return None
    return match.group(1).lower(), (match.group(2) or "").strip()


def active_task(session_id: str) -> Dict[str, Any] | None:
    """该会话最近一个未结束的任务（running/paused/blocked/review/pending）。

    blocked 也算「活动」——它等用户决定重试/跳过/改计划，上下文仍要注入。
    """
    for status in task_store.active_task_lookup_statuses():
        found = task_store.list_tasks(session_id, status=status, limit=1)
        if found:
            return found[0]
    return None


def run_meta_command(session_id: str, text: str) -> str | None:
    """处理用户元指令；返回给用户的回复文本（None = 不是任务指令，交回主链路）。"""
    parsed = parse_meta_command(text)
    if parsed is None:
        return None
    op, arg = parsed

    if op in ("help", "?"):
        return _META_HELP

    if op in ("create", "new", "goal"):
        if not arg:
            return "用法：`task:create <目标>`"
        steps = default_steps()
        git_state = ""
        try:
            from mcpserver.code_workspace import sandbox

            git_state = _git_state(sandbox.workspace_root())
        except Exception:  # noqa: BLE001
            git_state = ""
        task = task_store.create_task(
            session_id, arg, steps=steps,
            exec_mode="explore", git_state=git_state,
            status=task_store.STATUS_RUNNING,
        )
        task_store.append_trajectory(task["task_id"], tool="task:create", summary=arg,
                                     status=task_store.STATUS_RUNNING)
        bind_task_owner(task["task_id"])  # 卷123 W123-05：绑用户，供跨通道继续
        lines = [f"已建任务 `{task['task_id']}`：{arg}", "步骤计划："]
        lines += [f"{i}. [{s['type']}] {s['desc']}" for i, s in enumerate(task["steps"], 1)]
        lines.append("回复「确认」开始逐步执行，或 `task:pause` / `task:continue` 控制。")
        return "\n".join(lines)

    if op in ("confirm", "go", "start"):
        task = confirm_plan(session_id, task_id=arg)
        if not task:
            return "当前没有待确认的计划。用 `goal:<目标>` 或 `task:create <目标>` 建一个。"
        step = next_step(task)
        lines = [f"计划已确认，任务 `{task['task_id']}` 进入执行（{task['status']}）。"]
        if step:
            lines.append(f"当前步骤：{step['id']} {step['desc']}")
        lines.append("我会逐步执行并在每步结束时报告进度；`task:pause` 可暂停，`task:skip <step_id>` 可跳过某步。")
        return "\n".join(lines)

    if op == "skip":
        task = active_task(session_id)
        if not task:
            return "当前没有任务。"
        step_id = arg or ((next_step(task) or {}).get("id") or "")
        if not step_id:
            return "用法：`task:skip <step_id>`（当前没有待执行步骤）"
        result = skip_step(task["task_id"], step_id, reason="用户跳过")
        if not result.get("ok"):
            return f"跳过失败：{result.get('error')}"
        fresh = task_store.get_task(task["task_id"]) or {}
        return f"已跳过 {step_id}，任务状态 {fresh.get('status')}。"

    if op in ("replan", "plan"):
        if not arg:
            return "用法：`task:replan <新目标>`"
        task = replan(session_id, arg)
        if not task:
            return "当前没有可重计划的任务。"
        return f"已重新计划（任务 `{task['task_id']}`，状态 {task['status']}）：{arg}"

    if op == "list":
        tasks = channel_visible_tasks(session_id, limit=10)
        if not tasks:
            # 不回落到「全局任务列表」：那会把别人的任务漏给当前通道（隔离开关形同虚设）
            return "当前没有可见任务。用 `task:create <目标>` 建一个。"
        lines = ["可见任务（本通道 + 同用户其它通道）："]
        for t in tasks:
            steps = t.get("steps") or []
            done = sum(1 for s in steps if s.get("status") in (task_store.STEP_DONE, task_store.STEP_SKIPPED))
            cross = "" if t["session_id"] == session_id else f"｜来自会话 {t['session_id']}"
            lines.append(f"- `{t['task_id']}` [{t['status']}] {t['goal'][:60]}（{done}/{len(steps)} 步）{cross}")
        return "\n".join(lines)

    if op == "continue":
        task = find_visible_task(session_id, arg) if arg else active_task(session_id)
        if not task:
            task = active_task(session_id)
        if not task:
            return "没找到任务，用 `task:list` 看看。"
        task = task_store.resume_task(task["task_id"]) or task
        prefix = ""
        if task["session_id"] != session_id:
            prefix = f"（该任务来自会话 {task['session_id']}，本通道继续）\n"
        return prefix + "继续任务：\n" + task_store.task_summary(task)

    if op == "pause":
        task = task_store.get_task(arg) if arg else active_task(session_id)
        if not task:
            return "没找到任务，用 `task:list` 看看。"
        task = task_store.pause_task(task["task_id"]) or task
        task_store.append_trajectory(task["task_id"], tool="task:pause", status=task_store.STATUS_PAUSED)
        return f"任务 `{task['task_id']}` 已暂停（状态 {task['status']}）。`task:resume` 可继续。"

    if op == "resume":
        task = task_store.get_task(arg) if arg else active_task(session_id)
        if not task:
            return "没找到任务，用 `task:list` 看看。"
        task = task_store.resume_task(task["task_id"]) or task
        task_store.append_trajectory(task["task_id"], tool="task:resume", status=task["status"])
        return f"任务 `{task['task_id']}` 已恢复（状态 {task['status']}）。"

    if op == "review":
        task = task_store.get_task(arg) if arg else active_task(session_id)
        if not task:
            return "没找到任务，用 `task:list` 看看。"
        if task["status"] not in (task_store.STATUS_REVIEW, task_store.STATUS_DONE):
            task = task_store.set_status(task["task_id"], task_store.STATUS_REVIEW) or task
        try:
            from apiserver.task_review import build_review  # W123-04 提供

            review = build_review(task["task_id"])
        except Exception as e:  # noqa: BLE001 - 审查模块缺失/失败不影响其它指令
            logger.warning("[task_flow] 审查报告生成失败: %s", e)
            return f"审查报告暂时生成失败：{e}"
        return review.get("report", "审查报告生成失败。") + (
            "\n\n裁决：`task:accept` 确认 / `task:reject <意见>` 打回 / `task:skip-review` 跳过"
        )

    if op in ("accept", "approve"):
        task = task_store.get_task(arg) if arg else active_task(session_id)
        if not task:
            return "没找到任务，用 `task:list` 看看。"
        result = _apply_review_verdict(task["task_id"], "confirmed", note="用户确认")
        if not result.get("ok"):
            return f"确认失败：{result.get('error')}"
        return (f"审查通过，任务 `{task['task_id']}` 已 done，轨迹存档。"
                f"报告：{result.get('report_path') or '（未落盘）'}")

    if op in ("reject", "sendback", "redo"):
        task = active_task(session_id)
        note = arg
        if arg and task and arg.startswith(task["task_id"]):
            note = arg[len(task["task_id"]):].strip()
        if not task:
            return "没找到任务，用 `task:list` 看看。"
        result = _apply_review_verdict(task["task_id"], "rejected", note=note or "用户打回")
        if not result.get("ok"):
            return f"打回失败：{result.get('error')}"
        return (f"已打回任务 `{task['task_id']}`（回到 {result.get('status')}）。"
                f"意见：{note or '（无）'}——我会基于这个意见继续修。")

    if op in ("skip-review", "skipreview"):
        task = task_store.get_task(arg) if arg else active_task(session_id)
        if not task:
            return "没找到任务，用 `task:list` 看看。"
        result = _apply_review_verdict(task["task_id"], "skipped", note="用户跳过审查")
        if not result.get("ok"):
            return f"跳过失败：{result.get('error')}"
        return f"任务 `{task['task_id']}` 已 done，标记「未经 review」。"

    if op in ("step", "update"):
        return "`task:step` 由模型侧 `[TASK]` 段驱动，用户侧请用确认/打回。"

    if op in ("subagent", "sub", "subagents"):
        from apiserver import subagent as sa

        return sa.status_text(arg, session_id=session_id)

    return f"未知任务指令 `task:{op}`。\n{_META_HELP}"


def _git_state(workspace_root: Any) -> str:
    """记录任务开始时的 git 基线（分支 + HEAD 短 hash），失败返回空串。"""
    import subprocess

    try:
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(workspace_root), capture_output=True, text=True, timeout=5,
        )
        head = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(workspace_root), capture_output=True, text=True, timeout=5,
        )
        b = (branch.stdout or "").strip()
        h = (head.stdout or "").strip()
        return f"{b}@{h}" if b and h else ""
    except Exception:  # noqa: BLE001 - git 不可用不影响建任务
        return ""


# ---------------------------------------------------------------------------
# Goal Mode（W123-02）：PLAN → 步骤 → 确认 → 逐步执行
# ---------------------------------------------------------------------------


def infer_step_type(desc: str) -> str:
    """按描述猜步骤类型（explore / code / test / verify）。

    先看行首显式类型词（`实现：新建 utils.py 并写 tests/…` 应以「实现」为准，
    不能被正文里的 "tests/" 抢走），再退回关键词扫描。
    """
    text = str(desc).strip()
    lowered = text.lower()
    for kind, keywords in _LEADING_TYPE_HINTS:
        if any(lowered.startswith(k.lower()) for k in keywords):
            return kind
    for kind, keywords in _TYPE_HINTS:
        if any(k.lower() in lowered for k in keywords):
            return kind
    return "code"


def parse_plan_steps(text: str) -> List[Dict[str, str]]:
    """把 `[PLAN]` 段解析成步骤列表（每步 desc/type/tool）。

    行格式随意：`1. 探查相关文件`、`- 实现 divide（工具：file_edit）`、`[ ] 跑测试` 都认。
    """
    if not text:
        return []
    raw = str(text)
    match = _PLAN_BLOCK_RE.search(raw)
    if match:
        body, strict = match.group(1), False
    else:
        # 没有 [PLAN] 标记时保守处理：只认列表行（`1.` / `-` / `[ ]`），普通句子不算步骤
        body, strict = raw, True
    if not body.strip():
        return []
    steps: List[Dict[str, str]] = []
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        hit = _PLAN_LINE_RE.match(raw_line)
        if strict and not hit:
            continue
        desc = (hit.group(1) if hit else line).strip()
        if not desc or desc.startswith("```"):
            continue
        tool = ""
        tool_hit = _TOOL_HINT_RE.search(desc)
        if tool_hit:
            tool = tool_hit.group(1).strip()
            desc = _TOOL_HINT_RE.sub("", desc).strip(" -—:：")
        steps.append({"desc": desc, "type": infer_step_type(desc), "tool": tool})
    return steps


def create_task_from_plan(session_id: str, goal: str, plan_text: str,
                          *, exec_mode: str = "explore") -> Dict[str, Any]:
    """按模型给出的 `[PLAN]` 建任务；解析不出步骤时退回默认模板。"""
    steps = parse_plan_steps(plan_text)
    if not steps:
        steps = default_steps()
    git_state = ""
    try:
        from mcpserver.code_workspace import sandbox

        git_state = _git_state(sandbox.workspace_root())
    except Exception:  # noqa: BLE001
        git_state = ""
    task = task_store.create_task(
        session_id, goal, steps=steps, exec_mode=exec_mode, git_state=git_state,
        status=task_store.STATUS_PENDING,  # 等用户确认才执行（对齐 W121-03 确认语义）
    )
    bind_task_owner(task["task_id"])  # 卷123 W123-05：绑用户，供跨通道继续
    task_store.append_trajectory(task["task_id"], tool="goal:plan",
                                 summary=f"计划 {len(steps)} 步：{steps[0]['desc'][:40]}…" if steps else "",
                                 status=task_store.STATUS_PENDING)
    return task


def pending_plan(session_id: str) -> Dict[str, Any] | None:
    """该会话等待确认的计划（status=pending 的任务）。"""
    found = task_store.list_tasks(session_id, status=task_store.STATUS_PENDING, limit=1)
    return found[0] if found else None


def confirm_plan(session_id: str, *, task_id: str = "") -> Dict[str, Any] | None:
    """用户确认计划 → 任务转 running，进入逐步执行。"""
    task = task_store.get_task(task_id) if task_id else pending_plan(session_id)
    if not task:
        return None
    updated = task_store.set_status(task["task_id"], task_store.STATUS_RUNNING)
    task_store.append_trajectory(task["task_id"], tool="goal:confirm", status=task_store.STATUS_RUNNING)
    return updated


def next_step(task: Dict[str, Any]) -> Dict[str, Any] | None:
    """下一个待执行步骤（pending 的第一个）。"""
    for step in task.get("steps") or []:
        if step.get("status") == task_store.STEP_PENDING:
            return step
    return None


def record_step_result(
    task_id: str, step_id: str, status: str, *,
    result_ref: str = "", tool: str = "", summary: str = "",
) -> Dict[str, Any]:
    """落一步结果，并按 fail-closed 规则联动任务状态。

    - 步骤 blocked/failed → 任务 blocked（不自动继续下一步）
    - 全部步骤 done/skipped → 任务 review（等 W123-04 审查）或 done
    """
    failed = status in (task_store.STEP_BLOCKED, "failed", "error")
    step_status = task_store.STEP_BLOCKED if failed else status
    # 结果里提到的 .py 路径统一进 file_refs（供后续步骤上下文与验证门用）
    task_store.add_file_refs(task_id, _paths_from_text(f"{result_ref} {summary}"))
    updated = task_store.update_step(task_id, step_id, step_status, result_ref=result_ref)
    if updated is None:
        return {"ok": False, "error": "step_not_found"}
    task_store.append_trajectory(
        task_id, step_id=step_id, tool=tool, summary=summary or result_ref, status=status
    )
    applied_status = ""
    if failed:
        task_store.set_status(task_id, task_store.STATUS_BLOCKED)
        applied_status = task_store.STATUS_BLOCKED
    else:
        fresh = task_store.get_task(task_id) or {}
        steps = fresh.get("steps") or []
        if steps and all(s.get("status") in (task_store.STEP_DONE, task_store.STEP_SKIPPED) for s in steps):
            target = task_store.STATUS_REVIEW if _cfg_review_enabled() else task_store.STATUS_DONE
            task_store.set_status(task_id, target)
            applied_status = target
    return {"ok": True, "task_id": task_id, "step_id": step_id, "status": status,
            "task_status": applied_status}


def finish_step_with_verify(
    task_id: str, step_id: str, *,
    result_ref: str = "", tool: str = "", summary: str = "", session_id: str = "",
) -> Dict[str, Any]:
    """实现类步骤收尾：先过验证门（W123-03），再按 fail-closed 落状态。

    - 验证通过 → 步骤 done
    - 验证失败且还有重试额度 → 步骤停留在 blocked 语义但不锁任务（回给模型改），
      返回 `verify.retry=True` 让调用方提示模型继续修
    - 验证失败且额度用尽 → 步骤 blocked、任务 blocked（fail-closed）
    - `task_flow.verify_audit_only=true` → 只记审计，不拦（步骤照模型申报落 done）
    """
    from apiserver import task_verify

    task = task_store.get_task(task_id)
    if not task:
        return {"ok": False, "error": "no_task"}
    step = next((s for s in task.get("steps") or [] if str(s.get("id")) == str(step_id)), None)
    if step is None:
        return {"ok": False, "error": "step_not_found"}

    verify: Dict[str, Any] = {}
    # 步骤产出的 .py 路径统一进任务 file_refs（探查步也走这条，供后续验证门/上下文用）
    task_store.add_file_refs(task_id, _paths_from_text(f"{result_ref} {summary} {step.get('desc')}"))
    task = task_store.get_task(task_id) or task
    step = next((s for s in task.get("steps") or [] if str(s.get("id")) == str(step_id)), step)

    if task_verify.needs_verification(step):
        verify = task_verify.run_verify_gate(task, step, session_id=session_id or task.get("session_id", ""))
        task_verify.bump_attempts(task_id, step_id)
        step_note = f"{result_ref}｜{task_verify.format_outcome(verify)}".strip("｜")
        if not verify.get("ok") and not task_verify.audit_only():
            left = task_verify.retries_left({**step, "verify_attempts": int(step.get("verify_attempts") or 0) + 1})
            if left > 0:
                # 留额度：步骤标 blocked（提示模型「基于失败改」），但任务保持 running，
                # 让它能继续改；额度用尽才由 record_step_result 把任务整体锁死
                task_store.update_step(task_id, step_id, task_store.STEP_BLOCKED, result_ref=step_note)
                task_store.append_trajectory(
                    task_id, step_id=step_id, tool=tool, summary=summary or step_note, status="blocked"
                )
                result = {"ok": True, "task_id": task_id, "step_id": step_id,
                          "status": task_store.STEP_BLOCKED, "task_status": ""}
                result["verify"] = verify
                result["retry"] = True
                result["retries_left"] = left
                return result
            result = record_step_result(
                task_id, step_id, task_store.STEP_BLOCKED,
                result_ref=step_note, tool=tool, summary=summary,
            )
            result["verify"] = verify
            result["retry"] = False
            result["retries_left"] = 0
            return result
        result_ref = step_note

    # explore 步：没写理解摘要就留痕提醒（摘要必须用户可见）
    if str(step.get("type")) == "explore" and not str(result_ref or summary).strip():
        task_store.append_trajectory(task_id, step_id=step_id, tool=tool,
                                     summary="探查步骤未给出理解摘要/最小改动路径", status="warn")

    result = record_step_result(task_id, step_id, task_store.STEP_DONE,
                               result_ref=result_ref, tool=tool, summary=summary)
    if verify:
        result["verify"] = verify
        result["retry"] = False
        result["retries_left"] = task_verify.retries_left(step)
    return result


_PY_PATH_RE = re.compile(r"[\w./\\-]+\.py\b")


def _paths_from_text(text: str) -> List[str]:
    """从一段文本里挑出 .py 路径（用于任务 file_refs）。"""
    return list(dict.fromkeys(m.group(0) for m in _PY_PATH_RE.finditer(str(text or ""))))


def _cfg_review_enabled() -> bool:
    """Review 阶段是否启用（W123-04；关掉则任务直接 done）。"""
    cfg = _cfg()
    return bool(getattr(cfg, "review_enabled", True)) if cfg is not None else True


def _apply_review_verdict(task_id: str, verdict: str, *, note: str = "") -> Dict[str, Any]:
    """调用审查裁决（W123-04；模块缺失时返回错误而不是抛异常）。"""
    try:
        from apiserver.task_review import apply_verdict

        return apply_verdict(task_id, verdict, note=note)
    except Exception as e:  # noqa: BLE001
        logger.warning("[task_flow] 审查裁决失败: %s", e)
        return {"ok": False, "error": str(e)}


def skip_step(task_id: str, step_id: str, *, reason: str = "") -> Dict[str, Any]:
    """跳过某步（用户指令）。"""
    return record_step_result(task_id, step_id, task_store.STEP_SKIPPED,
                             summary=reason or "用户跳过", tool="task:skip")


def replan(session_id: str, new_goal: str) -> Dict[str, Any] | None:
    """重新计划：把当前活动任务打回 pending 并换目标（步骤清空重来）。"""
    task = active_task(session_id)
    if not task:
        return None
    task_store.set_steps(task["task_id"], default_steps())
    updated = task_store._update_fields(
        task["task_id"], {"goal": str(new_goal or task["goal"]), "status": task_store.STATUS_PENDING}
    )
    task_store.append_trajectory(task["task_id"], tool="goal:replan", summary=str(new_goal)[:200],
                                 status=task_store.STATUS_PENDING)
    return updated


def goal_mode_prompt(goal: str) -> str:
    """引导模型输出 `[PLAN]` 的目标模式提示（用户给目标时注入）。"""
    types = "/".join(task_store.EXEC_MODES)
    return (
        "【目标模式】用户给的是一个目标，不是一次性问题。请先输出执行计划，再等确认：\n"
        "[PLAN]\n"
        "1. 探查：读相关文件与目录结构，给出理解摘要与最小改动路径\n"
        "2. 实现：按最小改动路径落地\n"
        "3. 测试：跑受影响测试（无测试则语法门）\n"
        "4. 验证：复核是否符合目标、有无副作用\n"
        "[/PLAN]\n"
        f"每步一行，行首可用（工具：xxx）标注预计工具；步骤类型建议落在 {types} 内。\n"
        "计划展示后等用户确认；确认后每完成一步，用 "
        '[TASK]{"op":"step","step_id":"sN","status":"done","result_ref":"…"}[/TASK] 报告。'
    )


def task_context_prompt(session_id: str) -> str:
    """把会话内活动任务注入 LLM 上下文（目标 + 步骤进度 + 当前步 + 关键结果 + 相关文件）。"""
    task = active_task(session_id)
    if not task:
        return ""
    lines = [task_store.task_summary(task)]
    step = next_step(task)
    if task["status"] == task_store.STATUS_PENDING:
        lines.append("当前状态：计划待用户确认（确认后开始执行第 1 步）。")
    elif step and task["status"] == task_store.STATUS_RUNNING:
        lines.append(f"当前步骤：{step['id']} {step['desc']}（类型 {step.get('type')}）")
        if task.get("file_refs"):
            lines.append(f"本步相关文件（先读再改）：{', '.join(task['file_refs'][:8])}")
        prev = _last_result(task)
        if prev:
            lines.append(f"上一步结果：{prev}")
        lines.append(
            "完成该步后请用 [TASK] 段报告："
            '[TASK]{"op":"step","task_id":"%s","step_id":"%s","status":"done","result_ref":"…"}[/TASK]'
            % (task["task_id"], step["id"])
        )
    elif task["status"] == task_store.STATUS_BLOCKED:
        lines.append("任务已 blocked（有步骤失败）：请说明失败原因与两种可行方案，等用户决定。")
    return "\n".join(lines)


def _last_result(task: Dict[str, Any], *, max_chars: int = 240) -> str:
    """最近一条「有内容」的步骤结果（关键结果保留，供跨步上下文）。"""
    for entry in reversed(task.get("trajectory") or []):
        summary = str(entry.get("summary") or "").strip()
        if summary and entry.get("step_id"):
            return summary[:max_chars]
    for step in reversed(task.get("steps") or []):
        ref = str(step.get("result_ref") or "").strip()
        if ref:
            return ref[:max_chars]
    return ""


def key_results(task: Dict[str, Any], *, limit: int = 5, max_chars: int = 200) -> List[str]:
    """关键结果清单（每步最后的结论），供压缩后的上下文保留。"""
    out: List[str] = []
    for step in task.get("steps") or []:
        if step.get("status") not in (task_store.STEP_DONE, task_store.STEP_SKIPPED):
            continue
        ref = str(step.get("result_ref") or "").strip()
        if ref:
            out.append(f"{step.get('id')}：{ref[:max_chars]}")
    return out[-limit:]


#: 步骤边界压缩时保留的最近消息条数（当前步的对话细节不压）
KEEP_RECENT_MESSAGES = 6


def step_boundary_compact(
    messages: List[Dict[str, Any]], session_id: str, *, keep_recent: int = KEEP_RECENT_MESSAGES
) -> int:
    """步骤边界压缩：某步完成后把更早的工具结果消息收敛成一条摘要。

    任务级上下文 = goal 摘要 + 当前步上下文 + 关键结果；**全历史压缩**——
    历史里工具返回的大段 stdout/diff 不再逐条留在上下文里，改成一条「已完成步骤 + 关键结果」。
    返回被收敛掉的消息条数（0 表示没动）。
    """
    task = active_task(session_id)
    if not task or len(messages) <= keep_recent + 2:
        return 0
    results = key_results(task)
    if not results:
        return 0
    head = messages[:1] if messages and str(messages[0].get("role")) == "system" else []
    tail = messages[len(messages) - keep_recent:]
    # 尾部里若已含 system/user 交替结构，保持不动；只把中间段收掉
    middle = messages[len(head):len(messages) - keep_recent]
    if not middle:
        return 0
    keep = [m for m in middle if str(m.get("role")) == "assistant" and not m.get("tool_calls")]
    summary_msg = {
        "role": "user",
        "content": (
            "〔任务上下文压缩〕已完成步骤与关键结果：\n"
            + "\n".join(f"- {r}" for r in results)
            + f"\n（共收敛 {len(middle)} 条历史工具结果，任务目标与步骤清单见系统层当前任务块）"
        ),
    }
    new_messages = [*head, *keep[-2:], summary_msg, *tail] if keep else [*head, summary_msg, *tail]
    dropped = len(messages) - len(new_messages)
    if dropped <= 0:
        return 0
    messages[:] = new_messages
    logger.info("[task_flow] 步骤边界压缩：会话 %s 收敛 %d 条历史消息", session_id, dropped)
    return dropped


_GOAL_PREFIX_RE = re.compile(r"^(?:goal|目标|任务)\s*[:：]\s*(.+)$", re.IGNORECASE | re.DOTALL)


def current_user_id() -> str:
    """当前登录用户标识（未登录返回空串）——跨通道可见性判断用。"""
    try:
        from apiserver import naga_auth

        info = naga_auth.get_user_info() or {}
        return str(info.get("username") or info.get("id") or "").strip()
    except Exception:  # noqa: BLE001
        return ""


def cross_channel_shared() -> bool:
    cfg = _cfg()
    return bool(getattr(cfg, "cross_channel_shared", True)) if cfg is not None else True


def channel_visible_tasks(session_id: str, *, limit: int = 10) -> List[Dict[str, Any]]:
    """本通道可见的任务：本会话的 + （同用户且开启共享时）该用户其它通道的。

    跨通道维度落在 task_store.user_id（QQ/微信/CLI 同一登录用户即同一 user_id）。
    `task_flow.cross_channel_shared=false` 时只返回本会话任务（按通道隔离）。
    """
    own = task_store.list_tasks(session_id, limit=limit)
    if not cross_channel_shared():
        return own
    user_id = current_user_id()
    if not user_id:
        return own
    seen = {t["task_id"] for t in own}
    others = [t for t in task_store.list_tasks_by_user(user_id, limit=limit) if t["task_id"] not in seen]
    return [*own, *others]


def find_visible_task(session_id: str, task_id: str) -> Dict[str, Any] | None:
    """按 id 找任务，前提是该任务对本通道可见（否则 None，避免跨用户拿任务）。"""
    task = task_store.get_task(task_id)
    if not task:
        return None
    if task["session_id"] == session_id:
        return task
    if not cross_channel_shared():
        return None
    user_id = current_user_id()
    if user_id and str(task.get("user_id") or "") == user_id:
        return task
    return None


def bind_task_owner(task_id: str) -> None:
    """建任务时把当前登录用户绑上（跨通道继续的前提）。"""
    user_id = current_user_id()
    if user_id:
        task_store.set_user(task_id, user_id)


def idle_tasks(*, minutes: int = 30, limit: int = 5) -> List[Dict[str, Any]]:
    """空闲的进行中任务（供 SCHEDULER_TICK 联动：空闲期提示/自动推进）。"""
    cutoff = time.time() - max(1, int(minutes)) * 60
    out = []
    for status in (task_store.STATUS_RUNNING, task_store.STATUS_BLOCKED, task_store.STATUS_PAUSED):
        for task in task_store.list_tasks(status=status, limit=limit * 3):
            if float(task.get("updated_at") or 0) <= cutoff:
                out.append(task)
            if len(out) >= limit:
                return out
    return out


def scheduler_tick_advice(*, minutes: int = 30) -> str | None:
    """空闲任务提示文本（README 的 scheduler 联动示例用；无空闲任务返回 None）。"""
    tasks = idle_tasks(minutes=minutes)
    if not tasks:
        return None
    lines = [f"有 {len(tasks)} 个任务空闲超过 {minutes} 分钟："]
    for task in tasks:
        step = next_step(task)
        lines.append(f"- `{task['task_id']}` [{task['status']}] {task['goal'][:60]}"
                     + (f"｜下一步 {step['id']} {step['desc'][:40]}" if step else ""))
    lines.append("可 `task:continue <task_id>` 接着推进。")
    return "\n".join(lines)


def register_scheduler_advice(bus: Any) -> Any | None:
    """卷123 W123-05：把空闲任务提示挂到 SCHEDULER_TICK（卷120 W120-02 的发号器）。

    只在 `task_flow.idle_advance=true` 时发事件（默认关：只读提示，不自动改任务状态）。
    返回 disposer；未启用返回 None。
    """
    cfg = _cfg()
    if cfg is None or not getattr(cfg, "idle_advance", False):
        logger.info("[task_flow] 空闲任务提示未启用（task_flow.idle_advance=false）")
        return None
    try:
        from apiserver.event_bus import Topics
    except Exception as e:  # noqa: BLE001
        logger.warning("[task_flow] 调度联动挂载失败: %s", e)
        return None

    minutes = int(getattr(cfg, "idle_minutes", 30) or 30)

    def _on_tick(event: Any = None, *args: Any, **kwargs: Any) -> None:
        advice = scheduler_tick_advice(minutes=minutes)
        if advice:
            logger.info("[task_flow] 空闲任务提示：\n%s", advice)

    try:
        disposer = bus.on(Topics.SCHEDULER_TICK, _on_tick)
        logger.info("[task_flow] 空闲任务提示已挂到 SCHEDULER_TICK（阈值 %d 分钟）", minutes)
        return disposer
    except Exception as e:  # noqa: BLE001
        logger.warning("[task_flow] 调度联动注册失败: %s", e)
        return None


def goal_from_text(text: str) -> str:
    """从用户消息里取目标（`goal: xxx` / `目标：xxx`），没有前缀返回空串。"""
    hit = _GOAL_PREFIX_RE.match(str(text or "").strip())
    return (hit.group(1) or "").strip() if hit else ""


def goal_from_messages(messages: List[Dict[str, Any]]) -> str:
    """取最后一条用户消息里的目标（无前缀则整条当目标）。"""
    for msg in reversed(messages or []):
        if str(msg.get("role")) != "user":
            continue
        text = str(msg.get("content") or "").strip()
        return goal_from_text(text) or text[:400]
    return ""


def maybe_create_task_from_plan(session_id: str, plan_text: str, goal: str) -> Dict[str, Any] | None:
    """模型给出 `[PLAN]` 且本会话还没有任务时，按计划建任务（等用户确认才执行）。"""
    cfg = _cfg()
    if cfg is not None and not getattr(cfg, "enabled", True):
        return None
    if not plan_text or not str(goal or "").strip():
        return None
    if active_task(session_id) or pending_plan(session_id):
        return None
    return create_task_from_plan(session_id, goal, plan_text)


# ---------------------------------------------------------------------------
# 模型 [TASK] 段
# ---------------------------------------------------------------------------


def extract_task_ops(text: str) -> List[Dict[str, Any]]:
    """从模型输出里抽 `[TASK]{json}[/TASK]` 段（每段一个 JSON 对象或数组）。"""
    if not text or "[TASK]" not in text.upper():
        return []
    ops: List[Dict[str, Any]] = []
    for raw in _TASK_BLOCK_RE.findall(text):
        body = raw.strip()
        if not body:
            continue
        try:
            parsed = json.loads(body)
        except (json.JSONDecodeError, TypeError):
            logger.debug("[task_flow] [TASK] 段不是合法 JSON，跳过：%s", body[:120])
            continue
        if isinstance(parsed, dict):
            ops.append(parsed)
        elif isinstance(parsed, list):
            ops.extend([p for p in parsed if isinstance(p, dict)])
    return ops


def apply_task_ops(session_id: str, ops: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """把模型声明的任务操作落到 task_store，返回逐条执行结果（含 error 说明）。"""
    applied: List[Dict[str, Any]] = []
    for op in ops or []:
        kind = str(op.get("op") or op.get("action") or "").lower()
        try:
            applied.append(_apply_one(session_id, kind, op))
        except Exception as e:  # noqa: BLE001 - 单条失败不影响其它条
            logger.warning("[task_flow] 任务操作失败: %s", e)
            applied.append({"op": kind, "ok": False, "error": str(e)})
    return applied


def _apply_one(session_id: str, kind: str, op: Dict[str, Any]) -> Dict[str, Any]:
    if kind in ("create", "new"):
        task = task_store.create_task(
            session_id,
            str(op.get("goal") or ""),
            steps=op.get("steps") or default_steps(),
            exec_mode=str(op.get("exec_mode") or "explore"),
            status=task_store.STATUS_RUNNING,
        )
        return {"op": "create", "ok": True, "task_id": task["task_id"], "steps": len(task["steps"])}

    if kind in ("step", "update_step"):
        task_id = str(op.get("task_id") or "")
        if not task_id:
            task = active_task(session_id)
            task_id = task["task_id"] if task else ""
        if not task_id:
            return {"op": kind, "ok": False, "error": "no_task"}
        # fail-closed：blocked/failed 步骤会让任务整体 blocked，不再自动往下走；
        # 实现类步骤先过验证门（W123-03）
        if str(op.get("status") or task_store.STEP_DONE) in (task_store.STEP_DONE, "done"):
            result = finish_step_with_verify(
                task_id,
                str(op.get("step_id") or ""),
                result_ref=str(op.get("result_ref") or ""),
                tool=str(op.get("tool") or ""),
                summary=str(op.get("summary") or ""),
                session_id=session_id,
            )
        else:
            result = record_step_result(
                task_id,
                str(op.get("step_id") or ""),
                str(op.get("status") or task_store.STEP_DONE),
                result_ref=str(op.get("result_ref") or ""),
                tool=str(op.get("tool") or ""),
                summary=str(op.get("summary") or ""),
            )
        if not result.get("ok"):
            return {"op": kind, "ok": False, "error": result.get("error")}
        result["op"] = kind
        return result

    if kind in ("complete", "done", "finish"):
        task_id = str(op.get("task_id") or "")
        if not task_id:
            task = active_task(session_id)
            task_id = task["task_id"] if task else ""
        if not task_id:
            return {"op": kind, "ok": False, "error": "no_task"}
        updated = task_store.set_status(task_id, str(op.get("status") or task_store.STATUS_DONE))
        task_store.append_trajectory(task_id, tool="task:complete",
                                     summary=str(op.get("summary") or ""), status="done")
        return {"op": "complete", "ok": bool(updated), "task_id": task_id}

    if kind == "pause":
        task = active_task(session_id)
        if not task:
            return {"op": kind, "ok": False, "error": "no_task"}
        task_store.pause_task(task["task_id"])
        return {"op": kind, "ok": True, "task_id": task["task_id"]}

    return {"op": kind, "ok": False, "error": "unknown_op"}
