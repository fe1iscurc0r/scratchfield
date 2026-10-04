#!/usr/bin/env python3
"""W121-02 端到端实测：真实 LLM + 真实 code_workspace 工具，跑「写代码 → 跑 → 报错 → 改 → 再跑」闭环。

与 pytest（tests/test_agentic_loop_flow.py）的区别：那里用替身断言协议，这里走真实链路
（llm_service → 原生 function calling → execute_tool_calls → mcpserver code_workspace 沙箱）。

用法（仓库根目录）：
    .venv/Scripts/python.exe tools/e2e_agentic_loop.py
    .venv/Scripts/python.exe tools/e2e_agentic_loop.py --max-steps 6 --session e2e-demo

退出码：0 = 至少发生一次真实工具调用且循环正常收敛；1 = 未发生工具调用 / LLM 不可用。
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

DEFAULT_PROMPT = (
    "用 code_workspace 工具完成一个真实任务：在工作区写一个文件 calc.py，"
    "实现 add(a, b)；然后用 test_run 跑测试；如果测试文件还不存在，先用 file_write 写一个 "
    "tests/test_calc.py（包含一条断言 add(1, 1) == 2 的用例）。"
    "目标是把测试跑到全绿，最后用一句话告诉我最终的测试结果。"
)

SEED_PROMPT = (
    "工作区里已经有一个实现有 bug 的 calc.py 和一条失败的测试 tests/test_calc.py。"
    "请先 test_run 跑一次看失败信息，再用 file_read 看代码，定位并修好 bug（用 file_edit 改），"
    "最后再 test_run 确认全绿，并告诉我最终 passed/failed 计数。"
)

SEED_FILES = {
    "calc.py": "def add(a, b):\n    return a - b  # BUG: 应该是加法\n",
    "tests/test_calc.py": "from calc import add\n\n\ndef test_add():\n    assert add(1, 1) == 2\n",
}


def _setup_gates() -> None:
    """挂载工具安全门 + 写操作确认门（等价 api_server lifespan 里的注册；进程内单例，重复挂无害）。"""
    from apiserver.event_bus import get_bus
    from apiserver.event_bus.confirm_gate import register_confirm_gate
    from apiserver.event_bus.tool_gate import register_tool_gates

    bus = get_bus()
    register_tool_gates(bus)
    register_confirm_gate(bus)
    print("[E2E] 已挂载工具安全门 + 写操作确认门")


def seed_workspace(session_id: str) -> list[str]:
    """预置一个「实现有 bug + 测试失败」的工作区，强制走 失败→定位→改→再跑 闭环。"""
    from mcpserver.code_workspace import sandbox

    ws = sandbox.session_workspace(session_id)
    written = []
    for rel, content in SEED_FILES.items():
        target = ws / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content.encode("utf-8"))
        written.append(rel)
    return written


def _tool_schemas() -> list[dict]:
    """只取 code_workspace 的 native function calling schema（聚焦，避免 32 个 agent 干扰）。"""
    from apiserver.tool_schemas import get_all_tool_schemas

    schemas = [
        s
        for s in get_all_tool_schemas()
        if str(s.get("function", {}).get("name", "")).startswith("mcp__code_workspace__")
    ]
    return schemas


async def _run(prompt: str, max_steps: int, session_id: str, verbose: bool, confirm_flow: bool = False) -> int:
    from apiserver.agentic_tool_loop import run_agentic_loop

    _setup_gates()
    tools = _tool_schemas()
    if not tools:
        print("[E2E] 未取到 code_workspace 工具 schema —— MCP 注册失败？")
        return 1
    print(f"[E2E] 可用工具 {len(tools)} 个: {[t['function']['name'] for t in tools]}")
    print(f"[E2E] max_steps={max_steps} session={session_id}")

    messages = [
        {"role": "system", "content": "你是陆墨，一个能真正动手写代码的助手。需要写/跑代码时直接调用工具，不要只描述。"},
        {"role": "user", "content": prompt},
    ]

    tool_rounds, final_text = await _run_phase(messages, session_id, max_steps, tools, verbose, "阶段1")

    # W121-03：写操作确认门 —— 待确认时模拟用户回复「确认，执行」并再跑一轮
    if confirm_flow:
        from apiserver.event_bus.confirm_gate import get_confirm_gate

        gate = get_confirm_gate()
        pending = gate.pending(session_id)
        if pending:
            for item in pending:
                print(f"[E2E] 待确认: {item['tool']} → {item['path']} (sig={item['signature']})")
                print(f"[E2E]   diff: {str(item.get('diff', ''))[:200]}")
            decision = gate.observe_user_message(session_id, "确认，执行")
            print(f"[E2E] 用户回复「确认，执行」→ 确认门决策={decision}")
            messages.append({"role": "assistant", "content": final_text or "（已提交写操作，等待确认）"})
            messages.append({"role": "user", "content": "确认，执行"})
            extra_rounds, final_text2 = await _run_phase(
                messages, session_id, max_steps, tools, verbose, "阶段2（确认后）"
            )
            tool_rounds += extra_rounds
            final_text = final_text2 or final_text
        else:
            print("[E2E] 本轮无待确认写操作（确认门未触发）")

    print("\n===== 最终答复 =====")
    print(final_text.strip() or "(空)")

    # 落盘证据：工作区文件清单
    try:
        from mcpserver.code_workspace import sandbox

        ws = sandbox.session_workspace(session_id)
        print(f"\n===== 工作区 {ws} =====")
        for path in sorted(ws.rglob("*")):
            if path.is_file():
                print(f"- {path.relative_to(ws)}  ({path.stat().st_size}B)")
    except Exception as e:  # noqa: BLE001
        print(f"[E2E] 工作区列举失败: {e}")

    print(f"\n[E2E] 工具调用轮次={tool_rounds}")
    return 0 if tool_rounds else 1


async def _run_phase(
    messages: list[dict],
    session_id: str,
    max_steps: int,
    tools: list[dict],
    verbose: bool,
    label: str,
) -> tuple[int, str]:
    """跑一轮完整 agentic loop，返回 (工具调用轮次, 最终正文)。"""
    from apiserver.agentic_tool_loop import run_agentic_loop

    print(f"\n[E2E] ===== {label} =====")
    tool_rounds = 0
    final_text = ""
    async for chunk in run_agentic_loop(messages, session_id, max_rounds=max_steps, tools=tools):
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
            final_text += event.get("text", "")
            if verbose:
                print(event.get("text", ""), end="", flush=True)
        elif etype == "reasoning":
            continue
        elif etype == "tool_calls":
            tool_rounds += 1
            names = [
                f"{c.get('service_name', '')}:{c.get('tool_name', '')}"
                for c in event.get("calls", [])
                if c.get("agentType") != "live2d"
            ]
            if names:
                print(f"\n[E2E] 第 {tool_rounds} 次工具调用: {names}")
        elif etype == "tool_results":
            for r in event.get("results", []):
                preview = str(r.get("result", ""))[:220].replace("\n", " ")
                print(
                    f"[E2E]   结果 {r.get('tool_name')} status={r.get('status')} "
                    f"attempts={r.get('attempts', 1)}: {preview}"
                )
        elif etype == "tool_retry":
            print(f"[E2E]   触发重试: {event.get('retries')}")
        elif etype == "pending_confirm":
            print(f"[E2E]   待确认写操作: {[i.get('path') for i in event.get('items', [])]}")
        elif etype == "plan":
            print(f"[E2E]   [PLAN] 事件: {str(event.get('text'))[:160]}")
        elif etype in ("round_start", "round_end"):
            print(f"[E2E] {etype}: { {k: v for k, v in event.items() if k != 'type'} }")
        elif etype in ("content_clean", "status", "compress_start", "compress_end"):
            print(f"[E2E] {etype}: {str(event)[:160]}")
    return tool_rounds, final_text


def main() -> int:
    parser = argparse.ArgumentParser(description="W121-02 agentic loop 端到端实测")
    parser.add_argument("--prompt", default=None, help="自定义提示词（默认按 --seed 选择）")
    parser.add_argument("--max-steps", type=int, default=6)
    parser.add_argument("--session", default="e2e-w121")
    parser.add_argument("--quiet", action="store_true", help="不逐字打印流式正文")
    parser.add_argument(
        "--seed",
        action="store_true",
        help="预置「实现有 bug + 测试失败」的工作区，跑 失败→定位→改→再跑 闭环",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="W121-03：走确认门两阶段（首次写被拦 → 模拟用户「确认」→ 再跑一轮落盘）",
    )
    args = parser.parse_args()
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

    prompt = args.prompt or (SEED_PROMPT if args.seed else DEFAULT_PROMPT)
    if args.seed:
        written = seed_workspace(args.session)
        print(f"[E2E] 预置文件: {written}")
    return asyncio.run(
        _run(prompt, args.max_steps, args.session, verbose=not args.quiet, confirm_flow=args.confirm)
    )


if __name__ == "__main__":
    raise SystemExit(main())
