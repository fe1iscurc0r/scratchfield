"""Lorebook 核心：条目匹配与注入段构建。

语义对齐 airi character_book（MIT）：
- keys 触发词命中即注入；``use_regex`` 时按正则匹配，否则大小写不敏感的子串匹配
- ``selective`` 条目要求 keys 与 secondary_keys 同时命中
- ``constant`` 条目无条件注入
- 命中多条时按 ``priority`` 降序、``insertion_order`` 升序排列
- 未命中任何条目时返回空串 —— 闲聊零负载
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from typing import Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir, os.pardir))
DEFAULT_LOREBOOK_PATH = os.path.join(REPO_ROOT, "characters", "陆墨", "lorebook.json")


class LorebookEntry(BaseModel):
    """单条 Lorebook 知识条目（字段对齐 characterBookEntrySchema）。"""

    model_config = ConfigDict(extra="allow")

    keys: list[str] = Field(default_factory=list, description="触发词列表。")
    content: str = Field(default="", description="命中后注入的知识内容。")
    enabled: bool = True
    insertion_order: int = 0
    use_regex: bool = False
    case_sensitive: bool = False
    constant: bool = False
    id: Optional[Union[int, str]] = None
    name: Optional[str] = None
    comment: Optional[str] = None
    priority: int = 0
    selective: bool = False
    secondary_keys: list[str] = Field(default_factory=list)
    position: Literal["before_char", "after_char"] = "after_char"

    def matches(self, text: str) -> bool:
        """判断文本是否命中本条目。"""
        if not self.enabled:
            return False
        if self.constant:
            return True
        if not self._any_key_hits(text, self.keys):
            return False
        if self.selective and self.secondary_keys:
            return self._any_key_hits(text, self.secondary_keys)
        return True

    def _any_key_hits(self, text: str, keys: list[str]) -> bool:
        if not keys:
            return False
        haystack = text if self.case_sensitive else text.lower()
        for key in keys:
            if not key:
                continue
            if self.use_regex:
                flags = 0 if self.case_sensitive else re.IGNORECASE
                try:
                    if re.search(key, text, flags):
                        return True
                except re.error:
                    logger.warning("Lorebook 条目 %r 正则非法: %r", self.name, key)
                continue
            if (key if self.case_sensitive else key.lower()) in haystack:
                return True
        return False


class Lorebook(BaseModel):
    """整本 Lorebook（字段对齐 characterBookSchema）。"""

    model_config = ConfigDict(extra="allow")

    name: Optional[str] = None
    description: Optional[str] = None
    scan_depth: Optional[int] = None
    token_budget: Optional[int] = None
    recursive_scanning: Optional[bool] = None
    extensions: dict = Field(default_factory=dict)
    entries: list[LorebookEntry] = Field(default_factory=list)

    @classmethod
    def from_any(cls, payload: dict) -> "Lorebook":
        """兼容三种输入：character_book 本体 / CCv3 完整卡片 / {"entries": [...]}。"""
        if "data" in payload and isinstance(payload.get("data"), dict):
            payload = payload["data"].get("character_book") or {}
        return cls.model_validate(payload)

    def scan(self, text: str) -> list[LorebookEntry]:
        """返回命中的条目，按 priority 降序、insertion_order 升序。"""
        hits = [e for e in self.entries if e.matches(text)]
        return sorted(hits, key=lambda e: (-e.priority, e.insertion_order))

    def build_section(self, text: str) -> str:
        """构建注入段。未命中返回空串（闲聊零负载）。"""
        hits = self.scan(text)
        if not hits:
            return ""
        parts = ["【知识库命中 · Lorebook】"]
        for entry in hits:
            title = entry.name or (entry.keys[0] if entry.keys else "未命名条目")
            parts.append(f"### {title}\n{entry.content.strip()}")
        return "\n\n".join(parts)


def load_lorebook(path: str | None = None) -> Lorebook | None:
    """从 json 文件加载 Lorebook；文件不存在返回 None（fail-fast 由调用方决定）。"""
    target = path or DEFAULT_LOREBOOK_PATH
    if not os.path.exists(target):
        return None
    with open(target, encoding="utf-8") as f:
        return Lorebook.from_any(json.load(f))


_cache_lock = threading.Lock()
_cache: dict[str, tuple[float, Lorebook | None]] = {}


def lorebook_section_for(text: str, path: str | None = None) -> str:
    """对话注入入口：命中返回知识段，未命中/加载失败返回空串。

    聊天主链路调用，加载失败只告警不抛错（Lorebook 是增强项不是必需项）；
    按文件 mtime 缓存，改 lorebook.json 后无需重启即生效。
    """
    target = path or DEFAULT_LOREBOOK_PATH
    try:
        mtime = os.path.getmtime(target)
    except OSError:
        return ""
    with _cache_lock:
        cached = _cache.get(target)
        if cached is None or cached[0] != mtime:
            try:
                book = load_lorebook(target)
            except Exception as e:  # noqa: BLE001 - 聊天链路容错边界
                logger.warning("Lorebook 加载失败 %s: %s", target, e)
                book = None
            _cache[target] = (mtime, book)
            cached = _cache[target]
    book = cached[1]
    if book is None:
        return ""
    return book.build_section(text)
