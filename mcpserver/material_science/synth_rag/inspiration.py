"""灵感素材检索（工单 237 任务一：索引层）。

定位（工单 237 §1/§6）：**检索给候选、agent 拿 abstract 自查**；不做真伪判定
（`target` 句是 LLM 联想结果，偏差已实测，自动化裁决留给工单 238）。

打分口径：复用 ``retrieve`` 的轻量词元重合（英文词 + CJK 二元组），
**不引向量 DB**。工单原文写"内部走 embedding + cosine"与本仓实况不符——
`retrieve.py` 既有逻辑即词元重合，本模块沿用之（见 docs/inspiration_index.md「口径说明」）。
"""
from __future__ import annotations

from .retrieve import _match_score
from .schema import InspirationItem
from .store import THEME_DIRS, inspiration_theme_path, load_inspiration_pool

# 主题池缓存：全量索引 ~4.3MB，避免每次检索重复解析（key = "root::theme"）
_POOL_CACHE: dict[str, list[InspirationItem]] = {}


def available_themes() -> list[str]:
    """已知主题列表（biomass / sdr / agent / esp32 / other）。"""
    return sorted(THEME_DIRS)


def _present_themes(root: str | None) -> list[str]:
    """实际带 index.json 的主题（无 theme 检索时用，容忍某主题缺料）。"""
    return [th for th in available_themes()
            if (inspiration_theme_path(th, root) / "index.json").is_file()]


def load_pool(theme: str, root: str | None = None, use_cache: bool = True) -> list[InspirationItem]:
    """加载（并缓存）某主题的素材池。``root`` 变化时按新键缓存。"""
    key = f"{root or ''}::{theme}"
    if use_cache and key in _POOL_CACHE:
        return _POOL_CACHE[key]
    items = load_inspiration_pool(inspiration_theme_path(theme, root))
    if use_cache:
        _POOL_CACHE[key] = items
    return items


def clear_cache() -> None:
    """清空主题池缓存（测试用；素材更新后也应调用）。"""
    _POOL_CACHE.clear()


def _score(query: str, item: InspirationItem) -> float:
    """条目可检索文本 = target / abstract / match 三字段取最高分。"""
    return max(
        _match_score(query, item.target),
        _match_score(query, item.abstract),
        _match_score(query, item.match),
    )


def search_inspiration(query: str, top_k: int = 10, theme: str | None = None,
                       root: str | None = None) -> list[InspirationItem]:
    """按词元重合检索灵感素材，返回前 ``top_k`` 条。

    Args:
        query: 查询串（中文/英文皆可）
        top_k: 返回条数上限（负数按 0 处理）
        theme: 限定主题（biomass/sdr/agent/esp32/other）；``None`` 表示全主题合并检索
                （只遍历实际带 index.json 的主题）
        root: 语料根目录覆盖（测试用）；``None`` 用仓内默认落点

    Returns:
        分数降序的 ``InspirationItem`` 列表；同分按 composite 降序、pid 升序（稳定）。
    """
    if not query or not query.strip():
        return []
    themes = [theme] if theme is not None else _present_themes(root)
    scored: list[tuple[float, float, str, InspirationItem]] = []
    for th in themes:
        for item in load_pool(th, root=root):
            s = _score(query, item)
            if s > 0:
                scored.append((s, item.composite, item.pid, item))
    scored.sort(key=lambda x: (-x[0], -x[1], x[2]))
    return [it for _, _, _, it in scored[: max(top_k, 0)]]
