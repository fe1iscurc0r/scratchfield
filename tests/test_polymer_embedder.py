"""工单227 任务三 · 聚合物双通道 embedding 测试（rdkit 缺失环境 skip 而非 error）。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

rdkit = pytest.importorskip("rdit".replace("rdit", "rdkit"), reason="rdkit 未安装")

from tools.polymer_embedder import EMBED_DIM, cosine, embed, search, topology_feats  # noqa: E402


class TestEmbed:
    def test_dim_fixed(self):
        assert len(embed("C", 10, 0)) == EMBED_DIM

    def test_same_input_same_vector(self):
        assert embed("CCO", 5, 1) == embed("CCO", 5, 1)

    def test_invalid_smiles_raises(self):
        with pytest.raises(ValueError):
            embed("not_a_smiles!!")

    def test_topology_changes_vector(self):
        """同单体不同拓扑 → 向量不同（通道B 生效）。"""
        assert embed("C", 10, 0) != embed("C", 50, 3)


class TestSimilarity:
    def test_self_is_one(self):
        v = embed("CC1=CC=CC=C1", 100, 0)
        assert cosine(v, v) == pytest.approx(1.0)

    def test_same_family_higher_than_cross(self):
        """同族（同单体近同聚合度）> 异族（不同单体）——检索序合理。"""
        ps1 = embed("CC1=CC=CC=C1", 100, 0)
        ps2 = embed("CC1=CC=CC=C1", 110, 0)
        pe = embed("C", 100, 0)
        assert cosine(ps1, ps2) > cosine(ps1, pe)

    def test_search_top1_self(self):
        lib = {"PS": embed("CC1=CC=CC=C1", 100, 0),
               "PE": embed("C", 100, 0),
               "PEG": embed("CCO", 80, 0)}
        hits = search(lib["PS"], lib)
        assert hits[0][0] == "PS"
        assert all(hits[0][1] > s for _, s in hits[1:])


class TestTopology:
    def test_bounds(self):
        f = topology_feats(500, 20, False)  # 超界输入截断到 [0,1]
        assert all(0.0 <= x <= 1.0 for x in f)
