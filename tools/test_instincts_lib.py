# -*- coding: utf-8 -*-
"""
W64-05 instincts 行为规则库 pytest（验收：≥5 用例，
断言「项目级规则覆盖全局级」+「trigger 匹配到对应规则」）。

运行：cd /home/ubuntu/scratchpad && python -m pytest tools/test_instincts_lib.py -v
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import tempfile

import numpy as np
import yaml
from instincts_lib import (
    Action,
    Evidence,
    InstinctRule,
    InstinctStore,
)

# ---------------------------------------------------------------------------
# 共享测试数据
# ---------------------------------------------------------------------------

GLOBAL_RULES = [
    {
        "id": "g-safety-001",
        "trigger": "database connection leak or unclosed resource",
        "confidence": 0.95,
        "domain": "safety",
        "source": "ECC-2026",
        "source_repo": "ecc-core",
        "action": {"name": "warn", "message": "确保数据库连接在使用完毕后关闭。"},
        "evidence": {"quote": "资源泄漏是常见安全漏洞来源。"},
        "tags": ["resource", "leak"],
    },
    {
        "id": "g-perf-001",
        "trigger": "slow query without index or cache",
        "confidence": 0.88,
        "domain": "performance",
        "source": "ECC-2026",
        "action": {"name": "suggest", "message": "考虑添加数据库索引或缓存层。"},
        "tags": ["database", "slow"],
    },
    {
        "id": "g-safety-002",
        "trigger": "hardcoded password or secret in source code",
        "confidence": 0.99,
        "domain": "safety",
        "source": "ECC-2026",
        "action": {"name": "block", "message": "禁止在代码中硬编码密码或密钥。"},
    },
]

PROJECT_A_RULES = [
    {
        # 项目 A 的 safety-001：同名规则，置信度更高，覆盖全局
        "id": "g-safety-001",
        "trigger": "database connection leak or unclosed resource",
        "confidence": 0.99,          # 提升置信度
        "domain": "safety",
        "source": "ECC-2026 (project-a override)",
        "source_repo": "project-a",
        "action": {"name": "block", "message": "[项目A] 数据库连接必须使用 context manager。"},
        "tags": ["override"],
    },
    {
        "id": "proj-a-001",
        "trigger": "async function without timeout guard",
        "confidence": 0.91,
        "domain": "safety",
        "source": "project-a",
        "source_repo": "project-a",
        "action": {"name": "warn", "message": "异步函数应设置超时保护。"},
    },
    {
        "id": "proj-a-002",
        "trigger": "large batch insert without chunking",
        "confidence": 0.85,
        "domain": "performance",
        "source": "project-a",
        "action": {"name": "suggest", "message": "大批量插入建议分批执行。"},
    },
]


# ---------------------------------------------------------------------------
# 用例 1：Rule 序列化往返
# ---------------------------------------------------------------------------

def test_rule_serialization_roundtrip():
    """InstinctRule → dict → InstinctRule 往返一致。"""
    rule = InstinctRule(
        id="test-001",
        trigger="null pointer access in Java",
        confidence=0.97,
        domain="safety",
        source="test",
        source_repo="test-repo",
        action=Action(name="warn", message="检测到空指针访问。"),
        evidence=Evidence(quote="空指针是运行时异常之首。", url="https://example.com"),
        tags=["java", "null"],
    )
    d = rule.to_dict()
    restored = InstinctRule.from_dict(d)
    assert restored.id == rule.id
    assert restored.confidence == rule.confidence
    assert restored.action.name == rule.action.name
    assert restored.evidence.quote == rule.evidence.quote
    assert restored.tags == rule.tags


# ---------------------------------------------------------------------------
# 用例 2：项目级规则覆盖全局级（同名 ID，置信度不同）
# ---------------------------------------------------------------------------

def test_project_overrides_global_same_id():
    """项目级规则覆盖全局同名规则（更高置信度 + 不同 action）。"""
    store = InstinctStore()
    for d in GLOBAL_RULES:
        store.add_global(InstinctRule.from_dict(d))
    for d in PROJECT_A_RULES:
        store.add_project("project-a", InstinctRule.from_dict(d))

    effective = store.get_effective("project-a")
    # 项目 A 的 g-safety-001 覆盖了全局同名规则
    assert "g-safety-001" in effective
    rule = effective["g-safety-001"]
    assert rule.confidence == 0.99, f"应为 0.99，实际: {rule.confidence}"
    assert rule.action.name == "block", f"action 应为 block，实际: {rule.action.name}"
    assert rule.source_repo == "project-a"


def test_global_rules_unchanged_without_project():
    """全局规则在无项目上下文时保持不变。"""
    store = InstinctStore()
    for d in GLOBAL_RULES:
        store.add_global(InstinctRule.from_dict(d))
    effective = store.get_effective(None)  # 全局
    assert effective["g-safety-001"].confidence == 0.95
    assert effective["g-safety-001"].action.name == "warn"


# ---------------------------------------------------------------------------
# 用例 3：trigger 匹配到对应规则
# ---------------------------------------------------------------------------

def test_trigger_match_basic():
    """场景描述能匹配到对应 trigger 的规则（中英混合场景）。"""
    store = InstinctStore()
    for d in GLOBAL_RULES:
        store.add_global(InstinctRule.from_dict(d))

    # 中英混合场景：包含 database / connection / leak / closed 关键词
    matches = store.match(
        "发现 database connection 没有正确关闭，可能导致 leak，建议加上 timeout"
    )
    assert len(matches) >= 1, f"应匹配到至少 1 条规则，实际: {len(matches)}"
    ids = [r.id for r, _ in matches]
    assert "g-safety-001" in ids, f"应匹配到 g-safety-001，实际: {ids}"


def test_trigger_match_no_false_positive():
    """无关场景不匹配。"""
    store = InstinctStore()
    for d in GLOBAL_RULES:
        store.add_global(InstinctRule.from_dict(d))
    matches = store.match("just a simple print statement")
    assert all(score < 0.5 for _, score in matches)


# ---------------------------------------------------------------------------
# 用例 4：trigger 评分返回 [0,1] 且 top-k 正确
# ---------------------------------------------------------------------------

def test_trigger_score_bounds():
    """score_trigger 返回值 ∈ [0, 1]。"""
    store = InstinctStore()
    rule = InstinctRule(
        id="t", trigger="critical error unhandled exception",
        confidence=0.9, domain="safety", source="test",
    )
    scores = [
        store.score_trigger(rule.trigger, "there is a critical error here"),
        store.score_trigger(rule.trigger, "this is unrelated text"),
        store.score_trigger("", "any scene text"),
    ]
    for s in scores:
        assert 0.0 <= s <= 1.0, f"分数 {s} 超出 [0,1] 范围"


def test_match_top_k_respects_limit():
    """match 返回不超过 top_k 条结果。"""
    store = InstinctStore()
    for d in GLOBAL_RULES + PROJECT_A_RULES:
        store.add_project("project-a", InstinctRule.from_dict(d))
    matches = store.match("数据库连接资源问题", project_id="project-a", top_k=2)
    assert len(matches) <= 2


# ---------------------------------------------------------------------------
# 用例 5：status 按领域分组 + 置信度条
# ---------------------------------------------------------------------------

def test_status_by_domain():
    """status 返回按领域分组且包含置信度条。"""
    store = InstinctStore()
    for d in GLOBAL_RULES:
        store.add_global(InstinctRule.from_dict(d))
    for d in PROJECT_A_RULES:
        store.add_project("project-a", InstinctRule.from_dict(d))

    st = store.status("project-a")
    assert "safety" in st, f"应有 safety 领域，实际: {list(st.keys())}"
    assert "performance" in st
    safety = st["safety"]
    assert "count" in safety
    assert "confidence_bar" in safety
    assert isinstance(safety["confidence_bar"], str)
    assert safety["count"] >= 3, f"safety 领域规则数不足 3，实际: {safety['count']}"


# ---------------------------------------------------------------------------
# 用例 6：YAML import / export 往返
# ---------------------------------------------------------------------------

def test_yaml_export_and_import_roundtrip():
    """export_yaml 导出的内容可再次 import 回来，数量一致。"""
    store = InstinctStore()
    for d in GLOBAL_RULES:
        store.add_global(InstinctRule.from_dict(d))

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        tmp = f.name

    try:
        store.export_yaml(path=tmp)
        store2 = InstinctStore()
        n = store2.import_yaml(tmp)
        assert n == len(GLOBAL_RULES), f"应导入 {len(GLOBAL_RULES)} 条，实际: {n}"
        assert store2.get("g-safety-002").confidence == 0.99
    finally:
        os.unlink(tmp)


# ---------------------------------------------------------------------------
# 用例 7：置信度过滤
# ---------------------------------------------------------------------------

def test_export_confidence_threshold():
    """export_yaml 支持 confidence_threshold 过滤。"""
    store = InstinctStore()
    for d in GLOBAL_RULES:
        store.add_global(InstinctRule.from_dict(d))

    text_hi = store.export_yaml(confidence_threshold=0.95)
    text_lo = store.export_yaml(confidence_threshold=0.0)
    data_hi = yaml.safe_load(text_hi)
    data_lo = yaml.safe_load(text_lo)
    # 高阈值导出的规则数应 ≤ 低阈值
    assert len(data_hi["rules"]) <= len(data_lo["rules"])
    # 导出的每条规则置信度均 >= 阈值
    for r in data_hi["rules"]:
        assert r["confidence"] >= 0.95
