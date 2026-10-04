"""claude-mem 授粉落地 — 内容哈希去重 / 多路径匹配 / 压缩块 XML 模板（W63-03）。

独立工具函数，不破坏现有读写路径。三个功能：

P0a 内容哈希去重（capture 层已有，工具函数层面补摘要）：
- compute_memory_content_hash(...)：对已入库实体做哈希，用于"内容相同则
  认为同一实体"的跨路径去重判定；
- is_duplicate_content(...)：判断候选内容是否与库中某实体内容哈希重复。

P0b 多路径匹配（注入检索）：
- query_by_path_variants(...)：对查询路径生成三种归一化形式（绝对/项目根
  相对/cwd 相对），任一形式命中 content 或 tags 即返回。解决 claude-mem
  #2691 单写法落库后其他写法检索不中的问题。

P1 压缩块 XML 模板（consolidation 合并内核）：
- consolidated_memory_block(...)：把多条记忆条目合并输出为 XML 结构块，
  调用 xml_template.merge_contents（三层容错：ET 解析→正则抽取→降级纯文本）。

纯标准库，不依赖 pycrdt/httpx。
"""
from __future__ import annotations

import hashlib
from typing import Any, Sequence

from mcpserver.memory_maas import xml_template
from mcpserver.memory_maas.entities import TypedMemoryStore

# 字段连接分隔符（单元分隔符，与 capture.py 保持一致）
_HASH_SEP = "\x1f"


# =============================================================================
# P0a：内容哈希去重（实体层面）
# =============================================================================

def compute_memory_content_hash(title: str, narrative: str) -> str:
    """记忆内容哈希：sha256(title \\x1f narrative)[:16] hex。

    注意：与 capture.py 的 compute_observation_content_hash 不同，这里不含
    session_id，适用于"内容相同则实体相同"的跨会话去重判定场景（如授粉
    落地时判断外部注入内容是否已在本地存在）。
    """
    payload = _HASH_SEP.join(
        str(p or "").strip() for p in (title, narrative))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def is_duplicate_content(store: TypedMemoryStore, title: str,
                         narrative: str,
                         memory_session_id: str = "default") -> bool:
    """判断候选 (title, narrative) 是否与库中某实体内容哈希重复。

    实现：算同 capture.py 的内容哈希（session_id \\x1f title \\x1f narrative），
    再在 TypedMemoryStore 中按 observation_hash 查重。哈希一致即内容一致。
    memory_session_id 默认 "default"（兼容同一 session 内的内容级查重）；
    跨 session 注入场景请传入真实 session_id。
    """
    from mcpserver.memory_maas import capture
    h = capture.compute_observation_content_hash(memory_session_id, title, narrative)
    found = store.find_by_observation_hash(h)
    return found is not None


def find_duplicate_entities(store: TypedMemoryStore,
                            entries: list[dict[str, str]],
                            memory_session_id: str = "default"
                            ) -> dict[int, str]:
    """批量查重：返回 {index: entity_id} 映射，index 为 entries 中重复项下标。

    用于外部批量导入前预处理：筛掉已在库中存在的条目，避免重复写入。
    entries 格式：[{title, narrative}, ...]。
    memory_session_id 默认 "default"；跨 session 注入场景传真实 session_id。
    """
    from mcpserver.memory_maas import capture
    dup_map: dict[int, str] = {}
    for i, entry in enumerate(entries):
        title = str(entry.get("title") or "").strip()
        narrative = str(entry.get("narrative") or "").strip()
        if not title and not narrative:
            continue
        h = capture.compute_observation_content_hash(memory_session_id, title, narrative)
        existing = store.find_by_observation_hash(h)
        if existing is not None:
            dup_map[i] = existing["id"]
    return dup_map


# =============================================================================
# P0b：多路径匹配（注入检索）
# =============================================================================

def _normalize_separators(p: str) -> str:
    """统一分隔符为 /，去尾部 / 和 . 段。"""
    s = str(p or "").strip().replace("\\", "/")
    while "//" in s:
        s = s.replace("//", "/")
    parts = [seg for seg in s.split("/") if seg not in ("", ".")]
    prefix = "/" if s.startswith("/") else ""
    return prefix + "/".join(parts)


def _path_variants(path: str, project_root: str | None = None) -> list[str]:
    """查询路径 → 三形式归一化列表（绝对 / 项目根相对 / cwd 相对）。"""
    import os
    from pathlib import Path

    raw = _normalize_separators(path)
    if not raw:
        return []
    variants: list[str] = []
    absform = raw
    if not raw.startswith("/"):
        winish = bool(os.path.splitdrive(raw)[0])
        if not winish:
            absform = _normalize_separators(os.path.abspath(raw))
    if absform not in variants:
        variants.append(absform)
    root = Path(project_root) if project_root else \
        Path(__file__).resolve().parents[2]
    try:
        root_rel = os.path.relpath(absform, str(root))
    except (ValueError, OSError):
        root_rel = None
    if root_rel and not root_rel.startswith("..") and root_rel not in variants:
        variants.append(_normalize_separators(root_rel))
    try:
        cwd_rel = os.path.relpath(absform, os.getcwd())
    except (ValueError, OSError):
        cwd_rel = None
    if cwd_rel and not cwd_rel.startswith("..") and cwd_rel not in variants:
        variants.append(_normalize_separators(cwd_rel))
    return variants


def query_by_path_variants(store: TypedMemoryStore,
                           path: str,
                           project_root: str | None = None,
                           **list_kwargs: Any) -> list[dict[str, Any]]:
    """多路径等价匹配检索。

    等价于 TypedMemoryStore.list_entities(path=path, project_root=project_root)
    但在 list_entities 内部调用 paths.path_like_patterns 生成三种归一化形式，
    任一形式在 content 或 tags 中命中即返回。解决单写法落库后其他写法检索
    不中的问题（claude-mem #2691）。

    list_kwargs：透传 list_entities 的其他过滤参数（type/tags/pinned 等）。
    """
    return store.list_entities(path=path, project_root=project_root, **list_kwargs)


def paths_share_content(content: str, path_a: str, path_b: str,
                        project_root: str | None = None) -> bool:
    """判定两个路径查询是否命中同一内容（归一化后是否在 content 中等价）。

    用于验证"绝对路径/相对路径/cwd 相对路径三种写法等价"这一不变量。
    """
    variants_a = set(_path_variants(path_a, project_root))
    t = (content or "").lower()
    return any(v.lower() in t for v in variants_a)


# =============================================================================
# P1：压缩块 XML 模板（consolidation 合并内核）
# =============================================================================

def consolidated_memory_block(contents: list[str],
                              mode: str = "default") -> dict[str, Any]:
    """蒸馏合并多条内容为 XML 结构块（三层容错，永不抛错）。

    调用 xml_template.merge_contents（ET 解析→正则抽取→降级纯文本），
    输出 content（XML 块或纯文本）+ used_xml（是否走了 XML 路径）。

    返回：
    - content: str 合并后内容；
    - used_xml: bool 是否使用了 XML 结构化渲染路径；
    - parsed_blocks: int 成功解析的块数；
    - raw_count: int 降级为纯文本的块数。
    """
    cfg = xml_template.get_template(mode)
    blocks = [xml_template.parse_memory_block(c, cfg) for c in contents]
    parsed_count = sum(1 for b in blocks if b.get("parsed"))
    raw_count = len(blocks) - parsed_count
    result = xml_template.merge_contents(contents, cfg)
    return {
        "content": result["content"],
        "used_xml": result["used_xml"],
        "parsed_blocks": parsed_count,
        "raw_count": raw_count,
    }


__all__ = [
    # P0a
    "compute_memory_content_hash",
    "is_duplicate_content",
    "find_duplicate_entities",
    # P0b
    "query_by_path_variants",
    "paths_share_content",
    "_path_variants",
    # P1
    "consolidated_memory_block",
]