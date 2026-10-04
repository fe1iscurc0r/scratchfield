#!/usr/bin/env python3
"""卷123 端到端实测：目标模式全链路（目标 → [PLAN] → 建任务 → 确认 → 逐步执行 → 步状态落库）。

用法（仓库根目录）：
    .venv/Scripts/python.exe tools/e2e_task_flow.py
    .venv/Scripts/python.exe tools/e2e_task_flow.py --goal "给 utils.py 加一个 slugify 并测试" --max-steps 6

流程：
阶段1  `goal:<目标>` 进 loop → 模型出 [PLAN] → 系统建任务（pending，等确认）
阶段2  模拟用户 `task:confirm` → 任务转 running
阶段3  再进 loop → 模型逐步执行（调工具 / 报 [TASK] 步状态）→ 打印任务最终状态与轨迹
期间写操作会撞上卷121 的确认门，驱动脚本模拟用户确认（打印确认项）。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

DEFAULT_GOAL = "在工作区里加一个工具函数：写 utils.py 实现 slugify(text)（小写、空格转连字符），并写 tests/test_utils.py 覆盖它，跑到测试全绿。"

#: W123-03 验证门场景：工作区预置「实现是错的 + 测试已写好且失败」，逼出 验证失败→改→复验
SEED_BROKEN = {
    "utils.py": "def slugify(text):\n    return text  # BUG: 没做小写与空格转换\n",
    "tests/test_utils.py": (
        "from utils import slugify\n\n\n"
        "def test_slugify_lowercases():\n    assert slugify('Hello World') == 'hello-world'\n\n\n"
        "def test_slugify_spaces():\n    assert slugify('a  b') == 'a-b'\n"
    ),
}
SEED_GOAL = "工作区里 utils.py 的 slugify 实现是错的，tests/test_utils.py 现在是失败的。请把它修到测试全绿。"


def _seed(session_id: str, files: dict) -> list[str]:
    from mcpserver.code_workspace import sandbox

    ws = sandbox.session_workspace(session_id)
    written = []
    for rel, content in files.items():
        target = ws / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content.encode("utf-8"))
        written.append(rel)
    return written


def _setup() -> None:
    from apiserver.event_bus import get_bus
    from apiserver.event_bus.confirm_gate import register_confirm_gate
    from apiserver.event_bus.tool_gate import register_tool_gates

    bus = get_bus()
    register_tool_gates(bus)
    register_confirm_gate(bus)


def _tools() -> list[dict]:
    from apiserver.tool_schemas import get_all_tool_schemas

    return [
        s for s in get_all_tool_schemas()
        if str(s.get("function", {}).get("name", "")).startswith("mcp__code_workspace__")
    ]


async def _phase(messages: list[dict], session_id: str, max_steps: int, label: str) -> str:
    from apiserver.agentic_tool_loop import run_agentic_loop

    print(f"\n===== {label} =====")
    final = ""
    async for chunk in run_agentic_loop(messages, session_id, max_rounds=max_steps, tools=_tools()):
        if not chunk.startswith("data: "):
            continue
        body = chunk[6:].strip()
        if not body or body == "[DONE]":
            continue
        try:
            event = json.loads(body)
        except json.JSONDecodeError:
            continue
        etype = event.get("type", "content")
        if etype == "content":
            final += event.get("text", "")
        elif etype in ("error", "warning"):
            print(f"[E2E] {etype}: {str(event)[:300]}")
        elif etype == "tool_calls":
            names = [f"{c.get('tool_name')}" for c in event.get("calls", []) if c.get("agentType") != "live2d"]
            if names:
                print(f"[E2E] 工具调用: {names}")
        elif etype == "tool_results":
            for r in event.get("results", []):
                print(f"[E2E]   {r.get('tool_name')} {r.get('status')}: {str(r.get('result'))[:160]}")
        elif etype == "plan":
            print(f"[E2E] [PLAN] 事件（{len(str(event.get('text')).splitlines())} 行）")
        elif etype == "task_update":
            for item in event.get("applied", []):
                verify = item.get("verify")
                print(f"[E2E] task_update: {json.dumps({k: v for k, v in item.items() if k != 'verify'}, ensure_ascii=False)[:240]}")
                if verify:
                    print(f"[E2E]   验证门 mode={verify.get('mode')} ok={verify.get('ok')} "
                          f"passed={verify.get('passed')} failed={verify.get('failed')} "
                          f"errors={verify.get('errors')} exit={verify.get('exit_code')} "
                          f"retry={item.get('retry')} left={item.get('retries_left')}")
        elif etype == "pending_confirm":
            print(f"[E2E]   待确认写操作: {[i.get('path') for i in event.get('items', [])]}")
        elif etype in ("round_start", "round_end"):
            print(f"[E2E] {etype}: { {k: v for k, v in event.items() if k != 'type'} }")
    if final.strip():
        print(f"[E2E] 本轮正文（{len(final)} 字）：{final.strip()[:400].replace(chr(10), ' ')}")
    return final


def _confirm_pending_writes(session_id: str) -> list[dict]:
    """模拟用户确认写操作（卷121 确认门），让 goal 流程能真落盘。返回被确认的项。"""
    from apiserver.event_bus.confirm_gate import get_confirm_gate

    gate = get_confirm_gate()
    pending = gate.pending(session_id)
    if pending:
        for item in pending:
            print(f"[E2E] 确认写操作: {item['tool']} → {item['path']}")
        gate.decide(session_id, "confirm", source="e2e")
    return pending


async def _run(goal: str, session_id: str, max_steps: int, rounds: int) -> int:
    from apiserver import task_flow, task_store

    _setup()
    print(f"[E2E] goal={goal}\n[E2E] session={session_id} max_steps={max_steps}")

    messages = [
        {"role": "system", "content": "你是陆墨：先给计划，确认后逐步执行并报告进度。工具能用就直接用，不要只描述。"},
        {"role": "user", "content": f"goal: {goal}"},
    ]

    # 阶段1：出计划（模型输出 [PLAN] → 系统建任务）
    plan_text = await _phase(messages, session_id, max_steps, "阶段1 · 目标 → 计划")
    task = task_flow.active_task(session_id)
    if not task:
        print("[E2E] 未建出任务——模型没给 [PLAN]？")
        return 1
    print(f"[E2E] 任务 {task['task_id']} 状态={task['status']} 步骤={len(task['steps'])}")
    for s in task["steps"]:
        print(f"[E2E]   [{s['status']}] {s['id']} ({s['type']}) {s['desc']}")

    # 阶段2：用户确认计划
    confirm_reply = task_flow.run_meta_command(session_id, "task:confirm")
    print(f"\n[E2E] task:confirm → {confirm_reply.splitlines()[0]}")
    print(f"[E2E] 任务状态={task_store.get_task(task['task_id'])['status']}")

    messages.append({"role": "assistant", "content": plan_text or "（已给出计划）"})
    messages.append({"role": "user", "content": "确认，开始执行"})

    # 阶段3：逐步执行（多轮；每轮前把待确认写操作按真实 UX 处理：确认 + 用户回复「确认，执行」）
    last_text = plan_text
    for i in range(1, rounds + 1):
        confirmed = _confirm_pending_writes(session_id)
        if confirmed:
            messages.append({"role": "assistant", "content": last_text or "（已提交写操作）"})
            messages.append({"role": "user", "content": "确认，执行"})
        last_text = await _phase(messages, session_id, max_steps, f"阶段3.{i} · 执行")
        fresh = task_store.get_task(task["task_id"]) or {}
        print(f"[E2E] 执行 {i} 轮后：status={fresh.get('status')} "
              f"steps={[(s['id'], s['status']) for s in fresh.get('steps', [])]}")
        if fresh.get("status") in (task_store.STATUS_DONE, task_store.STATUS_REVIEW,
                                   task_store.STATUS_BLOCKED, task_store.STATUS_FAILED):
            break
    _confirm_pending_writes(session_id)

    final_task = task_store.get_task(task["task_id"]) or {}
    print("\n===== 任务最终状态 =====")
    print(task_store.task_summary(final_task))
    print("轨迹：")
    for t in final_task.get("trajectory", []):
        print(f"  - [{t.get('status')}] {t.get('tool') or '-'} {str(t.get('summary'))[:90]}")

    try:
        from mcpserver.code_workspace import sandbox

        ws = sandbox.session_workspace(session_id)
        print(f"\n===== 工作区 {ws} =====")
        for p in sorted(ws.rglob("*")):
            if p.is_file():
                print(f"- {p.relative_to(ws)} ({p.stat().st_size}B)")
    except Exception as e:  # noqa: BLE001
        print(f"[E2E] 工作区列举失败: {e}")

    return 0 if final_task.get("status") in (task_store.STATUS_DONE, task_store.STATUS_REVIEW) else 1


def _gate_demo(session_id: str) -> int:
    """W123-03 失败路径实测：对真实的「坏实现 + 失败测试」跑验证门 → 改 → 复验。

    不经过 LLM：直接对真实工作区调 `finish_step_with_verify`，看验证门自己怎么判。
    """
    from apiserver import task_flow, task_store, task_verify
    from mcpserver.code_workspace.tools import CodeWorkspaceBridge

    print("\n===== 验证门失败路径实测 =====")
    bridge = CodeWorkspaceBridge()
    task = task_store.create_task(
        session_id, "修好 slugify（验证门演示）",
        steps=[{"id": "s1", "desc": "探查：读 utils.py 与测试", "type": "explore"},
               {"id": "s2", "desc": "实现：改 utils.py 的 slugify", "type": "code"}],
        status=task_store.STATUS_RUNNING,
    )
    tid = task["task_id"]
    task_store.add_file_refs(tid, ["utils.py", "tests/test_utils.py"])

    # 步骤 1：探查（落摘要）
    task_flow.finish_step_with_verify(
        tid, "s1", result_ref="理解摘要：utils.py 的 slugify 直接 return text，测试期望小写+空格转连字符；最小改动路径：只改该函数",
        tool="file_read", session_id=session_id,
    )
    print(f"[GATE] s1 状态={task_store.get_task(tid)['steps'][0]['status']}，file_refs={task_store.get_task(tid)['file_refs']}")

    # 步骤 2：实现步（此时工作区里还是坏实现）→ 验证门应判失败
    first = task_flow.finish_step_with_verify(
        tid, "s2", result_ref="实现：slugify 保持直接返回 text", tool="file_edit", session_id=session_id,
    )
    v = first["verify"]
    print(f"[GATE] 第一次验证：mode={v['mode']} ok={v['ok']} passed={v['passed']} failed={v['failed']} "
          f"errors={v['errors']} exit={v['exit_code']} timeout={v['timeout']}")
    print(f"[GATE] 步骤状态={task_store.get_task(tid)['steps'][1]['status']} 任务状态={task_store.get_task(tid)['status']} "
          f"retry={first['retry']} 剩余额度={first['retries_left']}")
    print(f"[GATE] 结果行：{task_store.get_task(tid)['steps'][1]['result_ref'][:160]}")

    # 模型改：真正修好实现
    bridge.file_write("utils.py", "def slugify(text):\n    return '-'.join(text.lower().split())\n",
                      session_id=session_id)
    second = task_flow.finish_step_with_verify(
        tid, "s2", result_ref="实现：slugify 改为 '-'.join(text.lower().split())", tool="file_edit",
        session_id=session_id,
    )
    v2 = second["verify"]
    print(f"[GATE] 第二次验证：mode={v2['mode']} ok={v2['ok']} passed={v2['passed']} failed={v2['failed']} "
          f"exit={v2['exit_code']}")
    final = task_store.get_task(tid)
    print(f"[GATE] 最终：步骤={[(s['id'], s['status']) for s in final['steps']]} 任务状态={final['status']}")
    print(f"[GATE] 审计统计：{task_verify.max_retries()} 次重试额度，audit_only={task_verify.audit_only()}")
    return 0 if (v2["ok"] and final["status"] in (task_store.STATUS_DONE, task_store.STATUS_REVIEW)) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="卷123 目标模式端到端实测")
    parser.add_argument("--goal", default=None)
    parser.add_argument("--session", default="e2e-task-flow")
    parser.add_argument("--max-steps", type=int, default=6)
    parser.add_argument("--rounds", type=int, default=4, help="阶段3 最多执行几轮")
    parser.add_argument("--seed-broken", action="store_true",
                        help="W123-03：预置「实现有 bug + 测试失败」的工作区，逼出 验证门失败→改→复验")
    parser.add_argument("--gate-demo", action="store_true",
                        help="W123-03：直接跑验证门的失败→改→复验（不经 LLM）")
    args = parser.parse_args()
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if args.seed_broken or args.gate_demo:
        print(f"[E2E] 预置文件: {_seed(args.session, SEED_BROKEN)}")
    if args.gate_demo:
        return _gate_demo(args.session)
    goal = args.goal or (SEED_GOAL if args.seed_broken else DEFAULT_GOAL)
    return asyncio.run(_run(goal, args.session, args.max_steps, args.rounds))


if __name__ == "__main__":
    raise SystemExit(main())
