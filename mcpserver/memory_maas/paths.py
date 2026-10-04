"""路径归一化 — 注入检索三形式等价匹配（03-02，claude-mem #2691 坑）。

claude-mem #2691：记忆以某一种路径写法（如绝对路径）落库后，用另一种写法
（相对路径 / 项目根相对）检索只有 1/3 命中率。对策：查询路径同时生成
绝对 / 相对(cwd) / 项目根 三种归一化形式参与匹配，任何一种命中即算命中。

归一化规则：
- 分隔符统一为 ``/``（Windows ``\\`` 与 POSIX 互认）；
- 去尾部分隔符、去 ``.`` 段；
- SQLite LIKE 对 ASCII 天然大小写不敏感（Windows 盘符大小写差异被覆盖）；
- relpath 越界（跨盘符 / 不在子树内）时静默跳过该形式。

纯标准库 pathlib/os，无第三方依赖。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

# 默认项目根 = 仓根 scratchpad/（paths.py 位于 mcpserver/memory_maas/ 下）
DEFAULT_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def normalize_separators(p: str) -> str:
    """统一分隔符为 /，去尾分隔符与 . 段（不做大小写折叠——LIKE 已覆盖）。"""
    s = str(p or "").strip().replace("\\", "/")
    while "//" in s:
        s = s.replace("//", "/")
    parts = [seg for seg in s.split("/") if seg not in ("", ".")]
    # 保留前导 /（POSIX 绝对路径语义）；Windows 盘符段原样保留
    prefix = "/" if s.startswith("/") else ""
    return prefix + "/".join(parts)


def _try_relpath(target: str, start: str) -> str | None:
    """os.path.relpath 的容错包装：越界/跨盘/异常返回 None。"""
    try:
        rel = os.path.relpath(target, start)
    except (ValueError, OSError):  # Windows 跨盘符等
        return None
    if rel.startswith(".."):  # 不在子树内，该形式无意义
        return None
    return normalize_separators(rel)


def path_variants(path: str,
                  project_root: str | Path | None = None) -> list[str]:
    """查询路径 → 三形式归一化列表（绝对 / 项目根相对 / cwd 相对，去重保序）。

    绝对形式：输入本身（POSIX 风格原样保留）+ abspath（可解析时）；
    项目根相对：abspath 相对 project_root（默认仓根）；
    cwd 相对：abspath 相对当前工作目录（与项目根相同则不重复给）。
    """
    raw = normalize_separators(path)
    if not raw:
        return []
    variants: list[str] = []
    absform = raw
    # Windows 主机上把 POSIX 风格输入原样保留（不强行 abspath 语义漂移）
    if not raw.startswith("/"):
        winish = bool(os.path.splitdrive(raw)[0])
        if not winish:
            absform = normalize_separators(os.path.abspath(raw))
    if absform not in variants:
        variants.append(absform)
    root = Path(project_root) if project_root else DEFAULT_PROJECT_ROOT
    root_rel = _try_relpath(absform, str(root))
    if root_rel and root_rel not in variants:
        variants.append(root_rel)
    cwd_rel = _try_relpath(absform, os.getcwd())
    if cwd_rel and cwd_rel not in variants:
        variants.append(cwd_rel)
    return variants


def path_like_patterns(path: str,
                       project_root: str | Path | None = None) -> list[str]:
    """三形式 → SQL LIKE 模式（%variant% 子串匹配，供 content/tags 列）。"""
    return [f"%{v}%" for v in path_variants(path, project_root)]


def paths_match(text: str, path: str,
                project_root: str | Path | None = None) -> bool:
    """Python 层等价判定：text 中是否出现任一形式（大小写不敏感子串）。"""
    t = (text or "").lower()
    return any(v.lower() in t for v in path_variants(path, project_root))


def variants_or_patterns(text_or_path: str, patterns: Iterable[str]) -> bool:
    """LIKE 语义的 Python 复算（测试对账用）。"""
    t = (text_or_path or "").lower()
    return any(str(p).strip("%").lower() in t for p in patterns)


__all__ = [
    "DEFAULT_PROJECT_ROOT",
    "normalize_separators",
    "path_like_patterns",
    "path_variants",
    "paths_match",
    "variants_or_patterns",
]
