"""Lorebook 构建器：从 vault/ 知识条目生成 characters/陆墨/lorebook.json。

用法：``python -m research.lorebook.build_lorebook``
数据源是 vault/ 下的 md 原文（整篇嵌入 content），改 vault 后重跑即可再生。
"""

from __future__ import annotations

import json
import os
import sys

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), *([os.pardir] * 2)))
VAULT = os.path.join(REPO_ROOT, "vault")
OUT_PATH = os.path.join(REPO_ROOT, "characters", "陆墨", "lorebook.json")

# 条目定义：name / vault 相对路径 / keys 触发词 / 其余 characterBookEntry 字段
ENTRIES = [
    {
        "name": "木质素",
        "vault": os.path.join("01-材料库", "前驱体", "木质素.md"),
        "keys": ["木质素", "木素", "lignin"],
        "priority": 10,
        "insertion_order": 0,
    },
    {
        "name": "导电水凝胶",
        "vault": os.path.join("01-材料库", "复合材料", "导电水凝胶.md"),
        "keys": ["水凝胶", "导电水凝胶", "hydrogel"],
        "priority": 10,
        "insertion_order": 1,
    },
]


def _read_vault(rel: str) -> str:
    path = os.path.join(VAULT, rel)
    with open(path, encoding="utf-8") as f:
        return f.read().strip()


def build() -> dict:
    entries = []
    for i, spec in enumerate(ENTRIES):
        entries.append(
            {
                "id": i,
                "name": spec["name"],
                "keys": spec["keys"],
                "content": _read_vault(spec["vault"]),
                "enabled": True,
                "insertion_order": spec["insertion_order"],
                "use_regex": False,
                "case_sensitive": False,
                "constant": False,
                "priority": spec["priority"],
                "selective": False,
                "secondary_keys": [],
                "position": "after_char",
                "extensions": {"vault_source": spec["vault"]},
                "comment": "由 research/lorebook/build_lorebook.py 从 vault 生成",
            }
        )
    return {
        "name": "陆墨材料知识库",
        "description": "vault/ 材料知识条目的 Lorebook 化：命中触发词注入，闲聊零负载。",
        "extensions": {},
        "entries": entries,
    }


def main() -> int:
    book = build()
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(book, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"OK: {len(book['entries'])} 条目 -> {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
