"""code-review-graph 薄引擎 —— 审查专用代码知识图谱（stdlib ast，零新依赖，全确定性）。

授粉自 tirth8205/code-review-graph（MIT，见 UPSTREAM-LICENSE）：
上游用 tree-sitter 多语言解析 + networkx 建图 + fastmcp 暴露约 30 个 MCP 工具；
本引擎按"不引重依赖"铁律裁剪：目标场景（apiserver/、summer_memory/）全为 Python，
stdlib `ast` 即可全覆盖 —— 零新依赖、纯确定性。多语言（.ts/.go 等）将来可引入
tree-sitter 作可选增强（工单允许的唯一新依赖），本文件的 parser 分发位已预留。

语义对齐上游 4 个核心工具（设计参照级自研，非逐行翻译）：
- build（对应 build_or_update_graph）：目录 → 节点(module/class/function/method)
  + 边(contains/imports/calls)，JSON 落盘（字节级确定性：排序固定、无时间戳）
- detect_changes（对应 detect_changes）：git diff → 变更函数 → 风险分 + 测试缺口
  + 受影响执行流（风险分公式见 _risk_score，启发式，仅作审查优先级参考）
- impact_radius（对应 get_impact_radius）：变更文件 → 反向边 BFS → 受影响函数/文件
- query_graph（对应 query_graph）：按名查定义 + 调用者/被调者
- architecture_overview（对应 get_architecture_overview）：枢纽节点/大函数/目录分布

token 口径：estimate_tokens = ceil(chars/4)，与上游 context_savings.CHARS_PER_TOKEN
同口径（估算值，非 tokenizer 精确计数，README 数据均如实标注）。

fail-fast 原则（与 graphify 一致）：目录不存在 / 索引未建 / 节点缺失一律
CodeReviewError，绝不静默空返回。
"""
from __future__ import annotations

import ast
import json
import re
import subprocess
from pathlib import Path
from typing import Any, Iterable

# 上游 context_savings.CHARS_PER_TOKEN 同口径（估算，非精确 tokenizer）
CHARS_PER_TOKEN = 4
SCHEMA_VERSION = 1


class CodeReviewError(Exception):
    """code-review-graph 薄引擎错误（fail-fast，绝不静默空返回）。"""


def estimate_tokens(text: str) -> int:
    """chars/4 估算 token 数（与上游 CHARS_PER_TOKEN 同口径，向上取整）。"""
    return max(1, (len(text) + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN)


def _first_doc_line(node: ast.AST) -> str:
    """取 docstring 首行（无则空串），用于节点摘要。"""
    doc = ast.get_docstring(node)
    return doc.strip().splitlines()[0].strip() if doc else ""


def _node_line_end(node: ast.AST, fallback: int) -> int:
    """语句块结束行（含装饰器），保证与 diff 行区间求交不漏。"""
    end = getattr(node, "end_lineno", None) or fallback
    for dec in getattr(node, "decorator_list", []) or []:
        end = max(end, dec.end_lineno or fallback)
    return end


def _arg_names(args: ast.arguments) -> list[str]:
    """参数名列表（posonly/args/kwonly），供签名展示。"""
    names = [a.arg for a in getattr(args, "posonlyargs", []) or []]
    names += [a.arg for a in args.args]
    names += [a.arg for a in args.kwonlyargs]
    return names


class GraphIndex:
    """审查专用代码图谱索引（nodes + edges，JSON 可持久化、字节级确定性）。"""

    def __init__(self) -> None:
        self.root: str = ""
        self.nodes: list[dict[str, Any]] = []
        self.edges: list[dict[str, Any]] = []
        # 派生查找表（build/load 后由 _rebuild_lookup 重建）
        self._by_id: dict[str, dict[str, Any]] = {}
        self._by_name: dict[str, list[str]] = {}
        self._by_module: dict[str, list[str]] = {}
        self._class_ids: set[str] = set()
        self._module_of_file: dict[str, str] = {}
        self._file_of_module: dict[str, str] = {}
        # 边索引（调用/被调/导入关系，重建时生成）
        self._callers: dict[str, set[str]] = {}
        self._callees: dict[str, set[str]] = {}
        self._importers: dict[str, set[str]] = {}

    # ============================================================ 建图

    @classmethod
    def build(cls, root: str | Path, include: tuple[str, ...] = (".py",)) -> "GraphIndex":
        """扫描目录建图。v1 仅 .py（stdlib ast），多语言 tree-sitter 扩展位留此。"""
        root_path = Path(root).resolve()
        if not root_path.is_dir():
            raise CodeReviewError(f"待建图目录不存在或不是目录: {root_path}")
        idx = cls()
        idx.root = str(root_path)
        py_files = sorted(
            p for p in root_path.rglob("*")
            if p.is_file() and p.suffix in include
            and not any(part.startswith(".") for part in p.relative_to(root_path).parts)
        )
        if not py_files:
            raise CodeReviewError(f"目录下没有可解析的 {'/'.join(include)} 文件: {root_path}")

        # 先登记 文件↔模块 映射
        for path in py_files:
            rel = path.relative_to(root_path).as_posix()
            module = cls._module_name(path, root_path)
            idx._module_of_file[rel] = module
            idx._file_of_module[module] = rel

        # 第一遍：收集全部定义（跨文件调用解析需要全局名字表）
        for path in py_files:
            idx._collect_definitions(path, root_path)
        # 定义集齐后先建名字表，第二遍解析调用边才能跨文件消歧
        idx._rebuild_lookup()

        # 第二遍：解析 import 边与调用边（有全局表后可跨文件解析）
        for path in py_files:
            idx._collect_references(path, root_path)

        idx.nodes.sort(key=lambda n: (n["file"], n["line_start"], n["qualname"]))
        idx.edges.sort(key=lambda e: (e["src"], e["dst"], e["kind"]))
        idx._rebuild_lookup()
        return idx

    @staticmethod
    def _module_name(path: Path, root: Path) -> str:
        """文件路径 → 点分模块名（__init__.py 归属包名本身）。"""
        rel = path.relative_to(root)
        parts = list(rel.with_suffix("").parts)
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        return ".".join(parts) if parts else rel.stem

    # ---- 第一遍：定义 + contains 边 ----
    def _collect_definitions(self, path: Path, root: Path) -> None:
        rel = path.relative_to(root).as_posix()
        module = self._module_of_file[rel]
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as e:
            # 单文件语法坏不炸全图：module 节点带 parse_error 标记（诚实可见）
            self.nodes.append({
                "id": f"{rel}::", "kind": "module", "name": module, "qualname": "",
                "module": module, "file": rel, "line_start": 1, "line_end": 1,
                "doc": "", "args": [], "parse_error": str(e),
            })
            return
        mod_id = f"{rel}::"
        self.nodes.append({
            "id": mod_id, "kind": "module", "name": module, "qualname": "",
            "module": module, "file": rel, "line_start": 1,
            "line_end": getattr(tree, "end_lineno", 1) or 1,
            "doc": _first_doc_line(tree), "args": [],
        })
        # 递归作用域遍历：scope = [(qualname, node_id, kind)]，不含 module 自身
        self._walk_defs(tree.body, [], module, rel, mod_id)

    def _walk_defs(self, body: list[ast.stmt], scope: list[tuple[str, str, str]],
                   module: str, rel: str, mod_id: str) -> None:
        for stmt in body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qual = ".".join([q for q, _, _ in scope] + [stmt.name])
                nid = f"{rel}::{qual}"
                parent_kind = scope[-1][2] if scope else "module"
                kind = "method" if parent_kind == "class" else "function"
                self.nodes.append({
                    "id": nid, "kind": kind, "name": stmt.name, "qualname": qual,
                    "module": module, "file": rel, "line_start": stmt.lineno,
                    "line_end": _node_line_end(stmt, stmt.lineno),
                    "doc": _first_doc_line(stmt), "args": _arg_names(stmt.args),
                })
                parent_id = scope[-1][1] if scope else mod_id
                self.edges.append({"src": parent_id, "dst": nid, "kind": "contains"})
                self._walk_defs(stmt.body, scope + [(qual, nid, "function")],
                                module, rel, mod_id)
            elif isinstance(stmt, ast.ClassDef):
                qual = ".".join([q for q, _, _ in scope] + [stmt.name])
                nid = f"{rel}::{qual}"
                self.nodes.append({
                    "id": nid, "kind": "class", "name": stmt.name, "qualname": qual,
                    "module": module, "file": rel, "line_start": stmt.lineno,
                    "line_end": _node_line_end(stmt, stmt.lineno),
                    "doc": _first_doc_line(stmt), "args": [],
                })
                parent_id = scope[-1][1] if scope else mod_id
                self.edges.append({"src": parent_id, "dst": nid, "kind": "contains"})
                self._walk_defs(stmt.body, scope + [(qual, nid, "class")],
                                module, rel, mod_id)
            else:
                # 复合语句（If/For/While/With/Try 等）内部也可能有嵌套 def/class
                self._walk_defs(list(ast.iter_child_nodes(stmt)), scope, module, rel, mod_id)

    # ---- 第二遍：import 边 + 调用边 ----
    def _collect_references(self, path: Path, root: Path) -> None:
        rel = path.relative_to(root).as_posix()
        module = self._module_of_file[rel]
        mod_id = f"{rel}::"
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError:
            return
        import_map = self._build_import_map(tree)
        # import 边：module → module（相对/绝对都归一成点分模块名后查 _file_of_module）
        for dotted in self._imported_modules(tree, module, rel):
            if dotted in self._file_of_module:
                tgt_rel = self._file_of_module[dotted]
                self.edges.append({"src": mod_id, "dst": f"{tgt_rel}::", "kind": "imports"})
        # 调用边：逐函数/方法收集，作用域 scope 用于 self.method / 嵌套归属
        self._walk_calls(tree.body, [], module, rel, import_map)

    @staticmethod
    def _build_import_map(tree: ast.AST) -> dict[str, str]:
        """文件内 `import X as Y` / `from M import f` → 别名/名字 映射到点分模块。

        返回 {alias_or_name: dotted_module}，供调用解析 `alias.func` / 导入函数消歧。
        """
        mapping: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    alias = a.asname or a.name.split(".")[-1]
                    mapping[alias] = a.name
            elif isinstance(node, ast.ImportFrom):
                base = "." * (node.level or 0) + (node.module or "")
                for a in node.names:
                    mapping[a.asname or a.name] = (base + "." + a.name).lstrip(".")
        return mapping

    def _imported_modules(self, tree: ast.AST, module: str, rel: str) -> set[str]:
        """收集本文件 import 的（本仓内可解析的）模块点分名。"""
        result: set[str] = set()
        pkg = module.rsplit(".", 1)[0] if "." in module else ""
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    result.add(a.name)
            elif isinstance(node, ast.ImportFrom):
                if node.level and node.level > 1:
                    # 相对导入：从当前包回退 node.level-1 层
                    parts = pkg.split(".")
                    up = node.level - 1
                    base = ".".join(parts[:-up]) if up < len(parts) else ""
                    full = (base + "." + (node.module or "")).lstrip(".")
                else:
                    full = (node.module or "")
                result.add(full)
        return {m for m in result if m in self._file_of_module}

    def _walk_calls(self, body: list[ast.stmt], scope: list[tuple[str, str, str]],
                    module: str, rel: str, import_map: dict[str, str]) -> None:
        """遍历调用点：为每个 def 收集其自身 body 内的调用（嵌套 def 归自己）。"""
        for stmt in body:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qual = ".".join([q for q, _, _ in scope] + [stmt.name])
                nid = f"{rel}::{qual}"
                self._collect_calls_in(stmt, scope + [(qual, nid, "function")], rel, import_map)
                self._walk_calls(stmt.body, scope + [(qual, nid, "function")],
                                 module, rel, import_map)
            elif isinstance(stmt, ast.ClassDef):
                qual = ".".join([q for q, _, _ in scope] + [stmt.name])
                nid = f"{rel}::{qual}"
                self._walk_calls(stmt.body, scope + [(qual, nid, "class")],
                                 module, rel, import_map)
            else:
                self._walk_calls(list(ast.iter_child_nodes(stmt)), scope, module, rel, import_map)

    def _collect_calls_in(self, defnode: ast.AST, scope: list[tuple[str, str, str]],
                          rel: str, import_map: dict[str, str]) -> None:
        """递归收集 defnode 自身 body 的 Call，跳过嵌套 def/class（它们归各自作用域）。"""
        caller_id = scope[-1][1]
        for child in ast.iter_child_nodes(defnode):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
                continue
            if isinstance(child, ast.Call):
                self._emit_call(child, scope, rel, import_map, caller_id)
            self._collect_calls_in(child, scope, rel, import_map)

    def _emit_call(self, call: ast.Call, scope: list[tuple[str, str, str]],
                   rel: str, import_map: dict[str, str], caller_id: str) -> None:
        """解析单个 Call → 候选被调节点，发 calls 边。"""
        for target in self._resolve_call_targets(call, scope, rel, import_map):
            if target != caller_id:
                self.edges.append({"src": caller_id, "dst": target, "kind": "calls"})

    def _resolve_call_targets(self, call: ast.Call, scope: list[tuple[str, str, str]],
                              rel: str, import_map: dict[str, str]) -> list[str]:
        """解析调用目标节点 id 列表（确定性；跨文件重名歧义时优先同文件）。"""
        func = call.func
        # f(...)
        if isinstance(func, ast.Name):
            return self._by_name_candidates(func.id, rel)
        # base.attr(...)
        if isinstance(func, ast.Attribute):
            attr = func.attr
            base = func.value
            # self.method / cls.method → 就近类的方法
            if isinstance(base, ast.Name) and base.id in ("self", "cls"):
                cls_qual = next((q for q, _, k in reversed(scope) if k == "class"), "")
                if cls_qual:
                    full = f"{cls_qual}.{attr}"
                    return [full_id for full_id in self._by_id if full_id.endswith(f"::{full}")]
            # alias.func → 导入模块的成员
            if isinstance(base, ast.Name) and base.id in import_map:
                return self._by_module_attr(import_map[base.id], attr)
            # ClassName.method → 项目内类的成员
            if isinstance(base, ast.Name):
                return self._class_method_candidates(base.id, attr, rel)
            # obj.attr.attr(...) → 尝试最外层 attr 当作成员名
            if isinstance(base, ast.Attribute):
                return self._by_name_candidates(attr, rel)
        return []

    def _by_name_candidates(self, name: str, rel: str) -> list[str]:
        ids = self._by_name.get(name, [])
        if len(ids) == 1:
            return [ids[0]]
        # 多定义同名：优先同文件；仍多则放弃（避免噪声，确定性：取同文件全部）
        same_file = [i for i in ids if i.split("::", 1)[0] == rel]
        return same_file if same_file else []

    def _by_module_attr(self, module: str, attr: str) -> list[str]:
        ids = [i for i in self._by_module.get(module, []) if self._by_id[i]["name"] == attr]
        return ids

    def _class_method_candidates(self, cls_name: str, attr: str, rel: str) -> list[str]:
        cls_ids = [i for i in self._by_name.get(cls_name, []) if self._by_id[i]["kind"] == "class"]
        out: list[str] = []
        for cid in cls_ids:
            qual = self._by_id[cid]["qualname"]
            full = f"{qual}.{attr}"
            out += [i for i in self._by_id if i.endswith(f"::{full}")]
        return out

    # ============================================================ 持久化

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA_VERSION,
            "root": self.root,
            "files": len(self._module_of_file),
            "nodes": self.nodes,
            "edges": self.edges,
        }

    def save(self, path: str | Path) -> str:
        """写 JSON（字节级确定性：无时间戳、列表已排序）。返回落盘绝对路径。"""
        out = Path(path).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True),
                       encoding="utf-8")
        return str(out)

    @classmethod
    def load(cls, path: str | Path) -> "GraphIndex":
        """从 JSON 加载。schema 不匹配 / 文件缺失 → CodeReviewError。"""
        p = Path(path).resolve()
        if not p.is_file():
            raise CodeReviewError(f"索引不存在: {p}（先 code_review_build_index 或 "
                                  f"python tools/crg_index.py --build <目录>）")
        data = json.loads(p.read_text(encoding="utf-8"))
        if data.get("schema") != SCHEMA_VERSION:
            raise CodeReviewError(f"索引 schema 不匹配: 期望 {SCHEMA_VERSION}，实际 "
                                  f"{data.get('schema')}")
        idx = cls()
        idx.root = data.get("root", "")
        idx.nodes = data["nodes"]
        idx.edges = data["edges"]
        idx._module_of_file = {n["file"]: n["module"] for n in idx.nodes if n["kind"] == "module"}
        idx._file_of_module = {v: k for k, v in idx._module_of_file.items()}
        idx._rebuild_lookup()
        return idx

    # ============================================================ 查找表

    def _rebuild_lookup(self) -> None:
        self._by_id = {n["id"]: n for n in self.nodes}
        self._by_name = {}
        self._by_module = {}
        self._class_ids = set()
        for n in self.nodes:
            if n["kind"] != "module":
                self._by_name.setdefault(n["name"], []).append(n["id"])
            self._by_module.setdefault(n["module"], []).append(n["id"])
            if n["kind"] == "class":
                self._class_ids.add(n["id"])
        # 边索引：callers(被谁调用)/callees(调谁)/importers(被谁导入)
        self._callers = {}
        self._callees = {}
        self._importers = {}
        for e in self.edges:
            if e["kind"] == "calls":
                self._callers.setdefault(e["dst"], set()).add(e["src"])
                self._callees.setdefault(e["src"], set()).add(e["dst"])
            elif e["kind"] == "imports":
                self._importers.setdefault(e["dst"], set()).add(e["src"])

    def callers(self, node_id: str) -> list[str]:
        return sorted(self._callers.get(node_id, ()))

    def callees(self, node_id: str) -> list[str]:
        return sorted(self._callees.get(node_id, ()))

    def _node_ids_in_file(self, rel: str) -> list[str]:
        return [n["id"] for n in self.nodes if n["file"] == rel and n["kind"] != "module"]

    # ============================================================ 查询

    def query(self, name: str, limit: int = 10) -> dict[str, Any]:
        """按函数/类名查定义 + 调用者/被调者。精确 > 前缀 > 子串，fail-fast。"""
        if not name.strip():
            raise CodeReviewError("query 需要非空函数/类名")
        ids = self._match_ids(name.strip())
        if not ids:
            raise CodeReviewError(f"图谱中未找到节点: {name!r}")
        matches = []
        for nid in ids[:limit]:
            n = self._by_id[nid]
            matches.append({
                "node": n,
                "callers": [self._summary(i) for i in self.callers(nid)],
                "callees": [self._summary(i) for i in self.callees(nid)],
                "callers_count": len(self.callers(nid)),
                "callees_count": len(self.callees(nid)),
            })
        return {
            "name": name,
            "total": len(ids),
            "shown": len(matches),
            "matches": matches,
        }

    def _match_ids(self, name: str) -> list[str]:
        exact = [n["id"] for n in self.nodes if n["kind"] != "module" and n["name"] == name]
        if exact:
            return sorted(exact)
        qname = [n["id"] for n in self.nodes if n["kind"] != "module" and n["qualname"] == name]
        if qname:
            return sorted(qname)
        prefix = [n["id"] for n in self.nodes if n["kind"] != "module" and n["name"].startswith(name)]
        if prefix:
            return sorted(prefix)
        return sorted(n["id"] for n in self.nodes
                      if n["kind"] != "module" and name in n["name"])

    def _summary(self, node_id: str) -> dict[str, Any]:
        n = self._by_id[node_id]
        return {"name": n["qualname"] or n["name"], "file": n["file"],
                "line_start": n["line_start"], "kind": n["kind"]}

    # ============================================================ 影响半径

    def impact_radius(self, changed_files: Iterable[str], max_depth: int = 2) -> dict[str, Any]:
        """变更文件 → 反向边 BFS（谁调用这些函数 / 谁导入这些文件）。

        changed_files 为相对 root 的路径；缺失文件 fail-fast（诚实）。
        """
        depth = max(1, int(max_depth))
        seeds_file = set()
        for f in changed_files:
            f = f.replace("\\", "/")
            if f not in self._module_of_file:
                raise CodeReviewError(f"变更文件不在索引内: {f}")
            seeds_file.add(f)
        # 文件级：谁导入变更文件（反向 imports）
        impacted_files: dict[str, int] = {f: 0 for f in sorted(seeds_file)}
        frontier = {self._file_of_module[self._module_of_file[f]] for f in seeds_file}
        # 统一用 module_id 表示文件
        file_frontier = {f"{f}::" for f in seeds_file}
        for d in range(1, depth + 1):
            nxt = set()
            for mid in sorted(file_frontier):
                for imp in self._importers.get(mid, ()):
                    if imp not in impacted_files:
                        impacted_files[imp.split("::", 1)[0]] = d
                        nxt.add(imp)
            file_frontier = nxt
        # 函数级：谁调用变更文件内的函数（反向 calls）
        seed_nodes: set[str] = set()
        for f in seeds_file:
            seed_nodes.update(self._node_ids_in_file(f))
        impacted_nodes: dict[str, dict[str, Any]] = {
            nid: {"depth": 0, "via": "(changed file)"} for nid in sorted(seed_nodes)
        }
        frontier = set(seed_nodes)
        for d in range(1, depth + 1):
            nxt = set()
            for nid in sorted(frontier):
                for caller in self.callers(nid):
                    if caller not in impacted_nodes:
                        impacted_nodes[caller] = {"depth": d, "via": self._summary(nid)["name"]}
                        nxt.add(caller)
            frontier = nxt
        return {
            "changed_files": sorted(seeds_file),
            "max_depth": depth,
            "impacted_files": impacted_files,
            "impacted_nodes": impacted_nodes,
            "impacted_node_count": len(impacted_nodes),
        }

    # ============================================================ 变更检测

    def detect_changes(self, base: str = "HEAD~1",
                       changed_files: list[str] | None = None,
                       max_depth: int = 2,
                       max_results: int = 25,
                       max_flows: int = 20) -> dict[str, Any]:
        """git diff → 变更函数 → 风险分 + 测试缺口 + 受影响执行流。

        风险分为启发式公式（见 _risk_score），仅作审查优先级参考。
        """
        files, lines_by_file = self._git_changed_files(base, changed_files)
        if not files:
            return {"changed_files": [], "changed_functions": [], "test_gaps": [],
                    "affected_flows": [], "summary": "无变更（相对 base=" + base + "）"}
        changed_functions: list[dict[str, Any]] = []
        test_gaps: list[dict[str, Any]] = []
        affected_flows: list[dict[str, Any]] = []
        for f in sorted(files):
            if f not in self._module_of_file:
                continue  # 非索引内文件（如 .md/.json）跳过
            changed_lines = lines_by_file.get(f, set())
            for nid in self._node_ids_in_file(f):
                n = self._by_id[nid]
                if n["kind"] not in ("function", "method"):
                    continue
                churn = len([ln for ln in changed_lines
                             if n["line_start"] <= ln <= n["line_end"]])
                if not churn and changed_lines:
                    continue  # 文件有变更但此函数区间无命中
                if not churn and not changed_lines:
                    churn = n["line_end"] - n["line_start"] + 1  # 显式列出的文件：整函数视为变更
                fan_in = len(self.callers(nid))
                fan_out = len(self.callees(nid))
                has_test = self._has_test(f, n["name"])
                risk = _risk_score(churn, fan_in, fan_out, has_test)
                item = {
                    "function": n["qualname"] or n["name"], "file": f,
                    "line_start": n["line_start"], "line_end": n["line_end"],
                    "churn_lines": churn, "fan_in": fan_in, "fan_out": fan_out,
                    "has_test": has_test, "risk_score": risk, "level": _risk_level(risk),
                }
                changed_functions.append(item)
                if not has_test:
                    test_gaps.append(item)
        changed_functions.sort(key=lambda x: -x["risk_score"])
        # 受影响执行流：变更函数的上游调用链（深度 max_depth），按风险降序取前 max_flows
        for item in changed_functions[:max_flows]:
            nid = f"{item['file']}::{item['function']}"
            chain = [item["function"]]
            cur = nid
            for _ in range(max_depth):
                callers = self.callers(cur)
                if not callers:
                    break
                up = self._by_id[callers[0]]  # 确定性取字典序第一个调用者
                chain.insert(0, up["qualname"] or up["name"])
                cur = callers[0]
            affected_flows.append({"flow": " -> ".join(chain), "depth": len(chain) - 1,
                                   "risk_score": item["risk_score"]})
        return {
            "base": base,
            "changed_files": sorted(files),
            "changed_functions": changed_functions[:max_results],
            "changed_functions_total": len(changed_functions),
            "test_gaps": test_gaps[:max_results],
            "test_gaps_total": len(test_gaps),
            "affected_flows": affected_flows,
            "summary": (f"{len(files)} 个文件变更，{len(changed_functions)} 个函数受影响，"
                        f"{len(test_gaps)} 个无测试覆盖"),
        }

    def _git_changed_files(self, base: str, explicit: list[str] | None
                           ) -> tuple[list[str], dict[str, set[int]]]:
        """返回 (文件列表, {file: 变更行集合})。显式指定则跳过 git diff。"""
        if explicit:
            files = [f.replace("\\", "/") for f in explicit]
            return files, {f: set() for f in files}
        root = self.root
        try:
            names = subprocess.run(
                ["git", "-C", root, "diff", "--name-only", "--no-color", base],
                capture_output=True, text=True, check=True).stdout.splitlines()
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            raise CodeReviewError(f"git diff 失败（base={base}，root={root}）: {e}")
        files = [f for f in names if f.strip()]
        lines_by_file: dict[str, set[int]] = {}
        for f in files:
            try:
                diff = subprocess.run(
                    ["git", "-C", root, "diff", "-U0", "--no-color", base, "--", f],
                    capture_output=True, text=True, check=True).stdout
            except subprocess.CalledProcessError:
                continue
            lines_by_file[f] = _parse_diff_lines(diff)
        return files, lines_by_file

    def _has_test(self, rel: str, func_name: str) -> bool:
        """测试缺口启发式：模块有匹配测试文件 且 测试文件文本提及函数名（词边界）。"""
        stem = rel.rsplit("/", 1)[-1][:-3]  # 去 .py
        for tfile in self._test_files():
            tbase = tfile.rsplit("/", 1)[-1][:-3]  # 去 .py（test_xxx 或 xxx_test）
            if tbase == f"test_{stem}" or tbase == f"{stem}_test":
                if self._test_mentions(tfile, func_name):
                    return True
        return False

    def _test_files(self) -> list[str]:
        out = []
        for rel in self._module_of_file:
            parts = rel.split("/")
            is_test_path = any(p in ("tests", "test") for p in parts[:-1])
            base = rel.rsplit("/", 1)[-1]
            is_test_name = base.startswith("test_") or base.endswith("_test.py")
            if is_test_path or is_test_name:
                out.append(rel)
        return sorted(out)

    def _test_mentions(self, tfile: str, func_name: str) -> bool:
        # 索引内无测试文件内容缓存，直接读盘（文件数有限，可接受）
        p = Path(self.root) / tfile
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            return False
        return bool(re.search(rf"\b{re.escape(func_name)}\b", text))

    # ============================================================ 架构总览

    def architecture_overview(self, top_k: int = 10) -> dict[str, Any]:
        """枢纽节点（高扇入）、依赖大户（高扇出）、大函数、目录分布。"""
        non_module = [n for n in self.nodes if n["kind"] != "module"]
        fan_in = sorted(non_module, key=lambda n: -len(self.callers(n["id"])))[:top_k]
        fan_out = sorted(non_module, key=lambda n: -len(self.callees(n["id"])))[:top_k]
        big = sorted(non_module, key=lambda n: -(n["line_end"] - n["line_start"]))[:top_k]
        kinds: dict[str, int] = {}
        dirs: dict[str, int] = {}
        for n in self.nodes:
            kinds[n["kind"]] = kinds.get(n["kind"], 0) + 1
            if n["kind"] == "module":
                d = n["file"].split("/", 1)[0]
                dirs[d] = dirs.get(d, 0) + 1
        return {
            "files": len(self._module_of_file),
            "nodes_by_kind": kinds,
            "edges": len(self.edges),
            "top_by_fan_in": [self._hub_entry(n, "fan_in") for n in fan_in],
            "top_by_fan_out": [self._hub_entry(n, "fan_out") for n in fan_out],
            "largest_functions": [self._hub_entry(n, "lines") for n in big],
            "directories": dict(sorted(dirs.items())),
        }

    def _hub_entry(self, n: dict[str, Any], metric: str) -> dict[str, Any]:
        e = self._summary(n["id"])
        e[metric] = ({
            "fan_in": len(self.callers(n["id"])),
            "fan_out": len(self.callees(n["id"])),
            "lines": n["line_end"] - n["line_start"] + 1,
        })[metric]
        return e


# ============================================================ 模块级工具函数

def _parse_diff_lines(diff: str) -> set[int]:
    """解析 `git diff -U0` 输出，返回新文件侧变更行集合（1-based）。"""
    changed: set[int] = set()
    for line in diff.splitlines():
        m = re.match(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", line)
        if not m:
            continue
        start = int(m.group(1))
        count = int(m.group(2)) if m.group(2) else 1
        if count == 0:
            continue  # 纯删除 hunk（无新增行，start 指向插入点）
        changed.update(range(start, start + count))
    return changed


def _risk_score(churn: int, fan_in: int, fan_out: int, has_test: bool) -> int:
    """启发式风险分 0..100（审查优先级参考，非上游同款权重，公式已文档化）。

    变更体量(≤50 行计 0.6/行) + 被依赖度(≤10 记 3/个) + 依赖广度(≤10 记 1.5/个)
    + 测试缺口(无测试 +20)。上限截断 100。
    """
    score = (min(churn, 50) * 0.6 + min(fan_in, 10) * 3.0
             + min(fan_out, 10) * 1.5 + (0.0 if has_test else 20.0))
    return int(round(min(score, 100.0)))


def _risk_level(score: int) -> str:
    if score >= 60:
        return "high"
    if score >= 30:
        return "medium"
    return "low"
