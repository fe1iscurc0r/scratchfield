"""审查门 — multica「Review Gate」落地：nothing ships without a human saying so。

完成 → in_review（不进 done），人审通过才 done；记录 review 时间/人/结论。
与 G-01 集成：task 状态流转 in_progress → in_review → done / in_progress。
"""

from __future__ import annotations

from mcpserver.workflow.board import Board
from mcpserver.workflow.task import Task


def request_review(board: Board, task_id: str,
                   trace_id: str | None = None) -> Task:
    """完成 → in_review（不进 done）。发 review_requested 事件。"""
    task = board.get(task_id)
    if task is None:
        raise KeyError(f"task not found: {task_id}")
    return board.set_status(task_id, "in_review", trace_id=trace_id)


def approve(board: Board, task_id: str, reviewer: str,
            conclusion: str = "", trace_id: str | None = None) -> Task:
    """人审通过 → done，记录审查时间/人/结论。发 review_approved 事件。"""
    return board.approve(task_id, reviewer, conclusion=conclusion,
                         trace_id=trace_id)


def reject(board: Board, task_id: str, reviewer: str,
           conclusion: str = "", trace_id: str | None = None) -> Task:
    """人审退回 → in_progress，记录审查结论。"""
    return board.reject(task_id, reviewer, conclusion=conclusion,
                        trace_id=trace_id)


def review(board: Board, task_id: str, reviewer: str, approved: bool,
           conclusion: str = "", trace_id: str | None = None) -> Task:
    """统一审查入口：approved=True 通过进 done，False 退回 in_progress。

    记录 review 时间 / 人 / 结论（见 board.reviews 表 + task.review 字段）。
    """
    if approved:
        return approve(board, task_id, reviewer, conclusion=conclusion,
                       trace_id=trace_id)
    return reject(board, task_id, reviewer, conclusion=conclusion,
                  trace_id=trace_id)
