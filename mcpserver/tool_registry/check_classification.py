#!/usr/bin/env python3
"""总线能力分类的静态校验（stdlib only，不 import 任何 agent）。

校验每个 agent-manifest.json 的 `classification` 块是否符合
`docs/总线能力标签体系-2026-09-29.md` 定义的词汇表：

    families ⊆ FAMILIES（9 族）
    tier     ⊆ TIERS（4 档）
    domains  ⊆ DOMAINS（4 个数据域，允许空）
    origin.kind ∈ ORIGIN_KINDS

用法：
    python mcpserver/tool_registry/check_classification.py          # 只报错
    python mcpserver/tool_registry/check_classification.py -v       # 附缺失清单
    python mcpserver/tool_registry/check_classification.py --strict # 未分类也算失败

设计意图（对齐 S-01 勘察结论）：把兼容性/规范检查从运行时挪到装前——
毫秒级纯静态判定，不跑一行 agent 代码。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# ── 词汇表 ────────────────────────────────────────────────────────────
# FAMILIES/TIERS 的唯一真源在 apiserver/mcp_assembly.py（KNOWN_FAMILIES/
# KNOWN_TIERS——运行层装配策略与本校验脚本共用，改一处等于改规范）。
# 本脚本按文件路径加载它，绕开 apiserver 包的 __init__ 重依赖链
# （照 check_agent_requirements.py 的手法）。
import importlib.util as _il

_spec = _il.spec_from_file_location(
    "mcp_assembly_vocabulary", REPO_ROOT / "apiserver" / "mcp_assembly.py"
)
assert _spec and _spec.loader, "加载 apiserver/mcp_assembly.py 失败"
_vocabulary_mod = _il.module_from_spec(_spec)
_spec.loader.exec_module(_vocabulary_mod)
FAMILIES = set(_vocabulary_mod.KNOWN_FAMILIES)
TIERS = set(_vocabulary_mod.KNOWN_TIERS)
DOMAINS = {"materials", "mechat", "security", "law"}
ORIGIN_KINDS = {"native", "vendored", "bridge"}

# facets 块（卷178，设计稿 docs/Facet槽位-设计-2026-09-29.md §二）
FACET_KINDS = ("status-card", "control-panel")
MIN_POLL_INTERVAL_MS = 250

# tier=offensive 的入口必须带默认关闭闸门（环境变量名约定）
OFFENSIVE_FLAG_SUFFIX = "_ENABLE_INVOKE"


def iter_manifests() -> list[Path]:
    return sorted(REPO_ROOT.glob("mcpserver/**/agent-manifest.json"))


def check_yaml_meta(path: Path) -> tuple[list[str], bool]:
    """校验 tool_registry/*.meta.yaml 形式的分类（正则最小解析，避免引入 PyYAML）。

    只取 app 段内的 families/domains/tier/categories —— 这些是简单列表或标量，
    正则足够；**不解析整个 YAML**，以保持 stdlib only 的契约。
    """
    errs: list[str] = []
    rel = path.relative_to(REPO_ROOT)
    text = path.read_text(encoding="utf-8")
    # 截取 app 段（app: 到 functions: 之间）
    m_app = re.search(r"^app:\s*$", text, re.M)
    if not m_app:
        return [f"{rel}: 缺少 app: 段"], False
    m_fn = re.search(r"^functions:\s*$", text, re.M)
    seg = text[m_app.end(): m_fn.start() if m_fn else len(text)]

    def _list(key: str) -> list[str]:
        m = re.search(rf"^\s*{key}:\s*\[(.*?)\]", seg, re.M)
        return [x.strip().strip("'\"") for x in m.group(1).split(",") if x.strip()] if m else []

    fams, doms, cats = _list("families"), _list("domains"), _list("categories")
    m_tier = re.search(r"^\s*tier:\s*(\S+)", seg, re.M)
    tier = m_tier.group(1) if m_tier else ""

    if not fams:
        return [], False          # 未分类
    for f in fams:
        if f not in FAMILIES:
            errs.append(f"{rel}: 未知族 {f!r}")
    if tier not in TIERS:
        errs.append(f"{rel}: 未知 tier {tier!r}（合法值：{sorted(TIERS)}）")
    for d in doms:
        if d not in DOMAINS:
            errs.append(f"{rel}: 未知 domain {d!r}")
    # 领域名不得混进 categories（docs §六 登记的隐患）
    for c in cats:
        if c in DOMAINS:
            errs.append(f"{rel}: categories 里混入了领域名 {c!r}（应放 domains）")
    return errs, True


def _declared_tool_names(data: dict) -> set[str]:
    """manifest 已声明的工具面（tools[].name 或 capabilities.invocationCommands[].command）。"""
    names: set[str] = set()
    for t in data.get("tools") or []:
        if isinstance(t, dict) and t.get("name"):
            names.add(str(t["name"]))
    caps = data.get("capabilities")
    if isinstance(caps, dict):
        for c in caps.get("invocationCommands") or []:
            if isinstance(c, dict) and c.get("command"):
                names.add(str(c["command"]))
    return names


def check_facets_rules(data: dict, rel) -> list[str]:
    """facets 块校验（卷178-A，规则来自 docs/Facet槽位-设计-2026-09-29.md §二）。

    无 facets 块 = 该能力无面板面（现状行为，零迁移成本）——不报错。
    四条强制规则：
      ① poll.tool / actions[].tool 必须出现在已声明工具面（面板不是旁路）
      ② poll.interval_ms >= 250（防轮询风暴）
      ③ kind=control-panel 必须声明 actions（名不副实的面板不如不声明）
      ④ always_available: true 仅允许用于降低风险的动作（须同时声明 reduces_risk: true）
    """
    errs: list[str] = []
    facets = data.get("facets")
    if facets is None:
        return errs
    if not isinstance(facets, dict):
        return [f"{rel}: facets 必须是对象（含 panel 子块）"]
    panel = facets.get("panel")
    if panel is None:
        return errs
    if not isinstance(panel, dict):
        return [f"{rel}: facets.panel 必须是对象"]

    kind = panel.get("kind")
    if kind not in FACET_KINDS:
        errs.append(f"{rel}: facets.panel.kind 非法 {kind!r}（合法值：{list(FACET_KINDS)}）")
    if not panel.get("component"):
        errs.append(f"{rel}: facets.panel.component 必填（前端注册表解析名）")

    declared = _declared_tool_names(data)
    poll = panel.get("poll")
    if poll is not None:
        if not isinstance(poll, dict):
            errs.append(f"{rel}: facets.panel.poll 必须是对象")
        else:
            tool = poll.get("tool")
            if not tool:
                errs.append(f"{rel}: facets.panel.poll.tool 必填")
            elif tool not in declared:
                errs.append(f"{rel}: poll.tool {tool!r} 不在已声明工具面（面板必须走已声明工具）")
            iv = poll.get("interval_ms")
            if not isinstance(iv, int) or iv < MIN_POLL_INTERVAL_MS:
                errs.append(f"{rel}: poll.interval_ms 必须 >= {MIN_POLL_INTERVAL_MS}（防轮询风暴）")

    actions = panel.get("actions")
    if kind == "control-panel" and not actions:
        errs.append(f"{rel}: kind=control-panel 必须声明 actions")
    if actions is not None and not isinstance(actions, list):
        errs.append(f"{rel}: facets.panel.actions 必须是数组")
    else:
        for a in actions or []:
            if not isinstance(a, dict):
                errs.append(f"{rel}: actions 元素必须是对象")
                continue
            tool = a.get("tool")
            if not tool:
                errs.append(f"{rel}: actions[].tool 必填")
            elif tool not in declared:
                errs.append(f"{rel}: action.tool {tool!r} 不在已声明工具面")
            if a.get("always_available") is True and a.get("reduces_risk") is not True:
                errs.append(
                    f"{rel}: always_available 仅允许降低风险动作（须同时声明 reduces_risk: true）"
                )
    return errs


def check_one(path: Path) -> tuple[list[str], bool]:
    """返回 (错误列表, 是否已分类)。"""
    errs: list[str] = []
    rel = path.relative_to(REPO_ROOT)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return [f"{rel}: manifest 无法解析：{e}"], False

    cls = data.get("classification")
    if not cls:
        return [], False

    fams = cls.get("families")
    if not isinstance(fams, list) or not fams:
        errs.append(f"{rel}: families 必须是非空列表")
    else:
        for f in fams:
            if f not in FAMILIES:
                errs.append(f"{rel}: 未知族 {f!r}（合法值：{sorted(FAMILIES)}）")

    tier = cls.get("tier")
    if tier not in TIERS:
        errs.append(f"{rel}: 未知 tier {tier!r}（合法值：{sorted(TIERS)}）")

    doms = cls.get("domains", [])
    if not isinstance(doms, list):
        errs.append(f"{rel}: domains 必须是列表（可为空）")
    else:
        for d in doms:
            if d not in DOMAINS:
                errs.append(f"{rel}: 未知 domain {d!r}（合法值：{sorted(DOMAINS)}）")

    origin = cls.get("origin") or {}
    kind = origin.get("kind")
    if kind not in ORIGIN_KINDS:
        errs.append(f"{rel}: 未知 origin.kind {kind!r}（合法值：{sorted(ORIGIN_KINDS)}）")
    if kind == "bridge" and not origin.get("upstream"):
        errs.append(f"{rel}: origin.kind=bridge 必须声明 upstream（「借」的来源）")

    # tier=offensive → 入口必须有默认关闭闸门
    if tier == "offensive":
        name = data.get("name") or path.parent.name
        # 闸门变量名约定：去 agent_ 前缀（agent_frida → FRIDA_ENABLE_INVOKE）
        flag = name.removeprefix("agent_").upper() + OFFENSIVE_FLAG_SUFFIX
        impl = path.parent / f"{name}.py"
        if not impl.exists():
            # 适配器形态的 manifest 与实现常不同目录（如 vulnclaw_adapter/ ↔ vulnclaw.py）
            cands = sorted((REPO_ROOT / "mcpserver").glob(f"**/{name}.py"))
            if cands:
                impl = cands[0]
        if impl.exists() and flag not in impl.read_text(encoding="utf-8"):
            errs.append(
                f"{rel}: tier=offensive 但入口未见闸门（期望 {impl.name} 内出现 {flag}）"
            )

    errs.extend(check_facets_rules(data, rel))
    return errs, True


def main() -> int:
    ap = argparse.ArgumentParser(description="总线能力分类静态校验")
    ap.add_argument("-v", "--verbose", action="store_true", help="列出未分类项")
    ap.add_argument("--strict", action="store_true", help="未分类也算失败")
    args = ap.parse_args()

    all_errs: list[str] = []
    classified, unclassified = [], []
    for p in iter_manifests():
        errs, done = check_one(p)
        all_errs += errs
        name = json.loads(p.read_text(encoding="utf-8")).get("name", p.parent.name)
        (classified if done else unclassified).append(name)
    # meta.yaml（S-02 另一套格式，同样纳入词汇表纪律）
    for p in sorted((REPO_ROOT / "mcpserver" / "tool_registry").glob("*.yaml")):
        errs, done = check_yaml_meta(p)
        all_errs += errs
        (classified if done else unclassified).append(p.stem)

    total = len(classified) + len(unclassified)
    print(f"分类覆盖：{len(classified)}/{total}")
    by_fam: dict[str, int] = {}
    by_tier: dict[str, int] = {}
    for p in iter_manifests():
        data = json.loads(p.read_text(encoding="utf-8"))
        cls = data.get("classification")
        if not cls:
            continue
        for f in cls.get("families", []):
            by_fam[f] = by_fam.get(f, 0) + 1
        t = cls.get("tier")
        by_tier[t] = by_tier.get(t, 0) + 1
    print("  族分布：", dict(sorted(by_fam.items(), key=lambda kv: -kv[1])))
    print("  tier 分布：", dict(sorted(by_tier.items(), key=lambda kv: -kv[1])))

    if unclassified:
        print(f"\n未分类 {len(unclassified)} 个" + ("：" if args.verbose else "（-v 列出）"))
        if args.verbose:
            for n in unclassified:
                print(f"    {n}")

    if all_errs:
        print(f"\n✗ {len(all_errs)} 项不合规：")
        for e in all_errs:
            print(f"    {e}")
        return 1

    if args.strict and unclassified:
        print(f"\n✗ --strict：仍有 {len(unclassified)} 个未分类")
        return 1

    print("\n✓ 已分类项全部合法")
    return 0


if __name__ == "__main__":
    sys.exit(main())
