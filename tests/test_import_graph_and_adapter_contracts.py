"""导入图与适配契约的结构性守卫（工单244g）。

为什么要有
----------
244f 做了一次全仓人工审计，查出两类结构问题：

1. **真环**（SCC 里所有边都是模块级 eager import）—— 主干目录里**当前为 0**，
   但有 6 个「靠**惰性导入**（函数体内 import）存活」的环：谁把那个 import 提到模块级，
   就会立刻变成真环。这是**脆弱点**，需要一道守卫盯着别真的变 eager。
2. **适配契约不完整** —— `agent-manifest.json` 的 `entryPoint` 指向不存在的模块/类，
   或 `mcpserver/adapters` 注册表里的模块缺 `CAPABILITY`/`healthcheck`/`register` 三要素。

⚠️ **本文件是纯静态的**（`ast` + `json`，**不 import 任何被测模块**）：
① 不拉起重依赖（CI 上没有 docling/fastapi 的机器也能跑）；
② 不会因为导入副作用改变进程状态。
这与 `test_agent_server_parts_imports.py` 同源（把 lint 纪律变成不依赖 lint 的测试）。

扫描范围**刻意收窄**到主干四目录 + `tools/`，排除 `NEKO`/`vendor`/`skills`/`docs`/`github_haul`
（前三个是外部同步代码，后两个不是可导入的包）。
"""
from __future__ import annotations

import ast
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

#: 扫描范围（相对仓库根）
SCAN_ROOTS = ("mcpserver", "apiserver", "agentserver", "system", "tools")
#: 不参与包解析的目录名（外部同步代码 / 非包）
EXCLUDE_PARTS = {"NEKO", "vendor", "skills", "docs", "github_haul", "__pycache__",
                 "node_modules", ".venv", "build", "dist", "mod"}


def _iter_py() -> list[Path]:
    out: list[Path] = []
    for name in SCAN_ROOTS:
        root = REPO_ROOT / name
        if not root.is_dir():
            continue
        for p in root.rglob("*.py"):
            if EXCLUDE_PARTS & set(p.relative_to(REPO_ROOT).parts):
                continue
            out.append(p)
    assert out, f"扫描范围为空：{SCAN_ROOTS}"
    return out


def _module_name(path: Path) -> str:
    rel = path.relative_to(REPO_ROOT).as_posix()[:-3].split("/")
    if rel[-1] == "__init__":
        rel = rel[:-1]
    return ".".join(rel)


def _lazy_spans(tree: ast.Module) -> list[tuple[int, int]]:
    """函数/类体（行号区间）——落在这里面的 import 是**惰性**的。"""
    return [(n.lineno, n.end_lineno or n.lineno) for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]


def _edges(path: Path, mod: str, index: dict[str, Path]) -> list[tuple[str, str]]:
    """返回 [(目标模块, 'eager'|'lazy')]，只认**显式** import。

    ⚠️ 刻意**不展开隐式父包边**：`import pkg.sub` 必然先执行 `pkg/__init__`，
    但那条语言层面的边会把「eager 重导出子模块的 `__init__`」整棵子树吸成一个假 SCC
    （实测造出过 143 节点的假环）。循环检测只认显式 import。
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return []
    spans = _lazy_spans(tree)
    pkg = mod if path.name == "__init__.py" else (mod.rsplit(".", 1)[0] if "." in mod else "")
    out: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        targets: list[str] = []
        if isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                up = pkg.split(".") if pkg else []
                for _ in range(node.level - 1):
                    up = up[:-1]
                base = ".".join([*up, base]) if base else ".".join(up)
            # ⚠️ 每个名字**要么**落到具体子模块、**要么**落到 base，**不两者都加**。
            #    若 `from . import X` 既加 X 又加 base(=本包 __init__)，就等于把
            #    「隐式父包边」又引回来了 —— 那会把 pkg/__init__ ↔ pkg.sub 报成假真环
            #    （实测：多加这一条立刻凭空冒出 3 个「全 eager 真环」）。
            for a in node.names:
                cand = f"{base}.{a.name}" if base else a.name
                targets.append(cand if cand in index else base)
        elif isinstance(node, ast.Import):
            targets = [a.name for a in node.names]
        if not targets:
            continue          # ⚠️ ast.walk 会吐出 Module 等无 lineno 的节点，先短路
        kind = "lazy" if any(a < node.lineno <= b for a, b in spans) else "eager"
        for t in targets:
            if t and t in index:
                out.append((t, kind))
    return out


def _build_graph() -> tuple[dict[str, set[str]], dict[tuple[str, str], str]]:
    files = _iter_py()
    index = {_module_name(p): p for p in files}
    graph: dict[str, set[str]] = defaultdict(set)
    kind: dict[tuple[str, str], str] = {}
    for mod, path in index.items():
        for dst, k in _edges(path, mod, index):
            if dst == mod:
                continue
            graph[mod].add(dst)
            kind[(mod, dst)] = "eager" if kind.get((mod, dst)) == "eager" or k == "eager" else "lazy"
    return graph, kind


def _sccs(graph: dict[str, set[str]], nodes: list[str]) -> list[list[str]]:
    idx: dict[str, int] = {}
    low: dict[str, int] = {}
    on: dict[str, bool] = {}
    stack: list[str] = []
    out: list[list[str]] = []
    counter = 0
    sys.setrecursionlimit(100000)

    def strong(v: str) -> None:
        nonlocal counter
        idx[v] = low[v] = counter
        counter += 1
        stack.append(v)
        on[v] = True
        for w in graph.get(v, ()):
            if w not in idx:
                strong(w)
                low[v] = min(low[v], low[w])
            elif on.get(w):
                low[v] = min(low[v], idx[w])
        if low[v] == idx[v]:
            comp = []
            while True:
                w = stack.pop()
                on[w] = False
                comp.append(w)
                if w == v:
                    break
            out.append(comp)

    for n in nodes:
        if n not in idx:
            strong(n)
    return out


def test_no_all_eager_import_cycle_in_mainline():
    """主干里**不得**出现「全 eager」的导入环（SCC 的每条边都是模块级 import）。

    这种环 = 一导入就必然踩到**半初始化模块**，是真正的结构性故障。

    ⚠️ 允许「含惰性边」的环存在 —— 那是本仓刻意的解环手法（在函数体内 import）。
    当前主干有 6 个这样的环（`apiserver.agentic_loop_parts`、`mcpserver.mcp_manager`、
    `agentserver.openclaw.*` 等），**它们是脆弱点**：把那个惰性 import 提到模块级就会变真环。
    本用例正是那道闸门 —— 一旦有人这么改，这里先红。

    若本用例变红：**不要**往 `SCAN_ROOTS` 里加目录或放宽判据，
    而是把新出现的那条边改回函数体内 import（或在报告里说明为什么确实需要 eager 环）。
    """
    graph, kind = _build_graph()
    nodes = sorted(graph) or []
    offenders = []
    for comp in _sccs(graph, nodes):
        if len(comp) < 2:
            continue
        s = set(comp)
        kinds = {kind.get((a, b)) for a in comp for b in s & graph.get(a, set())}
        if kinds == {"eager"}:
            offenders.append(sorted(comp))
    assert not offenders, (
        "主干出现「全 eager」真环（导入即踩半初始化模块）：\n"
        + "\n".join("  " + " ↔ ".join(c) for c in offenders))


def test_lazy_surviving_cycles_do_not_grow_unnoticed():
    """「靠惰性边存活」的环数量**不得增加**（新增即意味着结构变脆）。

    基线 = 2026-10-15 人工审计结果（244f）。**只允许减少**。
    若确实需要新增，请同时更新基线并在报告里写明为什么。
    """
    BASELINE_LAZY_CYCLES = 6
    graph, kind = _build_graph()
    count = 0
    for comp in _sccs(graph, sorted(graph)):
        if len(comp) < 2:
            continue
        s = set(comp)
        if any(kind.get((a, b)) == "lazy" for a in comp for b in s & graph.get(a, set())):
            count += 1
    assert count <= BASELINE_LAZY_CYCLES, (
        f"「靠惰性边存活」的环从基线 {BASELINE_LAZY_CYCLES} 增加到 {count} —— "
        "新增的结构性环请单独评估（要么解掉，要么把基线调高并写清理由）")


def _manifests() -> list[Path]:
    """**全树**扫 `agent-manifest.json`。

    历史口径（244g）：只扫 `mcpserver/**` —— 因为当时 `mod/` 里有一个**指向不存在模块**的
    死 manifest（`mod/mcpserver/agent_llm_decompile/`），全树扫会红。
    244h 把那个化石删掉之后**放宽到全树**：任何目录下的 manifest 都必须可解析，
    这样以后再有「快照目录里躺着死 manifest」会在 CI 里**当场**暴露，而不是等人工审计。

    ⚠️ 已实测全树共 72 个 manifest（`mcpserver/**` 58 + `mod/mcpserver/**` 14）全部可解析。
    """
    return sorted(REPO_ROOT.rglob("agent-manifest.json"))


def test_every_manifest_entrypoint_resolves_statically():
    """每个 manifest 的 `entryPoint.{module,class}` 必须能**静态**落到真实文件与类定义。

    243 的等价性锚是「import 后 getattr」；这里是它的**离线版**：
    把 `module` 映射成路径、`ast` 里找 `class <class>`。

    ⚠️ 为什么不用真 import：CI 上未必装了 docling/fastapi 等重依赖，
    真 import 会让守卫在某些机器上假红。静态判据足以发现「指向不存在的模块/类」。
    """
    fails: list[str] = []
    for mf in _manifests():
        rel = mf.relative_to(REPO_ROOT).as_posix()
        try:
            d = json.loads(mf.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            fails.append(f"{rel}: JSON 解析失败 {exc}")
            continue
        ep = d.get("entryPoint") or {}
        mod, cls = ep.get("module"), ep.get("class")
        if not (mod and cls):
            fails.append(f"{rel}: entryPoint 缺 module/class（{ep}）")
            continue
        target = REPO_ROOT.joinpath(*mod.split("."))
        cand = [target.with_suffix(".py"), target / "__init__.py"]
        hit = next((c for c in cand if c.is_file()), None)
        if hit is None:
            fails.append(f"{rel}: entryPoint.module={mod!r} 找不到对应文件")
            continue
        tree = ast.parse(hit.read_text(encoding="utf-8", errors="replace"))
        names = {n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}
        if cls not in names:
            fails.append(f"{rel}: {hit.relative_to(REPO_ROOT)} 里没有 class {cls}")
    assert not fails, "manifest 契约不完整：\n" + "\n".join("  " + f for f in fails)


def test_every_registered_adapter_declares_the_three_part_contract():
    """`mcpserver/adapters` 注册表里每个模块都要有 `CAPABILITY` / `healthcheck` / `register`。

    这是 `validate_adapter(mod, name)` 的**静态版**（那个函数要 import 模块，
    CI 上未必装得齐依赖）。三要素缺失 ⇒ 该适配器永远不会被注册，但**没有任何报错**
    （`register_all_adapters` 只是 `logger.warning` 后 `continue`）——
    正是「适配不完善但静默」的典型，故用守卫盯着。
    """
    src = (REPO_ROOT / "mcpserver" / "adapters" / "__init__.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    registry: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "_ADAPTERS" for t in node.targets):
            for k, v in zip(node.value.keys, node.value.values):
                if isinstance(k, ast.Constant) and isinstance(v, ast.Tuple):
                    registry[str(k.value)] = str(v.elts[0].value)
    assert registry, "没能从 mcpserver/adapters/__init__.py 解析出 _ADAPTERS"

    fails: list[str] = []
    for name, modpath in sorted(registry.items()):
        target = REPO_ROOT.joinpath(*modpath.split("."))
        hit = next((c for c in (target.with_suffix(".py"), target / "__init__.py") if c.is_file()), None)
        if hit is None:
            fails.append(f"{name}: 模块 {modpath} 不存在")
            continue
        mod_tree = ast.parse(hit.read_text(encoding="utf-8", errors="replace"))
        defined = set()
        for n in mod_tree.body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                defined.add(n.name)
            elif isinstance(n, ast.Assign):
                defined.update(t.id for t in n.targets if isinstance(t, ast.Name))
            elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
                defined.add(n.target.id)
        # 也接受「从别处 import 进来」的形式（flat_bridges 那种聚合模块）
        imported = {a.asname or a.name for n in ast.walk(mod_tree)
                    if isinstance(n, ast.ImportFrom) for a in n.names}
        baked = {"mcpserver"} | {".", ".."}
        missing = [k for k in ("CAPABILITY", "healthcheck", "register")
                   if k not in defined and k not in imported and modpath.split(".")[0] not in baked]
        if missing:
            fails.append(f"{name}（{modpath}）缺：{missing}")
    assert not fails, "适配器三要素契约不完整：\n" + "\n".join("  " + f for f in fails)
