"""上游 KiCAD-MCP-Server 的能力地图（工单245 的「接入 agent 线」对照面）。

工单 §1 说「把 `mixelpixx/KiCAD-MCP-Server`（MIT）的 `mcp` 能力接入 `agent` 线」。
上游那 244 个工具**不可能**也不该被搬进本仓（依赖 KiCAD 运行时 + `kicad-python` IPC，
且作者已另起 Konnect）。可搬、且真有用的是**能力目录本身**：让 agent 线在不读上游源码的情况下知道
「上游能做哪些事、哪一类、叫什么」，从而 (a) 决定要不要装上游、(b) 把本模块的离线能力与上游工具对上号。

数据来源与口径
--------------
夹具 `tests/fixtures/upstream_capabilities.json` 由上游 `src/tools/registry.ts` 的
`toolCategories` 与 `directToolNames` **机械抽取**（MIT，出处写在夹具里）。
它覆盖的是上游 README 所称的 **indexed 184**（17 类别 / routed 159 + direct 32 / distinct 184），
**不是** registered 244 —— 后者不在该文件内，本模块**不猜**，只在 `stats()` 里如实说明。

搜索语义**逐条移植**上游 `searchTools()`（含它的两个怪癖，刻意保留以便行为一致）：
① `direct` 工具优先排在前面；
② 命中**类别名或类别描述**时，该类别下**所有**工具都算命中；
③ 结果上限 **20** 条。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

_FIXTURE = Path(__file__).resolve().parent / "tests" / "fixtures" / "upstream_capabilities.json"

#: 与上游一致的返回上限
SEARCH_LIMIT = 20


@dataclass
class SearchResult:
    """一条搜索结果（字段名与上游 ``SearchResult`` 一致）。"""

    category: str
    tool: str
    description: str

    def as_dict(self) -> dict:
        return {"category": self.category, "tool": self.tool, "description": self.description}


class CapabilityMap:
    """上游能力目录的只读视图。"""

    def __init__(self, data: dict, *, path: str = "") -> None:
        self._data = data
        self.path = path
        self.categories: list[dict] = list(data.get("categories", []))
        self.direct_tools: list[str] = list(data.get("direct_tools", []))
        self.distinct_tools: list[str] = list(data.get("distinct_tools", []))
        self._cat_map: dict[str, str] = {}
        for c in self.categories:
            for t in c["tools"]:
                self._cat_map.setdefault(t, c["name"])

    # ---------------------------------------------------------------- 构造
    @classmethod
    def load(cls, path: str | Path | None = None) -> CapabilityMap:
        p = Path(path) if path else _FIXTURE
        return cls(json.loads(p.read_text(encoding="utf-8")), path=str(p))

    # ---------------------------------------------------------------- 查询
    def stats(self) -> dict:
        c = self._data.get("counts", {})
        return {
            "source_repo": self._data.get("source_repo"),
            "source_ref": self._data.get("source_ref"),
            "license": self._data.get("license"),
            "fetched_at": self._data.get("fetched_at"),
            "categories": c.get("categories", len(self.categories)),
            "routed_tools": c.get("routed"),
            "direct_tools": c.get("direct", len(self.direct_tools)),
            "distinct_indexed_tools": c.get("distinct", len(self.distinct_tools)),
            "covers": "上游 README 所称的 indexed 184（registered 244 不在 registry.ts 内，未覆盖）",
            "provenance": self._data.get("provenance", ""),
        }

    def category_names(self) -> list[str]:
        return [c["name"] for c in self.categories]

    def tools_of(self, category: str) -> list[str]:
        for c in self.categories:
            if c["name"] == category:
                return list(c["tools"])
        return []

    def category_of(self, tool: str) -> str | None:
        """移植上游 ``getToolCategory``（direct 工具在上游没有类别）。"""
        if tool in self.direct_tools:
            return "direct"
        return self._cat_map.get(tool)

    def search(self, query: str, *, limit: int = SEARCH_LIMIT) -> list[SearchResult]:
        """移植上游 ``searchTools``（含其 20 条上限与「整类命中」语义）。"""
        q = (query or "").lower()
        out: list[SearchResult] = []
        if not q:
            return out
        for name in self.direct_tools:                       # ① direct 优先
            if q in name.lower():
                out.append(SearchResult("direct", name,
                                        f"{name} (direct tool — call directly by name)"))
        for cat in self.categories:
            cat_match = q in cat["name"].lower() or q in cat.get("description", "").lower()
            for name in cat["tools"]:                        # ② 整类命中
                if q in name.lower() or cat_match:
                    out.append(SearchResult(cat["name"], name, f"{name} ({cat['name']})"))
        return out[:limit]                                   # ③ 上限

    def compare_with(self, our_tools: list[str]) -> dict:
        """与**本仓**工具集做能力对照（名字层面的客观交并，不做语义猜测）。"""
        ours = {t for t in our_tools}
        theirs = set(self.distinct_tools)
        return {
            "ours": len(ours),
            "upstream_indexed": len(theirs),
            "shared_names": sorted(ours & theirs),
            "upstream_only_count": len(theirs - ours),
            "ours_only_count": len(ours - theirs),
            "upstream_categories": self.category_names(),
        }


@lru_cache(maxsize=1)
def default_map() -> CapabilityMap:
    """进程内缓存的默认能力地图（夹具只读，缓存安全）。"""
    return CapabilityMap.load()
