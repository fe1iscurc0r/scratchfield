"""workflow — 多智能体编排落地产物（GOLF 线）。

源自 D 组三份授粉报告：
- orca-ade（Run/Task/Dispatch 三元素、Task DAG、Decision Gate、worker 收件箱）
- multica（issue 即工作单元、squad 路由、DB-backed 租约调度、Admission reason code、审查门）
- buzz-herdr（事件日志即消息总线、agent 生命周期状态机）

子模块：
- task:        Task 数据类（id/title/desc/status/assignee/deps/parent/时间戳）
- state_machine: 状态迁移校验（合法跳转 / 自循环抑制 / 重复 enqueue 抑制）
- board:       工单板（list/create/assign/status，SQLite 持久化）
- claim:       单赢家认领 + 租约（heartbeat / 超时 / 释放）
- reason:      ReasonCode 枚举（成功 / 拒绝 / blocked 可等·不可等子分类）
- admission:   认领 / 状态流转前的准入检查，返回稳定 reason code
- review_gate: 完成 → in_review（不进 done），人审通过才 done
- event_bus:   pub/sub + append-only 事件日志（可回放、trace_id 贯穿）
- agent_state: agent 生命周期状态机（idle/working/blocked/waiting_review/done）
- cli:         workflow-board 命令行入口
"""

from mcpserver.workflow.board import Board
from mcpserver.workflow.reason import ReasonCode
from mcpserver.workflow.task import Task

__all__ = ["Task", "Board", "ReasonCode"]
