"""split_agent_server.py — 把 agentserver/agent_server.py 拆到 agent_server_parts/（工单204 任务一）。

纯搬移：块内容**逐字节搬运**，不改逻辑/签名/文案/装饰器。

方法论沿用卷190（split_extensions.py）：
  - 块边界用 AST 精确计算（lineno/end_lineno）——**不能用"行首无缩进"判断**（多行字符串会误判）；
  - 模块归属用「名字规则」而不是手写 70 项映射表；
  - 跨模块引用**自动补 import**（AST 收集 Name 引用 → 与全局名字表比对）。

本文件的特殊约束：
  端点是 `@app.get(...)` 装饰器（**非 APIRouter**）→ 采「共享 app 模块」：
  `lifecycle.py` 定义 `app = FastAPI(..., lifespan=lifespan)`（app 定义在原 L379，晚于 lifespan，
  两者**必须同模块**否则循环 import）；其余模块 `from .lifecycle import app` 后就地注册。

用法：
    .venv/Scripts/python.exe tools/split_agent_server.py --check   # 只报告 块→模块 映射与依赖图
    .venv/Scripts/python.exe tools/split_agent_server.py --write   # 生成 parts/ + 薄入口
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "agentserver" / "agent_server.py"
OUT_DIR = ROOT / "agentserver" / "agent_server_parts"

#: 子模块清单（顺序 = 生成的 import 顺序；common → session → lifecycle → 其余，**单向无环**）
MODULES = ("common", "session", "lifecycle", "health", "agents", "openclaw",
           "travel", "vision", "heartbeat", "dogtag", "search")

#: 语句块（非 def/class）的显式归属；未列出的语句块默认进 common
STMT_MODULE = {
    "app": "lifecycle",              # app = FastAPI(...)
    "_search_http_client": "search",
}

#: 旅行会话家族（session 模块）：**无路由装饰器**（不依赖 app），
#: 被 lifespan（启动恢复/关停中断）与 travel 路由共用。
#: 独立成模块是为了打断 lifecycle↔travel 循环，依赖：common ← session ← lifecycle ← travel。
SESSION_HELPERS = frozenset({
    "_track_travel_task", "_spawn_travel_session", "_resume_open_travel_sessions",
    "_mark_travel_sessions_interrupted", "_interrupt_travel_sessions",
    "_run_travel_session",
})

#: 通用小工具（多模块共用 → common，避免 health→agents 这类跨域依赖）
#: `Modules` 是全局状态容器，被几乎所有模块引用 —— 归 common 才能保持依赖单向。
COMMON_HELPERS = frozenset({"_now_iso", "Modules"})


def module_of(name: str) -> str:
    """函数/类名 → 目标模块（规则式，避免手写 70 项映射）。"""
    if name in SESSION_HELPERS:
        return "session"
    if name in COMMON_HELPERS:
        return "common"
    if name in ("lifespan", "_start_gateway_if_port_free", "_on_config_changed",
                "_is_port_in_use", "_delayed_health_check"):
        return "lifecycle"
    if "health" in name:
        return "health"
    if name.startswith("openclaw"):
        return "openclaw"
    if "travel" in name:
        return "travel"
    if "proactive_vision" in name or name in ("update_user_activity",):
        return "vision"
    if "heartbeat" in name or "checklist" in name:
        return "heartbeat"
    if "dogtag" in name or "dut" in name:          # duty / duties
        return "dogtag"
    if name in ("_get_search_client", "_local_search_proxy"):
        return "search"
    return "agents"                                 # 默认：实例/会话管理


def _start_line(node: ast.AST) -> int:
    """块起始行：**必须含装饰器行**——ast.FunctionDef.lineno 指向 def 行，
    直接用会丢掉 @app.get(...)，导致拆分后路由静默消失（本工具首版即踩此坑）。"""
    decs = getattr(node, "decorator_list", None) or []
    return min([node.lineno] + [d.lineno for d in decs])


def _blocks(tree: ast.Module, src_lines: list[str]):
    """全部顶层块：(kind, name, start, end, node)。start 含装饰器。"""
    out = []
    for node in tree.body:
        start = _start_line(node)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append(("func", node.name, start, node.end_lineno, node))
        elif isinstance(node, ast.ClassDef):
            out.append(("class", node.name, start, node.end_lineno, node))
        else:
            out.append(("stmt", type(node).__name__, start, node.end_lineno, node))
    return sorted(out, key=lambda b: b[2])


def _assign_names(node: ast.AST) -> list[str]:
    """语句块里被赋值的顶层名字（用于 STMT_MODULE 归属与全局名字表）。"""
    names = []
    if isinstance(node, ast.Assign):
        for t in node.targets:
            if isinstance(t, ast.Name):
                names.append(t.id)
    elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
        names.append(node.target.id)
    return names


def plan(src: str):
    """返回 (blocks, owner, global_names, preamble_end)。"""
    tree = ast.parse(src)
    lines = src.splitlines()
    blocks = _blocks(tree, lines)
    owner: dict[tuple[int, int], str] = {}
    global_names: dict[str, str] = {}
    preamble_end = 0

    for kind, name, a, b, _node in blocks:
        if kind in ("func", "class"):
            mod = module_of(name)
            global_names[name] = mod
        else:
            node = _node
            assigned = _assign_names(node)
            seg = "\n".join(lines[a - 1:b])
            mod = None
            for nm in assigned:
                if nm in STMT_MODULE:
                    mod = STMT_MODULE[nm]
            if mod is None and ("apply_local_cors(app)" in seg or "app = FastAPI(" in seg):
                mod = "lifecycle"           # app 的配套配置语句随 app 同模块
            if mod is None:
                # 前言（imports/logger/路径/`__main__`）→ common；`__main__` 特殊（进薄壳）
                is_main = isinstance(node, ast.If) and a > 3000
                mod = "__main__" if is_main else "common"
            for nm in assigned:
                global_names[nm] = mod
        owner[(a, b)] = mod
        if mod != "__main__":
            preamble_end = max(preamble_end, b)
    return blocks, owner, global_names, tree, lines


def cross_imports(tree: ast.Module, blocks, owner, global_names) -> dict[str, set[tuple[str, str]]]:
    """每个模块需要从兄弟模块 import 的 (模块, 名字) 集合。"""
    need: dict[str, set[tuple[str, str]]] = {m: set() for m in MODULES}
    for kind, name, a, b, _node in blocks:
        mod = owner.get((a, b))
        if mod not in need:
            continue
        # 逐块单独解析（避免跨块串扰）
        seg = "\n".join(SOURCE_LINES[a - 1:b])
        try:
            sub = ast.parse(seg)
        except SyntaxError:
            continue
        for n in ast.walk(sub):
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
                target = global_names.get(n.id)
                if target and target != mod and target != "__main__":
                    need[mod].add((target, n.id))
    return need


SOURCE_LINES: list[str] = []


def gen_module(mod: str, blocks, owner, src_lines, need) -> str:
    header = [f'"""agent_server_parts.{mod} —— 自 agentserver/agent_server.py 拆出（工单204 任务一，纯移动）。"""',
              "from __future__ import annotations", ""]
    if mod != "common":
        header.append("from .common import *  # noqa: F401,F403")
    # 跨模块引用一律按 need 精确生成（只在实际引用时 import，
    # 避免 session 等无路由模块反向依赖 lifecycle -> 循环）
    by_mod: dict[str, list[str]] = {}
    for target, nm in sorted(need.get(mod, ())):
        by_mod.setdefault(target, []).append(nm)
    for target, names in sorted(by_mod.items()):
        header.append(f"from .{target} import {', '.join(sorted(names))}  # noqa: F401")
    header.append("")
    header.append("")

    body: list[str] = []
    for kind, name, a, b, _node in blocks:
        if owner.get((a, b)) != mod:
            continue
        body.extend(src_lines[a - 1:b])
        body.append("")
        body.append("")
    return "\n".join(header) + "\n".join(body).rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    global SOURCE_LINES
    raw = SRC.read_bytes()
    src = raw.decode("utf-8")
    SOURCE_LINES = src.splitlines()

    blocks, owner, global_names, tree, lines = plan(src)
    print(f"顶层块: {len(blocks)}")
    from collections import Counter
    cnt = Counter(owner.values())
    for m in list(MODULES) + ["__main__"]:
        print(f"  {m:<10} {cnt.get(m, 0)} 块")

    need = cross_imports(tree, blocks, owner, global_names)
    print("\n跨模块引用：")
    for m in MODULES:
        items = sorted(need.get(m, ()))
        print(f"  {m:<10} -> {items if items else '(无)'}")

    if args.check and not args.write:
        return 0

    if not args.write:
        print("\n（未指定 --write，仅报告。加 --write 生成）")
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for mod in MODULES:
        text = gen_module(mod, blocks, owner, lines, need)
        (OUT_DIR / f"{mod}.py").write_bytes(text.encode("utf-8"))   # 显式 LF（bytes 写入）
        print(f"  写入 {OUT_DIR.name}/{mod}.py  ({text.count(chr(10))} 行)")

    main_body = "\n\n".join(
        "\n".join(lines[a - 1:b]) for kind, name, a, b, _n in blocks
        if owner.get((a, b)) == "__main__"
    )
    shell = [
        '"""agentserver/agent_server.py —— 薄入口（工单204 任务一拆分后）。',
        "",
        "原 3096 行实现已按职责拆到 `agent_server_parts/`；本文件保留对外契约",
        "（`app` / `Modules`）并导入子模块（导入即注册路由）。",
        '"""',
        "from __future__ import annotations",
        "",
        "from .agent_server_parts.common import Modules  # noqa: F401",
        "from .agent_server_parts.lifecycle import app  # noqa: F401",
        "from .agent_server_parts import (  # noqa: F401  导入即注册路由",
        "    agents,",
        "    dogtag,",
        "    health,",
        "    heartbeat,",
        "    openclaw,",
        "    search,",
        "    travel,",
        "    vision,",
        ")",
        "",
        '__all__ = ["app", "Modules"]',
        "",
        "",
        main_body.strip(),
        "",
    ]
    (OUT_DIR / "__init__.py").write_bytes(
        '"""agent_server_parts —— agent_server 拆分产物（工单204 任务一）。"""\n'.encode("utf-8"))
    SRC.write_bytes("\n".join(shell).encode("utf-8"))
    print(f"  薄入口已重写: {SRC.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
