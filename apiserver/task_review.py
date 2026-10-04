"""Review 阶段（卷123 W123-04）。

任务执行完不直接交付：自动汇总「改动 + 验证结果 + 涉及文件 + 待确认问题」给用户审，
用户裁决三选一——**确认**（done 且存档）/ **打回**（回 running，带意见继续修）/ **跳过**（done 但标「未经 review」）。

报告落盘 `docs/task-reviews/<task_id>.md`（目录可用 `task_flow.review_dir` 覆盖）；
保留策略：一任务一文件，不自动清理，重跑同一任务覆盖同名文件（旧内容以 git 历史为准）。
"""
from __future__ import annotations

import logging
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from apiserver import task_store

logger = logging.getLogger(__name__)

VERDICT_PENDING = "pending"
VERDICT_CONFIRMED = "confirmed"
VERDICT_REJECTED = "rejected"
VERDICT_SKIPPED = "skipped"

VALID_VERDICTS = {VERDICT_PENDING, VERDICT_CONFIRMED, VERDICT_REJECTED, VERDICT_SKIPPED}


def _cfg() -> Any:
    try:
        from system.config import get_config

        return getattr(get_config(), "task_flow", None)
    except Exception:  # noqa: BLE001
        return None


def review_dir() -> Path:
    cfg = _cfg()
    configured = str(getattr(cfg, "review_dir", "") or "").strip() if cfg is not None else ""
    base = Path(configured) if configured else Path("docs/task-reviews")
    if not base.is_absolute():
        base = Path(__file__).resolve().parent.parent / base
    return base


# ---------------------------------------------------------------------------
# diff 摘要
# ---------------------------------------------------------------------------


def _run_git(args: List[str], cwd: Path, timeout: float = 8.0) -> Tuple[bool, str]:
    try:
        proc = subprocess.run(
            ["git", *args], cwd=str(cwd), capture_output=True, text=True, timeout=timeout,
        )
    except Exception as e:  # noqa: BLE001 - git 不可用不算错误
        logger.debug("[task_review] git 不可用: %s", e)
        return False, ""
    if proc.returncode != 0:
        return False, (proc.stderr or "").strip()
    return True, (proc.stdout or "").strip()


def diff_summary(task: Dict[str, Any]) -> Dict[str, Any]:
    """改动摘要：优先任务工作区，其次仓库根，再退回任务记录（见 _diff_summary_impl）。"""
    return _diff_summary_impl(task)


def _diff_summary_impl(task: Dict[str, Any]) -> Dict[str, Any]:
    """改动摘要：优先任务工作区，其次（任务确实动了仓库文件时）仓库根，最后退回任务记录。

    注意：不能无条件拿仓库 `git diff` 当任务的改动——那只说明「当前工作区脏」，
    与这个任务做了什么无关。只有任务 file_refs 指向仓库内文件时才认为任务动了仓库。
    """
    from mcpserver.code_workspace import sandbox

    refs = [str(p) for p in (task.get("file_refs") or [])]
    candidates: List[Tuple[str, Path]] = []
    try:
        candidates.append(("workspace", sandbox.session_workspace(str(task.get("session_id") or "default"))))
    except Exception:  # noqa: BLE001
        pass
    repo_root = Path(__file__).resolve().parent.parent
    if any((repo_root / ref).exists() for ref in refs if ref and not ref.startswith(".")):
        candidates.append(("repo", repo_root))

    for source, path in candidates:
        ok, out = _run_git(["diff", "--stat", "HEAD"], path)
        if not ok or not out:
            continue
        if source == "repo":
            pathspec = [ref for ref in refs if (repo_root / ref).exists()]
            ok2, out2 = _run_git(["diff", "--stat", "HEAD", "--", *pathspec[:20]], path)
            if ok2 and out2:
                out = out2
        files = [line for line in out.splitlines() if "|" in line]
        tail = out.splitlines()[-1] if out.splitlines() else ""
        changed = len(files)
        insertions = deletions = 0
        hit = re.search(r"(\d+) insertions?\(\+\)", tail)
        if hit:
            insertions = int(hit.group(1))
        hit = re.search(r"(\d+) deletions?\(-\)", tail)
        if hit:
            deletions = int(hit.group(1))
        return {
            "source": source,
            "path": str(path),
            "changed_files": changed,
            "insertions": insertions,
            "deletions": deletions,
            "files": [line.split("|")[0].strip() for line in files][:30],
            "stat": out,
        }
    return {
        "source": "task_record",
        "path": "",
        "changed_files": len(refs),
        "insertions": 0,
        "deletions": 0,
        "files": refs[:30],
        "stat": "",
    }


# ---------------------------------------------------------------------------
# 汇总与报告
# ---------------------------------------------------------------------------


def collect_verifications(task: Dict[str, Any]) -> List[Dict[str, Any]]:
    """从步骤结果里收每步的验证结论（验证门写进 result_ref 的那段）。"""
    out: List[Dict[str, Any]] = []
    for step in task.get("steps") or []:
        ref = str(step.get("result_ref") or "")
        if "[验证门" not in ref:
            continue
        # 结论词必须整取：「未通过」含「通过」，用子串判断会把失败看成成功
        hit = re.search(r"\[验证门 ([^\]]+)\] (通过|未通过|超时|跳过|未执行)", ref)
        outcome = hit.group(2) if hit else "未知"
        out.append({
            "step_id": step.get("id"),
            "type": step.get("type"),
            "status": step.get("status"),
            "mode": hit.group(1) if hit else "",
            "result": outcome,
            "ok": outcome == "通过",
            "attempts": int(step.get("verify_attempts") or 0),
        })
    return out


def open_questions(task: Dict[str, Any], diff: Dict[str, Any], verifies: List[Dict[str, Any]]) -> List[str]:
    """待确认问题（自评清单，不调 LLM，纯规则）。"""
    questions: List[str] = []
    steps = task.get("steps") or []
    unfinished = [s for s in steps if s.get("status") not in (task_store.STEP_DONE, task_store.STEP_SKIPPED)]
    if unfinished:
        questions.append(f"仍有 {len(unfinished)} 步未完成：" +
                         "、".join(f"{s.get('id')}({s.get('status')})" for s in unfinished))
    failed_verify = [v for v in verifies if not v.get("ok")]
    if failed_verify:
        questions.append("验证未全绿：" +
                         "、".join(f"{v['step_id']} {v['result']}" for v in failed_verify))
    if not verifies:
        questions.append("本次没有任何验证门结果（步骤未含实现类变更？），改动未被自动验证")
    if diff.get("source") == "task_record":
        questions.append("工作区非 git 仓库，改动清单来自任务记录，行数统计缺失")
    retried = [v for v in verifies if v["attempts"] > 1]
    if retried:
        questions.append("存在重试验证的步骤：" + "、".join(v["step_id"] for v in retried))
    if not str(task.get("git_state") or ""):
        questions.append("任务未记录 git 基线，无法对比任务前后的版本差异")
    if not questions:
        questions.append("无明显遗留项：改动、验证、文件清单均已汇总，请确认是否符合预期")
    return questions


def build_review(task_id: str, *, write_report: bool = True) -> Dict[str, Any]:
    """生成审查汇总（markdown 报告 + 结构化字段），并入任务 review_json。"""
    task = task_store.get_task(task_id)
    if not task:
        return {"ok": False, "error": "task_not_found"}

    diff = _diff_summary_impl(task)
    verifies = collect_verifications(task)
    questions = open_questions(task, diff, verifies)
    steps_done = sum(1 for s in (task.get("steps") or [])
                     if s.get("status") in (task_store.STEP_DONE, task_store.STEP_SKIPPED))
    total = len(task.get("steps") or [])

    lines = [
        f"# 任务审查 · {task_id}",
        "",
        f"- 目标：{task.get('goal')}",
        f"- 状态：{task.get('status')}（{steps_done}/{total} 步完成）｜模式：{task.get('exec_mode')}",
        f"- 会话：{task.get('session_id')}｜git 基线：{task.get('git_state') or '（无）'}",
        "",
        "## 改动摘要",
        f"- 来源：{diff.get('source')}（{diff.get('path') or '—'}）",
        f"- 文件数：{diff.get('changed_files')}｜+{diff.get('insertions')} / -{diff.get('deletions')}",
    ]
    if diff.get("files"):
        lines += ["- 文件清单："] + [f"  - {f}" for f in diff["files"]]
    if diff.get("stat"):
        lines += ["", "```", str(diff["stat"])[:2000], "```"]

    lines += ["", "## 验证结果"]
    if verifies:
        for v in verifies:
            lines.append(f"- {v['step_id']}（{v['type']}，{v['status']}）：{v['mode']} {v['result']}"
                         + (f"｜重试 {v['attempts'] - 1} 次" if v["attempts"] > 1 else ""))
    else:
        lines.append("- （无验证门结果）")

    lines += ["", "## 涉及文件"]
    lines += [f"- {p}" for p in (task.get("file_refs") or [])] or ["- （无）"]

    lines += ["", "## 待确认问题"]
    lines += [f"- {q}" for q in questions]

    lines += ["", "## 裁决", f"- {_verdict_line((task.get('review') or {}).get('verdict'))}"]
    report = "\n".join(lines)

    review = {
        "generated_at": time.time(),
        "diff": diff,
        "verifications": verifies,
        "questions": questions,
        "steps_done": steps_done,
        "steps_total": total,
        "verdict": VERDICT_PENDING,
        "report": report,
    }
    path = ""
    if write_report:
        path = str(_write_report(task_id, report))
        review["report_path"] = path
    task_store.set_review(task_id, review)
    return {"ok": True, "task_id": task_id, "report": report, "review": review, "report_path": path}


def _verdict_line(verdict: str | None) -> str:
    return {
        VERDICT_CONFIRMED: "已确认（任务 done，轨迹存档）",
        VERDICT_REJECTED: "已打回（回到 running，按意见继续修）",
        VERDICT_SKIPPED: "已跳过（done，标记：未经 review）",
    }.get(str(verdict or VERDICT_PENDING), "待裁决（确认 / 打回 / 跳过）")


def _write_report(task_id: str, report: str) -> Path:
    directory = review_dir()
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{task_id}.md"
    path.write_bytes(report.encode("utf-8"))  # 字节写：避免 Windows 文本模式改行尾
    logger.info("[task_review] 审查报告已落盘 %s", path)
    return path


def apply_verdict(task_id: str, verdict: str, *, note: str = "") -> Dict[str, Any]:
    """用户裁决：确认 / 打回 / 跳过。"""
    if verdict not in VALID_VERDICTS - {VERDICT_PENDING}:
        return {"ok": False, "error": f"unknown_verdict:{verdict}"}
    task = task_store.get_task(task_id)
    if not task:
        return {"ok": False, "error": "task_not_found"}

    review = dict(task.get("review") or {})
    if not review:
        built = build_review(task_id, write_report=False)
        review = built.get("review") or {}
    review["verdict"] = verdict
    review["verdict_at"] = time.time()
    review["verdict_note"] = str(note or "")
    task_store.set_review(task_id, review)

    if verdict == VERDICT_CONFIRMED:
        status = task_store.STATUS_DONE
        task_store.append_trajectory(task_id, tool="review:confirm",
                                     summary="审查通过，轨迹存档", status=status)
    elif verdict == VERDICT_REJECTED:
        status = task_store.STATUS_RUNNING
        task_store.append_trajectory(task_id, tool="review:reject",
                                     summary=f"打回：{note or '（无意见）'}", status=status)
    else:  # skipped
        status = task_store.STATUS_DONE
        task_store.append_trajectory(task_id, tool="review:skip",
                                     summary="跳过审查（未经 review）", status=status)
    task_store.set_status(task_id, status)

    # 裁决后把报告补一行再落盘（保留同文件，git 历史留档）
    report = str(review.get("report") or "")
    if report:
        report = re.sub(r"## 裁决\n- .*$", f"## 裁决\n- {_verdict_line(verdict)}", report, flags=re.DOTALL)
        if note:
            report += f"\n- 用户意见：{note}"
        _write_report(task_id, report)
        review["report"] = report
        task_store.set_review(task_id, review)

    logger.info("[task_review] 任务 %s 裁决=%s（note=%s）", task_id, verdict, note[:80])
    return {"ok": True, "task_id": task_id, "verdict": verdict, "status": status,
            "review": review, "report_path": review.get("report_path", "")}


def review_prompt(task_id: str) -> str:
    """任务 review 完成后的对话提示（把报告要点丢给用户裁决）。"""
    task = task_store.get_task(task_id)
    if not task:
        return ""
    review = task.get("review") or {}
    if not review:
        built = build_review(task_id)
        review = built.get("review") or {}
    lines = [
        f"任务 `{task_id}` 已进入审查（{review.get('steps_done')}/{review.get('steps_total')} 步）：",
        str(review.get("report", ""))[:1200],
        "请裁决：`task:accept` 确认 / `task:reject <意见>` 打回继续修 / `task:skip-review` 跳过（标记未经 review）",
    ]
    return "\n".join(lines)


def stats() -> Dict[str, Any]:
    """审查目录统计（README 保留策略用）。"""
    directory = review_dir()
    files = list(directory.glob("*.md")) if directory.exists() else []
    return {"dir": str(directory), "reports": len(files),
            "latest": max((f.stat().st_mtime for f in files), default=0)}


__all__ = [
    "build_review", "apply_verdict", "review_prompt", "diff_summary",
    "collect_verifications", "open_questions", "review_dir", "stats",
    "VERDICT_CONFIRMED", "VERDICT_REJECTED", "VERDICT_SKIPPED", "VERDICT_PENDING",
]
