"""工单222 任务三 · 单例加锁 codemod（AST 判定 + 文本改写，幂等）。

把「裸 check-then-set 懒加载单例」就地改成仓内既有的 DCL 模式：

    _x: T | None = None                       _x: T | None = None
                                              _x_lock = threading.Lock()
    def get_x():                              def get_x():
        global _x                                 global _x
        if _x is None:                            if _x is None:
            _x = T()                                  with _x_lock:
        return _x                                         if _x is None:
                                                              _x = T()
                                              return _x

只在 AST 确认函数体形状完全匹配时改写（不匹配 → 跳过并报告），默认 dry-run。

用法：
    python tools/singleton_lock_codemod.py --check <file> [<file> ...]
    python tools/singleton_lock_codemod.py --write <file> [<file> ...]
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

TARGETS: dict[str, list[str]] = {
    # file -> 要处理的 getter 名（空列表 = 自动挑所有匹配的 getter）
    "apiserver/device_state.py": ["get_device_state_store"],
    "apiserver/message_queue.py": ["get_message_queue"],
    "apiserver/loop_checkpoint.py": ["get_loop_checkpoint"],
    "apiserver/llm_service.py": ["get_llm_service"],
    "apiserver/hil_evaluator.py": ["get_hil_evaluator"],
    "apiserver/knowledge_driver.py": ["get_knowledge_driver"],
    "apiserver/telemetry.py": ["get_telemetry_manager"],
    "apiserver/websocket_manager.py": ["get_websocket_manager"],
    "apiserver/von_client.py": ["get_von_client"],
    "apiserver/neko_cua.py": ["_get_client"],
    "apiserver/channels/__init__.py": ["get_channel_registry"],
    "apiserver/event_bus/__init__.py": ["get_bus"],
    "apiserver/event_bus/event_store.py": ["get_event_store"],
    "apiserver/event_bus/confirm_gate.py": ["get_confirm_gate"],
    "apiserver/event_bus/tool_gate.py": ["get_tool_gate_runtime"],
    "apiserver/event_bus/surface.py": ["get_surface_store"],
    "apiserver/event_bus/trace.py": ["get_trace_store"],
    "apiserver/event_bus/scheduler.py": ["get_scheduler"],
    "apiserver/event_bus/memory_lifecycle.py": ["get_memory_consumer"],
    "mcpserver/mcp_manager.py": ["get_mcp_manager"],
    "mcpserver/telemetry.py": ["get_recorder", "get_breaker"],
    "mcpserver/mcp_server.py": ["_get_chain_executor"],
    "agentserver/dogtag/registry.py": ["get_dogtag_registry"],
    "agentserver/openclaw/config_manager.py": ["get_openclaw_config_manager"],
    "agentserver/openclaw/detector.py": ["get_openclaw_detector"],
    "agentserver/openclaw/openclaw_client.py": ["get_openclaw_client"],
    "agentserver/dogtag/screen_vision/metrics.py": ["get_metrics"],
    "mcpserver/memory_maas/core.py": ["get_core"],
    "mcpserver/trust_layer.py": ["get_trust_scorer"],
    "mcpserver/ptz_service/tools.py": ["get_service"],
    "mcpserver/rf_brain/sentinel_bridge.py": ["get_store"],
    # ── 第二批（改写后扫描出的剩余裸单例）──
    "apiserver/agentic_loop_parts/executor_openclaw.py": ["_get_openclaw_client"],
    "apiserver/routes/lumo_proxy.py": ["_get_vision_client"],
    "mcpserver/adapters/semantic_web/bridge.py": ["get_bridge"],
    "mcpserver/agent_open_launcher/comprehensive_app_scanner.py": ["get_comprehensive_scanner"],
    "mcpserver/agent_open_launcher/registry_app_scanner.py": ["get_registry_scanner"],
    "mcpserver/rf_brain/spectrum_events_bridge.py": ["get_cache"],
    "mcpserver/rf_brain/sentinel_link/occupation.py": ["get_detector"],
    "agentserver/agent_server_parts/search.py": ["_get_search_client"],
    "agentserver/openclaw/embedded_runtime.py": ["get_embedded_runtime"],
    "agentserver/openclaw/installer.py": ["get_openclaw_installer"],
    "system/config.py": ["get_prompt_manager"],
    "system/health_check.py": ["get_health_checker"],
    "system/skill_manager.py": ["get_skill_manager"],
}


def _shape_ok(fn: ast.FunctionDef | ast.AsyncFunctionDef, src_lines: list[str]) -> dict | None:
    """校验函数体恰为「(docstring)? / global X / if X is None: X = Call(...) / return X」形状。

    If 体内已含 `with`（即已有锁）→ 返回 "already"，不改。
    """
    body = fn.body
    if not body:
        return None
    gi = 0
    if isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
            and isinstance(body[0].value.value, str):
        gi = 1  # 跳过 docstring
    if gi >= len(body) or not isinstance(body[gi], ast.Global):
        return None
    globals_ = body[gi].names
    gi += 1
    if len(body) != gi + 2:
        return None
    cond, ret = body[gi], body[gi + 1]
    if not isinstance(cond, ast.If) or not isinstance(ret, ast.Return):
        return None
    # if X is None:
    t = cond.test
    if not (isinstance(t, ast.Compare) and len(t.ops) == 1
            and isinstance(t.ops[0], ast.Is) and len(t.comparators) == 1):
        return None
    if not (isinstance(t.left, ast.Name) and isinstance(t.comparators[0], ast.Constant)
            and t.comparators[0].value is None):
        return None
    var = t.left.id
    if var not in globals_:
        return None
    if len(cond.body) != 1:
        return None
    asg = cond.body[0]
    if isinstance(asg, ast.With):
        return {"var": var, "already": True, "fn_lineno": fn.lineno}
    if not (isinstance(asg, ast.Assign) and isinstance(asg.value, ast.Call)
            and len(asg.targets) == 1 and isinstance(asg.targets[0], ast.Name)
            and asg.targets[0].id == var):
        return None
    ret_val = ret.value
    if not (isinstance(ret_val, ast.Name) and ret_val.id == var):
        return None
    return {"var": var, "already": False, "if_lineno": cond.lineno, "ret_lineno": ret.lineno,
            "fn_lineno": fn.lineno, "fn_end": fn.end_lineno}


def patch_file(path: Path, wanted: list[str], write: bool) -> list[str]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)
    tree = ast.parse(text)
    reports: list[str] = []

    fns = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    todo = []
    already = []
    for fn in fns:
        if wanted and fn.name not in wanted:
            continue
        info = _shape_ok(fn, lines)
        if info is None:
            if wanted and fn.name in wanted:
                reports.append(f"  ⚠ 跳过 {fn.name}: 形状不匹配（需人工看）")
            continue
        if info.get("already"):
            already.append(fn.name)
            continue
        todo.append((fn, info))

    for name in already:
        reports.append(f"  ✓ 已带锁 {name}（不改）")

    if not todo:
        return reports or ["  (无需处理)"]

    # 从后往前改行，避免行号漂移
    todo.sort(key=lambda x: x[1]["fn_lineno"], reverse=True)
    lock_decl_lines: dict[str, int] = {}
    for fn, info in todo:
        var = info["var"]
        lock_name = f"{var}_lock"
        indent = "    "
        # 1) 替换 if 块（含 global 保留）
        if_line_i = info["if_lineno"] - 1
        ret_line_i = info["ret_lineno"] - 1
        # 取原 if 块的两行（if ...: / 赋值）
        orig_if = lines[if_line_i]
        orig_asg = lines[if_line_i + 1]
        new_if = (f"{indent}if {var} is None:\n"
                  f"{indent}    with {lock_name}:\n"
                  f"{indent}        if {var} is None:\n"
                  f"{indent}            {orig_asg.strip()}\n")
        lines[if_line_i:if_line_i + 2] = [new_if]
        # 2) 记录 lock 声明插入点（函数定义行之前）
        lock_decl_lines[lock_name] = info["fn_lineno"] - 1
        reports.append(f"  ✓ {fn.name}: {var} → DCL({lock_name})")

    # 插入 lock 声明（按行号从后往前）
    for lock_name, at in sorted(lock_decl_lines.items(), key=lambda x: -x[1]):
        lines.insert(at, f"{lock_name} = threading.Lock()\n")

    new_text = "".join(lines)

    # 3) 确保 threading 已导入
    if "import threading" not in new_text:
        ins = 0
        for i, ln in enumerate(new_text.splitlines(keepends=True)):
            if ln.startswith("import ") or ln.startswith("from "):
                ins = i + 1
        nl = new_text.splitlines(keepends=True)
        nl.insert(ins, "import threading\n")
        new_text = "".join(nl)
        reports.append("  + 补 import threading")

    if write:
        # 统一 LF（仓库规范）
        new_text = new_text.replace("\r\n", "\n")
        path.write_bytes(new_text.encode("utf-8"))
    return reports


def main() -> int:
    mode = "--check"
    args = [a for a in sys.argv[1:]]
    if args and args[0] in ("--check", "--write"):
        mode = args.pop(0)
    write = mode == "--write"
    targets = args if args else list(TARGETS)
    total_ok = 0
    for t in targets:
        p = Path(t)
        if not p.exists():
            print(f"[缺失] {t}")
            continue
        wanted = TARGETS.get(t, [])
        reps = patch_file(p, list(wanted), write)
        ok = sum(1 for r in reps if r.strip().startswith("✓"))
        total_ok += ok
        print(f"[{t}] {'改写' if write else '待改写'} {ok} 处")
        for r in reps:
            print(r)
    print(f"\n合计: {total_ok} 处 | 模式={'--write' if write else '--check（未落盘）'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
