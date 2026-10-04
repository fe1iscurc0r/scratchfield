"""synthetic_evalset 合成评估集验收硬线（84号 A1）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mcpserver.orchestration.synthetic_evalset import generate_evalset  # noqa: E402

_SPEC = {
    "name": "summarize",
    "triggers": ["用户要求总结长文本", "用户粘贴一篇文章"],
    "steps": ["读取全文", "提取要点", "生成摘要"],
}


def test_evalset_generated():
    """给定 skill → 生成 ≥3 条用例且结构合法。"""
    cases = generate_evalset(_SPEC, n=4)
    assert len(cases) >= 3
    for c in cases:
        assert set(c) == {"case_id", "scenario", "expected"}
        exp = c["expected"]
        assert exp["type"] == "structured"
        assert exp["skill"] == "summarize"
        assert isinstance(exp["must_contain"], list) and exp["must_contain"]
        assert exp["steps_count"] == 3
        assert c["scenario"]


def test_evalset_reproducible():
    """同输入同 seed → 同输出（可复现）。"""
    a = generate_evalset(_SPEC, n=5, seed=7)
    b = generate_evalset(_SPEC, n=5, seed=7)
    assert a == b
    c = generate_evalset(_SPEC, n=5, seed=8)
    assert a != c
