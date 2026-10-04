"""split_tool_loop.py — 把 apiserver/agentic_tool_loop.py 按域拆到 agentic_loop_parts/（卷190-A2）。

与 tools/split_extensions.py 同一套方法论（AST 定块边界 + 纯搬移 + 薄壳），差异只在映射表。

用法：
    .venv/Scripts/python.exe tools/split_tool_loop.py --check
    .venv/Scripts/python.exe tools/split_tool_loop.py --write
"""
from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "apiserver" / "agentic_tool_loop.py"
OUT_DIR = ROOT / "apiserver" / "agentic_loop_parts"

# 相对 import 层级修正：原文件在 `apiserver/` 下，`from .llm_service import X` 指向
# `apiserver.llm_service`；搬进 `apiserver/agentic_loop_parts/<mod>.py` 后同一行会解析成
# `apiserver.agentic_loop_parts.llm_service`（不存在）→ 运行时 ModuleNotFoundError。
# 故把 `from .X` 上移一层为 `from ..X`（这些 import 全在函数体内，是延迟 import）。
_REL_IMPORT_RE = re.compile(r"(?m)^([ \t]*)from \.(?!\.)")


def fix_rel_imports(text: str) -> str:
    return _REL_IMPORT_RE.sub(r"\1from ..", text)

MODULE_OF: dict[str, str] = {}


def _assign(mod: str, names: list[str]) -> None:
    for n in names:
        MODULE_OF[n] = mod


# types：标记常量 + 结果口径（迭代控制的基础设施）
_assign("markers", [
    "_TOOL_SECTION_BEGIN", "_TOOL_SECTION_END", "_TOOL_CALL_BEGIN",
    "_TOOL_CALL_ARG_BEGIN", "_TOOL_CALL_END",
    "_RETRYABLE_MARKERS", "_PERMANENT_MARKERS", "_MCP_PAYLOAD_ERROR_RE",
    "_loop_config", "_effective_status", "_retryable_failure", "_step_entry",
])

# parser：文本 → 工具调用（含 native 格式转换）
_assign("parser", [
    "_normalize_fullwidth_json_chars", "_extract_json_objects", "_extract_tool_blocks",
    "_convert_special_tool_call_to_dispatch", "_extract_special_tool_calls",
    "parse_tool_calls_from_text", "_convert_native_to_dispatch",
    "_build_native_assistant_message",
])

# planner：计划段 / 收敛提示 / 任务与子代理编排
_assign("planner", [
    "extract_plan_section", "build_convergence_prompt", "_build_review_prompt",
    "_maybe_create_task_from_plan", "_collect_task_ops", "_apply_task_ops",
    "_collect_subagent_specs", "_run_subagents", "_subagent_results_prompt",
])

# context：上下文注入、任务/技能上下文、步骤边界压缩
_assign("context", [
    "_current_step_type", "_inject_skill_context", "_inject_task_context",
    "_compact_at_step_boundary", "_inject_session_id",
])

# executor：拆 3 块——openclaw 通道 / 搜索与本地 / 通用分发（各自 <800 行闸门）
_assign("executor_openclaw", [
    "_shared_openclaw_client", "_get_openclaw_client",
    "_openclaw_available", "_openclaw_check_time", "_OPENCLAW_CHECK_TTL",
    "_openclaw_start_attempted", "_check_openclaw_available", "_probe_openclaw_health",
    "_GATEWAY_DIRECT_TOOLS", "_execute_openclaw_call", "_execute_openclaw_tool_call",
    "_execute_openclaw_session_tool", "_extract_openclaw_tool_result",
])
_assign("executor_search", [
    "_execute_search_tool", "_execute_brave_search", "_LOCAL_EXEC_TOOLS",
    "_execute_local_tool", "_analyze_image_local", "_is_public_http_url",
    "_fetch_web_page_local", "_synthesize_speech_local",
])
_assign("executor", [
    "_execute_mcp_call", "_execute_memory_tool", "_execute_agent_relay",
    "_execute_control_tool", "_send_live2d_actions",
])

# hooks：调用前/后门禁与生命周期钩子
_assign("hooks", [
    "_run_guard", "_emit_post_execute", "_run_scope_gate", "_run_tool_gate",
])

# loop：主循环与对外入口
_assign("loop", [
    "execute_pre_search", "_dispatch_one_call", "execute_tool_calls",
    "format_tool_results_for_llm", "format_tool_result_for_display",
    "_format_sse_event", "run_agentic_loop",
])

MODULE_TITLES = {
    "markers": "标记常量与结果口径（迭代控制基础设施）",
    "parser": "文本 → 工具调用解析（含 native 格式转换）",
    "planner": "计划段、收敛提示、任务与子代理编排",
    "context": "上下文注入与步骤边界压缩",
    "executor": "工具执行器（MCP / 记忆 / 子代理 / 控制 / Live2D 分发）",
    "executor_openclaw": "openclaw 通道执行器（客户端池 / 健康检查 / 会话工具）",
    "executor_search": "搜索与本地执行器（Brave/搜索代理 / 本地能力直调）",
    "hooks": "调用门禁与生命周期钩子",
    "loop": "主循环与对外入口",
}

# logger 块刻意**不搬**：原 `logging.getLogger(__name__)` 搬进子模块后通道名会变成
# `apiserver.agentic_loop_parts.<mod>`，静默改变日志来源（影响日志过滤配置）。
# 改为每个模块注入**原通道名**，保持日志归属不变。
LOGGER_NAME = "apiserver.agentic_tool_loop"
SKIP_BLOCKS = {"logger"}
MODULE_OF["logger"] = "markers"  # 占位（实际不写入，见 SKIP_BLOCKS）


# 模块间依赖：低级 → 高级（生成时按此注入 `from .X import *`）
DEPS: dict[str, list[str]] = {
    "markers": [],
    "parser": ["markers"],
    "planner": ["markers"],
    "context": ["markers"],
    "executor_openclaw": ["markers"],
    "executor_search": ["markers"],
    "executor": ["markers", "executor_openclaw", "executor_search"],
    "hooks": ["markers"],
    "loop": ["markers", "parser", "planner", "context",
             "executor", "executor_openclaw", "executor_search", "hooks"],
}
# 聚合顺序（router 无关；此处决定 __init__ 的 import 次序）
ORDER = ["markers", "parser", "planner", "context",
         "executor_openclaw", "executor_search", "executor", "hooks", "loop"]


def _is_docstring(node) -> bool:
    return (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str))


def parse_blocks(src: str):
    tree = ast.parse(src)
    lines = src.splitlines(keepends=True)
    body = list(tree.body)

    def _skip(n) -> bool:
        return isinstance(n, (ast.Import, ast.ImportFrom)) or _is_docstring(n)

    first_real = next((n for n in body if not _skip(n)), None)
    header_end = (first_real.lineno - 1) if first_real else len(lines)
    header = "".join(lines[:header_end])

    blocks = []
    prev_end = header_end
    for node in body:
        if _skip(node):
            continue
        name = getattr(node, "name", None)
        if name is None:
            if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
                name = node.targets[0].id
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                name = node.target.id
            else:
                name = f"<{type(node).__name__}@{node.lineno}>"
        end = node.end_lineno
        text = "".join(lines[prev_end:end])
        blocks.append((name, text, node.lineno, end))
        prev_end = end
    return header, blocks


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    src = SRC.read_text(encoding="utf-8")
    header, blocks = parse_blocks(src)
    if len(blocks) < 30:
        print(f"✗ 源文件只有 {len(blocks)} 个顶层块（预期 >30）——疑似已是薄壳。"
              f"请先 `git checkout HEAD -- {SRC.relative_to(ROOT)}`", file=sys.stderr)
        return 2

    groups: dict[str, list] = {}
    unmapped = []
    for name, text, s, e in blocks:
        if name in SKIP_BLOCKS:
            continue
        mod = MODULE_OF.get(name)
        if mod is None:
            unmapped.append((name, s, e))
            continue
        groups.setdefault(mod, []).append((name, text, s, e))

    print(f"源文件 {len(src.splitlines())} 行 | 顶层块 {len(blocks)} | "
          f"已映射 {sum(len(v) for v in groups.values())}")
    for mod in ORDER:
        items = groups.get(mod, [])
        lines = sum(t.count("\n") for _, t, _, _ in items)
        print(f"  {mod:9s} {len(items):3d} 块 / ~{lines:5d} 行")
    if unmapped:
        print("\n⚠️ 未映射（需补 MODULE_OF）：")
        for n, s, e in unmapped:
            print(f"  L{s}-{e}  {n}")
        return 1
    if args.check or not args.write:
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    py_header = header if header.lstrip().startswith("#!/") else header
    for mod in ORDER:
        items = groups.get(mod, [])
        parts = [f'"""{MODULE_TITLES[mod]}（卷190-A2：从 agentic_tool_loop.py 纯搬移）。"""\n',
                 py_header.rstrip("\n") + "\n\n",
                 f'logger = logging.getLogger("{LOGGER_NAME}")  # 保持原日志通道名\n']
        for dep in DEPS[mod]:
            # 依赖注入放在定义之前；各模块只依赖更底层模块，无环
            parts.append(f"from .{dep} import *  # noqa: F401,F403\n")
        for name, text, s, e in items:
            parts.append("\n" + fix_rel_imports(text).rstrip("\n") + "\n")
        # 关键：显式 __all__ 列出**本模块全部顶层名（含下划线）**。
        # 否则 `from .types import *` 拿不到 `_TOOL_CALL_BEGIN` 这类下划线常量
        # （`import *` 默认跳过下划线名）——实测会导致 parse 函数运行时 NameError。
        parts.append(f"\n__all__ = {sorted(n for n, _, _, _ in items)!r}\n")
        (OUT_DIR / f"{mod}.py").write_text("".join(parts), encoding="utf-8")
        print(f"  ✓ {mod}.py")

    # __init__：动态 __all__（含下划线名，薄壳兼容）
    init = ['"""agentic_loop_parts —— 原 agentic_tool_loop.py 按域拆分后的聚合入口（卷190-A2）。\n\n',
            "薄壳兼容：把各域全部公共名（**含下划线**）提到包级，"
            "使 `from apiserver.agentic_tool_loop import X` 的既有调用方继续可用。\n",
            '"""\n\n']
    for mod in ORDER:
        init.append(f"from . import {mod}  # noqa: E402\n")
    init.append("\n_SUBMODULES = ("
                + ", ".join(ORDER) + ")\n")
    init.append("for _m in _SUBMODULES:\n"
                "    for _name in dir(_m):\n"
                "        if _name.startswith('__'):\n"
                "            continue\n"
                "        globals().setdefault(_name, getattr(_m, _name))\n\n")
    init.append("__all__ = sorted(\n"
                "    n for m in _SUBMODULES for n in dir(m) if not n.startswith('__')\n"
                ")\n")
    (OUT_DIR / "__init__.py").write_text("".join(init), encoding="utf-8")
    print("  ✓ __init__.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
