"""registry.py — 统一 meta 的发现入口（S-02）。

两条发现路径：
1. discover_meta_files(dir)：扫目录下 *.yaml/*.yml，按统一 meta 结构加载校验。
2. scan_manifest_dir(root)：扫 mcpserver/*/agent-manifest.json（旧格式），
   经 convert_manifest_to_meta 兼容转换为统一 meta——增量不破坏既有 manifest。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from mcpserver.tool_registry.meta import MetaApp, load_and_validate


def _params_to_json_schema(params: dict[str, Any]) -> dict[str, Any]:
    """旧 manifest 的扁平 {参数名: 描述字符串} → JSON Schema。

    旧格式无类型信息，全部参数默认 type=string、全部可选（required=[]），
    至少把「参数名 + 描述」升级为机器可读的 properties 契约。
    """
    properties: dict[str, dict[str, Any]] = {}
    for key, desc in (params or {}).items():
        properties[str(key)] = {"type": "string", "description": str(desc)}
    return {
        "type": "object",
        "properties": properties,
        "required": [],
        "additionalProperties": False,
    }


def convert_manifest_to_meta(manifest: dict[str, Any]) -> MetaApp:
    """旧 agent-manifest.json → 统一 MetaApp（兼容转换，只读不破坏原文件）。

    字段映射（详见 docs/aci-tool-registry-勘察报告.md §4.2）：
      name → app.name；displayName → app.display_name；
      capabilities.invocationCommands[].command → functions[].name；
      [].description → functions[].description；
      [].params(扁平描述) → functions[].parameters(JSON Schema)；
      entryPoint → app.entrypoint；
      **classification（families/domains/tier/origin）→ app 分类字段**（卷180-B：
      2026-09-30 前此处置空，加载侧完全没消费标签——本卷补上）。
    """
    if not isinstance(manifest, dict):
        raise ValueError("manifest 必须是 JSON 对象")

    cls = manifest.get("classification") or {}
    if not isinstance(cls, dict):
        cls = {}
    app_raw = {
        "name": manifest.get("name", ""),
        "display_name": manifest.get("displayName") or manifest.get("name", ""),
        "version": str(manifest.get("version") or ""),
        "description": manifest.get("description") or "",
        "categories": list(cls.get("categories") or []),
        "families": list(cls.get("families") or []),
        "domains": list(cls.get("domains") or []),
        "tier": str(cls.get("tier") or ""),
        "origin": dict(cls.get("origin") or {}),
        "security_schemes": {},
    }
    ep = manifest.get("entryPoint")
    if isinstance(ep, dict) and ep.get("module"):
        app_raw["entrypoint"] = {"module": ep.get("module", ""),
                                 "class": ep.get("class", "")}

    caps = manifest.get("capabilities") or {}
    commands = caps.get("invocationCommands") or [] if isinstance(caps, dict) else []
    functions = []
    for cmd in commands:
        if not isinstance(cmd, dict) or not cmd.get("command"):
            continue  # 跳过缺 command 的坏条目（增量兼容，不因一条坏行整体失败）
        functions.append({
            "name": cmd["command"],
            "description": cmd.get("description") or "",
            "parameters": _params_to_json_schema(cmd.get("params") or {}),
        })
    # 兼容第二种格式：capabilities 是字符串能力名数组（6 个 manifest 如此，卷180-B 实测）。
    # 这类能力名是**细粒度主题词**——并入 categories（可被标签查询），不伪造调用契约。
    if isinstance(caps, list):
        extra = [str(c) for c in caps if isinstance(c, str) and c.strip()]
        if extra and not app_raw["categories"]:
            app_raw["categories"] = extra

    from mcpserver.tool_registry.meta import validate_meta
    return validate_meta({"app": app_raw, "functions": functions})


def discover_meta_files(directory: str | Path) -> list[MetaApp]:
    """扫目录下所有 *.yaml/*.yml，加载校验为 MetaApp 列表（按文件名字典序）。"""
    directory = Path(directory)
    metas: list[MetaApp] = []
    files = sorted(list(directory.glob("*.yaml")) + list(directory.glob("*.yml")))
    for f in files:
        metas.append(load_and_validate(f))
    return metas


def scan_manifest_dir(root: str | Path) -> list[MetaApp]:
    """扫 mcpserver/**/agent-manifest.json（旧格式，**递归**），统一转换为 MetaApp 列表。

    注意：manifest 不只在 mcpserver/*/ 一层（`adapters/semantic_web/`、
    `ptz_service/` 等在更深层）——单层 glob 实测只扫到 38/53，故用 rglob。
    """
    root = Path(root)
    metas: list[MetaApp] = []
    for manifest_file in sorted(root.glob("mcpserver/**/agent-manifest.json")):
        data = json.loads(manifest_file.read_text(encoding="utf-8"))
        metas.append(convert_manifest_to_meta(data))
    return metas


# ---- 分类标签过滤查询（卷180-B 加载侧消费）----
#
# 语义（与 docs/总线能力标签体系-2026-09-29.md 一致）：
#   families：族/干什么——**交集非空**即命中（一个能力可属多族）
#   domains ：域/谁用——交集非空即命中；`domains=()` 的能力表示**跨领域通用**，
#             查询 domains 时默认不返回它们（要通用件用 include_generic=True）
#   tiers   ：谁能开——**精确匹配** app.tier（单值）
#   origins ：怎么来的——按 origin.kind 精确匹配（native/bridge/...）
# 所有参数可组合（AND 语义）；空参数 = 不参与过滤。


def filter_apps(
    apps: Iterable[MetaApp],
    *,
    families: Iterable[str] | None = None,
    domains: Iterable[str] | None = None,
    tier: str | None = None,
    origin_kind: str | None = None,
    include_generic: bool = False,
) -> list[MetaApp]:
    """按分类标签过滤 MetaApp（AND 组合）。

    include_generic：domains 过滤时是否把「跨领域通用」（domains 为空）的能力
    一并返回（缺省 False——通用件请显式索取）。
    """
    fam = set(families) if families else None
    dom = set(domains) if domains else None
    out: list[MetaApp] = []
    for app in apps:
        if fam is not None and not (set(app.families) & fam):
            continue
        if dom is not None:
            app_dom = set(app.domains)
            if app_dom:
                if not (app_dom & dom):
                    continue
            elif not include_generic:
                continue
        if tier is not None and app.tier != tier:
            continue
        if origin_kind is not None and str((app.origin or {}).get("kind") or "") != origin_kind:
            continue
        out.append(app)
    return out


def by_tier(apps: Iterable[MetaApp], tier: str) -> list[MetaApp]:
    """便捷：按 tier 精确查询（谁能开）。"""
    return filter_apps(apps, tier=tier)


def by_family(apps: Iterable[MetaApp], family: str) -> list[MetaApp]:
    """便捷：按族查询（干什么）。"""
    return filter_apps(apps, families=[family])


def by_domain(apps: Iterable[MetaApp], domain: str, *, include_generic: bool = False) -> list[MetaApp]:
    """便捷：按域查询（谁用）；include_generic 可并入跨领域通用件。"""
    return filter_apps(apps, domains=[domain], include_generic=include_generic)


def summarize_labels(apps: Iterable[MetaApp]) -> dict[str, list[str]]:
    """标签清单汇总：families/domains/tiers/origins → 各自出现的能力名（报告与对照表用）。"""
    out: dict[str, set[str]] = {"families": set(), "domains": set(), "tiers": set(), "origins": set()}
    for app in apps:
        out["families"].update(app.families)
        out["domains"].update(app.domains)
        if app.tier:
            out["tiers"].add(app.tier)
        kind = str((app.origin or {}).get("kind") or "")
        if kind:
            out["origins"].add(kind)
    return {k: sorted(v) for k, v in out.items()}
