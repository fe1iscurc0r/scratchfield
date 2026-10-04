"""卷189-A2 验收测试：能力索引（(动词, 宾语域) 二元组）+ 跨源冲突消歧。

覆盖（工单验收「≥6 用例覆盖动词/域/别名/优先级」）：
1. 解析：三种 capability_pairs 写法（列表对/对象/冒号串）+ 坏条目跳过
2. 构建：从 manifest 批量建索引命中 ("search","papers") → paper_miner
3. 动词查询：by_verb / lookup(verb) 返回该动词的域分布
4. 域查询：by_domain 返回动词分布
5. 消歧：同能力多来源按 source_priority 选默认，其余为 alias
6. 优先级：内置(manifest) > adapter > mcporter（与登记覆盖优先级语义不同）
7. 存量覆盖：全部可标注 manifest 均有 capability_pairs（--check 等价）
8. 幂等：重复 add 同 (name,verb,domain) 不重复计入
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]  # tests/ -> tool_registry/ -> mcpserver/ -> 仓库根
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mcpserver.tool_registry.capability_index import (  # noqa: E402
    CapabilityIndex,
    build_index,
    parse_capability_pairs,
)

# ---- 1. 解析三种写法 + 坏条目跳过 ----

def test_parse_three_forms_and_skip_bad():
    m = {"capability_pairs": [
        ["search", "papers"],
        {"verb": "Compute", "domain": " RF_Signal "},
        "decode:rf_signal",
        ["only_one"],            # 坏：长度不足
        {"verb": "x"},           # 坏：缺 domain
        ["", "empty"],           # 坏：动词空
    ]}
    assert parse_capability_pairs(m) == [
        ("search", "papers"),
        ("compute", "rf_signal"),   # 归一化：小写 + 去空白
        ("decode", "rf_signal"),
    ]
    assert parse_capability_pairs({}) == []
    assert parse_capability_pairs(None) == []


# ---- 2. 从 manifest 建索引并命中 ----

@pytest.fixture(scope="module")
def manifests() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for p in sorted(PROJECT_ROOT.glob("mcpserver/**/agent-manifest.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        out[d.get("name") or p.parent.name] = d
    return out


@pytest.fixture(scope="module")
def index(manifests) -> CapabilityIndex:
    return build_index(manifests)


def test_build_and_hit_search_papers(index):
    """工单验收：给定 ("search","papers") 能命中 paper_miner 等工具。"""
    r = index.resolve("search", "papers")
    assert r.default is not None
    names = [r.default.name] + [a.name for a in r.aliases]
    assert "paper_miner" in names
    assert r.default.source == "manifest"


# ---- 3. 动词查询 ----

def test_by_verb_and_lookup(index):
    domains = index.by_verb("search")
    assert "papers" in domains
    entries = index.lookup("search")          # 不给域 → 该动词下全部条目
    assert entries, "search 动词下应有条目"
    assert all(e.verb == "search" for e in entries)
    # 按优先级降序（同优先级按域/名稳定排序）
    prios = [e.priority for e in entries]
    assert prios == sorted(prios, reverse=True)


# ---- 4. 域查询 ----

def test_by_domain(index):
    verbs = index.by_domain("memory")
    assert {"read", "write", "search"} <= set(verbs)
    assert index.by_domain("nonexistent_domain_xyz") == []


# ---- 5 & 6. 消歧 + 优先级 ----

def test_conflict_resolution_priority():
    idx = CapabilityIndex()
    idx.add("ext_tool", [("search", "papers")], source="mcporter")   # 外部，priority 1
    idx.add("adp_tool", [("search", "papers")], source="adapter")    # adapter，priority 2
    idx.add("builtin", [("search", "papers")], source="manifest")    # 内置，priority 3
    r = idx.resolve("search", "papers")
    assert r.default.name == "builtin"                 # 内置优先
    assert [a.name for a in r.aliases] == ["adp_tool", "ext_tool"]  # 其余按优先级
    assert all(a.priority < r.default.priority for a in r.aliases)


def test_same_priority_stable_order():
    """同 priority 时按 name 字典序（可复现，便于断言）。"""
    idx = CapabilityIndex()
    idx.add("zeta", [("search", "papers")], source="manifest")
    idx.add("alpha", [("search", "papers")], source="manifest")
    assert idx.resolve("search", "papers").default.name == "alpha"


def test_custom_source_priority():
    idx = CapabilityIndex(source_priority={"mcporter": 9})
    idx.add("ext", [("search", "papers")], source="mcporter")
    idx.add("builtin", [("search", "papers")], source="manifest")
    assert idx.resolve("search", "papers").default.name == "ext"


# ---- 7. 存量覆盖 ----

def test_all_manifests_annotated(manifests):
    """补标后：全部 manifest 均有非空 capability_pairs（无能力标注丢失）。"""
    missing = [n for n, m in manifests.items() if not parse_capability_pairs(m)]
    assert missing == [], f"缺能力标注: {missing}"
    assert len(manifests) >= 50


def test_index_covers_all_services(manifests, index):
    assert set(index.services()) == set(manifests.keys())


# ---- 8. 幂等 ----

def test_add_is_idempotent():
    idx = CapabilityIndex()
    assert idx.add("t", [("search", "papers")]) == 1
    assert idx.add("t", [("search", "papers")]) == 0   # 重复同 (name,verb,domain)
    assert len(idx.lookup("search", "papers")) == 1


# ---- describe 报告 ----

def test_describe_shape(index):
    d = index.describe()
    assert d["pair_count"] > 0
    assert d["service_count"] == len(index.services())
    assert "conflicts" in d
    for c in d["conflicts"]:
        assert c["default"] and isinstance(c["aliases"], list)
