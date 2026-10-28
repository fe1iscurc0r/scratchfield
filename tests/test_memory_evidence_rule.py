"""「检索频次不得当真值证据」守卫（工单247 落地 · 设计主张借自 LimiNode/agent-memory-cpp）。

## 这条规则的来历

上游 `LimiNode/agent-memory-cpp` 的 README 把一条设计红线写成了一等公民：

> **"Separate storage, retrieval and evidence. ... retrieval frequency does not become
> proof of truth."**

查仓内实况后发现：**这条原则在本仓其实已经实现了** ——
`memory_maas/entities.py` 的 `confidence` 是 **`source_rank`（来源分级）的纯函数**
（`_RANK_CONFIDENCE = {0: 0.9, 1: 0.7, 2: 0.4, 3: 0.2}`，注释写着「供应链铁律：与 origin_rank
同源写时定级，读时确定性投影，可复算可对账」），而 `access_count`（检索/访问频次）
只在 `core.py` 里被**读出展示**、从不参与置信或排序。

⇒ **但它只写在注释里，没有任何闸门**。本文件把这条原则变成**会红的测试**：
一旦有人把检索频次接进置信/排序，或者把 confidence 改成不再由来源分级决定，这里立刻失败。

## 守卫的两层

- **静态层**：`access_count` 在整个 `mcpserver/` 里**只允许出现在白名单的只读展示路径**；
  且**同一行不得出现** `conf/score/rank/weight/sort/key` 之类的语义词。
- **动态层**：`confidence` 必须是 `source_rank` 的**纯函数**，且 provenance 必须同时带
  `origin_rank`（否则无法对账「这个置信度是从哪一级推出来的」）。

## 素材边界

本守卫**只读**，不改 `memory_maas` 任何行为（符合本仓「改了有测试锁着的文件 ⇒ 需显式开关」的纪律；
这里连开关都不需要，因为只是新增断言）。
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from mcpserver.memory_maas.entities import (
    SOURCE_AGENT,
    SOURCE_IMPORTED,
    SOURCE_UNVERIFIED,
    SOURCE_USER,
    TypedMemoryStore,
)

REPO_ROOT = Path(__file__).resolve().parents[1]

#: `access_count` 允许出现的**只读展示路径**白名单。
#: 每条都必须写明「为什么这里是只读展示、不影响置信/排序」。
#: ⚠️ 新增条目等于**放宽一条设计红线** ⇒ 必须在理由里说清它为什么不是「把频次当证据」。
ALLOWED_ACCESS_COUNT_SITES: dict[str, str] = {
    "mcpserver/memory_maas/core.py":
        "index_cards 列表查询把 access_count 读出给调用方展示；该值不回流到任何 score/confidence",
}

#: 出现在**同一行**即视为「可能把频次接进了决策」的语义词
_DECISION_WORDS = re.compile(
    r"conf|score|rank|weight|sort|order\s+by|boost|priority|trust|evidence", re.IGNORECASE)


def _iter_repo_py() -> list[Path]:
    """扫 mcpserver/ 下的 .py（排除 tests —— 测试里出现字符串是正常的）。"""
    out: list[Path] = []
    for p in sorted((REPO_ROOT / "mcpserver").rglob("*.py")):
        rel = p.relative_to(REPO_ROOT).as_posix()
        if "/tests/" in rel or p.name.startswith("test_") or p.name.startswith("conftest"):
            continue
        out.append(p)
    assert out, "扫描范围为空"
    return out


# ============================================================ 静态层


def test_access_count_only_in_allowlisted_read_only_paths():
    """`access_count` 只许出现在白名单文件里。

    ⚠️ 本用例红了**不要**直接往白名单加文件 —— 先问：
    这里读频次是为了**展示**，还是为了**当证据/排序键**？后者就是把红线踩了。
    """
    offenders: list[str] = []
    for p in _iter_repo_py():
        rel = p.relative_to(REPO_ROOT).as_posix()
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if "access_count" in line and rel not in ALLOWED_ACCESS_COUNT_SITES:
                offenders.append(f"{rel}:{i}: {line.strip()[:90]}")
    assert not offenders, (
        "`access_count`（检索/访问频次）出现在白名单之外 —— "
        "检索频次不得成为真值证据：\n  " + "\n  ".join(offenders))


def test_access_count_never_on_a_decision_line():
    """即使在白名单文件里，`access_count` 也**不得与置信/排序语义同现一行**。"""
    bad: list[str] = []
    for rel in ALLOWED_ACCESS_COUNT_SITES:
        p = REPO_ROOT / rel
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if "access_count" not in line:
                continue
            if _DECISION_WORDS.search(line):
                bad.append(f"{rel}:{i}: {line.strip()[:90]}")
    assert not bad, (
        "`access_count` 与置信/排序语义出现在同一行（疑似把频次接进决策）：\n  "
        + "\n  ".join(bad))


def test_allowlist_entries_have_a_stated_reason():
    """白名单每一项都要写清理由 —— 放宽红线必须留痕。"""
    for rel, why in ALLOWED_ACCESS_COUNT_SITES.items():
        assert (REPO_ROOT / rel).is_file(), f"白名单指向不存在的文件：{rel}"
        assert len(why) >= 20, f"{rel} 的理由太短，说不清它为什么不是「频次当证据」"


# ============================================================ 动态层


@pytest.fixture
def store(tmp_path):
    s = TypedMemoryStore(tmp_path / "evidence.db")
    yield s
    s.close()


def test_confidence_is_pure_function_of_source_rank(store):
    """confidence 必须**只**由 source_rank 决定（与写入顺序/时间/其它字段无关）。"""
    expected = {SOURCE_USER: 0.9, SOURCE_AGENT: 0.7,
                SOURCE_IMPORTED: 0.4, SOURCE_UNVERIFIED: 0.2}
    ids = {}
    for rank in expected:
        ids[rank] = store.add(f"内容-{rank}", "note", source_rank=rank)
    for rank, want in expected.items():
        got = store.get(ids[rank])
        assert got is not None
        assert got["provenance"]["confidence"] == pytest.approx(want), (
            f"rank={rank} 的 confidence 应为 {want}，实得 {got['provenance']['confidence']}")


def test_confidence_mapping_is_frozen(store):
    """档位表是**契约**：改了就是改了规则，必须显式过这里。

    （本用例的价值不在"断言四个数"，而在"改档位会被拦住并被要求解释"。）
    """
    from mcpserver.memory_maas.entities import TypedMemoryStore as _T
    mapping = _T._RANK_CONFIDENCE
    assert mapping == {0: 0.9, 1: 0.7, 2: 0.4, 3: 0.2}, (
        "来源分级→置信的档位表变了 —— 这是供应链铁律的一部分，变更需在 PR 里说明理由")
    assert list(mapping) == sorted(mapping), "档位表应按 rank 递增排列（0 最高可信）"


def test_provenance_carries_origin_rank_for_auditability(store):
    """provenance 必须同时给 `confidence` 与 `origin_rank` —— 否则置信度无法对账。"""
    eid = store.add("可对账性检查", "note", source_rank=SOURCE_AGENT)
    prov = store.get(eid)["provenance"]
    assert set(prov) >= {"source", "ts", "confidence", "origin_rank"}
    assert prov["origin_rank"] == SOURCE_AGENT
    # 可复算：同一 rank 的不同条目，置信度必须逐位相同
    other = store.add("另一条同 rank 条目", "note", source_rank=SOURCE_AGENT)
    assert store.get(other)["provenance"]["confidence"] == prov["confidence"]


def test_entity_schema_has_no_frequency_field():
    """实体表**没有**频次字段 —— 结构性保证「类型系统里不存在把频次当证据的位置」。

    若将来有人给 `memory_entities` 加了 `hit_count`/`access_count` 列，这里会红：
    那时必须回答「它会不会被接进 confidence」。
    """
    import sqlite3

    from mcpserver.memory_maas import entities as ent_mod

    src = Path(ent_mod.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    cols: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if "CREATE TABLE" in node.value and "memory_entities" in node.value:
                for m in re.finditer(r"[a-z_]+", node.value):
                    cols.add(m.group(0))
    assert cols, "没能从源码里解析出 memory_entities 的建表语句"
    for banned in ("access_count", "hit_count", "view_count", "retrieval_count"):
        assert banned not in cols, (
            f"memory_entities 出现了频次字段 {banned!r} —— 请先回答它是否会被接进 confidence")
    assert sqlite3 is not None or True          # 保持 sqlite3 导入有用途（表结构自检）
