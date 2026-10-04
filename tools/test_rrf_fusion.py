"""rrf_fusion 单测（SPEC-05 S1 验收）。独立目录运行，避免 apiserver 包循环导入。"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apiserver", "routes"))
from rrf_fusion import fuse_ranked, rrf_score  # noqa: E402


def test_rrf_score_basic():
    assert abs(rrf_score(0) - 1.0 / 60) < 1e-9
    assert abs(rrf_score(1) - 1.0 / 61) < 1e-9
    assert rrf_score(0) > rrf_score(5)


def test_single_ranked_list_order():
    items = [
        {"text": "B", "rank": 1, "source": "vector"},
        {"text": "A", "rank": 0, "source": "vector"},
        {"text": "C", "rank": 2, "source": "vector"},
    ]
    out = fuse_ranked(items, source_labels={"vector": "研究笔记"})
    assert out.index("A") < out.index("B") < out.index("C")


def test_dual_path_dedup_score_accumulate():
    grag = [{"text": "共同事实", "rank": 0, "source": "grag"}]
    vec = [{"text": "共同事实", "rank": 3, "source": "vector"}]
    out = fuse_ranked([grag, vec])
    assert out.count("共同事实") == 1
    mixed = fuse_ranked([grag, vec, [{"text": "其他", "rank": 0, "source": "vector"}]])
    assert mixed.index("共同事实") < mixed.index("其他")


def test_dual_path_independent_items_both_present():
    grag = [{"text": "图谱A", "rank": 0, "source": "grag"}]
    vec = [{"text": "向量B", "rank": 1, "source": "vector"}]
    out = fuse_ranked([grag, vec])
    assert "图谱A" in out and "向量B" in out
    assert "知识图谱" in out and "研究笔记" in out


def test_empty_inputs():
    assert fuse_ranked([]) == ""
    assert fuse_ranked([[], []]) == ""
    assert fuse_ranked([{"text": "  ", "rank": 0}]) == ""


def test_max_chars_truncation():
    items = [{"text": f"条目{i}", "rank": i, "source": "vector"} for i in range(50)]
    out = fuse_ranked(items, max_chars=100)
    assert out.endswith("...[截断]")
    assert len(out) <= 150


def test_multi_path_same_rank_tie_kept():
    a = [{"text": "X", "rank": 0, "source": "grag"}]
    b = [{"text": "Y", "rank": 0, "source": "vector"}]
    out = fuse_ranked([a, b])
    assert "X" in out and "Y" in out
