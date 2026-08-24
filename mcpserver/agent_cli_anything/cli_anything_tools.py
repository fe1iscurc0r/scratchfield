"""CLI-Anything 能力封装：本地注册表 / 矩阵能力数据查询。

上游: HKUDS/CLI-Anything（仓库根 LICENSE 为 Apache-2.0；cli-hub 包 setup.py 声明 MIT）。
本模块不联网、不安装任何 CLI，只读 vendor checkout 里的 registry.json /
public_registry.json / matrix_registry.json，把 `cli-hub list --json` 与
`cli-hub can <query>` 两个能力暴露为结构化工具。
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

_SCRATCHPAD_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CLI_ANYTHING_ROOT = _SCRATCHPAD_ROOT.parent / "github_haul" / "software" / "CLI-Anything"


def _cli_anything_root() -> Path:
    """返回 CLI-Anything checkout 根目录（可用环境变量覆盖，避免硬编码绝对路径）。"""
    override = os.environ.get("CLI_ANYTHING_ROOT")
    if override:
        return Path(override)
    return _DEFAULT_CLI_ANYTHING_ROOT


def _read_json(*parts: str) -> dict[str, Any] | None:
    path = _cli_anything_root().joinpath(*parts)
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _load_clis() -> list[dict[str, Any]]:
    """合并 harness 注册表与 public 注册表，每条打 _source 标记。"""
    entries: list[dict[str, Any]] = []
    for filename, source in (("registry.json", "harness"), ("public_registry.json", "public")):
        data = _read_json(filename)
        if not isinstance(data, dict):
            continue
        for cli in data.get("clis", []):
            if not isinstance(cli, dict):
                continue
            entry = dict(cli)
            entry["_source"] = source
            entries.append(entry)
    return entries


def _summarize_cli(cli: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": cli.get("name", ""),
        "display_name": cli.get("display_name", ""),
        "version": cli.get("version", ""),
        "description": cli.get("description", ""),
        "category": cli.get("category", "uncategorized"),
        "source": cli.get("_source", "harness"),
        "entry_point": cli.get("entry_point", ""),
        "install_cmd": cli.get("install_cmd", ""),
        "package_manager": cli.get("package_manager", ""),
        "npm_package": cli.get("npm_package", ""),
        "homepage": cli.get("homepage", ""),
        "skill_md": cli.get("skill_md", ""),
        "requires": cli.get("requires", ""),
    }


def list_cli_tools(
    category: str | None = None,
    source: str | None = None,
    query: str | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    """列出 CLI-Anything 可用 CLI 工具（等价 `cli-hub list --json`）。

    参数：
    - category: 按分类过滤（image / 3d / video / audio / office / ai ...）
    - source: harness（官方 harness）/ public（第三方）/ all
    - query: 按 name / display_name / description / category 模糊搜索
    - limit: 限制返回条数
    """
    entries = _load_clis()

    if category:
        entries = [e for e in entries if str(e.get("category", "")).lower() == str(category).lower()]
    if source and str(source).lower() != "all":
        entries = [e for e in entries if e.get("_source") == str(source).lower()]
    if query:
        q = str(query).lower()
        entries = [
            e for e in entries
            if q in " ".join(str(e.get(k, "")) for k in ("name", "display_name", "description", "category")).lower()
        ]
    if limit is not None:
        try:
            entries = entries[: int(limit)]
        except (TypeError, ValueError):
            pass

    tools = [_summarize_cli(e) for e in entries]
    categories = sorted({str(e.get("category", "uncategorized")) for e in _load_clis()})
    return {
        "status": "success",
        "message": f"共 {len(tools)} 个 CLI 工具",
        "data": {"tools": tools, "total": len(tools), "categories": categories},
    }


def _capability_match_field(cap: dict[str, Any], query_lower: str) -> str | None:
    if query_lower in str(cap.get("id", "")).lower():
        return "id"
    if query_lower in str(cap.get("intent", "")).lower():
        return "intent"
    if any(query_lower in str(hint).lower() for hint in cap.get("skill_search_hints", [])):
        return "hint"
    for provider in cap.get("providers", []):
        if query_lower in str(provider.get("name", "")).lower():
            return "provider"
    return None


def _summarize_provider(provider: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": provider.get("name", ""),
        "kind": provider.get("kind", ""),
        "cost_tier": provider.get("cost_tier", "unknown"),
        "quality_tier": provider.get("quality_tier", "unknown"),
        "offline": bool(provider.get("offline")),
        "requires": provider.get("requires") or {},
        "install_hint": provider.get("install_hint", ""),
    }


def search_capabilities(query: str | None = None) -> dict[str, Any]:
    """跨矩阵搜索能力（等价 `cli-hub can <query>`）。

    命中字段：capability id / intent / skill_search_hints / provider name。
    """
    if not query or not str(query).strip():
        return {"status": "error", "message": "缺少 query 参数", "data": {}}

    data = _read_json("matrix_registry.json")
    if not isinstance(data, dict):
        return {"status": "error", "message": "无法加载 matrix_registry.json（vendor checkout 缺失）", "data": {}}

    query_lower = str(query).lower()
    hits: list[dict[str, Any]] = []
    for matrix in data.get("matrices", []):
        if not isinstance(matrix, dict):
            continue
        for cap in matrix.get("capabilities", []):
            if not isinstance(cap, dict):
                continue
            field = _capability_match_field(cap, query_lower)
            if not field:
                continue
            hits.append({
                "matrix": matrix.get("name", ""),
                "matrix_id": matrix.get("matrix_id", ""),
                "capability_id": cap.get("id", ""),
                "intent": cap.get("intent", ""),
                "match_field": field,
                "providers": [_summarize_provider(p) for p in cap.get("providers", []) if isinstance(p, dict)],
            })

    return {
        "status": "success",
        "message": f"匹配到 {len(hits)} 个能力",
        "data": {"query": query, "matched_capabilities": hits, "total": len(hits)},
    }
