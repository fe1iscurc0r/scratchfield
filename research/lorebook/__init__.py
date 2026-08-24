"""Lorebook 知识注入管线（授粉-A2）。

参考 airi character_book 机制（MIT，
github_haul/fusion/airi/packages/ccc/src/codec/characterCardV3.ts）。
命中触发词时把对应知识条目注入上下文，闲聊时零负载（返回空串）。
"""

from research.lorebook.lorebook import (
    Lorebook,
    LorebookEntry,
    lorebook_section_for,
    load_lorebook,
)

__all__ = ["Lorebook", "LorebookEntry", "load_lorebook", "lorebook_section_for"]
