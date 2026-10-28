"""agent 资产盘存（工单249 · 方法借自 karmine05/agentic-detector）。

产出**一张表**，每行是一件仓内 agent 资产，带：

- **静态契约信号**（manifest / entryPoint 可解析 / 派发表一致 / handle_handoff / 测试 / README / requirements）
  ⇒ 汇总成 **置信度** 与可核对的 **evidence 令牌**；
- **风险姿态**（`posture.scan_text_risks`，含 `remote_fetch_exec` / `unpinned_dependency` /
  `cleartext_endpoint` / `plaintext_secret` …）；
- **指纹**：`sha256`（manifest 内容）+ `launch_hash`（entryPoint 的"启动向量"）
  ⇒ 两份快照一比就能发现**签名变了**（上游叫 rug-pull 检测）。

另外做一件上游没有、但本仓特别需要的事：**注册表对账** ——
`manifest 里声明的 command` 与 `代码里派发表 _TOOLS` 是否逐项一致、
以及 entryPoint 是否**真能静态落地**。244g/244h 是**人工**做过这件事的，本模块把它变成**可反复跑的能力**。

⚠️ **只读**：不 import 被盘对象（避免副作用）、不执行任何二进制、不建立任何连接。
"""

from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from . import posture

#: 表列（照上游 `ai_tools` 的形状，去掉我们做不了的 running/pid/port —— 见 README §边界）
COLUMNS = ("type", "name", "identifier", "category", "location", "source", "version", "path",
           "endpoint", "risk_flags", "quality_flags", "confidence", "band", "evidence",
           "sha256", "launch_hash", "detail")

#: 指令文件名（agent 会自动加载并服从它们 —— 提示注入面）
INSTRUCTION_NAMES = ("AGENTS.md", "CLAUDE.md", "GEMINI.md", ".cursorrules")

#: 扫描时跳过的目录（外部同步代码 / 产物 / 第三方）
_SKIP_DIRS = frozenset({"NEKO", "vendor", "mod", "github_haul", "node_modules", ".venv",
                        "build", "dist", "__pycache__", ".git"})


@dataclass
class AssetRow:
    """一行资产。"""

    type: str
    name: str
    path: str
    identifier: str = ""
    category: str = ""
    location: str = "local"
    source: str = ""
    version: str = ""
    endpoint: str = ""
    sha256: str = ""
    launch_hash: str = ""
    post: posture.Posture = field(default_factory=posture.Posture)
    detail: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        d = {
            "type": self.type, "name": self.name, "identifier": self.identifier,
            "category": self.category, "location": self.location, "source": self.source,
            "version": self.version, "path": self.path, "endpoint": self.endpoint,
            "sha256": self.sha256, "launch_hash": self.launch_hash,
            "detail": self.detail,
        }
        d.update(self.post.as_dict())
        return d


# --------------------------------------------------------------------------- 工具


def sha256_bytes(raw: bytes) -> str:
    """内容指纹（用于 diff 快照：内容变了 ⇒ 指纹变了）。"""
    return hashlib.sha256(raw).hexdigest()


def launch_fingerprint(module: str, cls: str) -> str:
    """**启动向量**的指纹（照上游 `launch_hash` 的概念）：entryPoint 变了就是变了。"""
    return hashlib.sha256(f"{module}::{cls}".encode()).hexdigest()[:16]


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _module_file(repo_root: Path, module: str) -> Path | None:
    """把 `a.b.c` 静态映射到文件（`a/b/c.py` 或 `a/b/c/__init__.py`）。"""
    base = repo_root.joinpath(*module.split("."))
    for cand in (base.with_suffix(".py"), base / "__init__.py"):
        if cand.is_file():
            return cand
    return None


def _class_info(py: Path, cls_name: str) -> dict | None:
    """静态取一个类的信息：是否存在 / 有没有 `handle_handoff` / `_TOOLS` 的键。

    **不 import** —— 用 AST 读，避免拉起被盘对象的依赖与副作用。

    ⚠️ **必须沿基类递归**（实测踩过）：只看类自身的方法体时，`FlatAdapterBridge` 的子类
    会被判成"没有 `handle_handoff`"—— 而它其实是**继承**来的（`hasattr(C, ...) == True`），
    于是一口气报出 8 个假缺口。基类若**不在本文件内**（跨文件继承），则如实标
    `handoff_known=False`（**无法判定**，不是"没有"），由调用方决定怎么记。
    """
    try:
        tree = ast.parse(_read(py))
    except SyntaxError:
        return None
    classes = {n.name: n for n in tree.body if isinstance(n, ast.ClassDef)}
    if cls_name not in classes:
        return None

    def self_tools(node: ast.ClassDef) -> list[str]:
        for n in node.body:
            targets, value = [], None
            if isinstance(n, ast.Assign):
                targets, value = n.targets, n.value
            elif isinstance(n, ast.AnnAssign):
                targets, value = [n.target], n.value
            else:
                continue
            if not any(isinstance(t, ast.Name) and t.id == "_TOOLS" for t in targets):
                continue
            if isinstance(value, ast.Dict):
                return sorted(k.value for k in value.keys
                              if isinstance(k, ast.Constant) and isinstance(k.value, str))
        return []

    def collect(name: str, seen: frozenset[str]) -> dict:
        """返回 ``{has_handoff, tools, bases_known}``；`bases_known=False` 表示判据不完整。"""
        node = classes.get(name)
        if node is None or name in seen:
            return {"has_handoff": False, "tools": [], "bases_known": False}
        methods = {n.name for n in node.body
                   if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        out = {"has_handoff": "handle_handoff" in methods, "tools": self_tools(node),
               "bases_known": True}
        for base in node.bases:
            bname = base.id if isinstance(base, ast.Name) else None
            if bname is None or bname == "object":
                if bname is None:
                    out["bases_known"] = False          # 复杂基类表达式（如 mixin 调用）
                continue
            if bname not in classes:
                out["bases_known"] = False              # 跨文件基类 ⇒ 无法判定
                continue
            parent = collect(bname, seen | {name})
            out["has_handoff"] = out["has_handoff"] or parent["has_handoff"]
            if not out["tools"]:
                out["tools"] = parent["tools"]
            out["bases_known"] = out["bases_known"] and parent["bases_known"]
        return out

    got = collect(cls_name, frozenset())
    return {"has_handoff": got["has_handoff"],
            "handoff_known": got["has_handoff"] or got["bases_known"],
            "tools": got["tools"], "has_tools_table": bool(got["tools"]),
            "method_count": len({n.name for n in classes[cls_name].body
                                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))})}


# --------------------------------------------------------------------------- 扫描


def scan_agents(repo_root: str | Path) -> list[AssetRow]:
    """扫 `mcpserver/**/agent-manifest.json`，逐条算出信号与姿态。"""
    root = Path(repo_root)
    rows: list[AssetRow] = []
    for mf in sorted((root / "mcpserver").rglob("agent-manifest.json")):
        rel_dir = mf.parent.relative_to(root)
        if _SKIP_DIRS & set(rel_dir.parts):
            continue
        raw = mf.read_bytes()
        text = raw.decode("utf-8", errors="replace")
        try:
            man = json.loads(text)
        except json.JSONDecodeError as exc:
            rows.append(AssetRow(type="mcp_agent", name=rel_dir.name, path=mf.relative_to(root).as_posix(),
                                 source="manifest-invalid", sha256=sha256_bytes(raw),
                                 detail={"json_error": f"{exc.msg} @line {exc.lineno}"}))
            continue

        ep = man.get("entryPoint") or {}
        module, cls = str(ep.get("module") or ""), str(ep.get("class") or "")
        info = None
        pf = _module_file(root, module) if module else None
        if pf is not None and cls:
            info = _class_info(pf, cls)

        # ⚠️ 宽松解析：`capabilities` 未必是 dict、`invocationCommands` 未必是 dict 列表
        #    （实测踩过：某个 manifest 的该项是列表的列表 ⇒ 直接 .get() 会 AttributeError）。
        caps = man.get("capabilities")
        cmds = caps.get("invocationCommands") if isinstance(caps, dict) else None
        declared = {c["command"] for c in (cmds if isinstance(cmds, list) else [])
                    if isinstance(c, dict) and c.get("command")}
        code_tools = set(info["tools"]) if info else set()

        checkable = bool(info and info["has_tools_table"])
        signals = {
            "manifest": True,
            "entrypoint_resolves": info is not None,
            "handoff_contract": bool(info and info["has_handoff"]),
            # 只在**真的用了 `_TOOLS` 派发表**时才判定；未用 ⇒ 记为不匹配为 False 但**不产出缺口**
            "dispatcher_match": bool(checkable and declared == code_tools),
            "tests": (root / "tests" / f"test_{rel_dir.name}.py").is_file(),
            "readme": (mf.parent / "README.md").is_file(),
            "requirements_declared": (mf.parent / "requirements.txt").is_file(),
        }
        post = posture.score(signals)
        if not signals["handoff_contract"]:
            # 继承链**没能完整解析**时不许断言"没有" —— 那是"无法判定"，不是缺口
            post.quality_flags.append(
                "no_handoff" if (info and info.get("handoff_known")) else "handoff_uncheckable")
        if checkable and declared != code_tools:
            post.quality_flags.append("dispatcher_mismatch")
        elif not checkable:
            # 不适用**不是**缺口：如实标注"该 bridge 未使用 `_TOOLS` 表，派发表无法静态核对"
            post.quality_flags.append("dispatcher_uncheckable")
        if not signals["tests"]:
            post.quality_flags.append("no_tests")
        if not signals["readme"]:
            post.quality_flags.append("no_readme")
        if not signals["requirements_declared"]:
            post.quality_flags.append("no_requirements")

        # 风险：扫 manifest 自身 + 模块的 README/requirements（本仓的"依赖声明"就在这两处）
        risk: set[str] = set(posture.scan_text_risks(text, kind="manifest"))
        for extra in ("README.md", "requirements.txt"):
            risk |= set(posture.scan_text_risks(_read(mf.parent / extra), kind="config"))
        post.risk_flags = sorted(risk)

        cls_meta = (man.get("classification") or {})
        rows.append(AssetRow(
            type="mcp_agent", name=rel_dir.name,
            path=mf.relative_to(root).as_posix(),
            identifier=str(man.get("name") or rel_dir.name),
            category=",".join((cls_meta.get("families") or []) + (cls_meta.get("domains") or [])),
            source=str(man.get("author") or ""), version=str(man.get("version") or ""),
            sha256=sha256_bytes(raw), launch_hash=launch_fingerprint(module, cls),
            post=post,
            detail={
                "agentType": man.get("agentType", ""), "tier": cls_meta.get("tier", ""),
                "entryPoint": {"module": module, "class": cls},
                "declared_commands": sorted(declared), "code_tools": sorted(code_tools),
                "dispatcher_checkable": checkable,
                "entrypoint_file": pf.relative_to(root).as_posix() if pf else "",
                "secret_var_names": posture.secret_var_names(
                    "".join(_read(mf.parent / x) for x in ("README.md", "requirements.txt"))),
            },
        ))
    return rows


def scan_instructions(repo_root: str | Path, *, max_depth: int = 3) -> list[AssetRow]:
    """扫仓内的 agent 指令文件（agent 会自动加载并服从 ⇒ 提示注入面）。"""
    root = Path(repo_root)
    rows: list[AssetRow] = []
    for p in sorted(root.rglob("*")):
        if p.name not in INSTRUCTION_NAMES or not p.is_file():
            continue
        rel = p.relative_to(root)
        if _SKIP_DIRS & set(rel.parts) or len(rel.parts) > max_depth:
            continue
        raw = p.read_bytes()
        text = raw.decode("utf-8", errors="replace")
        post = posture.Posture(confidence=100, signals=["instruction_file"])
        post.risk_flags = sorted(posture.scan_text_risks(text, kind="instruction"))
        rows.append(AssetRow(
            type="instruction_file", name=p.name, path=rel.as_posix(),
            identifier=",".join(p.parent.parts[:2]) or "root",
            category="agent-instruction", source="repo", sha256=sha256_bytes(raw),
            post=post, detail={"size": len(raw), "lines": text.count("\n") + 1}))
    return rows


def reconcile(agent_rows: list[AssetRow]) -> list[AssetRow]:
    """注册表对账：把「静态契约不成立」的资产单独出一类行（`registry_gap`）。

    两类缺口：
    - `entryPoint 静态不可解析` ⇒ 注册器**永远注册不上**（244h 在 `mod/` 抓到的就是这类）
    - `派发表与 manifest 不一致` ⇒ 声明的工具**调不到**（244 的教训：
      只把方法写在类上、不登记进 `_TOOLS`，LM 是调不到的）
    """
    gaps: list[AssetRow] = []
    for r in agent_rows:
        reasons: list[str] = []
        if not r.post.signals or "entrypoint_resolves" not in r.post.signals:
            reasons.append("entryPoint 静态不可解析（注册器注册不上）")
        if "no_handoff" in r.post.quality_flags and "handoff_uncheckable" not in r.post.quality_flags:
            reasons.append("entryPoint 的类没有 handle_handoff（注册器会直接拒）")
        if "dispatcher_mismatch" in r.post.quality_flags:
            reasons.append("manifest 声明与代码派发表不一致（声明的工具调不到）")
        if not reasons:
            continue
        post = posture.Posture(confidence=100 - 30 * len(reasons),
                               signals=["registry_gap"], risk_flags=[],
                               quality_flags=list(r.post.quality_flags))
        gaps.append(AssetRow(
            type="registry_gap", name=r.name, path=r.path, identifier=r.identifier,
            category=r.category, source="reconcile", sha256=r.sha256,
            launch_hash=r.launch_hash, post=post,
            detail={"reasons": reasons, "entryPoint": r.detail.get("entryPoint", {})}))
    return gaps


def build_inventory(repo_root: str | Path) -> dict:
    """一次完整盘存：三类行 + 汇总。**低于阈值不出行**仍计入 summary（照上游纪律）。"""
    agents = scan_agents(repo_root)
    instr = scan_instructions(repo_root)
    gaps = reconcile(agents)
    emitted = [r for r in agents if r.post.emitted] + instr + gaps
    suppressed = [r for r in agents if not r.post.emitted]
    return {
        "rows": [r.as_dict() for r in emitted],
        "columns": list(COLUMNS),
        "summary": {
            "total_rows": len(emitted),
            "by_type": _count_by(emitted, "type"),
            "by_band": _count_by(emitted, "band"),
            "with_risk_flags": sum(1 for r in emitted if r.post.risk_flags),
            "risk_flag_counts": _risk_counts(emitted),
            "suppressed_below_threshold": [r.name for r in suppressed],
            "suppressed_note": f"置信度 < {posture.MIN_EMITTED} 不出行（照上游纪律：只有名字不构成一行）",
        },
    }


def _count_by(rows: list[AssetRow], key: str) -> dict:
    out: dict[str, int] = {}
    for r in rows:
        k = getattr(r, key) if key != "band" else r.post.band
        out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items()))


def _risk_counts(rows: list[AssetRow]) -> dict:
    out: dict[str, int] = {}
    for r in rows:
        for f in r.post.risk_flags:
            out[f] = out.get(f, 0) + 1
    return dict(sorted(out.items()))


# --------------------------------------------------------------------------- 快照与 diff


def snapshot(inv: dict) -> dict:
    """把盘存压成**可 diff 的快照**：名字 → {指纹, 置信度, 风险, 质量}。"""
    # ⚠️ 键必须是 `type:path`，**不是** `type:name` —— 名字连**同类型内**都不唯一：
    #    实测仓里有三个 `AGENTS.md`（apiserver/、frontend/src/、mcpserver/），按 name 做键会静默合并。
    return {f"{r['type']}:{r['path']}": {"type": r["type"], "sha256": r["sha256"],
                                         "launch_hash": r["launch_hash"],
                                         "confidence": r["confidence"],
                                         "risk_flags": r["risk_flags"],
                                         "quality_flags": r["quality_flags"]}
            for r in inv["rows"]}


def diff_snapshots(old: dict, new: dict) -> dict:
    """两份快照相减：新增 / 消失 / **指纹变化**（rug-pull 候选）/ 风险或质量标记变化。

    ⚠️ `launch_hash` 变化 = **启动向量被改** —— 这是最需要人看的一类变化（上游概念）。
    """
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    changed: list[dict] = []
    for name in sorted(set(old) & set(new)):
        o, n = old[name], new[name]
        fields = [k for k in ("sha256", "launch_hash", "confidence",
                              "risk_flags", "quality_flags") if o.get(k) != n.get(k)]
        if fields:
            changed.append({"name": name, "fields": fields,
                            "launch_vector_changed": o.get("launch_hash") != n.get("launch_hash"),
                            "old": {k: o.get(k) for k in fields},
                            "new": {k: n.get(k) for k in fields}})
    return {"added": added, "removed": removed, "changed": changed,
            "launch_vector_changes": [c["name"] for c in changed if c["launch_vector_changed"]]}
