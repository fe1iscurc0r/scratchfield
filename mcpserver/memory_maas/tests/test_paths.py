"""03-02 多路径匹配验收测试（claude-mem #2691 坑）。

跑法: python -m pytest mcpserver/memory_maas/tests/test_paths.py -q
覆盖：三形式归一化（绝对/项目根相对/cwd 相对）/ 同一记忆三种路径写法检索
等价命中 / tags 落库路径同样等价 / 未命中不误报 / POSIX 风格输入容错。
"""
from __future__ import annotations

import pytest

from mcpserver.memory_maas.entities import TypedMemoryStore
from mcpserver.memory_maas.paths import (
    normalize_separators,
    path_like_patterns,
    path_variants,
    paths_match,
)


@pytest.fixture
def store(tmp_path):
    s = TypedMemoryStore(tmp_path / "e.db")
    yield s
    s.close()


@pytest.fixture
def proj(tmp_path, monkeypatch):
    """伪项目根 + cwd 切换（三形式可预期的沙箱环境）。"""
    root = tmp_path / "proj"
    (root / "src").mkdir(parents=True)
    monkeypatch.chdir(root)
    return root


def _abs(proj) -> str:
    """proj 下某文件的正斜杠绝对路径（测试输入用）。"""
    return (proj / "src" / "main.py").resolve().as_posix()


# ---------------------------------------------------------------- 归一化

def test_normalize_separators_unifies_slashes():
    assert normalize_separators("a\\\\b//c/.\\") == "a/b/c"
    assert normalize_separators("/home//neko/./x/") == "/home/neko/x"
    assert normalize_separators("D:\\proj\\src") == "D:/proj/src"


def test_path_variants_contains_three_forms(proj):
    abs_path = _abs(proj)
    vs = path_variants(abs_path, project_root=proj)
    # 绝对 / 项目根相对 / cwd 相对（cwd==项目根时后两者去重合一）
    assert abs_path in vs                   # 绝对形式
    assert "src/main.py" in vs              # 项目根相对（= cwd 相对）
    assert len(vs) == 2


def test_path_variants_dedup_when_cwd_differs_from_root(proj, monkeypatch):
    monkeypatch.chdir(proj / "src")
    abs_path = _abs(proj)
    vs = path_variants(abs_path, project_root=proj)
    assert abs_path in vs                # 绝对
    assert "src/main.py" in vs           # 项目根相对
    assert "main.py" in vs               # cwd 相对（比项目根相对更短）
    assert len(vs) == 3


def test_path_variants_out_of_subtree_skipped(proj):
    # 不在项目根子树内的路径：只给绝对形式，不硬造 .. 相对形式
    other = (proj.parent / "elsewhere" / "x.py").as_posix()
    vs = path_variants(other, project_root=proj)
    assert vs == [other]


def test_like_patterns_wrap_percent(proj):
    pats = path_like_patterns(_abs(proj), project_root=proj)
    assert all(p.startswith("%") and p.endswith("%") for p in pats)


# ---------------------------------------------------------------- 三写法等价检索

def _seed_memory(store, proj):
    # 落库写法：绝对路径写在 content 里（模拟观察记录）
    return store.add(f"修复了 {_abs(proj)} 的越界 bug",
                     type="insight", tags=["proj"])


def test_same_memory_hit_by_all_three_path_forms(store, proj):
    eid = _seed_memory(store, proj)
    for query_path in (_abs(proj),                     # 绝对（与落库同形）
                       "src/main.py",                  # 项目根相对
                       (proj / "src" / "main.py").as_posix().replace(
                           "/", "\\")):                # 反斜杠原始写法
        hits = store.list_entities(path=query_path, project_root=proj)
        assert [e["id"] for e in hits] == [eid], f"查询 {query_path!r} 未命中"


def test_path_hit_via_tags_column(store, proj):
    # 落库写法：路径在 tags 里（file: 前缀标签惯例）
    eid = store.add("主入口改动了", tags=["file:src/main.py"])
    hits = store.list_entities(path="src/main.py", project_root=proj)
    assert [e["id"] for e in hits] == [eid]


def test_unrelated_path_no_hit(store, proj):
    _seed_memory(store, proj)
    hits = store.list_entities(path="src/other.py", project_root=proj)
    assert hits == []


def test_path_filter_composes_with_type_filter(store, proj):
    eid = _seed_memory(store, proj)
    store.add("无关决策", type="decision",
              tags=["file:src/main.py"])  # 同路径但不同 type
    hits = store.list_entities(type="insight", path="src/main.py",
                               project_root=proj)
    assert [e["id"] for e in hits] == [eid]


def test_paths_match_python_level(proj):
    assert paths_match(f"见 {_abs(proj)} 第 10 行", "src/main.py",
                       project_root=proj)
    assert not paths_match("无路径内容", "src/main.py", project_root=proj)


def test_posix_style_input_tolerated(store, proj):
    # POSIX 风格输入在 Windows 主机上不崩、按字符串形式参与匹配
    stored = _seed_memory(store, proj)
    hits = store.list_entities(path=_abs(proj), project_root=proj)
    assert [e["id"] for e in hits] == [stored]


# ---------------------------------------------------------------- core 集成

def test_core_query_by_path(tmp_path):
    from mcpserver.memory_maas.core import MemoryMaasCore
    core = MemoryMaasCore(tmp_path)
    try:
        eid = core.add_memory("改动了 D:/my git/scratchpad/mcpserver/core.py",
                              type="note")["id"]
        r = core.query(path="mcpserver/core.py")  # 项目根相对写法命中
        assert eid in [e["id"] for e in r["entities"]]
        assert r["count"] == 1
    finally:
        core.close()
