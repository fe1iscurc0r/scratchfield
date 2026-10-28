"""RAG 灵感素材库索引测试（工单 237 任务二）。

覆盖：index_inspiration_pool 写入与计数、幂等重建、filter_theme 过滤、
search_by_keyword 的 tag_filter、真实 sdr 语料索引（≥1010 chunk）。
用 mock 嵌入引擎 + 临时 DB 隔离，不依赖外部模型/服务。
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from rag.rag_service import RAGService

REPO_ROOT = Path(__file__).resolve().parents[1]
SDR_DIR = (REPO_ROOT / "mcpserver/material_science/synth_rag/corpus"
           / "inspiration_pool_2026-10-11/sdr_rag_test_corpus")


def _make_mock_embedding_engine(dim: int = 384):
    """固定归一化向量的 mock 引擎（同 test_rag_pipeline），聚焦流水线而非语义。"""
    engine = MagicMock()
    engine.is_available.return_value = False
    engine.get_device.return_value = "cpu"
    fixed = np.random.RandomState(42).randn(dim).astype(np.float32)
    fixed = fixed / np.linalg.norm(fixed)

    def _encode(texts, batch_size: int = 32):
        if not texts:
            return None
        return np.tile(fixed, (len(texts), 1))

    engine.encode.side_effect = _encode
    return engine


@pytest.fixture
def rag_service(tmp_path):
    RAGService._instance = None
    db_path = str(tmp_path / "test_rag_insp.db")
    mock_engine = _make_mock_embedding_engine()
    with patch("rag.rag_service.get_embedding_engine", return_value=mock_engine):
        service = RAGService(db_path=db_path)
    yield service
    service.close()
    RAGService._instance = None


def _item(pid: str, target: str, abstract: str = "", composite: float = 80.0) -> dict:
    return {"pid": pid, "composite": composite, "match": "kw",
            "target": target, "abstract": abstract,
            "arxiv_url": f"https://arxiv.org/abs/{pid}"}


def _write_pool(dir_path: Path, theme: str, items: list[dict]) -> Path:
    dir_path.mkdir(parents=True, exist_ok=True)
    payload = {"meta": {"source": "test", "theme": theme, "count": len(items)}, "items": items}
    (dir_path / "index.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return dir_path


# ---------- 索引 ----------

def test_index_returns_chunk_count(rag_service, tmp_path):
    d = _write_pool(tmp_path / "biomass", "biomass",
                    [_item("a1", "木质素"), _item("a2", "纤维素")])
    assert rag_service.index_inspiration_pool(d) == 2
    stats = rag_service.get_stats()["collections"]["materialscience"]
    assert stats["chunk_count"] == 2
    assert stats["doc_count"] == 1
    assert stats["embedding_count"] == 2


def test_index_accepts_index_json_path(rag_service, tmp_path):
    d = _write_pool(tmp_path / "sdr", "sdr", [_item("s1", "频谱")])
    assert rag_service.index_inspiration_pool(d / "index.json") == 1


def test_index_is_idempotent(rag_service, tmp_path):
    d = _write_pool(tmp_path / "sdr", "sdr", [_item("s1", "频谱")])
    rag_service.index_inspiration_pool(d)
    rag_service.index_inspiration_pool(d)
    stats = rag_service.get_stats()["collections"]["materialscience"]
    assert stats["chunk_count"] == 1   # 重复索引不累积
    assert stats["doc_count"] == 1


def test_index_theme_override(rag_service, tmp_path):
    d = _write_pool(tmp_path / "sdr", "sdr", [_item("s1", "频谱")])
    assert rag_service.index_inspiration_pool(d, theme="custom") == 1
    assert rag_service.list_documents()["docs"][0]["docId"] == "inspiration_custom"


def test_index_missing_file_raises(rag_service, tmp_path):
    with pytest.raises(FileNotFoundError):
        rag_service.index_inspiration_pool(tmp_path / "nope")


def test_index_empty_pool_returns_zero(rag_service, tmp_path):
    d = _write_pool(tmp_path / "other", "other", [])
    assert rag_service.index_inspiration_pool(d) == 0


# ---------- filter_theme ----------

def test_query_filter_theme_scopes_results(rag_service, tmp_path):
    da = _write_pool(tmp_path / "biomass", "biomass", [_item("a1", "木质素 碳化")])
    db = _write_pool(tmp_path / "sdr", "sdr", [_item("s1", "木质素 频谱")])
    rag_service.index_inspiration_pool(da)
    rag_service.index_inspiration_pool(db)

    res = rag_service.query("木质素", top_k=10, min_score=0.0, filter_theme="biomass")
    assert res["results"], "应命中 biomass"
    assert all(r["doc_id"] == "inspiration_biomass" for r in res["results"])


def test_query_without_filter_returns_all_themes(rag_service, tmp_path):
    da = _write_pool(tmp_path / "biomass", "biomass", [_item("a1", "木质素")])
    db = _write_pool(tmp_path / "sdr", "sdr", [_item("s1", "木质素")])
    rag_service.index_inspiration_pool(da)
    rag_service.index_inspiration_pool(db)
    res = rag_service.query("木质素", top_k=10, min_score=0.0)
    assert {r["doc_id"] for r in res["results"]} == {"inspiration_biomass", "inspiration_sdr"}


def test_query_filter_theme_no_match_returns_empty(rag_service, tmp_path):
    da = _write_pool(tmp_path / "biomass", "biomass", [_item("a1", "木质素")])
    rag_service.index_inspiration_pool(da)
    res = rag_service.query("木质素", top_k=10, min_score=0.0, filter_theme="sdr")
    assert res["results"] == []


# ---------- search_by_keyword tag_filter ----------

def test_keyword_search_tag_filter(rag_service, tmp_path):
    da = _write_pool(tmp_path / "biomass", "biomass", [_item("a1", "木质素 碳化")])
    db = _write_pool(tmp_path / "sdr", "sdr", [_item("s1", "木质素 频谱")])
    rag_service.index_inspiration_pool(da)
    rag_service.index_inspiration_pool(db)
    vecdb = rag_service._vec_db

    hits = vecdb.search_by_keyword("arxiv", top_k=10, tag_filter=["sdr"])
    assert hits, "应命中 sdr 文档"
    assert all(h["doc_id"] == "inspiration_sdr" for h in hits)

    hits_all = vecdb.search_by_keyword("arxiv", top_k=10)
    assert {h["doc_id"] for h in hits_all} == {"inspiration_biomass", "inspiration_sdr"}


# ---------- 真实语料 ----------

@pytest.mark.skipif(not SDR_DIR.is_dir(), reason="灵感素材语料未随仓分发")
def test_index_real_sdr_corpus_chunk_count(rag_service):
    n = rag_service.index_inspiration_pool(SDR_DIR)
    assert n >= 1010, f"sdr 语料应 ≥1010 条，实际 {n}"
    stats = rag_service.get_stats()["collections"]["materialscience"]
    assert stats["chunk_count"] >= 1010
